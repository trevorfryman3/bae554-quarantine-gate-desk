"""Re-score saved traces with code (no inference) and print a Markdown results table.

  python eval/score.py traces/dell_baseline.jsonl [--label baseline] [--json eval/results_baseline.json]
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval.checkers import CHECKS, load_cases  # noqa: E402


def cell(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return "--"
    p = sum(vals)
    return f"{p}/{len(vals)}" + (" !" if 0 < p < len(vals) else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("traces", nargs="+")
    ap.add_argument("--label", default="", help="only score runs whose version.label matches")
    ap.add_argument("--json", default="", help="write machine-readable summary here")
    a = ap.parse_args()
    cases = load_cases(ROOT / "eval" / "cases.json")
    runs = [json.loads(l) for t in a.traces for l in Path(t).read_text(encoding="utf-8").splitlines() if l.strip()]
    runs = [r for r in runs if not a.label or r["version"].get("label") == a.label]
    versions = {json.dumps(r["version"], sort_keys=True) for r in runs}
    if len(versions) > 1:
        sys.exit(f"refusing to mix {len(versions)} configurations; pass --label")
    by_case = defaultdict(list)
    for r in runs:
        by_case[r["case_id"]].append(r)

    rows, summary = [], {"runs": len(runs), "cases": {}, "checks": {}}
    print("| Case | Type | " + " | ".join(CHECKS) + " | all three | Overall |")
    print("|---|---|" + "---|" * (len(CHECKS) + 2))
    totals = defaultdict(list)
    for cid, case in cases.items():
        rs = by_case.get(cid, [])
        res = {n: [fn(r, case) for r in rs] for n, fn in CHECKS.items()}
        allv = [all(res[n][i] for n in CHECKS) for i in range(len(rs))]
        for n in CHECKS:
            totals[n] += res[n]
        totals["all"] += allv
        p = sum(allv)
        overall = "no runs" if not rs else "reliable" if p == len(rs) else "always fails" if p == 0 else "inconsistent"
        print(f"| {cid} | {case['type']} | " + " | ".join(cell(res[n]) for n in CHECKS) + f" | {cell(allv)} | {overall} |")
        summary["cases"][cid] = {"runs": len(rs), "all_pass": p, "overall": overall,
                                 **{n: sum(v for v in res[n] if v) for n in CHECKS}}
    print()
    for n, v in totals.items():
        v = [x for x in v if x is not None]
        rate = sum(v) / len(v) if v else None
        summary["checks"][n] = {"pass": sum(v), "n": len(v), "rate": rate}
        print(f"- {n}: {sum(v)}/{len(v)}" + (f" = {rate:.0%}" if v else ""))
    first_ok = [bool(r["validations"]) and r["validations"][0]["ok"] for r in runs]
    fb = sum(1 for r in runs if r.get("fallback"))
    lat = sorted(r["latency_s"] for r in runs)
    summary.update(first_attempt_valid=sum(first_ok), fallbacks=fb,
                   latency_median_s=lat[len(lat) // 2] if lat else None, version=json.loads(next(iter(versions))) if versions else None)
    print(f"- harness validator passed on first answer: {sum(first_ok)}/{len(runs)}; harness fallbacks: {fb}/{len(runs)}")
    if lat:
        print(f"- latency per run: median {lat[len(lat) // 2]} s, max {lat[-1]} s")
    if a.json:
        Path(a.json).write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
