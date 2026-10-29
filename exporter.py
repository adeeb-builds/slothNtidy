"""Stage 6 (export): merges each topic's documents into one topic-wise PDF
using PyMuPDF insert_pdf. Original page content is preserved exactly as
received - no OCR text replacement, no image recompression - with a
divider page per topic."""
import os
import pymupdf as fitz
from config import TOPIC_FOLDER

def make_divider(topic) -> fitz.Document:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 200), topic["subject"].upper(), fontsize=24, fontname="hebo")
    page.insert_text((72, 245), f'Unit {topic["unit"]}: {topic["topic"]}', fontsize=15, fontname="hebo")
    page.insert_text((72, 285), "slothNtidy - syllabus-mapped notes", fontsize=9, fontname="helv")
    return doc

def export_topics(results: list, out_dir=TOPIC_FOLDER, log=print):
    os.makedirs(out_dir, exist_ok=True)
    topics = {}
    for r in results:
        if r.get("coverage") == "covered" and r.get("topic"):
            topics.setdefault(r["topic"]["topic"], []).append(r)
    exported = []
    for topic_name, docs in topics.items():
        out = fitz.open()
        div = make_divider(docs[0]["topic"])
        out.insert_pdf(div)
        div.close()
        for r in docs:
            if os.path.exists(r["path"]):
                with fitz.open(r["path"]) as src:
                    out.insert_pdf(src)   # original pages, content preserved as-is
        safe = topic_name.lower().replace(" ", "_").replace("&", "and")[:40]
        path = os.path.join(out_dir, f"{safe}.pdf")
        out.save(path)
        out.close()
        exported.append(path)
        log(f"   [EXPORT] {path} ({len(docs)} document(s))")
    return exported