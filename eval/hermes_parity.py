"""Run selected cases through the REAL Hermes CLI (on the Dell) and check its answers with the same code.

  python eval/hermes_parity.py --out traces/dell_hermes_parity.jsonl --cases C07-water-area-individual,C08-group-one-uncleared,C13-irrelevant-water-plus-injection

Hermes does not document a temperature setting, so these runs use the model's default sampling
(Ollama Modelfile: temperature 1). The scored 42+ runs use eval/run_eval.py (script reproduction,
same SKILL.md + same tools, temperature 0.7); this script only checks that the real Hermes setup
produces the same kind of validated answer. Raw stdout events are saved unmodified.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval.checkers import check_policy_outcome, load_cases  # noqa: E402
from tools.policy_engine import evaluate  # noqa: E402
from tools.validator import ids_in, parse_answer, validate  # noqa: E402
from tools.world import World  # noqa: E402

DEFAULT_CMD = ["hermes", "chat", "--oneshot", "--format", "stream-json", "--toolsets", "mcp-gate_desk",
               "--skills", "quarantine-gate-desk", "--max-turns", "12", "-q"]


def strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from strings(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--machine", required=True)
    ap.add_argument("--cmd", default=json.dumps(DEFAULT_CMD), help="JSON list; prompt is appended")
    a = ap.parse_args()
    cases = load_cases(ROOT / "eval" / "cases.json")
    cmd = json.loads(a.cmd)
    for rep in range(1, a.reps + 1):
        for cid in a.cases.split(","):
            case = cases[cid]
            if case.get("faults"):
                print(f"skip {cid}: fault injection needs the scripted harness")
                continue
            t0 = time.time()
            p = subprocess.run(cmd + [case["prompt"]], capture_output=True, text=True, encoding="utf-8", timeout=1800)
            events = []
            for line in p.stdout.splitlines():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    events.append({"raw": line})
            answer_text = next((s for s in reversed(list(strings(events))) if (parse_answer(s) or {}).get("recommendation")), "")
            world = World()
            engine = evaluate(world, case["request_id"])
            ok, errs, parsed = validate(answer_text, engine, ids_in(p.stdout))
            run = {"final_output": dict(parsed or {}, source="model_validated") if ok else {}, "messages": []}
            rec = {"case_id": cid, "rep": rep, "harness": "hermes-cli", "cmd": cmd, "machine": a.machine,
                   "exit_code": p.returncode, "latency_s": round(time.time() - t0, 1), "stdout_events": events,
                   "stderr_tail": p.stderr[-2000:], "answer_text": answer_text, "validator_ok": ok, "validator_errors": errs,
                   "policy_outcome": check_policy_outcome(run, case) if ok else False,
                   "note": "grounding here uses IDs anywhere in Hermes stdout (weaker than the scripted harness)"}
            with open(a.out, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"{cid} r{rep}: exit={p.returncode} valid={ok} policy={rec['policy_outcome']} {rec['latency_s']}s {errs[:2]}")


if __name__ == "__main__":
    main()
