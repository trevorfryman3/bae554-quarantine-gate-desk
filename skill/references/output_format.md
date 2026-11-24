# Output format

Reply with exactly one JSON object and nothing else:

```json
{
  "request_id": "REQ-900",
  "entity_type": "GROUP",
  "recommendation": "HOLD",
  "travel_blocked": true,
  "members": [
    {"person_id": "P-901", "status": "CLEAR", "holds": [], "next_step": "No personal hold"},
    {"person_id": "P-902", "status": "HOLD", "holds": ["WA-90"], "next_step": "Complete follow-up testing; needs a current authorized CLEAR clearance for WA-90"}
  ],
  "applicable_rule_ids": ["DEC-001", "WATER-001", "WATER-003"],
  "evidence": ["REQ-900", "WA-90", "PR-902", "CL-901", "BUL-900-v1"],
  "missing_or_conflicting": [],
  "next_action": "Keep travel blocked until P-902 completes follow-up testing and has a current authorized CLEAR clearance. Do not split the group.",
  "human_approval_required": true
}
```

- `entity_type`: INDIVIDUAL, GROUP or VEHICLE (from the request).
- `recommendation`: APPROVE, DENY, HOLD or ESCALATE. Decision order: DENY > ESCALATE > HOLD > APPROVE.
- `travel_blocked`: true for DENY, HOLD and ESCALATE; false only for APPROVE.
- `members`: one entry for EVERY person in the request (vehicle: driver and occupants). `status` is CLEAR (no unreleased personal hold), HOLD (unreleased water hold) or REVIEW (needs the human reviewer). `holds` lists the alert IDs of unreleased holds.
- `applicable_rule_ids`: every rule ID that blocks the request (from check_policy blockers), plus DEC-001.
- `evidence`: record IDs you actually received from tools (request, bulletin, pass, presence, alert, sample, clearance, log, report IDs). Never invent IDs.
- `missing_or_conflicting`: each missing, stale, contradictory or suspicious item, with its record ID. Empty list if none.
- `next_action`: the exact next step for the operator, naming the reviewer when escalating.
- `human_approval_required`: always true.
