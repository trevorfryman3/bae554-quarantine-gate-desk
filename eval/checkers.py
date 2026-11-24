"""Three programmatic checkers (plain code, never a model), Lecture-28 style.

Each takes (run, case) and returns True (pass), False (fail) or None (not applicable).
A run is one JSONL record written by eval/run_eval.py; a case is one entry of eval/cases.json.
Crashes, loop exhaustion, harness fallbacks and unparseable output are failures.
"""
import json

from tools.validator import ids_in, schema_errors


def tool_calls(run):
    return [(c["function"]["name"], c["function"]["arguments"])
            for m in run["messages"] if m["role"] == "assistant" for c in m.get("tool_calls", [])]


def seen_ids(run):
    out = set()
    for m in run["messages"]:
        if m["role"] == "tool":
            out |= ids_in(m["content"])
    return out


def _arg_ids(args, key):
    v = args.get(key)
    v = [v] if isinstance(v, str) else (v or [])
    return {str(x).strip().upper() for x in v}


def _usable(run):
    out = run.get("final_output") or {}
    return (not run.get("error") and not run.get("fallback") and out.get("source") == "model_validated"
            and not schema_errors(out))


def check_evidence_and_entities(run, case):
    """Right tools with the right IDs, and members resolved exactly by ID (no extra, none dropped)."""
    if not _usable(run):
        return False
    calls = tool_calls(run)
    rid = case["request_id"]
    asked = lambda name, key: set().union(*[_arg_ids(a, key) for n, a in calls if n == name] or [set()])
    out = run["final_output"]
    return all([
        rid in asked("get_request", "request_id"),
        rid in asked("check_policy", "request_id"),
        set(case["persons"]) <= asked("get_person_records", "person_ids"),
        set(case["zones"]) <= asked("get_zone_rules", "zone_ids"),
        out["request_id"] == rid,
        {m["person_id"] for m in out["members"]} == set(case["persons"]),
    ])


def check_grounding(run, case):
    """Every cited ID came from a tool in THIS run; the decisive current records are cited; no stale/forbidden IDs."""
    if not _usable(run):
        return False
    out, seen, e = run["final_output"], seen_ids(run), case["expect"]
    cited = set(out["evidence"])
    mentioned = cited | {m["person_id"] for m in out["members"]} | ids_in(" ".join(out["missing_or_conflicting"]))
    hold_ids = {h for m in out["members"] for h in m.get("holds", [])}
    return all([
        bool(cited) and cited <= seen,
        hold_ids <= seen,
        ids_in(" ".join(out["missing_or_conflicting"])) <= seen,
        all(set(group) & cited for group in e["evidence_any"]),
        not (set(e["forbidden_evidence"]) & mentioned),
    ])


def check_policy_outcome(run, case):
    """Recommendation, travel block, per-member statuses/holds and group aggregation match the fictional policy."""
    if not _usable(run):
        return False
    out, e = run["final_output"], case["expect"]
    rec = out["recommendation"]
    if rec not in e["recommendation"]:
        return False
    alt = e.get("alt_needs_citation", {}).get(rec)
    if alt and not (ids_in(" ".join(out["missing_or_conflicting"])) & set(alt)):
        return False
    if out["travel_blocked"] != (rec != "APPROVE") or out["human_approval_required"] is not True:
        return False
    got = {m["person_id"]: m for m in out["members"]}
    for pid, ok_status in e["members"].items():
        m = got.get(pid)
        if m is None or m["status"] not in ok_status:
            return False
        if not set(e["holds"].get(pid, [])) <= set(m.get("holds", [])):
            return False
        if ok_status == ["CLEAR"] and m.get("holds"):
            return False
    rules = set(out["applicable_rule_ids"])
    return set(e["rules"]) <= rules and not (set(e["forbidden_rules"]) & rules)


CHECKS = {"evidence_entities": check_evidence_and_entities,
          "grounding": check_grounding,
          "policy_outcome": check_policy_outcome}


def score(run, case):
    return {name: fn(run, case) for name, fn in CHECKS.items()}


def load_cases(path="eval/cases.json"):
    return {c["id"]: c for c in json.load(open(path, encoding="utf-8"))["cases"]}
