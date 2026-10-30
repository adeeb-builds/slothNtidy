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

from concurrent.futures import ThreadPoolExecutor, as_completed

from config import (IMAGE_TYPES, INBOX_FOLDER, OUTPUT_FOLDER, PARSE_WORKERS, SYLLABUS_FILE, TOPIC_FOLDER,
                    VAULT_FOLDER, WORK_FOLDER, configure_tesseract)
from exporter import PACK_FOLDER_NAME, export_subject_packs, export_units
from filing import file_notes
from filters import clean
from matcher import match, total_hits, unit_coverage
from parser import extract_document, file_hash, scan_inbox
from report import build_report
from syllabus import load_syllabus

STAGES = ["Import", "Parse", "Clean", "Match", "File", "Export", "Report"]


def _reset_output(log):
    """output/ is generated - wipe it so every run starts clean. The inbox is never touched."""
    if os.path.isdir(OUTPUT_FOLDER):
        shutil.rmtree(OUTPUT_FOLDER)
    for p in (VAULT_FOLDER, TOPIC_FOLDER, WORK_FOLDER):
        os.makedirs(p, exist_ok=True)


def _read_all(files, meta_by_folder, step, log):
    """Reads every file, several at a time. Identical files (same bytes, e.g. the same PDF shared in two
    groups) are read once. A file that cannot be opened is reported and skipped - it never stops the run."""
    by_hash, first_of = {}, {}
    for path in files:
        try:
            h = file_hash(path)
        except OSError:
            h = path
        first_of[path] = by_hash.setdefault(h, path)
    unique = list(by_hash.values())
    if PARSE_WORKERS > 1:
        os.environ.setdefault("OMP_THREAD_LIMIT", "1")   # one core per Tesseract, files run side by side
    read, failed = {}, []

    def work(path):
        return extract_document(path, meta_by_folder.get(os.path.dirname(path), {}))

    with ThreadPoolExecutor(max_workers=PARSE_WORKERS) as pool:
        futures = {pool.submit(work, p): p for p in unique}
        for n, fut in enumerate(as_completed(futures), 1):
            path = futures[fut]
            step(1, "Parse", n, len(unique), os.path.basename(path))
            try:
                read[path] = fut.result()
            except Exception as e:  # damaged / unsupported file
                failed.append({"name": os.path.basename(path), "path": path, "reason": f"{type(e).__name__}: {e}"[:200]})
                log(f"   [SKIP] {os.path.basename(path)}: could not be read ({type(e).__name__})")
    docs = []
    for path in files:                      # keep the inbox order; copies reuse the text of the first copy
        src = read.get(first_of[path])
        if src is None:
            if first_of[path] != path:
                failed.append({"name": os.path.basename(path), "path": path, "reason": "same file as one that could not be read"})
            continue
        if first_of[path] == path:
            d = src
        else:
            info = meta_by_folder.get(os.path.dirname(path), {}).get(os.path.basename(path), {})
            d = dict(src, path=path, pdf_path=path if src["pdf_path"] == src["path"] else src["pdf_path"],
                     orig_name=os.path.basename(path), sender=info.get("sender", ""),
                     timestamp=info.get("timestamp", ""), date=info.get("date", ""),
                     group=info.get("group", ""), caption=info.get("caption", ""),
                     page_texts=list(src["page_texts"]))
        docs.append(d)
        log(f"   [READ] {d['orig_name']}: {d['pages']} page(s), {d['chars']} chars"
            + (" (OCR)" if d["ocr_used"] else "") + (f" - caption: \"{d['caption']}\"" if d["caption"] else ""))
    return docs, failed


def run(inbox: str = INBOX_FOLDER, syllabus_path: str = SYLLABUS_FILE, embedder=None,
        progress=None, log=print, read_photos: bool = True) -> dict:
    """progress(stage_index, stage_name, done, total, message) is called as work happens.
    read_photos=False skips photos (only PDFs are read) - much faster on big groups."""
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
    photos_off = []
    if not read_photos:
        photos_off = [f for f in files if f.lower().endswith(IMAGE_TYPES)]
        files = [f for f in files if not f.lower().endswith(IMAGE_TYPES)]
        log(f"   photos switched off: {len(photos_off)} photo(s) not read")
    chats = sum(1 for m in meta_by_folder.values() if m)
    log(f"   {len(files)} file(s), {chats} chat export(s), {len(skipped)} unsupported file(s) skipped")
    if not files:
        raise FileNotFoundError(f"No PDFs or photos found in {', '.join(roots)}")

    log("\n[2 PARSE] reading every note" + ("" if ocr_ok else " (Tesseract not found: photos cannot be read)"))
    docs, failed = _read_all(files, meta_by_folder, step, log)
    if not docs:
        raise FileNotFoundError("None of the files in the inbox could be read.")

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
    packs = export_subject_packs(kept, rows, log=log)

    result = {
        "subject_packs": packs,         # {subject_code: one exam-pack PDF for the whole subject}
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
        "failed": failed,               # files that could not be opened (listed, never stop the run)
        "photos_off": len(photos_off),  # photos not read because "Read photos" was switched off
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
    pack_dir = os.path.join(os.path.dirname(TOPIC_FOLDER.rstrip("/\\")), PACK_FOLDER_NAME)
    for folder in (TOPIC_FOLDER, pack_dir):
        if os.path.isdir(folder):
            shutil.rmtree(folder)
    exported = export_units(kept, rows, log=log)
    for r in rows:
        r["export_path"] = exported.get(r["unit_id"])
    result["units"] = rows
    result["subject_packs"] = export_subject_packs(kept, rows, log=log)
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
