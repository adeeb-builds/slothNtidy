"""Stage 7 (report): writes output/COVERAGE.md (readable anywhere, even on GitHub)
and output/report.json (everything the UI shows)."""
import json
import os

from config import REPORT_JSON, REPORT_MD

# Fields the UI needs per document (page_texts are trimmed to keep report.json small)
_DOC_FIELDS = ["orig_name", "path", "pdf_path", "vault_path", "kind", "pages", "chars", "ocr_used",
               "sender", "timestamp", "date", "group", "caption", "status", "dup_of", "dup_reason",
               "removed_reason", "coverage", "unit_id", "suggested_unit_id", "candidates", "reason",
               "hits", "scores"]


def build_report(result: dict, md_path: str = REPORT_MD, json_path: str = REPORT_JSON, log=print):
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    rows, c = result["units"], result["counts"]
    lines = [
        "# slothNtidy - Coverage Dashboard", "",
        f"**Files in:** {c['total']}  |  **Circulars removed:** {c['circulars']}  |  "
        f"**Duplicates removed:** {c['exact_dups'] + c['near_dups']}  |  **Notes kept:** {c['kept']}", "",
        f"**Matching engine:** {result['engine']}", "",
        "| Unit | What is covered | What is NOT covered | Status | Pages |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        cov = ", ".join(r["covered"]) or "-"
        miss = ", ".join(r["missing"]) or "All subtopics present"
        status = f"**{r['status']}**" if r["status"] != "READY" else r["status"]
        lines.append(f"| {r['subject_code']} U{r['unit']}: {r['title']} | {cov} | {miss} | {status} | {r['pages']} |")
    lines += ["", "## Needs your review (never auto-assigned)", ""]
    review = [d for d in result["documents"] if d.get("coverage") == "needs-review"]
    lines += [f"- `{d['orig_name']}`: {d['reason']}" for d in review] or ["(none)"]
    lines += ["", "## Removed", ""]
    removed = [d for d in result["documents"] if d.get("status") in ("circular", "exact_dup", "near_dup")]
    lines += [f"- `{d['orig_name']}`: {d['removed_reason']}" for d in removed] or ["(none)"]
    lines += ["", "> Covered = a subtopic's keywords were found on a page of a note you received.",
              "> That is coverage of your material, not a guarantee of exam completeness."]
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    slim = dict(result)
    slim["documents"] = []
    for d in result["documents"]:
        s = {k: d.get(k) for k in _DOC_FIELDS}
        s["preview"] = [t[:600] for t in d.get("page_texts", [])[:3]]
        slim["documents"].append(s)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(slim, f, indent=2, ensure_ascii=False)
    log(f"   [REPORT] {md_path} and {json_path}")
