import json

import pytest

from tools import gate_tools
from tools.policy_engine import evaluate
from tools.validator import validate
from tools.world import World


@pytest.fixture
def world():
    return World()


def call(w, name, args):
    return json.loads(gate_tools.dispatch(w, name, args))


@pytest.mark.parametrize("name", ["issue_clearance", "open_gate", "write_file"])
def test_non_allowlisted(world, name):
    assert "error" in call(world, name, {})


def test_tool_names():
    assert set(gate_tools.TOOLS) == {"find_request", "get_request", "get_zone_rules",
                                     "get_person_records", "get_area_reports", "check_policy"}
    bad = ("write", "issue", "open", "edit", "delete", "create", "update", "set")
    assert not [n for n in gate_tools.TOOLS if any(b in n for b in bad)]


@pytest.mark.parametrize("rid", ["../etc", "P 001;rm"])
def test_malformed_single_id(world, rid):
    assert "error" in call(world, "get_request", {"request_id": rid})


def test_malformed_ids(world):
    assert "error" in call(world, "get_person_records", {"person_ids": ["../etc"]})
    assert "error" in call(world, "get_person_records", {"person_ids": ["P 001;rm"]})
    assert "error" in call(world, "get_person_records", {"person_ids": [f"P-{i:03d}" for i in range(13)]})


def test_untrusted_wrapping(world):
    r = call(world, "get_request", {"request_id": "REQ-111"})
    assert set(r["operator_note"]) == {"untrusted_text"}
    a = call(world, "get_area_reports", {"zone_ids": ["Z-A"]})
    assert a["patrol_logs"]
    assert all("untrusted_text" in p["text"] for p in a["patrol_logs"])
    assert "PL-040" in {p["report_id"] for p in a["patrol_logs"]}


def test_closed_alert_retrievable(world):
    a = call(world, "get_area_reports", {"zone_ids": ["Z-E"]})
    assert any(x["alert_id"] == "WA-03" and x["status"] == "CLOSED" for x in a["water_alerts"])


def test_find_request(world):
    r = call(world, "find_request", {"entity_id": "VH-12"})
    assert "REQ-109" in {x["request_id"] for x in r["requests"]}
    assert "error" in call(world, "find_request", {"entity_id": "P-999"})


def test_unavailable_clearances():
    w = World(unavailable={"clearances"})
    p = call(w, "get_person_records", {"person_ids": ["P-024"]})["people"][0]
    assert set(p["clearances"]) == {"error"}
    assert p["presence"]


def _answer(w, **over):
    e = evaluate(w, "REQ-108")
    a = {"request_id": "REQ-108", "entity_type": e["entity_type"], "recommendation": e["recommendation"],
         "travel_blocked": e["travel_blocked"],
         "members": [{"person_id": m["person_id"], "status": m["status"],
                      "holds": [h["alert_id"] for h in m["holds"] if h["release_status"] != "RELEASED"],
                      "next_step": m["next_step"]} for m in e["members"]],
         "evidence": e["evidence_ids"], "applicable_rule_ids": e["applicable_rule_ids"],
         "missing_or_conflicting": [], "next_action": e["next_action"], "human_approval_required": True}
    a.update(over)
    return e, a


def test_validator(world):
    e, a = _answer(world)
    seen = set(e["evidence_ids"])
    assert validate(json.dumps(a), e, seen)[0]
    assert not validate(json.dumps({**a, "recommendation": "APPROVE", "travel_blocked": False}), e, seen)[0]
    drop = [m for m in a["members"] if m["person_id"] != "P-012"]
    assert not validate(json.dumps({**a, "members": drop}), e, seen)[0]
    assert not validate(json.dumps({**a, "evidence": a["evidence"] + ["CL-777"]}), e, seen)[0]
    assert not validate("not json at all", e, seen)[0]
