"""Stage 3 (clean): removes circulars/notices, exact duplicates and near-duplicates.

* Circulars   - filename words + official phrases ("dear students", "last date"...),
                unless the document is clearly study material (hits 3+ syllabus subtopics).
* Exact dups  - SHA-256 fingerprint of the file's bytes: identical files, identical code.
* Near dups   - (a) text similarity, for typed notes re-exported or re-typed;
                (b) pHash, a fingerprint of how a page LOOKS, for re-photographed scans.
* When two copies are near-duplicates we keep the FULLER one (more pages / more text)
  and record why, so the student can check the decision in the UI.

Nothing is deleted from disk: removed files are copied to _Removed/ by the filing stage.
"""
import hashlib
import io
import os
from difflib import SequenceMatcher

import pymupdf as fitz

from config import (CIRCULAR_FILENAME_WORDS, CIRCULAR_MAX_SYLLABUS_HITS, CIRCULAR_MIN_SIGNALS,
                    CIRCULAR_PHRASES, DUP_TEXT_RATIO, MIN_TEXT_CHARS, PHASH_MAX_DISTANCE)


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def page_phash(pdf_path: str):
    """Perceptual hash of the first page. Two photos of the same page give nearly the same hash."""
    try:
        import imagehash
        from PIL import Image
        with fitz.open(pdf_path) as doc:
            pix = doc[0].get_pixmap(dpi=72)
        return imagehash.phash(Image.open(io.BytesIO(pix.tobytes("png"))))
    except Exception:
        return None


def circular_signals(text: str, filename: str = ""):
    """Returns (score, reasons) for how much a document looks like a circular/notice.
    A filename hit scores 2, every official phrase in the first part of the text scores 1."""
    score, reasons = 0, []
    low_name = filename.lower()
    for w in CIRCULAR_FILENAME_WORDS:
        if w in low_name:
            score += 2
            reasons.append(f'filename contains "{w}"')
            break
    head = " " + " ".join(text[:900].lower().split()) + " "
    for p in CIRCULAR_PHRASES:
        if f" {p} " in head or f" {p}," in head or f" {p}." in head or f" {p}:" in head:
            score += 1
            reasons.append(f'says "{p}"')
    return score, reasons


def is_circular(text: str, filename: str = "", syllabus_hits: int = 0) -> bool:
    score, _ = circular_signals(text, filename)
    return score >= CIRCULAR_MIN_SIGNALS and syllabus_hits <= CIRCULAR_MAX_SYLLABUS_HITS


def text_ratio(a: str, b: str) -> float:
    a, b = " ".join(a.lower().split()), " ".join(b.lower().split())
    n = min(len(a), len(b), 2000)
    if n < 150:
        return 0.0
    return SequenceMatcher(None, a[:n], b[:n], autojunk=False).ratio()


def _fuller(a: dict, b: dict) -> dict:
    """More pages wins, then more text, then the bigger file (a sharper photo)."""
    def size(d):
        try:
            return os.path.getsize(d["path"])
        except OSError:
            return 0
    ka, kb = (a["pages"], a["chars"], size(a)), (b["pages"], b["chars"], size(b))
    return a if ka >= kb else b


def clean(docs: list, syllabus_hits=None, log=print):
    """Labels every document with a status and returns (kept_docs, counts).

    status: kept | unreadable | circular | exact_dup | near_dup
    syllabus_hits: optional function(doc) -> number of syllabus subtopics found (protects notes
                   from being mistaken for circulars)."""
    counts = {"total": len(docs), "circulars": 0, "exact_dups": 0, "near_dups": 0,
              "unreadable": 0, "kept": 0}
    hits_of = syllabus_hits or (lambda d: 0)

    # 1. circulars
    candidates = []
    for d in docs:
        d["dup_of"], d["dup_reason"], d["removed_reason"] = None, "", ""
        _, signals = circular_signals(d["text"], d["orig_name"])
        if is_circular(d["text"], d["orig_name"], hits_of(d)):
            d["status"] = "circular"
            d["removed_reason"] = "Circular / notice: " + ", ".join(signals)
            counts["circulars"] += 1
            log(f"   [DROP] {d['orig_name']}: circular/notice ({', '.join(signals)})")
            continue
        candidates.append(d)

    # 2. exact duplicates (same bytes)
    by_hash, unique = {}, []
    for d in candidates:
        d["sha256"] = sha256_of(d["path"])
        first = by_hash.get(d["sha256"])
        if first:
            d["status"], d["dup_of"] = "exact_dup", first["orig_name"]
            d["dup_reason"] = "Byte-for-byte identical file (same SHA-256 fingerprint)"
            d["removed_reason"] = f"Exact copy of {first['orig_name']}"
            counts["exact_dups"] += 1
            log(f"   [DROP] {d['orig_name']}: identical to {first['orig_name']}")
            continue
        by_hash[d["sha256"]] = d
        unique.append(d)

    # 3. near duplicates: compare every pair, keep the fuller copy of each group
    for d in unique:
        is_image = d["kind"] in ("photo", "scan") or d["chars"] < MIN_TEXT_CHARS
        d["_phash"] = page_phash(d["pdf_path"]) if is_image else None
    survivors = []
    for d in unique:
        match, reason = None, ""
        for s in survivors:
            if d["_phash"] is not None and s["_phash"] is not None:
                dist = d["_phash"] - s["_phash"]
                if dist <= PHASH_MAX_DISTANCE:
                    match, reason = s, (f"Same page photographed again (image fingerprint pHash "
                                        f"distance {dist} of 64)")
                    break
            ratio = text_ratio(d["text"], s["text"])
            if ratio >= DUP_TEXT_RATIO:
                match, reason = s, f"Same notes: {ratio:.0%} of the text matches"
                break
        if not match:
            survivors.append(d)
            continue
        keep = _fuller(match, d)
        drop = d if keep is match else match
        if keep is d:  # the newcomer is fuller - swap it in, and re-point earlier drops
            survivors[survivors.index(match)] = d
            for other in unique:
                if other.get("dup_of") == match["orig_name"] and other.get("status") == "near_dup":
                    other["dup_of"] = d["orig_name"]
        drop["status"], drop["dup_of"], drop["dup_reason"] = "near_dup", keep["orig_name"], reason
        drop["removed_reason"] = f"Near-duplicate of {keep['orig_name']} - kept the fuller copy"
        counts["near_dups"] += 1
        log(f"   [DROP] {drop['orig_name']}: near-duplicate of {keep['orig_name']} ({reason})")

    # 4. what is left is kept; unreadable ones are kept but flagged for review
    for d in survivors:
        d.pop("_phash", None)
        if d["chars"] < MIN_TEXT_CHARS:
            d["status"] = "unreadable"
            counts["unreadable"] += 1
            log(f"   [FLAG] {d['orig_name']}: no readable text -> needs your review")
        else:
            d["status"] = "kept"
        counts["kept"] += 1
    for d in unique:
        d.pop("_phash", None)
    return survivors, counts
