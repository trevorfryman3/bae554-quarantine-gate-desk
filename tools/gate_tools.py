"""The six READ-ONLY tools the gate-desk agent may call, plus the allowlisted dispatcher.

There is deliberately no tool that writes records, issues passes or clearances,
changes zone rules, or opens a gate. dispatch() refuses any other name.
Free text from records is wrapped as {"untrusted_text": ...}.
"""
import json
import re

from tools.policy_engine import evaluate
from tools.world import SourceUnavailable, iso, ts

ID_RE = re.compile(r"^[A-Z]{1,4}-[A-Za-z0-9]{1,8}$")
MAX_IDS = 12


def _ids(v, name):
    if isinstance(v, str):
        v = [s.strip() for s in v.split(",")]
    if not isinstance(v, list) or not v or len(v) > MAX_IDS:
        raise ValueError(f"{name} must be a list of 1-{MAX_IDS} IDs")
    out = [str(x).strip().upper() for x in v]
    bad = [x for x in out if not ID_RE.match(x)]
    if bad:
        raise ValueError(f"malformed ID(s) {bad}; IDs look like P-001, Z-W, REQ-101")
    return out


def _one(v, name):
    return _ids([v] if isinstance(v, str) else v, name)[0]


def find_request(world, entity_id):
    eid = _one(entity_id, "entity_id")
    hits = []
    for r in world.section("requests", "requests"):
        ids = {r["entity_id"], *(r.get("person_ids") or [])}
        m = r.get("manifest") or {}
        ids |= {m.get("vehicle_id"), m.get("driver_id"), *(m.get("occupant_ids") or [])}
        if eid in ids:
            hits.append({k: r[k] for k in ("request_id", "entity_type", "entity_id", "gate_id", "requested_passage_time")})
    return {"entity_id": eid, "requests": hits} if hits else {"error": f"no request involves {eid}"}


def get_request(world, request_id):
    rid = _one(request_id, "request_id")
    r = world.get_request(rid)
    if r is None:
        return {"error": f"unknown request_id {rid}"}
    r = dict(r)
    r["operator_note"] = {"untrusted_text": r.get("operator_note", "")}
    return r


def get_zone_rules(world, zone_ids, at=None):
    zids = _ids(zone_ids, "zone_ids")
    when = ts(at) if at else world.now
    bul = world.current_bulletin(when)
    known = world.zone_ids()
    out = {"bulletin": None if bul is None else {k: bul[k] for k in ("bulletin_id", "version", "issuer", "valid_from", "valid_to")},
           "zones": {}, "gates": []}
    if bul is None:
        out["error"] = "no current authorized bulletin"
    for z in zids:
        if z not in known:
            out["zones"][z] = {"error": f"unknown zone {z}"}
        elif bul:
            out["zones"][z] = bul["zones"][z]
    out["gates"] = [g for g in world._d["registry"]["gates"] if set(g["connects"]) & set(zids)]
    out["escorts_registered"] = [e["escort_id"] for e in world._d["registry"]["escorts"]]
    return out


def get_person_records(world, person_ids):
    out = []
    for pid in _ids(person_ids, "person_ids"):
        p = world.person(pid)
        if p is None:
            out.append({"person_id": pid, "error": "not in person registry"})
            continue
        rec = {"person_id": pid, "name": p["name"]}
        for key, fn in (("presence", lambda: [r for r in world.section("people", "presence") if r["person_id"] == pid]),
                        ("passes", lambda: [x for x in world.section("passes", "passes") if pid in x["holder_ids"]]),
                        ("clearances", lambda: [c for c in world.section("clearances", "clearances") if c["person_id"] == pid]),
                        ("field_reports", lambda: [dict(f, text={"untrusted_text": f["text"]})
                                                   for f in world.section("reports", "field_reports") if f.get("person_id") == pid])):
            try:
                rec[key] = fn()
            except SourceUnavailable as e:
                rec[key] = {"error": str(e)}
        out.append(rec)
    return {"people": out}


def get_area_reports(world, zone_ids):
    zids = set(_ids(zone_ids, "zone_ids"))
    out = {}
    try:
        out["water_alerts"] = [a for a in world.section("water", "alerts") if a["zone_id"] in zids]
        out["water_samples"] = [s for s in world.section("water", "samples") if s["zone_id"] in zids]
    except SourceUnavailable as e:
        out["water_error"] = str(e)
    try:
        lo = world.now - world.win["field_report_relevance_hours"]
        out["patrol_logs"] = [dict(p, text={"untrusted_text": p["text"]}) for p in world.section("reports", "patrol_logs")
                              if p["zone_id"] in zids and ts(p["received_at"]) >= lo]
    except SourceUnavailable as e:
        out["patrol_error"] = str(e)
    out["patrol_relevance_hours"] = world.policy["windows_hours"]["patrol_relevance_hours"]
    out["simulation_clock"] = iso(world.now)
    return out


def check_policy(world, request_id):
    return evaluate(world, _one(request_id, "request_id"))


def _arr(desc):
    return {"type": "array", "items": {"type": "string"}, "description": desc}


TOOLS = {
    "find_request": (find_request, "Find request IDs that involve a person, group or vehicle ID (e.g. P-010, GRP-02, VH-12).",
                     {"entity_id": {"type": "string", "description": "person, group or vehicle ID"}}, ["entity_id"]),
    "get_request": (get_request, "Get one travel request: entity, members or vehicle manifest, origin, destination, gate, time, passes, escort.",
                    {"request_id": {"type": "string", "description": "e.g. REQ-101"}}, ["request_id"]),
    "get_zone_rules": (get_zone_rules, "Current official bulletin rules (travel OPEN/CLOSED, escort_required) for zones, and the gates that touch them.",
                       {"zone_ids": _arr("zone IDs, e.g. [\"Z-A\", \"Z-D\"]")}, ["zone_ids"]),
    "get_person_records": (get_person_records, "Registry records for people: presence history, passes, follow-up clearance records, field reports.",
                           {"person_ids": _arr("person IDs, e.g. [\"P-011\", \"P-012\"]")}, ["person_ids"]),
    "get_area_reports": (get_area_reports, "Water alerts (including closed ones), water samples and recent patrol radio logs for zones.",
                         {"zone_ids": _arr("zone IDs")}, ["zone_ids"]),
    "check_policy": (check_policy, "Run the deterministic fictional policy check for a request. Returns recommendation, all blockers, per-person holds, rule IDs and evidence IDs.",
                     {"request_id": {"type": "string"}}, ["request_id"]),
}

TOOL_SPECS = [{"type": "function", "function": {"name": n, "description": d,
                                                 "parameters": {"type": "object", "properties": p, "required": req}}}
              for n, (_, d, p, req) in TOOLS.items()]


def dispatch(world, name, args):
    """Allowlisted call. Always returns a JSON string; errors are returned, never raised."""
    if name not in TOOLS:
        return json.dumps({"error": f"tool '{name}' is not allowed. Allowed: {sorted(TOOLS)}"})
    fn, _, props, req = TOOLS[name]
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return json.dumps({"error": "arguments must be a JSON object"})
    args = {k: v for k, v in (args or {}).items() if k in props}
    missing = [k for k in req if k not in args]
    if missing:
        return json.dumps({"error": f"missing argument(s) {missing}"})
    try:
        return json.dumps(fn(world, **args), separators=(",", ":"))
    except (ValueError, SourceUnavailable) as e:
        return json.dumps({"error": str(e)})
    except Exception as e:  # tool failure is reported to the model, never hidden
        return json.dumps({"error": f"tool failure: {type(e).__name__}: {e}"})
