"""The whole slothNtidy pipeline as one function, used by both the UI (app.py)
and the command line (main.py).

  1 IMPORT   find chat exports, PDFs and photos in the inbox (unzips WhatsApp exports)
  2 PARSE    pair each file with sender/caption/group; read text (OCR for photos & scans)
  3 CLEAN    drop circulars, exact duplicates, near-duplicates (keep the fuller copy)
  4 MATCH    map each note to a syllabus unit; tick subtopics with page evidence
  5 FILE     copy everything into output/SlothVault, sorted, with clean names
  6 EXPORT   one merged exam-ready PDF per unit (original pages)
  7 REPORT   output/COVERAGE.md + output/report.json
"""
import os
import shutil
import time

from config import (INBOX_FOLDER, OUTPUT_FOLDER, SYLLABUS_FILE, TOPIC_FOLDER, VAULT_FOLDER,
                    WORK_FOLDER, configure_tesseract)
from exporter import export_units
from filing import file_notes
from filters import clean
from matcher import match, total_hits, unit_coverage
from parser import extract_document, scan_inbox
from report import build_report
from syllabus import load_syllabus

STAGES = ["Import", "Parse", "Clean", "Match", "File", "Export", "Report"]


def _reset_output(log):
    """output/ is generated - wipe it so every run starts clean. The inbox is never touched."""
    if os.path.isdir(OUTPUT_FOLDER):
        shutil.rmtree(OUTPUT_FOLDER)
    for p in (VAULT_FOLDER, TOPIC_FOLDER, WORK_FOLDER):
        os.makedirs(p, exist_ok=True)


def run(inbox: str = INBOX_FOLDER, syllabus_path: str = SYLLABUS_FILE, embedder=None,
        progress=None, log=print) -> dict:
    """progress(stage_index, stage_name, done, total, message) is called as work happens."""
    t0 = time.time()
    step = progress or (lambda *a: None)
    units = load_syllabus(syllabus_path)
    ocr_ok = configure_tesseract()

    _reset_output(log)
    step(0, "Import", 0, 1, "Looking for chat exports, PDFs and photos")
    roots = list(inbox) if isinstance(inbox, (list, tuple)) else [inbox]
    files, meta_by_folder, skipped = [], {}, []
    for root in roots:
        log(f"\n[1 IMPORT] scanning {root}")
        f, m, s = scan_inbox(root, log)
        files += f
        meta_by_folder.update(m)
        skipped += s
    chats = sum(1 for m in meta_by_folder.values() if m)
    log(f"   {len(files)} file(s), {chats} chat export(s), {len(skipped)} unsupported file(s) skipped")
    if not files:
        raise FileNotFoundError(f"No PDFs or photos found in {', '.join(roots)}")

    log("\n[2 PARSE] reading every note" + ("" if ocr_ok else " (Tesseract not found: photos cannot be read)"))
    docs = []
    for i, path in enumerate(files):
        step(1, "Parse", i, len(files), os.path.basename(path))
        docs.append(extract_document(path, meta_by_folder.get(os.path.dirname(path), {})))
        d = docs[-1]
        log(f"   [READ] {d['orig_name']}: {d['pages']} page(s), {d['chars']} chars"
            + (" (OCR)" if d["ocr_used"] else "") + (f" - caption: \"{d['caption']}\"" if d["caption"] else ""))

    step(2, "Clean", 0, 1, "Removing circulars and duplicates")
    log("\n[3 CLEAN] circulars, duplicates, noise")
    kept, counts = clean(docs, syllabus_hits=lambda d: total_hits(d, units), log=log)

    step(3, "Match", 0, 1, "Matching notes to your syllabus")
    log("\n[4 MATCH] mapping notes to syllabus units")
    match(kept, units, embedder, log=log)
    rows = unit_coverage(kept, units)

    step(4, "File", 0, 1, "Sorting copies into SlothVault")
    log("\n[5 FILE] sorting copies into the vault")
    filed = file_notes(docs, units, log=log)

    step(5, "Export", 0, 1, "Merging exam-ready PDFs per unit")
    log("\n[6 EXPORT] merged PDF per unit")
    exported = export_units(kept, rows, log=log)
    for r in rows:
        r["export_path"] = exported.get(r["unit_id"])

    result = {
        "inbox": [os.path.abspath(r) for r in roots],
        "engine": embedder.name if embedder else "Keyword evidence only (no embedding model installed)",
        "ocr": ocr_ok,
        "counts": counts,
        "filed": filed,
        "match_counts": {k: sum(1 for d in kept if d.get("coverage") == k)
                         for k in ("sorted", "needs-review", "unmatched")},
        "chats": chats,
        "groups": sorted({d["group"] for d in docs if d.get("group")}),
        "skipped": skipped,
        "units": rows,
        "documents": docs,
        "seconds": round(time.time() - t0, 1),
    }
    result["syllabus_path"] = syllabus_path
    step(6, "Report", 0, 1, "Writing the coverage report")
    log("\n[7 REPORT]")
    build_report(result, log=log)
    step(6, "Report", 1, 1, "Done")
    log(f"\nDone in {result['seconds']}s.")
    return result


# ---------------------------------------------------------------- your decisions (from the UI)

def _refresh(result: dict, log=print):
    """Recompute everything downstream of a human decision: counts, coverage, merged PDFs, report."""
    units = load_syllabus(result["syllabus_path"])
    docs = result["documents"]
    kept = [d for d in docs if d.get("status") in ("kept", "unreadable")]
    c = result["counts"]
    c["circulars"] = sum(d.get("status") == "circular" for d in docs)
    c["exact_dups"] = sum(d.get("status") == "exact_dup" for d in docs)
    c["near_dups"] = sum(d.get("status") == "near_dup" for d in docs)
    c["unreadable"] = sum(d.get("status") == "unreadable" for d in docs)
    c["kept"] = len(kept)
    result["match_counts"] = {k: sum(1 for d in kept if d.get("coverage") == k)
                              for k in ("sorted", "needs-review", "unmatched")}
    rows = unit_coverage(kept, units)
    if os.path.isdir(TOPIC_FOLDER):
        shutil.rmtree(TOPIC_FOLDER)
    exported = export_units(kept, rows, log=log)
    for r in rows:
        r["export_path"] = exported.get(r["unit_id"])
    result["units"] = rows
    build_report(result, log=log)


def _refile(doc: dict, units: list, log=print):
    old = doc.get("vault_path")
    if old and os.path.exists(old):
        os.remove(old)          # only ever removes our own COPY inside output/, never the original
    file_notes([doc], units, log=log)


def assign_to_unit(result: dict, orig_name: str, unit_id: str, log=print):
    """The student decides where an uncertain note belongs."""
    units = load_syllabus(result["syllabus_path"])
    doc = next(d for d in result["documents"] if d["orig_name"] == orig_name)
    doc.update(coverage="sorted", unit_id=unit_id, suggested_unit_id=None,
               reason="Assigned by you" + (f" (evidence: {', '.join(doc['hits'][unit_id])})"
                                           if doc.get("hits", {}).get(unit_id) else ""))
    _refile(doc, units, log)
    _refresh(result, log)


def mark_not_in_syllabus(result: dict, orig_name: str, log=print):
    units = load_syllabus(result["syllabus_path"])
    doc = next(d for d in result["documents"] if d["orig_name"] == orig_name)
    doc.update(coverage="unmatched", unit_id=None, suggested_unit_id=None, reason="Marked by you as not in syllabus")
    _refile(doc, units, log)
    _refresh(result, log)


def restore_removed(result: dict, orig_name: str, embedder=None, log=print):
    """'Not a duplicate / not a circular - keep it': the note goes back through matching."""
    units = load_syllabus(result["syllabus_path"])
    doc = next(d for d in result["documents"] if d["orig_name"] == orig_name)
    doc.update(status="kept", dup_of=None, dup_reason="", removed_reason="")
    if not doc.get("page_texts"):  # results reloaded from report.json carry only a preview - read again
        fresh = extract_document(doc["path"])
        doc.update(page_texts=fresh["page_texts"], text=fresh["text"], chars=fresh["chars"])
    match([doc], units, embedder, log=log)
    doc["reason"] = "Restored by you. " + doc["reason"]
    _refile(doc, units, log)
    _refresh(result, log)
