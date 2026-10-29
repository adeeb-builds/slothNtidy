"""Stage 5 (report): writes COVERAGE.md - the covered / needs-review /
missing dashboard shown on deck slide 8."""
import os
from collections import Counter

def build_report(results: list, syllabus: list,
                 out_path="./SlothVault/COVERAGE.md", log=print):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    counts = Counter(r["coverage"] for r in results)
    lines = ["# slothNtidy - Coverage Dashboard", "",
             f"**Documents kept:** {len(results)} | "
             f"**Covered:** {counts.get('covered', 0)} | "
             f"**Needs review:** {counts.get('needs-review', 0)} | "
             f"**Missing:** {counts.get('missing', 0)}", "",
             "> Covered = matched to at least one syllabus topic with clean text.",
             "> That is coverage, not a guarantee of exam completeness.", "",
             "| Topic | Status | Files |", "|---|---|---|"]
    for t in syllabus:
        docs = [r for r in results if r.get("topic") and r["topic"]["topic"] == t["topic"]]
        covered = [r for r in docs if r["coverage"] == "covered"]
        status = "covered" if covered else ("needs-review" if docs else "**MISSING**")
        names = ", ".join(f'`{r["orig_name"]}`' for r in docs) or "-"
        lines.append(f'| {t["subject"]} U{t["unit"]}: {t["topic"]} | {status} | {names} |')
    lines += ["", "## Needs review (uncertain matches - never auto-assigned)", ""]
    flagged = [r for r in results if r["coverage"] == "needs-review"]
    lines += [f'- `{r["orig_name"]}`: {r.get("reason", "")}' for r in flagged] or ["(none)"]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    log(f"\n[REPORT] Coverage dashboard written to {out_path}")