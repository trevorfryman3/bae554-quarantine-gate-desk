"""Code checks the harness runs on the model's final answer BEFORE it is shown.

validate(answer_text, engine, seen_ids) -> (ok, errors, parsed)
  * schema: required fields, types, enums
  * policy agreement with the deterministic engine (DEC-001/DEC-002)
  * per-member statuses/holds, group aggregation
  * grounding: every cited ID was returned by a tool in this run
"""
import json
import re

REC = {"APPROVE", "DENY", "HOLD", "ESCALATE"}
ENTITY = {"INDIVIDUAL", "GROUP", "VEHICLE"}
STATUS = {"CLEAR", "HOLD", "REVIEW"}
ID_IN_TEXT = re.compile(r"\b[A-Z]{1,4}-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?\b")
REQUIRED = {"request_id": str, "entity_type": str, "recommendation": str, "travel_blocked": bool, "members": list,
            "applicable_rule_ids": list, "evidence": list, "missing_or_conflicting": list, "next_action": str,
            "human_approval_required": bool}


def ids_in(text):
    return set(ID_IN_TEXT.findall(text or ""))


def parse_answer(text):
    """Return the JSON object in the answer (bare, or inside a ``` fence), else None."""
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    cand = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    try:
        obj = json.loads(cand)
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def schema_errors(a):
    errs = [f"missing field '{k}'" for k in REQUIRED if k not in a]
    errs += [f"'{k}' must be {t.__name__}" for k, t in REQUIRED.items() if k in a and not isinstance(a[k], t)]
    if errs:
        return errs
    if a["recommendation"] not in REC:
        errs.append(f"recommendation must be one of {sorted(REC)}")
    if a["entity_type"] not in ENTITY:
        errs.append(f"entity_type must be one of {sorted(ENTITY)}")
    if a["human_approval_required"] is not True:
        errs.append("human_approval_required must be true (the operator always decides)")
    if not a["next_action"].strip():
        errs.append("next_action must not be empty")
    for i, m in enumerate(a["members"]):
        if not isinstance(m, dict) or not isinstance(m.get("person_id"), str) or m.get("status") not in STATUS \
                or not isinstance(m.get("holds", []), list) or not all(isinstance(h, str) for h in m.get("holds", [])):
            errs.append(f"members[{i}] needs person_id, status in {sorted(STATUS)}, holds (list of alert IDs)")
    for k in ("applicable_rule_ids", "evidence", "missing_or_conflicting"):
        if not all(isinstance(x, str) for x in a[k]):
            errs.append(f"'{k}' must be a list of strings")
    return errs


def validate(text, engine, seen_ids):
    a = parse_answer(text)
    if a is None:
        return False, ["final answer is not a single JSON object"], None
    errs = schema_errors(a)
    if errs:
        return False, errs, a
    if engine.get("entity_type") is None:
        return False, [f"request {a['request_id']} could not be verified; escalate"], a
    if a["request_id"] != engine["request_id"]:
        errs.append(f"request_id {a['request_id']} does not match {engine['request_id']}")
    if a["entity_type"] != engine["entity_type"]:
        errs.append(f"entity_type should be {engine['entity_type']}")

    rec, erec = a["recommendation"], engine["recommendation"]
    upgrade = (rec == "ESCALATE" and erec in ("APPROVE", "HOLD") and a["missing_or_conflicting"]
               and any(ids_in(x) & seen_ids for x in a["missing_or_conflicting"]))
    if rec != erec and not upgrade:
        errs.append(f"recommendation {rec} disagrees with the policy check ({erec}); see DEC-001"
                    + (" (ESCALATE instead needs a cited conflicting record in missing_or_conflicting, DEC-002)" if rec == "ESCALATE" else ""))
    if a["travel_blocked"] != (rec != "APPROVE"):
        errs.append("travel_blocked must be true for DENY/HOLD/ESCALATE and false only for APPROVE")

    want = {m["person_id"]: m for m in engine["members"]}
    got = {m["person_id"]: m for m in a["members"]}
    if set(got) != set(want):
        errs.append(f"members must be exactly {sorted(want)} (got {sorted(got)}); never add, drop or split members")
    for pid, em in want.items():
        gm = got.get(pid)
        if not gm:
            continue
        need = {h["alert_id"] for h in em["holds"] if h["release_status"] != "RELEASED"}
        if em["status"] == "CLEAR" and gm["status"] != "CLEAR":
            errs.append(f"{pid} has no unreleased hold; status should be CLEAR")
        if em["status"] in ("HOLD", "REVIEW") and gm["status"] == "CLEAR":
            errs.append(f"{pid} must not be CLEAR (policy status {em['status']})")
        if not need <= set(gm.get("holds", [])):
            errs.append(f"{pid} holds must include {sorted(need)}")

    must_rules = {b["rule_id"] for b in engine["blockers"]}
    if not must_rules <= set(a["applicable_rule_ids"]):
        errs.append(f"applicable_rule_ids must include {sorted(must_rules - set(a['applicable_rule_ids']))}")

    cited = set(a["evidence"])
    if not cited:
        errs.append("evidence must cite record IDs returned by the tools")
    unseen = sorted(cited - seen_ids)
    if unseen:
        errs.append(f"evidence IDs {unseen} were not returned by any tool in this run")
    for b in engine["blockers"]:
        if b["evidence_ids"] and not (set(b["evidence_ids"]) & cited):
            errs.append(f"cite at least one of {b['evidence_ids']} for {b['rule_id']}")
    return not errs, errs, a
