"""Run with:  python -m pytest -q
None of these tests need the AI model or the internet. OCR tests are skipped if Tesseract is missing."""
import os
import shutil

import pymupdf as fitz
import pytest

import config
from config import configure_tesseract
from filters import clean, is_circular
from matcher import find_hits, match, unit_coverage
from parser import extract_pdf, parse_chat
from syllabus import load_syllabus

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNITS = load_syllabus(os.path.join(ROOT, "sample_data", "syllabus.json"))


def make_pdf(tmp_path, name, *pages):
    p = str(tmp_path / name)
    doc = fitz.open()
    for body in pages:
        doc.new_page().insert_textbox(fitz.Rect(50, 50, 550, 800), body, fontsize=10)
    doc.save(p)
    doc.close()
    return p


# ---------------------------------------------------------------- cleaning

def test_exact_duplicate_is_dropped(tmp_path):
    a = make_pdf(tmp_path, "a.pdf", "B+ tree indexing in DBMS " * 20)
    b = str(tmp_path / "b.pdf")
    shutil.copyfile(a, b)
    kept, counts = clean([extract_pdf(a), extract_pdf(b)], log=lambda *x: None)
    assert counts["exact_dups"] == 1 and counts["kept"] == 1


def test_circular_is_filtered(tmp_path):
    p = make_pdf(tmp_path, "c.pdf", "OFFICIAL CIRCULAR: Dear students, holiday on Monday. " * 5)
    kept, counts = clean([extract_pdf(p)], log=lambda *x: None)
    assert counts["circulars"] == 1


def test_scheduling_notes_are_not_mistaken_for_a_circular():
    # the first version dropped anything containing "schedule" - which killed CPU *scheduling* notes
    text = "CPU scheduling: FCFS, SJF and Round Robin with time quantum. Schedule of processes."
    assert not is_circular(text, "OS_Unit1_CPU_Scheduling.pdf", syllabus_hits=3)


def test_unreadable_scan_is_flagged_not_dropped(tmp_path):
    p = make_pdf(tmp_path, "s.pdf", "x")
    kept, counts = clean([extract_pdf(p)], log=lambda *x: None)
    assert counts["unreadable"] == 1 and kept[0]["status"] == "unreadable"


def test_near_duplicate_keeps_the_fuller_copy(tmp_path):
    body = ("First come first serve scheduling runs processes in order of arrival. "
            "Shortest job first picks the smallest burst. ") * 6
    short = make_pdf(tmp_path, "short.pdf", body)
    full = make_pdf(tmp_path, "full.pdf", body, "Round robin uses a time quantum. " * 10)
    kept, counts = clean([extract_pdf(short), extract_pdf(full)], log=lambda *x: None)
    assert counts["near_dups"] == 1
    assert [d["orig_name"] for d in kept] == ["full.pdf"]


# ---------------------------------------------------------------- WhatsApp parsing

def test_android_export_with_invisible_mark_pairs_caption(tmp_path):
    chat = tmp_path / "WhatsApp Chat with OS_Lab_Section.txt"
    chat.write_text("21/10/26, 9:14 pm - Rohan: ‎DOC-20261021-WA0019.pdf (file attached)\n"
                    "Deadlock notes, recovery skipped\n", encoding="utf-8")
    meta = parse_chat(str(chat))
    assert meta["DOC-20261021-WA0019.pdf"]["caption"] == "Deadlock notes, recovery skipped"
    assert meta["DOC-20261021-WA0019.pdf"]["group"] == "OS_Lab_Section"
    assert meta["DOC-20261021-WA0019.pdf"]["sender"] == "Rohan"


def test_iphone_export_caption_in_next_message(tmp_path):
    chat = tmp_path / "_chat.txt"
    chat.write_text("‎[21/10/26, 9:14:03 PM] Rohan: ‎<attached: 00000019-DOC.pdf>\n"
                    "[21/10/26, 9:15:20 PM] Rohan: Deadlock notes\n", encoding="utf-8")
    assert parse_chat(str(chat))["00000019-DOC.pdf"]["caption"] == "Deadlock notes"


def test_short_format_from_the_original_sample():
    meta = parse_chat(os.path.join(ROOT, "sample_data", "whatsapp_chat.txt"))
    assert meta["dbms_pdf3.pdf"]["caption"] == "Deadlock notes, recovery skipped"


# ---------------------------------------------------------------- matching

def test_subtopics_need_page_evidence_not_captions(tmp_path):
    p = make_pdf(tmp_path, "d.pdf", "Deadlock prevention and deadlock avoidance using the banker's algorithm. " * 3)
    d = extract_pdf(p, {"d.pdf": {"caption": "Deadlock notes, recovery skipped"}})
    hits = find_hits(d, UNITS)
    assert set(hits["OS-U2"]) == {"Deadlock Prevention", "Deadlock Avoidance", "Banker's Algorithm"}
    match([d], UNITS, None, log=lambda *x: None)
    row = next(r for r in unit_coverage([d], UNITS) if r["unit_id"] == "OS-U2")
    assert row["missing"] == ["Recovery from Deadlock"] and row["status"] == "NEEDS REVIEW"


def test_equal_evidence_for_two_units_goes_to_review(tmp_path):
    p = make_pdf(tmp_path, "x.pdf", "Two phase locking can cause deadlocks. Deadlock prevention: wait-die. " * 2)
    d = extract_pdf(p)
    match([d], UNITS, None, log=lambda *x: None)
    assert d["coverage"] == "needs-review" and set(d["candidates"]) == {"OS-U2", "DBMS-U4"}


# ---------------------------------------------------------------- end to end on the demo groups

@pytest.fixture()
def demo_run(tmp_path, monkeypatch):
    out = tmp_path / "output"
    for name, value in {"OUTPUT_FOLDER": str(out), "VAULT_FOLDER": str(out / "SlothVault"),
                        "TOPIC_FOLDER": str(out / "TopicPDFs"), "WORK_FOLDER": str(out / "_work"),
                        "REPORT_JSON": str(out / "report.json"), "REPORT_MD": str(out / "COVERAGE.md")}.items():
        monkeypatch.setattr(config, name, value)
    import importlib
    import exporter, filing, parser, pipeline, report  # noqa: E401
    for m in (parser, filing, exporter, report, pipeline):
        importlib.reload(m)
    yield pipeline, out
    for m in (parser, filing, exporter, report, pipeline):
        importlib.reload(m)


@pytest.mark.skipif(not configure_tesseract(), reason="Tesseract not installed")
def test_demo_end_to_end(demo_run):
    pipeline, out = demo_run
    r = pipeline.run(os.path.join(ROOT, "sample_data", "demo_inbox"),
                     os.path.join(ROOT, "sample_data", "syllabus.json"), None, log=lambda *x: None)
    c = r["counts"]
    assert (c["total"], c["circulars"], c["exact_dups"], c["near_dups"], c["kept"]) == (13, 3, 1, 2, 7)
    status = {u["unit_id"]: u["status"] for u in r["units"]}
    assert status == {"OS-U1": "READY", "OS-U2": "NEEDS REVIEW", "OS-U3": "MISSING", "OS-U4": "READY",
                      "DBMS-U4": "NEEDS REVIEW", "DBMS-U5": "READY"}
    # every note was filed somewhere, nothing left behind
    assert all(os.path.exists(d["vault_path"]) for d in r["documents"])
    assert os.path.isdir(out / "SlothVault" / "Operating Systems" / "Unit 1 - CPU Scheduling")
    # merged PDF = 1 cover page + every original page of the unit's notes
    u1 = next(u for u in r["units"] if u["unit_id"] == "OS-U1")
    with fitz.open(u1["export_path"]) as merged:
        assert merged.page_count == 1 + u1["pages"]
    # the student's decision on the ambiguous note is applied everywhere
    pipeline.assign_to_unit(r, "00000044-DOC-20261023-WA0044.pdf", "DBMS-U4", log=lambda *x: None)
    assert r["match_counts"]["needs-review"] == 0
