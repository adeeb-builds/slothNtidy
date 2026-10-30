"""Stage 6 (export): one exam-ready PDF per syllabus unit.

Each PDF starts with a cover page listing what is covered (with the source file and
page for every subtopic) and what is missing, followed by the ORIGINAL pages of every
note sorted into that unit. Pages are copied with PyMuPDF insert_pdf: no OCR text
swapped in, no re-rendering, no recompression. Bookmarks let you jump to each source.
"""
import os

import pymupdf as fitz

from config import TOPIC_FOLDER

INK = (0.18, 0.28, 0.26)      # deck green
RED = (0.85, 0.25, 0.17)
GREY = (0.35, 0.35, 0.35)


def make_cover(row: dict, docs: list) -> fitz.Document:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(fitz.Rect(0, 0, 595, 150), color=INK, fill=INK)
    page.insert_text((48, 62), f"{row['subject_name'].upper()}  //  UNIT {row['unit']}",
                     fontsize=11, fontname="cour", color=(0.89, 0.66, 0.18))
    page.insert_text((48, 108), row["title"], fontsize=28, fontname="hebo", color=(1, 1, 1))
    y = 190
    page.insert_text((48, y), "COVERED", fontsize=10, fontname="cour", color=INK)
    y += 20
    for st in row["covered"]:
        src = row["evidence"][st][0]
        page.insert_text((48, y), f"+  {st}", fontsize=12, fontname="hebo", color=INK)
        page.insert_text((250, y), f"{src['file']}  p.{','.join(map(str, src['pages']))}",
                         fontsize=9, fontname="helv", color=GREY)
        y += 18
    if not row["covered"]:
        page.insert_text((48, y), "(nothing yet)", fontsize=11, fontname="helv", color=GREY)
        y += 18
    y += 16
    page.insert_text((48, y), "NOT COVERED - ASK YOUR CLASS FOR THESE", fontsize=10, fontname="cour", color=RED)
    y += 20
    for st in row["missing"]:
        page.insert_text((48, y), f"x  {st}", fontsize=12, fontname="hebo", color=RED)
        y += 18
    if not row["missing"]:
        page.insert_text((48, y), "All subtopics present", fontsize=11, fontname="helv", color=INK)
        y += 18
    y += 16
    page.insert_text((48, y), "SOURCES IN THIS PDF", fontsize=10, fontname="cour", color=INK)
    y += 20
    for d in docs:
        who = " - ".join(x for x in (d.get("sender"), d.get("group"), d.get("date")) if x)
        page.insert_text((48, y), f"{d['orig_name']}  ({d['pages']} p.)", fontsize=10, fontname="helv")
        if who:
            page.insert_text((300, y), who, fontsize=9, fontname="helv", color=GREY)
        y += 16
        if y > 800:
            break
    page.insert_text((48, 818), "slothNtidy - original pages follow, unchanged. Coverage is based on the notes "
                                "you received; it is not a guarantee of exam completeness.",
                     fontsize=7, fontname="helv", color=GREY)
    return doc


def export_units(docs: list, rows: list, out_dir: str = TOPIC_FOLDER, log=print) -> dict:
    """Returns {unit_id: pdf_path} for every unit that has at least one sorted note."""
    os.makedirs(out_dir, exist_ok=True)
    exported = {}
    for row in rows:
        unit_docs = [d for d in docs if d.get("unit_id") == row["unit_id"]]
        if not unit_docs:
            continue
        out = fitz.open()
        cover = make_cover(row, unit_docs)
        out.insert_pdf(cover)
        cover.close()
        toc = [[1, "Coverage summary", 1]]
        for d in unit_docs:
            start = out.page_count + 1
            with fitz.open(d["pdf_path"]) as src:
                out.insert_pdf(src)       # original pages, content preserved as-is
            toc.append([1, f"{d['orig_name']}" + (f" - {d['sender']}" if d.get("sender") else ""), start])
        out.set_toc(toc)
        name = f"{row['subject_code']}_Unit{row['unit']}_{row['title']}".replace(" ", "_").replace("&", "and")
        name = "".join(c for c in name if c.isalnum() or c in "_-")[:60] + ".pdf"
        path = os.path.join(out_dir, name)
        out.save(path, garbage=3, deflate=True)
        out.close()
        exported[row["unit_id"]] = path
        log(f"   [EXPORT] {path} ({len(unit_docs)} note(s))")
    return exported


def export_topics(results: list, out_dir: str = TOPIC_FOLDER, log=print):
    """Kept for compatibility with the first version of main.py."""
    from syllabus import load_syllabus
    from matcher import unit_coverage
    units = load_syllabus()
    return list(export_units(results, unit_coverage(results, units), out_dir, log).values())


# ---------------------------------------------------------------- one exam pack per subject

PACK_FOLDER_NAME = "SubjectPacks"


def _safe(text: str) -> str:
    """The built-in PDF fonts only cover Latin-1: swap common typographic characters."""
    rep = {"—": "-", "–": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "...", "•": "-", " ": " "}
    text = "".join(rep.get(c, c) for c in str(text))
    return text.encode("latin-1", "replace").decode("latin-1")


def _fit(text: str, size: float, width: float, font="helv") -> str:
    """Shortens text with '...' so it fits on one line."""
    text = _safe(text)
    if fitz.get_text_length(text, fontname=font, fontsize=size) <= width:
        return text
    while text and fitz.get_text_length(text + "...", fontname=font, fontsize=size) > width:
        text = text[:-1]
    return text + "..."


class _Writer:
    """Writes lines top to bottom, starting a new page when one is full."""
    TOP, BOTTOM, LEFT, RIGHT = 60, 800, 48, 547

    def __init__(self, doc):
        self.doc, self.page, self.y = doc, None, 0

    def new_page(self):
        self.page = self.doc.new_page(width=595, height=842)
        self.y = self.TOP
        return self.page

    def line(self, text, size=10, font="helv", color=(0, 0, 0), x=None, gap=None, right=None):
        if self.page is None or self.y + (gap or size + 6) > self.BOTTOM:
            self.new_page()
        x = self.LEFT if x is None else x
        width = (self.RIGHT if right is None else right) - x
        self.page.insert_text((x, self.y), _fit(text, size, width, font), fontsize=size, fontname=font, color=color)
        if gap != 0:
            self.y += gap or size + 6


def _status_color(status):
    return {"READY": INK, "MISSING": RED}.get(status, (0.72, 0.5, 0.1))


def _subject_cover(subject, rows, unit_start, total_pages):
    doc = fitz.open()
    w = _Writer(doc)
    page = w.new_page()
    page.draw_rect(fitz.Rect(0, 0, 595, 170), color=INK, fill=INK)
    page.insert_text((48, 62), "EXAM PACK  //  SLOTHNTIDY", fontsize=11, fontname="cour", color=(0.89, 0.66, 0.18))
    page.insert_text((48, 112), _fit(subject["name"], 26, 500, "hebo"), fontsize=26, fontname="hebo", color=(1, 1, 1))
    ready = sum(r["status"] == "READY" for r in rows)
    missing = sum(r["status"] == "MISSING" for r in rows)
    page.insert_text((48, 145), _safe(f"{len(rows)} units  ·  {ready} ready  ·  {len(rows) - ready - missing} to review"
                                      f"  ·  {missing} missing  ·  {total_pages} pages").replace("·", "-"),
                     fontsize=11, fontname="helv", color=(1, 1, 1))
    w.y = 210
    w.line("UNITS IN THIS PACK", 10, "cour", INK, gap=22)
    for r in rows:
        w.line(f"Unit {r['unit']}: {r['title']}", 13, "hebo", INK, gap=0, right=360)
        w.line(r["status"], 9, "cour", _status_color(r["status"]), x=372, gap=0)
        w.line(f"page {unit_start.get(r['unit_id'], '?')}", 10, "helv", GREY, x=475, gap=16)
        sub = (f"{len(r['covered'])} of {len(r['covered']) + len(r['missing'])} topics found in the notes"
               if r["status"] != "MISSING" else "No notes shared yet - ask your class")
        w.line(sub, 9, "helv", GREY, x=60, gap=22)
    w.y += 10
    w.line("HOW TO USE THIS PACK", 10, "cour", INK, gap=16)
    for t in ("Every unit starts with a divider page: what is covered, what is missing, and a topic index.",
              "The topic index lists every page in this pack where a topic appears - including pages in other",
              "units' notes - so overlapping explanations can be read together.",
              "All note pages are the original pages, unchanged. Use the bookmarks to jump to a unit or a note."):
        w.line(t, 9, "helv", GREY, gap=13)
    return doc


def _unit_divider(row, unit_docs, index, total_units):
    doc = fitz.open()
    w = _Writer(doc)
    page = w.new_page()
    color = _status_color(row["status"])
    page.draw_rect(fitz.Rect(0, 0, 595, 120), color=color, fill=color)
    page.insert_text((48, 50), _safe(f"UNIT {row['unit']} OF {total_units}  //  {row['status']}"),
                     fontsize=11, fontname="cour", color=(1, 1, 1))
    page.insert_text((48, 92), _fit(row["title"], 24, 500, "hebo"), fontsize=24, fontname="hebo", color=(1, 1, 1))
    w.y = 150
    if not unit_docs:
        w.line("No notes for this unit were shared in your groups yet.", 12, "hebo", RED, gap=22)
        w.line("ASK YOUR CLASS FOR THESE TOPICS", 10, "cour", RED, gap=18)
        for st in row["missing"]:
            w.line(f"x  {st}", 11, "helv", RED, gap=16)
        return doc
    w.line("NOTES IN THIS UNIT", 10, "cour", INK, gap=16)
    for d, start in unit_docs:
        who = " - ".join(x for x in (d.get("sender"), d.get("group"), d.get("date")) if x)
        w.line(f"{d['orig_name']}  ({d['pages']} p.)", 10, "hebo", (0, 0, 0), gap=0, right=330)
        w.line(f"from page {start}" + (f"  ·  {who}" if who else ""), 8, "helv", GREY, x=340, gap=15)
    w.y += 10
    w.line("TOPIC INDEX  -  every page in this pack where the topic appears", 10, "cour", INK, gap=18)
    for st_name, refs in index:
        mark, col = ("+", INK) if any(not other for _, _, other in refs) else (("~", (0.72, 0.5, 0.1)) if refs else ("x", RED))
        w.line(f"{mark}  {st_name}", 11, "hebo", col, gap=14)
        if not refs:
            w.line("not found in any note - ask your class", 9, "helv", RED, x=66, gap=16)
            continue
        text = "; ".join(f"p.{', '.join(map(str, pages))} ({name}{' - Unit ' + str(other) + ' notes' if other else ''})"
                         for name, pages, other in refs)
        line_ = ""                    # page references under the topic, wrapped over full width
        for wd in text.split(" "):
            if fitz.get_text_length(_safe(line_ + " " + wd), fontname="helv", fontsize=9) > 470 and line_:
                w.line(line_, 9, "helv", GREY, x=66, gap=12)
                line_ = wd
            else:
                line_ = (line_ + " " + wd).strip()
        w.line(line_, 9, "helv", GREY, x=66, gap=17)
    w.line("+ found in this unit's notes   ~ only found in another unit's notes   x not found", 8, "helv", GREY, gap=12)
    return doc


def export_subject_packs(docs: list, rows: list, out_dir: str = None, log=print) -> dict:
    """One exam pack PDF per subject: subject cover -> for every unit a divider page (coverage + topic
    index with page numbers in this pack) -> the original pages of the unit's notes. Units without notes
    get a divider listing what to ask for. Returns {subject_code: pdf_path}."""
    out_dir = out_dir or os.path.join(os.path.dirname(TOPIC_FOLDER.rstrip("/\\")), PACK_FOLDER_NAME)
    os.makedirs(out_dir, exist_ok=True)
    packs = {}
    subjects = {}
    for r in rows:
        subjects.setdefault(r["subject_code"], {"code": r["subject_code"], "name": r["subject_name"], "rows": []})["rows"].append(r)
    for code, subject in subjects.items():
        srows = sorted(subject["rows"], key=lambda r: r["unit"])
        per_unit = {r["unit_id"]: [d for d in docs if d.get("unit_id") == r["unit_id"]] for r in srows}
        if not any(per_unit.values()):
            continue
        sources = {}
        for r in srows:
            for d in per_unit[r["unit_id"]]:
                with fitz.open(d["pdf_path"]) as src:
                    sources[id(d)] = src.page_count

        def layout(cover_pages, divider_pages):
            """Page numbers (1-based) of every unit divider and every note, given the page counts."""
            pos, unit_start, note_start = cover_pages + 1, {}, {}
            for r in srows:
                unit_start[r["unit_id"]] = pos
                pos += divider_pages[r["unit_id"]]
                for d in per_unit[r["unit_id"]]:
                    note_start[id(d)] = pos
                    pos += sources[id(d)]
            return unit_start, note_start, pos - 1

        def topic_index(r, note_start):
            """For every subtopic of the unit: pages in this pack where it was found, own unit's notes first."""
            entries = []
            unit_of = {id(d): rr["unit"] for rr in srows for d in per_unit[rr["unit_id"]]}
            for st_name in r["covered"] + r["missing"]:
                refs = []
                for rr in sorted(srows, key=lambda x: x["unit_id"] != r["unit_id"]):
                    for d in per_unit[rr["unit_id"]]:
                        pages = d.get("hits", {}).get(r["unit_id"], {}).get(st_name)
                        if pages:
                            other = unit_of[id(d)] if rr["unit_id"] != r["unit_id"] else None
                            refs.append((d["orig_name"][:40], [note_start[id(d)] + p - 1 for p in pages][:6], other))
                entries.append((st_name, refs))
            # keep the syllabus order
            order = {s: i for i, s in enumerate(r["covered"] + r["missing"])}
            return sorted(entries, key=lambda e: order[e[0]])

        # pass 1: page counts with provisional numbers; pass 2: real numbers
        divider_pages = {r["unit_id"]: 1 for r in srows}
        cover_pages = 1
        for _ in range(2):
            unit_start, note_start, total = layout(cover_pages, divider_pages)
            dividers = {r["unit_id"]: _unit_divider(r, [(d, note_start[id(d)]) for d in per_unit[r["unit_id"]]],
                                                    topic_index(r, note_start), len(srows)) for r in srows}
            cover = _subject_cover(subject, srows, unit_start, total)
            new_div = {k: v.page_count for k, v in dividers.items()}
            if new_div == divider_pages and cover.page_count == cover_pages:
                break
            divider_pages, cover_pages = new_div, cover.page_count
        out = fitz.open()
        out.insert_pdf(cover)
        toc = [[1, f"{subject['name']} - exam pack", 1]]
        for r in srows:
            toc.append([1, f"Unit {r['unit']}: {r['title']} ({r['status'].lower()})", out.page_count + 1])
            out.insert_pdf(dividers[r["unit_id"]])
            for d in per_unit[r["unit_id"]]:
                toc.append([2, d["orig_name"] + (f" - {d['sender']}" if d.get("sender") else ""), out.page_count + 1])
                with fitz.open(d["pdf_path"]) as src:
                    out.insert_pdf(src)     # original pages, unchanged
        out.set_toc(toc)
        name = "".join(c for c in f"{code}_{subject['name']}_Exam_Pack".replace(" ", "_") if c.isalnum() or c in "_-")
        path = os.path.join(out_dir, name[:70] + ".pdf")
        out.save(path, garbage=3, deflate=True)
        out.close()
        packs[code] = path
        log(f"   [PACK] {path} ({total} pages)")
    return packs
