"""Stage 4 (match): decides which syllabus unit each note belongs to, and which
subtopics it actually covers.

Two kinds of evidence, each doing the job it is good at:

1. KEYWORD EVIDENCE (deterministic, traceable) - a subtopic is "covered" only when
   one of its keywords appears on a page of the note. We record the page number,
   so every tick on the dashboard can be traced back to the original page.
   Captions are NOT used for ticking subtopics ("recovery skipped" must not tick Recovery).

2. EMBEDDING SIMILARITY (MiniLM, local) - measures how close the note's meaning is
   to each unit's description. It breaks ties and rescues notes whose keywords OCR
   could not read - but such notes are only ever SUGGESTED (needs review), never
   silently assigned.

Outcome per document:
  sorted        - clear evidence for one unit
  needs-review  - evidence for two units equally, or only a caption / AI suggestion
  unmatched     - nothing in the syllabus fits (memes, other subjects)
"""
import re

from config import EMBED_SUGGEST, WEIGHT_KEYWORDS
from embedder import cosine
from syllabus import norm


def _phrase_regex(phrase: str):
    # whole words, optional plural "s": "banker" matches "bankers" but "scan" does not match "scanned"
    return re.compile(r"\b" + re.escape(phrase) + r"s?\b")


_REGEX_CACHE = {}


def _has(phrase: str, text_norm: str) -> bool:
    rx = _REGEX_CACHE.get(phrase)
    if rx is None:
        rx = _REGEX_CACHE[phrase] = _phrase_regex(phrase)
    return bool(rx.search(text_norm))


def find_hits(doc: dict, units: list) -> dict:
    """{unit_id: {subtopic_name: [page numbers]}} - only units with at least one hit."""
    pages = [norm(t) for t in doc.get("page_texts", [doc.get("text", "")])]
    hits = {}
    for u in units:
        found = {}
        for st in u["subtopics"]:
            pnums = [i + 1 for i, p in enumerate(pages) if any(_has(ph, p) for ph in st["phrases"])]
            if pnums:
                found[st["name"]] = pnums
        if found:
            hits[u["id"]] = found
    return hits


def total_hits(doc: dict, units: list) -> int:
    return sum(len(v) for v in find_hits(doc, units).values())


def caption_units(doc: dict, units: list) -> list:
    """Units named in the caption or filename (e.g. 'disk scheduling notes' -> Storage)."""
    words = norm(doc.get("caption", "") + " " + doc.get("orig_name", "").rsplit(".", 1)[0])
    if not words:
        return []
    found = []
    for u in units:
        title = norm(u["title"])
        named = (title and _has(title, words)) or any(
            _has(ph, words) for st in u["subtopics"] for ph in st["phrases"])
        if named:
            found.append(u["id"])
    return found


def unit_profile(u: dict) -> str:
    names = ", ".join(st["name"] for st in u["subtopics"])
    phrases = ", ".join(ph for st in u["subtopics"] for ph in st["phrases"])
    return f"{u['subject_name']} - {u['title']}: {names}. {phrases}"


def doc_profile(d: dict) -> str:
    return f"{d.get('caption', '')}\n{d.get('text', '')}"[:2000]


def match(docs: list, units: list, embedder=None, log=print) -> list:
    """Adds coverage / unit / hits / scores / reason to every document and returns them."""
    by_id = {u["id"]: u for u in units}
    unit_vecs = embedder.embed([unit_profile(u) for u in units]) if embedder and units else None

    for d in docs:
        d["hits"] = find_hits(d, units)
        d["caption_units"] = caption_units(d, units)
        d["scores"] = {}
        if unit_vecs is not None and d.get("chars", 0) > 0:
            vec = embedder.embed([doc_profile(d)])[0]
            d["scores"] = {u["id"]: round(cosine(vec, uv), 3) for u, uv in zip(units, unit_vecs)}

        def rank(uid):
            n = len(d["hits"].get(uid, {}))
            share = min(1.0, n / 2)
            emb = d["scores"].get(uid, 0.0)
            combined = WEIGHT_KEYWORDS * share + (1 - WEIGHT_KEYWORDS) * emb if d["scores"] else share
            return (n, combined)

        ranked = sorted(by_id, key=rank, reverse=True)
        best = ranked[0] if ranked else None
        second = ranked[1] if len(ranked) > 1 else None
        n_best = len(d["hits"].get(best, {})) if best else 0
        n_second = len(d["hits"].get(second, {})) if second else 0
        d["unit_id"], d["suggested_unit_id"], d["reason"] = None, None, ""

        if n_best and n_best == n_second:
            d["coverage"] = "needs-review"
            d["suggested_unit_id"] = best
            d["candidates"] = [best, second]
            d["reason"] = (f"Fits two units equally: {by_id[best]['subject_code']} U{by_id[best]['unit']} "
                           f"{by_id[best]['title']} and {by_id[second]['subject_code']} U{by_id[second]['unit']} "
                           f"{by_id[second]['title']} - you decide")
        elif n_best:
            d["coverage"] = "sorted"
            d["unit_id"] = best
            subs = ", ".join(f"{k} (p.{','.join(map(str, v))})" for k, v in d["hits"][best].items())
            d["reason"] = f"Found on the page: {subs}"
        elif d["caption_units"]:
            d["coverage"] = "needs-review"
            d["suggested_unit_id"] = d["caption_units"][0]
            u = by_id[d["suggested_unit_id"]]
            why = "no readable text" if d.get("chars", 0) < 60 else "no syllabus keywords found on the pages"
            d["reason"] = (f"Caption/filename points to {u['subject_code']} U{u['unit']} {u['title']}, "
                           f"but {why} - please confirm")
        elif d["scores"] and max(d["scores"].values()) >= EMBED_SUGGEST:
            top = max(d["scores"], key=d["scores"].get)
            d["coverage"] = "needs-review"
            d["suggested_unit_id"] = top
            u = by_id[top]
            d["reason"] = (f"AI similarity suggests {u['subject_code']} U{u['unit']} {u['title']} "
                           f"({d['scores'][top]:.2f}), but no keyword evidence - please confirm")
        elif d.get("chars", 0) < 60:
            d["coverage"] = "needs-review"
            d["reason"] = "No readable text and no caption - open it and decide where it goes"
        else:
            d["coverage"] = "unmatched"
            d["reason"] = "Nothing in your syllabus matches this file"

        label = d["unit_id"] or d["suggested_unit_id"] or "-"
        log(f"   [{d['coverage'].upper()}] {d['orig_name']} -> {label}: {d['reason']}")
    return docs


def unit_coverage(docs: list, units: list) -> list:
    """Per-unit dashboard rows: which subtopics are covered (with evidence) and which are missing."""
    rows = []
    for u in units:
        sorted_docs = [d for d in docs if d.get("unit_id") == u["id"]]
        review_docs = [d for d in docs if d.get("coverage") == "needs-review"
                       and (d.get("suggested_unit_id") == u["id"] or u["id"] in d.get("candidates", []))]
        evidence = {}
        for d in sorted_docs:
            for st, pages in d["hits"].get(u["id"], {}).items():
                evidence.setdefault(st, []).append({"file": d["orig_name"], "pages": pages,
                                                    "sender": d.get("sender", ""),
                                                    "group": d.get("group", "")})
        covered = [st["name"] for st in u["subtopics"] if st["name"] in evidence]
        missing = [st["name"] for st in u["subtopics"] if st["name"] not in evidence]
        if not sorted_docs:
            status = "MISSING"
        elif missing or review_docs:
            status = "NEEDS REVIEW"
        else:
            status = "READY"
        rows.append({
            "unit_id": u["id"], "subject_code": u["subject_code"], "subject_name": u["subject_name"],
            "unit": u["unit"], "title": u["title"], "status": status,
            "covered": covered, "missing": missing, "evidence": evidence,
            "files": [d["orig_name"] for d in sorted_docs],
            "review_files": [d["orig_name"] for d in review_docs],
            "pages": sum(d["pages"] for d in sorted_docs),
        })
    return rows
