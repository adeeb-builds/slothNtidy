"""Gemma 4 handwriting reader - tested with a FAKE Gemma, so no internet, API key or download is needed.
Run with:  python -m pytest -q"""
import json

import pymupdf as fitz
import pytest
from PIL import Image

import gemma as G
import parser as P

HANDWRITTEN = ("Unit 2 Transport layer. TCP three way handshake: SYN, SYN-ACK, ACK. "
               "Flow control with sliding window. Congestion control: slow start.")


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code, self._payload, self.text = status, payload, json.dumps(payload)

    def json(self):
        return self._payload


class FakeGemmaServer:
    """Pretends to be the Gemini API (or Ollama). Counts calls; can be told to fail."""

    def __init__(self, text=HANDWRITTEN, fail=False, backend="api"):
        self.text, self.fail, self.backend, self.calls, self.last = text, fail, backend, 0, None

    def __call__(self, url, json=None, timeout=None, headers=None):
        self.calls += 1
        self.last = {"url": url, "json": json, "headers": headers}
        if self.fail:
            raise ConnectionError("no internet at the venue")
        if self.backend == "api":
            return FakeResponse(200, {"candidates": [{"content": {"parts": [
                {"text": "thinking...", "thought": True}, {"text": self.text}]}}]})
        return FakeResponse(200, {"response": self.text})


def _scan_pdf(path, pages=1):
    """An image-only PDF (what a phone scan of handwriting looks like to the program)."""
    img = path.parent / "page.png"
    Image.new("RGB", (600, 800), "white").save(img)
    pdf = fitz.open()
    for _ in range(pages):
        pg = pdf.new_page()
        pg.insert_image(pg.rect, filename=str(img))
    pdf.save(str(path))
    return str(path)


def _reader(tmp_path, server, backend="api"):
    return G.GemmaReader(backend, api_key="test-key" if backend == "api" else "",
                         cache_dir=str(tmp_path / "cache"), post=server)


def test_gemma_reads_a_handwritten_scan_and_marks_the_page(tmp_path):
    server = FakeGemmaServer()
    d = P.extract_document(_scan_pdf(tmp_path / "cn_notes.pdf"), gemma=_reader(tmp_path, server))
    assert "sliding window" in d["text"]
    assert d["page_readers"] == ["gemma"] and d["gemma_pages"] == 1
    # the API request carries the page image and the key goes in a header, never in the URL
    part = server.last["json"]["contents"][0]["parts"][0]
    assert part["inline_data"]["mime_type"] == "image/png" and part["inline_data"]["data"]
    assert "key=" not in server.last["url"] and server.last["headers"]["x-goog-api-key"] == "test-key"


def test_thinking_parts_are_not_used_as_page_text(tmp_path):
    d = P.extract_document(_scan_pdf(tmp_path / "n.pdf"), gemma=_reader(tmp_path, FakeGemmaServer()))
    assert "thinking..." not in d["text"]


def test_local_ollama_backend(tmp_path):
    server = FakeGemmaServer(backend="local")
    d = P.extract_document(_scan_pdf(tmp_path / "n.pdf"), gemma=_reader(tmp_path, server, "local"))
    assert d["gemma_pages"] == 1 and server.last["json"]["model"] == "gemma4:e4b"
    assert server.last["json"]["images"]


def test_cache_means_second_run_needs_no_internet(tmp_path):
    pdf = _scan_pdf(tmp_path / "n.pdf")
    first = FakeGemmaServer()
    P.extract_document(pdf, gemma=_reader(tmp_path, first))
    offline = FakeGemmaServer(fail=True)
    reader = _reader(tmp_path, offline)
    d = P.extract_document(pdf, gemma=reader)
    assert offline.calls == 0 and reader.cache_hits == 1 and "sliding window" in d["text"]


def test_gemma_down_never_crashes_and_switches_itself_off(tmp_path):
    server = FakeGemmaServer(fail=True)
    reader = _reader(tmp_path, server)
    d = P.extract_document(_scan_pdf(tmp_path / "n.pdf", pages=4), gemma=reader)
    assert d["gemma_pages"] == 0 and d["pages"] == 4          # still read, Tesseract result kept
    assert reader.disabled and "no internet" in reader.last_error
    assert server.calls == 6                                   # 3 pages x (1 try + 1 retry), then off


def test_only_a_few_pages_per_document_go_to_gemma(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "MAX_GEMMA_PAGES", 2)
    server = FakeGemmaServer()
    reader = _reader(tmp_path, server)
    # different page images so the cache does not answer for them
    pdf = fitz.open()
    for i in range(5):
        img = tmp_path / f"p{i}.png"
        Image.new("RGB", (600, 800), (255, 255 - i * 20, 255)).save(img)
        pg = pdf.new_page()
        pg.insert_image(pg.rect, filename=str(img))
    pdf.save(str(tmp_path / "long.pdf"))
    d = P.extract_document(str(tmp_path / "long.pdf"), gemma=reader)
    assert d["gemma_pages"] == 2 and server.calls == 2


def test_typed_pdfs_never_go_to_gemma(tmp_path):
    doc = fitz.open()
    doc.new_page().insert_textbox(fitz.Rect(50, 50, 550, 800), HANDWRITTEN * 3, fontsize=11)
    doc.save(str(tmp_path / "typed.pdf"))
    server = FakeGemmaServer()
    d = P.extract_document(str(tmp_path / "typed.pdf"), gemma=_reader(tmp_path, server))
    assert server.calls == 0 and d["page_readers"] == ["pdf"]


def test_garbage_ocr_counts_as_unreadable_but_real_text_does_not():
    assert G.looks_unreadable("", 60)
    assert G.looks_unreadable("~ i_ ,| .. ee ry a; 7) ]] -- lll' ¢ % rr tt Il |1 ~~ ::: Y¥", 20)
    assert not G.looks_unreadable("Deadlock happens when processes wait for each other in a circular chain", 20)


def test_api_backend_needs_a_key(tmp_path):
    with pytest.raises(ValueError):
        G.GemmaReader("api", api_key="", cache_dir=str(tmp_path))


def test_connection_check_explains_problems_in_plain_english():
    bad = lambda *a, **k: FakeResponse(403, {"error": "bad key"})
    assert "rejected" in G.check_connection("api", "x", post=bad)
    assert G.check_connection("api", "") == "Paste your Gemini API key first."
    ok = lambda *a, **k: FakeResponse(200, {})
    assert G.check_connection("api", "x", post=ok) == ""
    no_model = lambda *a, **k: FakeResponse(200, {"models": [{"name": "qwen2.5:7b"}]})
    assert "ollama pull" in G.check_connection("local", get=no_model)


def test_full_sort_files_a_handwritten_note_only_because_gemma_read_it(tmp_path, monkeypatch):
    """End to end: a blank-looking scan (Tesseract reads nothing) lands in OS Unit 2 Deadlocks once Gemma reads it."""
    import importlib
    import os
    import config
    import exporter, filing, pipeline, report  # noqa: E401
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
        (inbox / "IMG-20261030-WA0007.pdf").write_bytes(open(_scan_pdf(tmp_path / "scan.pdf"), "rb").read())
        syl = os.path.join(os.path.dirname(__file__), "demo_data", "syllabus.json")
        quiet = lambda *a: None
        before = pipeline.run(str(inbox), syl, None, log=quiet)
        assert before["documents"][0].get("unit_id") is None
        handwriting = ("Deadlocks - Operating Systems. Deadlock prevention: deny one of the four conditions. "
                       "Deadlock avoidance using safe state. Banker's algorithm with need matrix.")
        reader = _reader(tmp_path, FakeGemmaServer(text=handwriting))
        after = pipeline.run(str(inbox), syl, None, log=quiet, gemma=reader)
        d = after["documents"][0]
        assert d["gemma_pages"] == 1 and d["coverage"] == "sorted" and d["unit_id"].endswith("2")
        assert after["gemma"]["pages"] == 1 and not after["gemma"]["disabled"]
    finally:
        monkeypatch.undo()
        for m in mods:
            importlib.reload(m)


SYLLABUS_ANSWER = """```json
{"subjects": [{"name": "Computer Networks", "code": "CN", "units": [
 {"unit": 1, "title": "Computer Networks and the Internet", "subtopics": [
   {"name": "What is the Internet", "keywords": ["internet", "ISP"]},
   {"name": "Network Core", "keywords": ["packet switching", "circuit switching"]}]},
 {"unit": 3, "title": "Transport Layer", "subtopics": [
   {"name": "TCP", "keywords": ["tcp", "three way handshake", "tcp"]}]},
 {"unit": 4, "title": "Empty unit", "subtopics": []}]}]}
```"""


def test_gemma_reads_the_syllabus_photo_and_suggests_keywords(tmp_path):
    import syllabus_reader as SR
    from syllabus import flatten
    server = FakeGemmaServer(text=SYLLABUS_ANSWER)
    buf = tmp_path / "syl.png"
    Image.new("RGB", (800, 600), "white").save(buf)
    got = SR.read_syllabus([("syl.png", buf.read_bytes())], gemma=_reader(tmp_path, server))
    assert got["reader"] == "gemma"
    cn = got["syllabus"]["subjects"][0]
    assert cn["code"] == "CN" and [u["unit"] for u in cn["units"]] == [1, 3]   # empty unit dropped
    assert cn["units"][0]["subtopics"][0]["keywords"] == ["internet", "isp"]      # lower-cased
    assert cn["units"][1]["subtopics"][0]["keywords"] == ["tcp", "three way handshake"]  # de-duplicated
    assert server.last["json"]["contents"][0]["parts"][0]["inline_data"]["data"]   # the photo was sent
    assert len(flatten(got["syllabus"])) == 2                                      # loads as a normal syllabus


def test_syllabus_falls_back_to_tesseract_when_gemma_fails(tmp_path):
    import os
    import syllabus_reader as SR
    with open(os.path.join(os.path.dirname(__file__), "fixtures", "real_syllabus_cn.png"), "rb") as f:
        data = f.read()
    got = SR.read_syllabus([("cn.png", data)], gemma=_reader(tmp_path, FakeGemmaServer(fail=True)))
    assert got["reader"] == "tesseract" and got["syllabus"]["subjects"]
    assert "built-in reader" in got["warnings"][0]
