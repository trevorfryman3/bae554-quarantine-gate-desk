"""Scripted reproduction of the Hermes gate-desk agent: same SKILL.md text, same six tools.

run_agent(prompt, world, ...) talks ONLY to a local Ollama server, executes tool calls
through the allowlisted dispatcher, validates the final JSON with code, gives the model
at most `max_repairs` corrections, then falls back to a safe blocked ESCALATE.
"""
import hashlib
import json
import time
from pathlib import Path

from tools.gate_tools import TOOL_SPECS, dispatch
from tools.policy_engine import evaluate
from tools.validator import ids_in, parse_answer, validate

ROOT = Path(__file__).resolve().parent.parent
LOCAL_HOST = "http://127.0.0.1:11434"


def skill_text():
    body = (ROOT / "skill" / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[2]
    fmt = (ROOT / "skill" / "references" / "output_format.md").read_text(encoding="utf-8")
    return body.strip() + "\n\n" + fmt.strip()


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def local_client(timeout):
    import ollama  # imported here so tests of the tools need no model runtime
    return ollama.Client(host=LOCAL_HOST, timeout=timeout)


def model_info(client, model):
    """Refuse cloud models; return actual size/quantization reported by the local server."""
    if "cloud" in model.lower():
        raise RuntimeError(f"refusing cloud model {model}: evaluation must stay local")
    s = client.show(model)
    d = s.details
    if getattr(s, "remote_host", None) or getattr(s, "remote_model", None):
        raise RuntimeError(f"{model} is served remotely; refusing")
    return {"model": model, "parameter_size": d.parameter_size, "quantization": d.quantization_level, "family": d.family}


def _plain(msg):
    """Ollama Message -> plain dict for the next request and for the trace."""
    out = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        out["tool_calls"] = [{"function": {"name": c.function.name, "arguments": dict(c.function.arguments or {})}}
                             for c in msg.tool_calls]
    return out


def fallback(world, request_id, reason):
    """Code-built safe result after verification keeps failing: travel stays blocked."""
    e = evaluate(world, request_id) if request_id else None
    keep_deny = e and e["recommendation"] == "DENY"
    return {
        "request_id": request_id or "UNKNOWN",
        "entity_type": e["entity_type"] if e else None,
        "recommendation": "DENY" if keep_deny else "ESCALATE",
        "travel_blocked": True,
        "members": [{"person_id": m["person_id"], "status": m["status"],
                     "holds": [h["alert_id"] for h in m["holds"] if h["release_status"] != "RELEASED"],
                     "next_step": m["next_step"]} for m in (e["members"] if e else [])],
        "applicable_rule_ids": e["applicable_rule_ids"] if e else ["DEC-001"],
        "evidence": e["evidence_ids"] if e else [],
        "missing_or_conflicting": [f"agent answer failed verification: {reason}"] + (e["missing_or_conflicting"] if e else []),
        "next_action": f"Keep travel blocked; refer to {world.reviewer['name']}.",
        "human_approval_required": True,
        "source": "harness_fallback",
    }


def run_agent(prompt, world, model="qwen3.5:4b", temperature=0.7, seed=None, num_ctx=8192,
              max_tool_rounds=6, max_repairs=2, num_predict=1500, timeout=600, client=None):
    client = client or local_client(timeout)
    system = skill_text()
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    opts = {"temperature": temperature, "num_ctx": num_ctx, "num_predict": num_predict}
    if seed is not None:
        opts["seed"] = seed
    rec = {"harness": "script-reproduction (tools/agent.py)", "skill_sha": sha(system), "options": dict(opts, think=False),
           "rounds": [], "validations": [], "repairs": 0, "fallback": False, "error": None}
    seen, last_req, tool_rounds, t0 = set(), None, 0, time.time()
    try:
        while True:
            t1 = time.time()
            r = client.chat(model=model, messages=msgs, tools=TOOL_SPECS, options=opts, think=False)
            m = _plain(r.message)
            msgs.append(m)
            rec["rounds"].append({"seconds": round(time.time() - t1, 2), "prompt_tokens": r.prompt_eval_count,
                                  "completion_tokens": r.eval_count, "done_reason": r.done_reason})
            if r.prompt_eval_count and r.prompt_eval_count >= num_ctx - 64:
                rec["truncation_suspected"] = True
            if m.get("tool_calls"):
                tool_rounds += 1
                for c in m["tool_calls"]:
                    name, args = c["function"]["name"], c["function"]["arguments"]
                    out = dispatch(world, name, args)
                    seen |= ids_in(out)
                    if name in ("get_request", "check_policy") and '"error"' not in out[:20]:
                        last_req = json.loads(out).get("request_id", last_req)
                    msgs.append({"role": "tool", "tool_name": name, "content": out})
                if tool_rounds > max_tool_rounds:
                    raise RuntimeError(f"tool loop exceeded {max_tool_rounds} rounds")
                continue
            if r.done_reason == "length":
                rec["truncated_output"] = True
            ans = parse_answer(m["content"])
            rid = (ans or {}).get("request_id") or last_req
            engine = evaluate(world, rid) if rid else {"entity_type": None, "request_id": None}
            ok, errs, parsed = validate(m["content"], engine, seen)
            rec["validations"].append({"ok": ok, "errors": errs})
            if ok:
                rec["final_output"] = dict(parsed, source="model_validated")
                break
            if rec["repairs"] >= max_repairs:
                rec["fallback"] = True
                rec["final_output"] = fallback(world, last_req, "; ".join(errs[:3]))
                break
            rec["repairs"] += 1
            msgs.append({"role": "user", "content": "VERIFICATION FAILED. Fix these problems and reply with only the corrected JSON object:\n- "
                         + "\n- ".join(errs)})
    except Exception as e:  # crash/timeout/loop exhaustion: safe blocked result, recorded as failure
        rec["error"] = f"{type(e).__name__}: {e}"
        rec["fallback"] = True
        rec["final_output"] = fallback(world, last_req, rec["error"])
    rec["latency_s"] = round(time.time() - t0, 2)
    rec["usage"] = {"prompt_tokens": sum(x["prompt_tokens"] or 0 for x in rec["rounds"]),
                    "completion_tokens": sum(x["completion_tokens"] or 0 for x in rec["rounds"])}
    rec["messages"] = msgs
    return rec
