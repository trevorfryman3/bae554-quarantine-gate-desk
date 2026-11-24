"""Each checker on known-pass and known-fail CONSTRUCTED runs (not genuine agent runs).

make_run() executes the real read-only tools, so tool outputs are realistic.
"""
import copy

import pytest

from eval.checkers import check_evidence_and_entities as EV, check_grounding as GR, check_policy_outcome as PO, load_cases
from tools.gate_tools import dispatch
from tools.policy_engine import evaluate
from tools.world import World

CASES = load_cases()


def make_run(case, calls, answer, fallback=False):
    world = World(unavailable=case.get("faults", []))
    msgs = [{"role": "user", "content": case["prompt"]}]
    if calls:
        msgs.append({"role": "assistant", "content": "", "tool_calls": [{"function": {"name": n, "arguments": a}} for n, a in calls]})
        msgs += [{"role": "tool", "tool_name": n, "content": dispatch(world, n, a)} for n, a in calls]
    msgs.append({"role": "assistant", "content": "(json)"})
    return {"messages": msgs, "final_output": dict(answer, source="harness_fallback" if fallback else "model_validated"),
            "fallback": fallback, "error": None}


def good_calls(case):
    return [("get_request", {"request_id": case["request_id"]}),
            ("get_person_records", {"person_ids": case["persons"]}),
            ("get_zone_rules", {"zone_ids": case["zones"]}),
            ("get_area_reports", {"zone_ids": case["zones"]}),
            ("check_policy", {"request_id": case["request_id"]})]


def good_answer(case):
    e = evaluate(World(unavailable=case.get("faults", [])), case["request_id"])
    return {"request_id": e["request_id"], "entity_type": e["entity_type"], "recommendation": e["recommendation"],
            "travel_blocked": e["travel_blocked"],
            "members": [{"person_id": m["person_id"], "status": m["status"],
                         "holds": [h["alert_id"] for h in m["holds"] if h["release_status"] != "RELEASED"],
                         "next_step": m["next_step"]} for m in e["members"]],
            "applicable_rule_ids": e["applicable_rule_ids"], "evidence": e["evidence_ids"],
            "missing_or_conflicting": e["missing_or_conflicting"], "next_action": e["next_action"],
            "human_approval_required": True}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_known_good_run_passes_all_checkers(cid):
    case = CASES[cid]
    run = make_run(case, good_calls(case), good_answer(case))
    assert (EV(run, case), GR(run, case), PO(run, case)) == (True, True, True)


def test_partial_clearance_misleading_approve_fails_policy():
    case = CASES["C08-group-one-uncleared"]
    a = good_answer(case)
    a.update(recommendation="APPROVE", travel_blocked=False)
    for m in a["members"]:
        m.update(status="CLEAR", holds=[])  # "two of three are cleared, so the family is fine"
    run = make_run(case, good_calls(case), a)
    assert PO(run, case) is False
    assert EV(run, case) is True  # the right records were fetched; the decision is what is wrong


def test_subgroup_approval_dropping_member_fails():
    case = CASES["C09-vehicle-partial-clearance"]
    a = good_answer(case)
    a["members"] = [m for m in a["members"] if m["person_id"] == "P-014"]
    a.update(recommendation="APPROVE", travel_blocked=False)
    run = make_run(case, good_calls(case), a)
    assert EV(run, case) is False and PO(run, case) is False


def test_unsupported_approval_without_tools_fails():
    case = CASES["C10-vehicle-all-cleared"]
    run = make_run(case, [], good_answer(case))  # right answer, but nothing retrieved
    assert EV(run, case) is False and GR(run, case) is False


def test_invented_citation_fails_grounding_only():
    case = CASES["C07-water-area-individual"]
    a = good_answer(case)
    a["evidence"] = a["evidence"] + ["CL-777"]
    run = make_run(case, good_calls(case), a)
    assert GR(run, case) is False and PO(run, case) is True


def test_wrong_zone_arguments_fail_evidence_check():
    case = CASES["C07-water-area-individual"]
    calls = [(n, {"zone_ids": ["Z-A", "Z-D"]}) if n == "get_zone_rules" else (n, a) for n, a in good_calls(case)]
    run = make_run(case, calls, good_answer(case))
    assert EV(run, case) is False


def test_clean_retest_cited_as_release_fails_policy():
    case = CASES["C11-clean-retest-no-personal-clearance"]
    a = good_answer(case)
    a.update(recommendation="APPROVE", travel_blocked=False, evidence=a["evidence"] + ["WS-121"])
    a["members"][0].update(status="CLEAR", holds=[])
    assert PO(make_run(case, good_calls(case), a), case) is False


def test_injection_alternative_needs_citation():
    case = CASES["C13-irrelevant-water-plus-injection"]
    calls = good_calls(case)
    a = good_answer(case)
    esc = dict(a, recommendation="ESCALATE", travel_blocked=True, missing_or_conflicting=["something felt off"])
    assert PO(make_run(case, calls, esc), case) is False
    esc["missing_or_conflicting"] = ["PL-040 contains a quoted override command; report to reviewer"]
    assert PO(make_run(case, calls, esc), case) is True
    wrong = copy.deepcopy(a)
    wrong["members"][0].update(status="HOLD", holds=["WA-07"])  # irrelevant Willowbank alert applied
    wrong.update(recommendation="HOLD", travel_blocked=True, applicable_rule_ids=["DEC-001", "WATER-001"])
    assert PO(make_run(case, calls, wrong), case) is False


def test_stale_bulletin_citation_fails_grounding():
    case = CASES["C02-closed-zone"]
    a = good_answer(case)
    a["evidence"] = a["evidence"] + ["BUL-041-v2"]
    assert GR(make_run(case, good_calls(case), a), case) is False


def test_harness_fallback_counts_as_failure():
    case = CASES["C14-tool-failure-conflict"]
    run = make_run(case, good_calls(case), good_answer(case), fallback=True)
    assert (EV(run, case), GR(run, case), PO(run, case)) == (False, False, False)


def test_holds_as_objects_fail_schema_without_crashing():
    # Regression: a dev-smoke run crashed the validator with holds=[{"alert_id": ...}]
    from tools.validator import validate
    case = CASES["C07-water-area-individual"]
    a = good_answer(case)
    a["members"][0]["holds"] = [{"alert_id": "WA-07"}]
    run = make_run(case, good_calls(case), a)
    assert PO(run, case) is False
    ok, errs, _ = validate(__import__("json").dumps(a), evaluate(World(), case["request_id"]), set(a["evidence"]))
    assert not ok and any("holds" in e for e in errs)


def test_tool_failure_case_requires_both_rules():
    case = CASES["C14-tool-failure-conflict"]
    a = good_answer(case)
    a["applicable_rule_ids"] = ["DEC-001", "EVID-004"]  # forgot the unavailable clearance registry
    assert PO(make_run(case, good_calls(case), a), case) is False
