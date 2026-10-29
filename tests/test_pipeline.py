import os, pymupdf as fitz
from parser import extract_pdf
from filters import clean
import shutil

def make_pdf(tmp_path, name, body):
    p = str(tmp_path / name)
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), body)
    doc.save(p); doc.close()
    return p

def test_exact_duplicate_is_dropped(tmp_path):
    a = make_pdf(tmp_path, "a.pdf", "B+ tree indexing in DBMS " * 20)
    b = str(tmp_path / "b.pdf")
    shutil.copyfile(a, b)
    kept, counts = clean([extract_pdf(a), extract_pdf(b)])
    assert counts["exact_dups"] == 1 and counts["kept"] == 1

def test_circular_is_filtered(tmp_path):
    p = make_pdf(tmp_path, "c.pdf", "OFFICIAL CIRCULAR: holiday on Monday. " * 10)
    kept, counts = clean([extract_pdf(p)])
    assert counts["circulars"] == 1

def test_unreadable_scan_is_flagged_not_dropped(tmp_path):
    p = make_pdf(tmp_path, "s.pdf", "x")  # too little text
    kept, counts = clean([extract_pdf(p)])
    assert counts["unreadable"] == 1 and kept[0]["status"] == "unreadable"