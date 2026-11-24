"""Deterministic FICTIONAL policy engine (rules in data/v1/policy.json).

evaluate(world, request_id) -> dict with the recommendation, every blocker,
per-person statuses/holds, rule IDs, evidence IDs and next action. Pure reads.
Decision order (DEC-001): DENY > ESCALATE > HOLD > APPROVE.
"""
from tools.world import SourceUnavailable, iso, ts

ORDER = ["DENY", "ESCALATE", "HOLD", "APPROVE"]


def _overlap(a0, a1, b0, b1):
    s, e = max(a0, b0), min(a1, b1)
    return (s, e) if s < e else None


def evaluate(world, request_id):
    now, win = world.now, world.win
    blockers, notes, evidence = [], [], set()

    def block(rule, effect, detail, ev=()):
        blockers.append({"rule_id": rule, "effect": effect, "detail": detail, "evidence_ids": sorted(set(ev))})
        evidence.update(ev)

    try:
        req = world.get_request(request_id)
    except SourceUnavailable as e:
        req, notes = None, [str(e)]
    if req is None:
        block("EVID-005" if notes else "EVID-003", "ESCALATE", f"request {request_id} could not be retrieved")
        return _finish(world, request_id, None, blockers, notes, evidence, [])
    evidence.add(request_id)
    t = ts(req["requested_passage_time"])
    o, d, g = req["origin_zone"], req["destination_zone"], req["gate_id"]
    zones = world.zone_ids()

    # --- route / zones (EVID-002) -------------------------------------------------
    route_ok = True
    for z in (o, d):
        if z not in zones:
            route_ok = False
            block("EVID-002", "ESCALATE", f"zone {z} is not a known zone")
    gate = world.gate(g)
    if gate is None:
        route_ok = False
        block("EVID-002", "ESCALATE", f"gate {g} is not a known gate")
    elif route_ok and set(gate["connects"]) != {o, d}:
        route_ok = False
        block("EVID-002", "ESCALATE", f"gate {g} does not connect {o} and {d}")

    # --- bulletin (EVID-001, GATE-001, GATE-003) -----------------------------------
    bul = world.current_bulletin(t)
    if bul is None:
        block("EVID-001", "ESCALATE", "no current authorized bulletin covers the passage time")
    else:
        evidence.add(bul["bulletin_id"])
        for z in (o, d):
            zr = bul["zones"].get(z)
            if zr and zr["travel"] == "CLOSED":
                block("GATE-001", "DENY", f"zone {z} travel is CLOSED in {bul['bulletin_id']}", [bul["bulletin_id"]])
        dz = bul["zones"].get(d)
        if route_ok and dz and dz["escort_required"]:
            esc = next((e for e in world.section("registry", "escorts") if e["escort_id"] == req.get("escort_id")), None)
            if esc is None or ts(esc["cert_valid_to"]) < t:
                block("GATE-003", "DENY", f"destination {d} requires a registered escort; none valid on request", [bul["bulletin_id"]])

    # --- travellers / manifest (VEH-001, VEH-002, EVID-003) --------------------------
    members = []  # (person_id, role)
    if req["entity_type"] == "VEHICLE":
        m = req.get("manifest")
        if not m:
            block("VEH-001", "ESCALATE", "vehicle request has no manifest")
        else:
            if m.get("driver_id"):
                members.append((m["driver_id"], "driver"))
            else:
                block("VEH-001", "ESCALATE", "manifest has no driver_id")
            occ = m.get("occupant_ids") or []
            members += [(p, "occupant") for p in occ]
            if m.get("manifest_status") == "EMPTY_CERTIFIED":
                if occ or m.get("declared_occupant_count") != 0 or not m.get("inspection_id"):
                    block("VEH-002", "ESCALATE", "EMPTY_CERTIFIED manifest is inconsistent (occupants or no inspection record)")
                else:
                    notes.append(f"VEH-002: vehicle certified empty by {m['inspection_id']}; driver still checked")
                    evidence.add(m["inspection_id"])
            elif m.get("unresolved_entries") or len(occ) != m.get("declared_occupant_count"):
                block("VEH-001", "ESCALATE",
                      f"manifest lists {len(occ)} resolved occupant(s) but declares {m.get('declared_occupant_count')}; "
                      f"unresolved entries: {m.get('unresolved_entries') or 'none'}")
    else:
        role = "traveller" if req["entity_type"] == "INDIVIDUAL" else "member"
        members = [(p, role) for p in req.get("person_ids") or []]
        if not members:
            block("EVID-003", "ESCALATE", "request lists no travellers")
    resolved = []
    for pid, role in members:
        if world.person(pid) is None:
            block("EVID-003", "ESCALATE", f"{pid} is not in the person registry")
        else:
            resolved.append((pid, role))

    # --- passes (GATE-002) — only meaningful on a valid route -------------------------
    if route_ok:
        reg = world._d["registry"]
        passes = {p["pass_id"]: p for p in world.section("passes", "passes")}
        need = [pid for pid, _ in resolved] + ([req["entity_id"]] if req["entity_type"] == "VEHICLE" else [])
        for pid_ in req.get("pass_ids") or []:
            if pid_ not in passes:
                block("GATE-002", "DENY", f"pass {pid_} is not in the pass registry")
        for who in need:
            ok = [p for p in (passes.get(x) for x in req.get("pass_ids") or []) if p and who in p["holder_ids"]]
            good = [p for p in ok if p["status"] == "ACTIVE" and p["issuer"] in reg["pass_issuers"]
                    and g in p["gates"] and ts(p["valid_from"]) <= t <= ts(p["valid_to"])]
            if not good:
                why = "no pass names them" if not ok else "pass " + ", ".join(
                    f"{p['pass_id']} (valid {p['valid_from']}..{p['valid_to']}, gates {p['gates']}, {p['status']})" for p in ok
                ) + " is not valid for this gate/time"
                block("GATE-002", "DENY", f"{who}: {why}", [p["pass_id"] for p in ok])
            else:
                evidence.update(p["pass_id"] for p in good)

    # --- patrol logs (FIELD-001) ----------------------------------------------------
    try:
        for log in world.section("reports", "patrol_logs"):
            if log["zone_id"] not in (o, d) or not (now - win["patrol_relevance_hours"] <= ts(log["received_at"]) <= now):
                continue
            if log["category"] == "CONCERN" and log["provenance"] == "DIRECT_OBSERVATION":
                block("FIELD-001", "ESCALATE", f"fresh direct patrol concern {log['report_id']} in {log['zone_id']}", [log["report_id"]])
            elif log["category"] == "CONCERN":
                notes.append(f"{log['report_id']} is a {log['provenance']} rumour in {log['zone_id']}: reported, not acted on (FIELD-001)")
    except SourceUnavailable as e:
        block("EVID-005", "ESCALATE", str(e))

    # --- per person: field reports, presence, water holds --------------------------------
    member_out = [_person(world, pid, role, t, block, notes, evidence) for pid, role in resolved]
    held = [m for m in member_out if m["holds"] and any(h["release_status"] != "RELEASED" for h in m["holds"])]
    if held and len(resolved) > 1:
        block("WATER-003", "HOLD", "uncleared member(s) " + ", ".join(m["person_id"] for m in held)
              + " block the whole submitted journey; do not split or drop members")
    return _finish(world, request_id, req, blockers, notes, evidence, member_out)


def _person(world, pid, role, t, block, notes, evidence):
    now, win = world.now, world.win
    review, holds = [], []
    # field reports (FIELD-002)
    try:
        for fr in world.section("reports", "field_reports"):
            if fr.get("person_id") != pid:
                continue
            obs = ts(fr.get("observed_at")) if fr.get("observed_at") else None
            missing = [k for k in ("person_id", "zone_id", "observed_at", "observer_id", "tier") if not fr.get(k)]
            if obs and obs < now - win["field_report_relevance_hours"]:
                continue
            if missing or fr["tier"] == "T2":
                block("FIELD-002", "ESCALATE", f"{pid}: field report {fr['report_id']} "
                      + (f"missing {missing}" if missing else "tier T2 review required"), [fr["report_id"]])
                review.append(fr["report_id"])
            elif fr["tier"] == "T1":
                notes.append(f"{pid}: field report {fr['report_id']} tier T1 (monitor, note only)")
    except SourceUnavailable as e:
        block("EVID-005", "ESCALATE", f"{pid}: {e}")
        review.append("reports")

    # presence history (EVID-004)
    lo = now - win["water_lookback_hours"]
    try:
        pres = sorted((r for r in world.section("people", "presence") if r["person_id"] == pid), key=lambda r: r["from"])
    except SourceUnavailable as e:
        block("EVID-005", "ESCALATE", f"{pid}: {e}")
        return {"person_id": pid, "role": role, "status": "REVIEW", "holds": [], "next_step": "Restore presence records, then re-run review."}
    spans = [(r, ts(r["from"]), ts(r["to"]) if r["to"] else now) for r in pres]
    if not spans:
        block("EVID-004", "ESCALATE", f"{pid}: no presence history")
        review.append("presence")
    else:
        cursor = lo
        for r, a, b in spans:
            if a - cursor > win["presence_gap_tolerance_hours"]:
                block("EVID-004", "ESCALATE", f"{pid}: presence gap before {r['presence_id']}", [r["presence_id"]])
                review.append(r["presence_id"])
            cursor = max(cursor, b)
        if now - cursor > win["presence_gap_tolerance_hours"]:
            block("EVID-004", "ESCALATE", f"{pid}: presence history ends before the simulation clock")
            review.append("presence")
        for i, (r1, a1, b1) in enumerate(spans):
            for r2, a2, b2 in spans[i + 1:]:
                if r1["zone_id"] != r2["zone_id"] and _overlap(a1, b1, a2, b2):
                    block("EVID-004", "ESCALATE", f"{pid}: conflicting presence {r1['presence_id']} ({r1['zone_id']}) "
                          f"vs {r2['presence_id']} ({r2['zone_id']})", [r1["presence_id"], r2["presence_id"]])
                    review.append(r2["presence_id"])

    # water exposure (WATER-001) and release (WATER-002/004/005)
    try:
        alerts = [a for a in world.section("water", "alerts") if a["confirmed"] and a["status"] in ("ACTIVE", "CLOSED")]
        samples = world.section("water", "samples")
    except SourceUnavailable as e:
        block("EVID-005", "ESCALATE", f"{pid}: {e}")
        alerts, samples = [], []
        review.append("water")
    for al in alerts:
        a0, a1 = ts(al["affected_from"]), ts(al["affected_to"])
        hits = [(r, _overlap(s, e, a0, a1)) for r, s, e in spans if r["zone_id"] == al["zone_id"]]
        hits = [(r, ov) for r, ov in hits if ov and ov[1] > lo]
        if not hits:
            continue
        last = max(ov[1] for _, ov in hits)
        ids = [r["presence_id"] for r, _ in hits] + [al["alert_id"]]
        hold = {"alert_id": al["alert_id"], "rule_id": "WATER-001", "last_exposure_end": iso(last),
                "release_status": "NOT_RELEASED", "reason": "", "record_ids": ids}
        evidence.update(ids)
        try:
            recs = [c for c in world.section("clearances", "clearances") if c["person_id"] == pid]
        except SourceUnavailable as e:
            block("EVID-005", "ESCALATE", f"{pid}: {e}; hold for {al['alert_id']} cannot be assessed")
            hold["reason"] = "clearance registry unavailable"
            holds.append(hold)
            review.append("clearances")
            continue
        same = [c for c in recs if c["alert_id"] == al["alert_id"]]
        other = [c for c in recs if c["alert_id"] != al["alert_id"]]
        officers = {o_["officer_id"] for o_ in world._d["registry"]["clearance_officers"]}
        good, why = None, []
        for c in same:
            evidence.add(c["clearance_id"])
            hold["record_ids"].append(c["clearance_id"])
            issued = ts(c["issued_at"])
            if c["result"] == "FLAGGED":
                block("WATER-005", "ESCALATE", f"{pid}: {c['clearance_id']} result FLAGGED for {al['alert_id']}", [c["clearance_id"]])
                review.append(c["clearance_id"])
                why.append(f"{c['clearance_id']} FLAGGED")
            elif c["result"] in ("PENDING", "INCONCLUSIVE"):
                why.append(f"{c['clearance_id']} {c['result']} (follow-up testing not complete)")
            elif c["issued_by"] not in officers or c["signature_status"] != "VERIFIED":
                why.append(f"{c['clearance_id']} not from a registered officer with VERIFIED signature")
            elif issued <= last:
                why.append(f"{c['clearance_id']} issued {c['issued_at']} before last exposure {iso(last)} (re-exposure)")
            elif t > issued + win["clearance_validity_hours"]:
                why.append(f"{c['clearance_id']} expired (issued {c['issued_at']}, valid {int(win['clearance_validity_hours'].total_seconds() // 3600)} h)")
            else:
                good = c
        if good and not any(c["result"] == "FLAGGED" for c in same):
            hold.update(release_status="RELEASED", reason=f"released by {good['clearance_id']}")
        else:
            why += [f"{c['clearance_id']} is for {c['alert_id']}, not {al['alert_id']} (mismatch)" for c in other]
            evidence.update(c["clearance_id"] for c in other)
            hold["record_ids"] += [c["clearance_id"] for c in other]
            hold["reason"] = "; ".join(why) or "no clearance record for this alert"
            block("WATER-001", "HOLD", f"{pid}: personal hold for {al['alert_id']} — {hold['reason']}", hold["record_ids"])
            retests = [s for s in samples if s["source_id"] == al["source_id"] and s["result"] == "BELOW_LIMIT"
                       and ts(s["sampled_at"]) > a0]
            if retests:
                notes.append(f"WATER-004: source retest {', '.join(s['sample_id'] for s in retests)} does not release {pid}'s hold")
        holds.append(hold)

    unreleased = [h for h in holds if h["release_status"] != "RELEASED"]
    status = "REVIEW" if review else ("HOLD" if unreleased else "CLEAR")
    if status == "REVIEW":
        step = f"Refer to {world.reviewer['name']}; keep blocked" + (" and keep the personal water hold" if unreleased else "")
    elif status == "HOLD":
        step = "Complete follow-up testing; needs a current authorized CLEAR clearance for " + ", ".join(h["alert_id"] for h in unreleased)
    else:
        step = "No personal hold"
    return {"person_id": pid, "role": role, "status": status, "holds": holds, "next_step": step}


def _finish(world, request_id, req, blockers, notes, evidence, members):
    effects = {b["effect"] for b in blockers}
    rec = next((e for e in ORDER if e in effects), "APPROVE")
    rules = sorted({b["rule_id"] for b in blockers} | {"DEC-001"}
                   | ({"WATER-004"} if any(n.startswith("WATER-004") for n in notes) else set()))
    missing = [b["detail"] for b in blockers if b["effect"] == "ESCALATE"]
    holders = [m["person_id"] for m in members if any(h["release_status"] != "RELEASED" for h in m["holds"])]
    if rec == "DENY":
        nxt = "Do not open the gate. Tell the traveller which prohibition applies; a new request is needed once it is resolved."
    elif rec == "ESCALATE":
        nxt = f"Keep travel blocked and refer to {world.reviewer['name']} with the missing/conflicting evidence listed."
    elif rec == "HOLD":
        nxt = ("Keep travel blocked until " + ", ".join(holders) + " complete follow-up testing and have current authorized "
               "CLEAR clearances. Do not split the group or drop occupants; a revised manifest is a new request.")
    else:
        nxt = "Eligible for human authorization: the operator confirms identities at the gate and makes the final decision."
    if holders and rec in ("DENY", "ESCALATE"):
        nxt += " Personal water holds remain for " + ", ".join(holders) + "."
    return {
        "request_id": request_id,
        "entity_type": req["entity_type"] if req else None,
        "recommendation": rec,
        "travel_blocked": rec != "APPROVE",
        "members": members,
        "blockers": blockers,
        "applicable_rule_ids": rules,
        "evidence_ids": sorted(evidence),
        "missing_or_conflicting": missing,
        "notes": notes,
        "next_action": nxt,
        "human_approval_required": True,
        "reviewer": world.reviewer if rec == "ESCALATE" else None,
        "simulation_clock": iso(world.now),
        "data_version": world.version + (f"+{world.snapshot}" if world.snapshot else ""),
    }
