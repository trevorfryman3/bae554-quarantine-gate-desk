"""Run every case N times against the LOCAL Ollama model and append one JSON line per run.

  python eval/run_eval.py --out traces/<label>.jsonl --machine "Dell Latitude 5420 (i7-1185G7, 32 GB)"

* temperature 0.7 by default; seed left UNSET so repeats are independent samples
* resumes: (case, rep) pairs already in --out with the same version key are skipped
* refuses cloud models and non-local hosts (tools/agent.py)
* checker results are stored for convenience; eval/score.py re-scores saved traces from scratch
"""
import argparse
import datetime
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval.checkers import load_cases, score  # noqa: E402
from tools.agent import local_client, model_info, run_agent, sha, skill_text  # noqa: E402
from tools.world import World  # noqa: E402


def code_version():
    h = hashlib.sha256()
    for p in sorted([*ROOT.glob("tools/*.py"), *ROOT.glob("data/**/*.json"), ROOT / "eval" / "cases.json"]):
        h.update(p.relative_to(ROOT).as_posix().encode() + p.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:12]


def git_commit():
    try:
        c = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "tools", "data", "skill", "eval"], cwd=ROOT,
                               capture_output=True, text=True).stdout.strip()
        return (c or "none") + ("+dirty" if dirty else "")
    except OSError:
        return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="qwen3.5:4b")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--cases", default="", help="comma-separated case ids (default: all)")
    ap.add_argument("--machine", required=True, help="human label of the machine actually running the model")
    ap.add_argument("--label", default="", help="free label, e.g. baseline or after-fix-1")
    ap.add_argument("--num-ctx", type=int, default=8192)
    a = ap.parse_args()
    if a.temperature <= 0:
        sys.exit("temperature must be > 0 for the repeated evaluation")

    cases = load_cases(ROOT / "eval" / "cases.json")
    chosen = [c for cid, c in cases.items() if not a.cases or cid in a.cases.split(",")]
    client = local_client(timeout=900)
    info = model_info(client, a.model)
    digest = next((m.digest for m in client.list().models if m.model == a.model), None)
    version = {"code": code_version(), "skill": sha(skill_text()), "model": a.model, "model_digest": digest,
               "temperature": a.temperature, "num_ctx": a.num_ctx, "label": a.label}
    vkey = json.dumps(version, sort_keys=True)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if json.dumps(r["version"], sort_keys=True) == vkey:
                done.add((r["case_id"], r["rep"]))
    todo = [(c, rep) for rep in range(1, a.reps + 1) for c in chosen if (c["id"], rep) not in done]
    print(f"{len(done)} runs already saved for this version; {len(todo)} to run. version={version}", flush=True)

    machine = {"label": a.machine, "os": platform.platform(), "cpu": platform.processor(), "python": platform.python_version()}
    for i, (case, rep) in enumerate(todo, 1):
        world = World(snapshot=case.get("snapshot"), unavailable=case.get("faults", []))
        started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        rec = run_agent(case["prompt"], world, model=a.model, temperature=a.temperature, seed=None, num_ctx=a.num_ctx)
        rec.update(run_id=f"{case['id']}-r{rep}-{int(time.time())}", case_id=case["id"], rep=rep, started_at=started,
                   version=version, model_info=info, machine=machine, git_commit=git_commit(), seed=None,
                   simulation_clock=world.policy["simulation_clock"], data_version=world.version,
                   faults=case.get("faults", []), final_answer_text=rec["messages"][-1]["content"]
                   if rec["messages"][-1]["role"] == "assistant" else None)
        rec["checks"] = score(rec, case)
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fo = rec["final_output"]
        print(f"[{i}/{len(todo)}] {case['id']} r{rep}: {fo.get('recommendation')} ({fo.get('source')}) "
              f"checks={rec['checks']} repairs={rec['repairs']} {rec['latency_s']}s", flush=True)


if __name__ == "__main__":
    main()
