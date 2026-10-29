"""Stage 3 (clean): removes circulars/notices, exact duplicates (SHA-256),
and near-duplicates (text ratio + pHash for scans). This is where the
deck's noise-reduction numbers come from."""
import os
import io
import hashlib
from difflib import SequenceMatcher
import pymupdf as fitz
from config import DUP_TEXT_RATIO, PHASH_MAX_DISTANCE, CIRCULAR_KEYWORDS, MIN_TEXT_CHARS

def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()

def page_phash(path: str):
    try:
        import imagehash
        from PIL import Image
        doc = fitz.open(path)
        pix = doc[0].get_pixmap(dpi=100)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        doc.close()
        return imagehash.phash(img)
    except Exception:
        return None

def is_circular(text: str, filename: str = "") -> bool:
    low = (filename + " " + text[:600]).lower()
    return any(k in low for k in CIRCULAR_KEYWORDS)

def text_ratio(a: str, b: str) -> float:
    n = min(len(a), len(b), 1500)
    if n < 50:
        return 0.0
    return SequenceMatcher(None, a[:n], b[:n]).ratio()

def clean(docs: list, log=print):
    """Returns (kept_docs, counts). Dropped docs get a status label."""
    kept, seen_hashes, seen_phash = [], {}, {}
    counts = {"total": len(docs), "circulars": 0, "exact_dups": 0,
              "near_dups": 0, "unreadable": 0, "kept": 0}
    for d in docs:
        if d["chars"] < MIN_TEXT_CHARS and not d["ocr_used"]:
            d["status"] = "unreadable"
            counts["unreadable"] += 1
            log(f"   [FLAG] {d['orig_name']}: scan with no text layer -> needs-review")
            kept.append(d)
            continue
        if is_circular(d["text"], d["orig_name"]):
            d["status"] = "circular"
            counts["circulars"] += 1
            log(f"   [DROP] {d['orig_name']}: circular/notice")
            continue
        h = sha256_of(d["path"])
        if h in seen_hashes:
            d["status"] = "exact_dup"
            counts["exact_dups"] += 1
            log(f"   [DROP] {d['orig_name']}: identical to {seen_hashes[h]}")
            continue
        seen_hashes[h] = d["orig_name"]
        ph = page_phash(d["path"])
        dup_of = None
        for other, other_ph in seen_phash.values():
            if text_ratio(d["text"], other["text"]) >= DUP_TEXT_RATIO:
                dup_of = other
                break
            if ph and other_ph and (ph - other_ph) <= PHASH_MAX_DISTANCE:
                dup_of = other
                break
        if dup_of:
            d["status"] = "near_dup"
            counts["near_dups"] += 1
            log(f"   [DROP] {d['orig_name']}: near-duplicate of {dup_of['orig_name']}")
            continue
        seen_phash[d["orig_name"]] = (d, ph)
        d["status"] = "kept"
        counts["kept"] += 1
        kept.append(d)
    return kept, counts