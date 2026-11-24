"""Check README.md against the course template with code.

  python eval/check_readme.py [--strict]

Word counts cover section prose only: tables, code blocks and headings are excluded,
and a markdown link counts as its visible text. --strict exits 1 on any problem.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RANGES = {"1": (100, 200), "2": (75, 150), "3": (75, 150), "5": (200, 400), "6": (250, 450), "7": (200, 350), "8": (300, 500)}
HEADINGS = ["1. Task", "2. Agent and model", "3. Skill", "4. Tools and autonomy", "5. Evaluation", "6. Failure discussion",
            "7. Variability and safety", "8. Physical-systems reflection", "9. How to run", "Repository contents"]
SUB8 = ["8.1 Harness responsibilities and rate", "8.2 Lower layer", "8.3 World model", "8.4 Success detection and escalation"]


def prose_words(text):
    words, in_code = 0, False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code or s.startswith("|") or s.startswith("#"):
            continue
        s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)  # link -> visible text
        words += len(re.findall(r"[A-Za-z0-9][\w'’./%-]*", s))
    return words


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--readme", default=str(ROOT / "README.md"))
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    md = Path(a.readme).read_text(encoding="utf-8")
    problems = []
    heads = re.findall(r"^## (.+)$", md, re.M)
    if heads != HEADINGS:
        problems.append(f"section headings/order differ from template: {heads}")
    if re.findall(r"^### (8\.\d .+)$", md, re.M) != SUB8:
        problems.append("Section 8 must keep the four template subheadings")
    parts = re.split(r"^## ", md, flags=re.M)[1:]
    for part in parts:
        title, body = part.split("\n", 1)
        num = title.split(".")[0]
        n = prose_words(body)
        lo_hi = RANGES.get(num)
        flag = "" if not lo_hi or lo_hi[0] <= n <= lo_hi[1] else f"  <-- outside {lo_hi[0]}-{lo_hi[1]}"
        print(f"{title:38} {n:4} words{flag}")
        if flag:
            problems.append(f"{title}: {n} words outside {lo_hi}")
        if "PENDING" in body:
            problems.append(f"{title}: contains PENDING")
    if re.search(r"^>", md, re.M):
        problems.append("template guidance lines starting with '>' remain")
    leftover = [b for b in re.findall(r"\[([^\]\n]+)\](?!\()", md) if b[:1].isupper() or b.startswith(("e.g", "link"))]
    if leftover:
        problems.append(f"bracketed template prompts remain: {leftover[:5]}")
    for target in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", md):
        if not target.startswith(("http://", "https://", "mailto:")) and not (ROOT / target).exists():
            problems.append(f"broken relative link: {target}")
    print("\n".join(["", "PROBLEMS:"] + [f"- {p}" for p in problems]) if problems else "\nREADME OK")
    sys.exit(1 if problems and a.strict else 0)


if __name__ == "__main__":
    main()
