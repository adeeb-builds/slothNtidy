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
