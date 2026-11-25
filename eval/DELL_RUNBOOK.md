# Dell runbook: collecting the graded local runs

Graded runs must come from the Dell Latitude 5420 (i7-1185G7, 32 GB, no discrete GPU) with Ollama `qwen3.5:4b`.
Development smoke runs in `traces/dev/` came from a different desktop and are **not** evaluation evidence.
Run these in PowerShell on the Dell from the repository folder.

## 0. Get the code and environment
```powershell
git clone https://github.com/<user>/bae554-quarantine-gate-desk.git
cd bae554-quarantine-gate-desk
uv sync
ollama show qwen3.5:4b
hermes --version
```
`ollama show` must report `4.2B` and `Q4_K_M`. If Windows blocks `.venv\Scripts\python.exe`, use the fallback in README Section 9.

## 1. Tests (no model needed)
```powershell
uv run pytest -q tests eval
```

## 2. Timing probe (one run, to estimate the full suite)
```powershell
uv run python eval/run_eval.py --out traces/dell_probe.jsonl --cases C08-group-one-uncleared --reps 1 --label probe --machine "Dell Latitude 5420 (i7-1185G7, 32 GB, CPU only)"
```
Multiply the printed seconds by 42 for the baseline estimate. Plug the laptop in and keep it awake.

## 3. Baseline: 14 cases x 3 repeats at temperature 0.7 (resumable)
```powershell
uv run python eval/run_eval.py --out traces/dell_baseline.jsonl --reps 3 --label baseline --machine "Dell Latitude 5420 (i7-1185G7, 32 GB, CPU only)"
uv run python eval/score.py traces/dell_baseline.jsonl --label baseline --json eval/results_baseline.json
```
If interrupted, run the same command again: finished (case, repeat) pairs are skipped.

## 4. Hermes setup and parity runs
1. Copy `skill\` to `%LOCALAPPDATA%\hermes\skills\bae554\quarantine-gate-desk\` (Hermes v0.23 keeps skills as `skills\<category>\<name>\`).
2. Add the MCP server: `uv run python config/merge_hermes_mcp.py "$env:LOCALAPPDATA\hermes\config.yaml"`. It backs up the config to `config.yaml.bak-bae554` and replaces any existing `mcp_servers` entry (a second key makes Hermes refuse the whole file). The model section already points at local Ollama on the Dell.
3. Export a sanitized copy for the repository, then read it before committing:
```powershell
uv run python config/export_sanitized.py "$env:LOCALAPPDATA\hermes\config.yaml"
uv run python eval/hermes_parity.py --out traces/dell_hermes_parity.jsonl --cases C07-water-area-individual,C08-group-one-uncleared,C13-irrelevant-water-plus-injection --machine "Dell Latitude 5420"
```
If a Hermes flag is rejected, run `hermes chat --help` and pass the corrected command with `--cmd '["hermes","chat",...,"-q"]'`.

## 5. Send results back
```powershell
git add traces eval/results_baseline.json config/hermes_config.sanitized.yaml
git commit -m "Dell baseline runs"
git push
```
