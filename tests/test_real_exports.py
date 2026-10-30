"""Edge cases found in the first real WhatsApp exports (30 Oct 2026): stickers, a damaged file, the same
zip added twice, the same PDF shared in two groups, long scanned PDFs, and the photos switch.
Run with:  python -m pytest -q"""
import os
import zipfile

import pymupdf as fitz
import pytest
from PIL import Image

import config
import parser as P
import pipeline
from config import configure_tesseract
from filters import text_ratio


def _pdf(path, text, pages=1):
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page().insert_textbox(fitz.Rect(50, 50, 550, 800), text, fontsize=11)
    doc.save(str(path))
    doc.close()


def _export(tmp_path, name, files):
    """A WhatsApp-style export zip: chat .txt + media."""
    z = tmp_path / f"WhatsApp Chat with {name}.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr(f"WhatsApp Chat with {name}.txt", "")
        for f in files:
            zf.write(f, os.path.basename(f))
    return z


@pytest.fixture()
def media(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    notes = src / "CN notes.pdf"
    _pdf(notes, "Application layer. The Web and HTTP. DNS is the Internet's directory service. " * 5)
    sticker = src / "STK-20260323-WA0022.webp"           # animated sticker, like WhatsApp sends
    frames = [Image.new("RGB", (64, 64), c) for c in ("red", "blue")]
    frames[0].save(sticker, save_all=True, append_images=frames[1:], duration=100, loop=0)
    photo = src / "IMG-20261001-WA0004.webp"              # an ordinary .webp photo (MuPDF cannot open webp)
    Image.new("RGB", (200, 120), "white").save(photo)
    broken = src / "DOC-20261002-WA0005.pdf"               # damaged download
    broken.write_bytes(b"%PDF-1.4 this is not really a pdf")
    return {"notes": notes, "sticker": sticker, "photo": photo, "broken": broken}


def test_stickers_are_skipped_not_read(tmp_path, media):
    inbox = tmp_path / "inbox" / "upload-1"
    inbox.mkdir(parents=True)
    _export(inbox, "Akshat", [media["notes"], media["sticker"]])
    files, _, skipped = P.scan_inbox(str(tmp_path / "inbox"), log=lambda *a: None)
    assert [os.path.basename(f) for f in files] == ["CN notes.pdf"]
    assert any(os.path.basename(s) == "STK-20260323-WA0022.webp" for s in skipped)


def test_the_same_zip_added_twice_is_read_once(tmp_path, media):
    for batch in ("upload-1", "upload-2"):
        d = tmp_path / "inbox" / batch
        d.mkdir(parents=True)
        _export(d, "Akshat", [media["notes"]])
    files, _, _ = P.scan_inbox(str(tmp_path / "inbox"), log=lambda *a: None)
    assert len(files) == 1


def test_a_damaged_file_is_listed_and_the_rest_is_still_read(tmp_path, media, monkeypatch):
    monkeypatch.setattr(P, "WORK_FOLDER", str(tmp_path / "work"))
    files = [str(media["notes"]), str(media["broken"]), str(media["photo"])]
    docs, failed = pipeline._read_all(files, {}, lambda *a: None, lambda *a: None)
    assert [d["orig_name"] for d in docs] == ["CN notes.pdf", "IMG-20261001-WA0004.webp"]   # webp photo opens
    assert [f["name"] for f in failed] == ["DOC-20261002-WA0005.pdf"]


def test_the_same_pdf_in_two_groups_is_read_once(tmp_path, media, monkeypatch):
    calls = []
    real = pipeline.extract_document
    monkeypatch.setattr(pipeline, "extract_document", lambda p, m=None: calls.append(p) or real(p, m))
    copy_dir = tmp_path / "group2"
    copy_dir.mkdir()
    copy = copy_dir / "CN notes.pdf"
    copy.write_bytes(media["notes"].read_bytes())
    docs, failed = pipeline._read_all([str(media["notes"]), str(copy)], {}, lambda *a: None, lambda *a: None)
    assert len(calls) == 1 and len(docs) == 2 and not failed
    assert docs[1]["path"] == str(copy) and docs[1]["text"] == docs[0]["text"]


@pytest.mark.skipif(not configure_tesseract(), reason="Tesseract not installed")
def test_long_scanned_pdf_reads_only_the_first_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "MAX_OCR_PAGES", 2)
    img = tmp_path / "scan.png"
    Image.new("RGB", (400, 300), "white").save(img)
    pdf = fitz.open()
    for _ in range(5):                               # 5 image-only pages = a phone scan
        page = pdf.new_page()
        page.insert_image(page.rect, filename=str(img))
    pdf.save(str(tmp_path / "scan.pdf"))
    d = P.extract_document(str(tmp_path / "scan.pdf"))
    assert d["pages"] == 5 and d["ocr_capped"] == 3


def test_photos_switch_off_reads_only_pdfs(tmp_path, media, monkeypatch):
    import importlib
    import exporter, filing, report  # noqa: E401
    out = tmp_path / "output"
    for name, value in {"OUTPUT_FOLDER": out, "VAULT_FOLDER": out / "SlothVault", "TOPIC_FOLDER": out / "TopicPDFs",
                        "WORK_FOLDER": out / "_work", "REPORT_JSON": out / "report.json",
                        "REPORT_MD": out / "COVERAGE.md"}.items():
        monkeypatch.setattr(config, name, str(value))
    mods = (P, filing, exporter, report, pipeline)
    try:
        for m in mods:
            importlib.reload(m)
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        for k in ("notes", "photo"):
            (inbox / media[k].name).write_bytes(media[k].read_bytes())
        syl = os.path.join(os.path.dirname(__file__), "demo_data", "syllabus.json")
        r = pipeline.run(str(inbox), syl, None, log=lambda *a: None, read_photos=False)
        assert r["photos_off"] == 1 and [d["orig_name"] for d in r["documents"]] == ["CN notes.pdf"]
    finally:
        monkeypatch.undo()
        for m in mods:
            importlib.reload(m)


def test_fast_duplicate_check_gives_the_same_decision():
    a = "Transport layer services. Multiplexing and demultiplexing. Connectionless transport UDP. " * 8
    b = a.replace("UDP", "U.D.P")
    c = "Network layer: routing algorithms, link state, distance vector, broadcast and multicast. " * 8
    assert text_ratio(a, b, need=0.8) == pytest.approx(text_ratio(a, b))     # likely duplicate: exact ratio
    assert text_ratio(a, c, need=0.8) < 0.8 and text_ratio(a, c) < 0.8         # quick rejection agrees


def test_phrase_cache_survives_more_texts_than_it_keeps():
    import filters
    for i in range(5100):   # more texts than the cache holds: must not lose the one being compared
        filters._shingles(f"note number {i} about routing and switching in networks")
    assert text_ratio("routing algorithms " * 40, "routing algorithms " * 40, need=0.8) == 1.0
