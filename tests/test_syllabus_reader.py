"""Tests for reading a syllabus from a photo / PDF / Word file (syllabus_reader.py).
Run with:  python -m pytest -q        The photo test is skipped if Tesseract is missing."""
import io
import os
import zipfile

import pymupdf as fitz
import pytest

from config import configure_tesseract
from syllabus import flatten
from syllabus_reader import keywords_for, parse_text, read_syllabus, split_subtopics, to_syllabus

HERE = os.path.dirname(os.path.abspath(__file__))


def units_of(text):
    syl = to_syllabus(parse_text(text))
    return [(s["code"], u["unit"], u["title"], [t["name"] for t in u["subtopics"]])
            for s in syl["subjects"] for u in s["units"]]


HEADINGS = """VEER MADHO SINGH BHANDARI UTTARAKHAND TECHNICAL UNIVERSITY
B.Tech. Computer Science & Engineering - Semester IV
Course Code: BCS-401 Course Title: Operating Systems L-T-P: 3-1-0 Credits: 4
UNIT - I: Introduction
Operating system and its functions, Classification of operating systems: Batch, Interactive,
Time sharing, System calls.
UNIT -- II: Process Management and CPU Scheduling
Process concept, Threads; Scheduling algorithms: First Come First Serve (FCFS), Shortest Job First (SJF),
Round Robin. [10 Hours]
UNIT-III
Deadlocks
System model, Deadlock prevention, Banker's algorithm.
Text Books:
1. Silberschatz, Galvin and Gagne, "Operating System Concepts", Wiley.
Course Outcomes: CO1: Understand the structure and functions of OS.
"""


def test_unit_headings_titles_and_subtopics():
    got = units_of(HEADINGS)
    assert [(c, n, t) for c, n, t, _ in got] == [
        ("OS", 1, "Introduction"), ("OS", 2, "Process Management and CPU Scheduling"), ("OS", 3, "Deadlocks")]
    assert got[0][3] == ["Operating system and its functions", "Classification of operating systems", "Batch",
                         "Interactive", "Time sharing", "System calls"]       # line break kept the comma split
    assert "Round Robin" in got[1][3] and not any("Hours" in s for s in got[1][3])  # lecture hours dropped
    assert got[2][3] == ["System model", "Deadlock prevention", "Banker's algorithm"]  # book list left out


# OCR of a photographed table: the small unit numerals I-III were lost, IV came out as "Iv"
TABLE_OCR = """Subject: Database Management System Subject Code: BCS-402 Max Marks: 100
. Proposed
Ll te
Introduction: Data, Database, File system vs DBMS, Data
independence, Three schema architecture.
Relational Model: Integrity constraints, Keys: super key,
candidate key, primary key; Relational algebra.
SQL: DDL, DML, Joins, Nested queries, Views, Triggers,
Stored procedures.
Iv Normalization: Functional dependencies, 1NF, 2NF, 3NF, Boyce Codd
Normal Form (BCNF), Lossless decomposition. 08
V Transaction Processing: ACID properties, Serializability, Two phase
locking, Recovery techniques.
Reference Books: 1. Korth, Silberschatz, "Database System Concepts", McGraw Hill.
"""


def test_table_rows_without_numerals_still_become_units():
    got = units_of(TABLE_OCR)
    assert [(c, n, t) for c, n, t, _ in got] == [
        ("DBMS", 1, "Introduction"), ("DBMS", 2, "Relational Model"), ("DBMS", 3, "SQL"),
        ("DBMS", 4, "Normalization"), ("DBMS", 5, "Transaction Processing")]
    assert "Data independence" in got[0][3]          # wrapped line joined back together
    assert "Two phase locking" in got[4][3]
    assert "Boyce Codd Normal Form (BCNF)" in got[3][3]


def test_two_subjects_and_a_page_header_in_between():
    text = TABLE_OCR + "\nB.Tech CSE Semester IV   Page 2\n" + HEADINGS
    got = units_of(text)
    assert [c for c, *_ in got] == ["DBMS"] * 5 + ["OS"] * 3
    assert not any("Semester" in s for *_, subs in got for s in subs)


def test_numbering_restart_without_subject_name_starts_a_new_subject():
    syl = to_syllabus(parse_text("UNIT 1: A\nx, y.\nUNIT 2: B\nz.\nUNIT 1: C\nw."))
    assert [len(s["units"]) for s in syl["subjects"]] == [2, 1]
    assert syl["subjects"][0]["code"] != syl["subjects"][1]["code"]


def test_subtopic_splitting_and_short_forms():
    assert split_subtopics("Paging, Page replacement algorithms: FIFO, LRU and Optimal; Thrashing etc.") == \
        ["Paging", "Page replacement algorithms", "FIFO", "LRU", "Optimal", "Thrashing"]
    assert split_subtopics("Asymptotic notations (Big O, Omega, Theta), Master theorem") == \
        ["Asymptotic notations (Big O, Omega, Theta)", "Master theorem"]   # commas inside brackets kept
    assert keywords_for("Shortest Job First (SJF)") == ["shortest job first", "sjf"]
    assert keywords_for("Asymptotic notations (Big O, Omega, Theta)") == []


def test_result_is_a_valid_syllabus_for_the_matcher():
    units = flatten(to_syllabus(parse_text(HEADINGS)))
    assert units[1]["id"] == "OS-U2"
    assert ["first come first serve", "fcfs"] in [s["phrases"] for s in units[1]["subtopics"]]


def make_docx(paragraphs, table_rows):
    """A minimal real .docx: paragraphs, then a table (as Word saves it)."""
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    para = lambda t: f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>"
    rows = "".join("<w:tr>" + "".join(f"<w:tc>{para(c)}</w:tc>" for c in r) + "</w:tr>" for r in table_rows)
    body = "".join(para(p) for p in paragraphs) + f"<w:tbl>{rows}</w:tbl>" + para("Text Books") + \
        para("1. Horowitz, Sahni, Fundamentals of Computer Algorithms.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", f'<w:document xmlns:w="{w}"><w:body>{body}</w:body></w:document>')
    return buf.getvalue()


def test_word_file_with_a_table():
    data = make_docx(["Paper Code: TCS-501    Paper Name: Design and Analysis of Algorithms"],
                     [("Unit", "Contents", "Hrs"),
                      ("I", "Introduction: Algorithm specification, Time complexity.", "8"),
                      ("II", "Divide and Conquer: Binary search, Merge sort, Quick sort.", "7"),
                      ("III", "Greedy Method: Knapsack problem, Huffman coding.", "9")])
    got = read_syllabus([("daa.docx", data)])
    s = got["syllabus"]["subjects"]
    assert len(s) == 1 and s[0]["code"] == "DAA" and s[0]["name"] == "Design and Analysis of Algorithms"
    assert [(u["unit"], u["title"]) for u in s[0]["units"]] == [
        (1, "Introduction"), (2, "Divide and Conquer"), (3, "Greedy Method")]
    assert got["warnings"] == []          # the book list after the table is not a second subject


def test_pdf_with_text():
    doc = fitz.open()
    doc.new_page().insert_textbox(fitz.Rect(50, 50, 550, 800), HEADINGS, fontsize=9)
    got = read_syllabus([("os.pdf", doc.tobytes())])
    assert [u["title"] for u in got["syllabus"]["subjects"][0]["units"]][:2] == [
        "Introduction", "Process Management and CPU Scheduling"]


def test_nothing_found_gives_a_clear_warning():
    got = read_syllabus([("x.docx", make_docx(["Hello there"], [("a", "b")]))])
    assert got["syllabus"]["subjects"] == []
    assert any("No units were found" in w for w in got["warnings"])


@pytest.mark.skipif(not configure_tesseract(), reason="Tesseract not installed")
def test_phone_photo_of_a_printed_syllabus_table():
    with open(os.path.join(HERE, "fixtures", "syllabus_table_photo.jpg"), "rb") as f:
        got = read_syllabus([("IMG_2026.jpg", f.read())])
    s = got["syllabus"]["subjects"]
    assert s[0]["code"] == "DBMS"
    assert [u["title"] for u in s[0]["units"]] == [
        "Introduction", "Relational Model", "SQL", "Normalization", "Transaction Processing"]


# Shaped like the first real college syllabus read with the app (30 Oct 2026): the subject is only a
# heading line, OCR glued "Unit $5" onto the end of a line, and a hyphenated word is split across lines.
REAL_CN = """HEMVATI NANDAN BAHUGUNA GARHWAL UNIVERSITY
B.Sc. (Computer Science) Semester V
COMPUTER NETWORKS
Unit 1: Computer Networks and The Internet
What is the Internet, network edge, Delay, Loss and throughput in Packet-
Switched Networks.
Unit 4: Network Layer
Introduction, Internet Protocol (IP): Forwarding
and Addressing in the Internet, Broadcast and Multicast Routing. Unit $5
Data Link Layer
Introduction to the link layer, Error Detection and Correction Techniques, Multiplexing and Demultiplexing.
"""


def test_real_syllabus_shapes():
    syl = to_syllabus(parse_text(REAL_CN))
    s = syl["subjects"][0]
    assert (s["code"], s["name"]) == ("CN", "Computer Networks")         # name from the heading line
    assert [(u["unit"], u["title"]) for u in s["units"]] == [
        (1, "Computer Networks and The Internet"), (4, "Network Layer"), (5, "Data Link Layer")]
    u1, u4, u5 = [[t["name"] for t in u["subtopics"]] for u in s["units"]]
    assert "Loss and throughput in Packet-Switched Networks" in u1         # hyphen kept, one subtopic
    assert "Introduction" not in u4                                        # too generic to prove anything
    assert "Forwarding and Addressing in the Internet" in u4
    assert "Error Detection and Correction Techniques" in u5               # not split at "and"
