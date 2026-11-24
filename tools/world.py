"""Read-only loader for the versioned FICTIONAL fixtures in data/.

Every tool and the policy engine read records only through World. Nothing here
writes files. Paths are confined to data/<version>/ and data/snapshots.json.
"""
import copy
import json
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = (Path(__file__).resolve().parent.parent / "data").resolve()
FILES = ("policy", "registry", "people", "passes", "requests", "reports", "water", "clearances")


def ts(s):
    return None if s is None else datetime.fromisoformat(s.replace("Z", "+00:00"))


def iso(d):
    return None if d is None else d.strftime("%Y-%m-%dT%H:%M:%SZ")


class SourceUnavailable(Exception):
    """A record source is down (used for fault-injection cases)."""


class World:
    def __init__(self, version="v1", snapshot=None, unavailable=()):
        base = (DATA_DIR / version).resolve()
        if DATA_DIR not in base.parents:
            raise ValueError("fixture version must be a folder inside data/")
        self.version = version
        self.snapshot = snapshot
        self.unavailable = set(unavailable)
        self._d = {n: json.loads((base / f"{n}.json").read_text(encoding="utf-8")) for n in FILES}
        if snapshot:
            self._apply_snapshot(snapshot)
        p = self._d["policy"]
        self.now = ts(p["simulation_clock"])
        self.win = {k: timedelta(hours=v) for k, v in p["windows_hours"].items()}
        self.reviewer = p["reviewer"]

    def _apply_snapshot(self, name):
        snaps = json.loads((DATA_DIR / "snapshots.json").read_text(encoding="utf-8"))["snapshots"]
        spec = snaps[name]
        for path, ids in spec.get("remove", {}).items():
            f, key = path.split(".")
            idk = _id_key(self._d[f][key])
            self._d[f][key] = [r for r in self._d[f][key] if r[idk] not in ids]
        for path, recs in spec.get("add", {}).items():
            f, key = path.split(".")
            self._d[f][key] = self._d[f][key] + copy.deepcopy(recs)
        if "simulation_clock" in spec:
            self._d["policy"]["simulation_clock"] = spec["simulation_clock"]

    def section(self, file, key):
        if file in self.unavailable:
            raise SourceUnavailable(f"{file} registry unavailable (simulated fault)")
        return self._d[file][key]

    # convenience lookups -------------------------------------------------
    @property
    def policy(self):
        return self._d["policy"]

    def get_request(self, request_id):
        return next((r for r in self.section("requests", "requests") if r["request_id"] == request_id), None)

    def person(self, pid):
        return next((p for p in self.section("people", "persons") if p["person_id"] == pid), None)

    def zone_ids(self):
        return {z["zone_id"] for z in self._d["registry"]["zones"]}

    def gate(self, gid):
        return next((g for g in self._d["registry"]["gates"] if g["gate_id"] == gid), None)

    def current_bulletin(self, at):
        """Latest non-superseded bulletin from an authorized issuer valid at `at`."""
        reg = self._d["registry"]
        ok = [b for b in reg["bulletins"]
              if b["superseded_by"] is None and b["issuer"] in reg["bulletin_issuers"]
              and ts(b["valid_from"]) <= at <= ts(b["valid_to"])]
        return max(ok, key=lambda b: b["version"]) if ok else None


def _id_key(records):
    return next(k for k in records[0] if k.endswith("_id")) if records else "id"
