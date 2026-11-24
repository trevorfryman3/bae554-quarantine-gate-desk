# Quarantine Gate Desk (fictional BAE 554 agent)

> **DRAFT STATUS (2026-11-24):** working implementation and tests only. The graded Dell evaluation runs, failure analysis, November 30 robot-stack notes and December 2 peer results are **not yet done**; the report sections below are still the course template. All people, zones, tests and rules here are classroom fiction.

**BAE 554 Final Project · Fall 2026 · [Your name]**

> **How to use this template:** copy it into your repository as `README.md`. Keep the section headings and their order. Replace every `[bracketed]` prompt and delete the guidance lines that start with `>`. Word ranges are for the prose in each section; tables and code blocks don't count.

[One-sentence summary: what your agent does and for whom.]

- Project page (optional): [link or delete this line]
- Demo video (only if absent on 12/4): [link or delete this line]

---

## 1. Task
> 100–200 words.

**Task:** [What the agent does, in one or two sentences.]

**User:** [Who would use it, and in what situation.]

**Why an agent:** [Why this needs an agent rather than a fixed script or a single prompt. What varies from case to case?]

**Done criterion:** [How you, or the agent, know the task succeeded.]

## 2. Agent and model
> 75–150 words.

| Item | Your answer |
|---|---|
| Harness | [Hermes / approved website tool] |
| Model | [e.g., qwen3.5:4b] |
| Size | [parameters, e.g., 4B; for MoE give total and active] |
| Quantization | [e.g., Q4_K_M] |
| Runs on | [your laptop / lab machine / cloud, with justification if cloud] |

**Why this model:** [Capability, speed, memory, or tool-calling reliability. Mention anything you tested.]

## 3. Skill
> 75–150 words. Files go in [`skill/`](skill/).

- **Skill file:** [`skill/SKILL.md`](skill/SKILL.md)
- **Triggers when:** [Paste or summarize the description. What requests should load it?]
- **Should not trigger when:** [One example request that should not load it.]
- **Stops and asks a person when:** [At least two conditions.]
- **Scripts and references:** [List each file and what it does, or "none."]

## 4. Tools and autonomy
> A table. Code goes in [`tools/`](tools/).

| Tool or action | What it does | Built-in or custom | Autonomy level | Why this level |
|---|---|---|---|---|
| [name] | [description] | [built-in / custom] | [suggest-only / ask-before-acting / autonomous] | [reason] |
| [name] | | | | |

## 5. Evaluation
> 200–400 words plus the results table. Code goes in [`eval/`](eval/); saved runs in [`traces/`](traces/).

**How I ran the cases:** [Through Hermes (batch or scripted) or a notebook that reproduces the agent with my skill text and tools. Model(s), temperature, number of repeats.]

**Test cases:** [Where they are, e.g., `eval/cases.json`. Total cases; which are edge cases; which should escalate or refuse.]

**Programmatic checks:**

| Check | What it tests | Returns None when | Tested on (pass / fail example) |
|---|---|---|---|
| [check_name] | [question it answers] | [cases it doesn't apply to] | [which hand-built runs] |
| [check_name] | | | |

**Results** (passes / runs for each case; mark inconsistent cases with `!`):

| Case | Type | [Check 1] | [Check 2] | Overall |
|---|---|---|---|---|
| [case id] | [normal / edge / escalate] | [3/3] | [2/3 !] | [reliable / inconsistent / always fails] |

**Summary:** [Overall pass rates. Which cases are reliable, always failing, or inconsistent? Did any check disagree with your own judgment after reading a trace?]

## 6. Failure discussion
> 250–450 words.

### Failure 1: [case id]
- **Trace:** [link to the trace file in `traces/`]
- **What the model saw:** [the relevant context: question, skill text, tool results]
- **What it did:** [the call or answer]
- **Step that broke:** [tool choice / arguments / grounding / escalation], because [reason]

### Failure 2: [case id]
- **Trace:** [link]
- **What the model saw:**
- **What it did:**
- **Step that broke:**

### Change I made
[What you changed (skill text, tool description, check, model), the evidence that prompted it, and the before/after result.]

### Peer testing (12/2)
[Who tested it, the cases they wrote, what happened, and what you learned.]

## 7. Variability and safety
> 200–350 words.

**Unusual or poor-quality inputs:** [Examples you tested and how the agent handled them.]

**Escalation:** [When it hands off to a person, and how.]

**Not allowed to do, and how that's enforced:** [Toolsets, approvals, or checks. Instructions alone are not enforcement.]

**Prompt-injection risk:** [Where untrusted text enters, what it could make the agent do, and your mitigation.]

## 8. Physical-systems reflection
> 300–500 words total. Imagine your agent directing a robot, drone, sampler, pump, or dosing device. Use the robot stack from 11/30.

### 8.1 Harness responsibilities and rate
[What your agent would handle, and how often it would need to act.]

### 8.2 Lower layer
[What a VLA or classical controller would handle, and why your agent shouldn't.]

### 8.3 World model
[What you'd need a world model to predict before acting.]

### 8.4 Success detection and escalation
[How the system would know it succeeded, and when it would stop and escalate.]

## 9. How to run
> Short. Someone else should be able to reproduce your results.

```bash
# 1. Install and pull the model
[commands]

# 2. Install the skill and tools into Hermes
[commands]

# 3. Run the evaluation
[commands]
```

## Repository contents

| Folder | Contents |
|---|---|
| `skill/` | SKILL.md, scripts/, references/ |
| `tools/` | Tool code |
| `config/` | Copy of my Hermes configuration, secrets removed |
| `eval/` | Test cases, checks, checker tests, and the notebook or scripts that run them |
| `traces/` | Saved runs (JSON or JSONL) |
