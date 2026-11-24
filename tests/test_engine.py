import pytest

from tools.policy_engine import evaluate
from tools.world import World

EXPECT = {
    "REQ-101": "APPROVE", "REQ-102": "DENY", "REQ-103": "ESCALATE", "REQ-104": "ESCALATE",
    "REQ-105": "DENY", "REQ-106": "ESCALATE", "REQ-107": "HOLD", "REQ-108": "HOLD",
    "REQ-109": "HOLD", "REQ-110": "APPROVE", "REQ-111": "HOLD", "REQ-112": "HOLD",
    "REQ-113": "APPROVE", "REQ-114": "ESCALATE", "REQ-115": "APPROVE",
}


@pytest.fixture
def world():
    return World()


def rules(r):
    return {b["rule_id"] for b in r["blockers"]}


def status(r):
    return {m["person_id"]: m["status"] for m in r["members"]}


@pytest.mark.parametrize("rid,rec", sorted(EXPECT.items()))
def test_recommendation_and_flags(world, rid, rec):
    r = evaluate(world, rid)
    assert r["recommendation"] == rec
    assert r["travel_blocked"] is (rec != "APPROVE")
    assert r["human_approval_required"] is True


def test_req102_gate001(world):
    assert "GATE-001" in rules(evaluate(world, "REQ-102"))


def test_req103_field001(world):
    r = evaluate(world, "REQ-103")
    assert "FIELD-001" in rules(r)
    assert "PL-031" in r["evidence_ids"]


def test_req104_vehicle_manifest(world):
    r = evaluate(world, "REQ-104")
    assert "VEH-001" in rules(r)
    assert "P-031" not in status(r)


def test_req105_both_gate_blockers(world):
    assert {"GATE-002", "GATE-003"} <= rules(evaluate(world, "REQ-105"))


def test_req106_route(world):
    r = evaluate(world, "REQ-106")
    assert "EVID-002" in rules(r)
    assert "GATE-002" not in rules(r)


def test_req108_statuses(world):
    assert status(evaluate(world, "REQ-108")) == {"P-011": "CLEAR", "P-012": "HOLD", "P-013": "CLEAR"}


def test_req109_statuses(world):
    assert status(evaluate(world, "REQ-109")) == {"P-014": "CLEAR", "P-015": "HOLD", "P-016": "HOLD"}


def test_req111_water004(world):
    assert "WATER-004" in evaluate(world, "REQ-111")["applicable_rule_ids"]


def test_req112_reasons(world):
    r = evaluate(world, "REQ-112")
    assert status(r) == {"P-020": "HOLD", "P-021": "HOLD", "P-022": "HOLD"}
    reason = {m["person_id"]: " ".join(h["reason"] for h in m["holds"]) for m in r["members"]}
    assert "expired" in reason["P-020"]
    assert "re-exposure" in reason["P-021"]
    assert "mismatch" in reason["P-022"]


def test_req114_evid004(world):
    assert "EVID-004" in rules(evaluate(world, "REQ-114"))


def test_req115_empty_vehicle(world):
    r = evaluate(world, "REQ-115")
    assert list(status(r)) == ["P-025"]


def test_fault_clearances_req114():
    r = evaluate(World(unavailable={"clearances"}), "REQ-114")
    assert r["recommendation"] == "ESCALATE"
    assert "EVID-005" in rules(r)


def test_fault_clearances_never_approve():
    r = evaluate(World(unavailable={"clearances"}), "REQ-110")
    assert r["recommendation"] == "ESCALATE"
    assert r["travel_blocked"] is True


@pytest.mark.parametrize("snap,rec,sts", [
    ("t0_baseline", "APPROVE", None),
    ("t1_alert", "HOLD", {"P-030": "HOLD", "P-031": "HOLD"}),
    ("t2_partial", "HOLD", {"P-030": "CLEAR", "P-031": "HOLD"}),
    ("t3_complete", "APPROVE", None),
])
def test_snapshots_req120(snap, rec, sts):
    r = evaluate(World(snapshot=snap), "REQ-120")
    assert r["recommendation"] == rec
    if sts:
        assert status(r) == sts


def test_deny_preserves_holds(world):
    for b in world._d["registry"]["bulletins"]:
        if b["bulletin_id"] == "BUL-041-v3":
            b["zones"]["Z-D"]["travel"] = "CLOSED"
    r = evaluate(world, "REQ-107")
    assert r["recommendation"] == "DENY"
    m = r["members"][0]
    assert m["person_id"] == "P-010"
    assert any(h["alert_id"] == "WA-07" and h["release_status"] != "RELEASED" for h in m["holds"])
    assert "P-010" in r["next_action"]


def test_flagged_clearance_escalates(world):
    world._d["clearances"]["clearances"].append({
        "clearance_id": "CL-F11", "person_id": "P-011", "alert_id": "WA-07", "result": "FLAGGED",
        "sampled_at": "2026-11-20T09:00:00Z", "issued_at": "2026-11-20T10:00:00Z",
        "issued_by": "OFF-11", "signature_status": "VERIFIED"})
    r = evaluate(world, "REQ-108")
    assert r["recommendation"] == "ESCALATE"
    assert "WATER-005" in rules(r)
    assert status(r)["P-011"] == "REVIEW"


def test_unverified_clearance_holds(world):
    for c in world._d["clearances"]["clearances"]:
        if c["clearance_id"] == "CL-017":
            c["signature_status"] = "UNVERIFIED"
    assert evaluate(world, "REQ-110")["recommendation"] == "HOLD"
