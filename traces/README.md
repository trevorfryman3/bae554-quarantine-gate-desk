# Trace files

| File | What it is |
|---|---|
| `dell_probe.jsonl` | 1 timing probe run (C08), Dell, skill 8210eab. |
| `dell_baseline.jsonl` | Baseline: 14 cases x 3 repeats, Dell, skill 8210eab, commit d9eb6aa. |
| `dell_baseline_replicate2.jsonl` | A second, independent run of the **same baseline configuration** (skill 8210eab, same code hash and model digest). Its records carry `label: after_change` because it was started before the Dell pulled the skill change in 3e2ee70; it is therefore NOT an after-change measurement. Kept unedited as evidence of run-to-run variability. |
| `dev/omen_smoke.jsonl` | Development smoke runs on a different desktop. Not evaluation evidence. |
| `dell_after_change.jsonl` | After the one failure-driven change (skill 925c1ea, commit 6ee8472): 14 cases x 3 repeats, Dell. Records marked `+dirty` differ from 6ee8472 only by CRLF line endings in the OneDrive-synced clone; the harness skill hash matches the committed skill. |
