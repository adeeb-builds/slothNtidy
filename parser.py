"""Stage 1 (import) + Stage 2 (parse).

1. Reads WhatsApp chat exports (.txt) and pairs every attachment with its
   sender, timestamp, group and caption.
2. Reads each note: text from PDFs with PyMuPDF; photos and scanned pages
   are read with Tesseract OCR. Photos are also converted into PDF pages so
   they can be merged later - the original pixels are kept, never redrawn.

A file the pipeline cannot read is FLAGGED for review, never silently dropped.
"""
import io
import os
import re
from datetime import datetime

import pymupdf as fitz

from gemma import looks_unreadable

from config import (CHAT_TYPES, IMAGE_TYPES, MAX_GEMMA_PAGES, MAX_OCR_PAGES, MIN_TEXT_CHARS, MIN_PAGE_TEXT, PDF_TYPES, STICKER_PREFIX, WORK_FOLDER,
                    configure_tesseract)

# Invisible characters WhatsApp sprinkles into exports. U+200E before attachment
# names is the reason captions never paired in the first version of this parser.
_INVISIBLE = dict.fromkeys(map(ord, "‎‏‪‫‬⁨⁩﻿"), None)

# A message starts with a timestamp. Three layouts are supported:
#   Android : 21/10/26, 9:14 pm - Rohan: text
#   iPhone  : [21/10/26, 9:14:03 PM] Rohan: text
#   Short   : [21:14] Rohan: text            (the original sample file)
_MSG_START = re.compile(
    r"^\[?(?P<ts>\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s?[apAP]\.?[mM]\.?)?"
    r"|\d{1,2}:\d{2})\]?\s*(?:-\s*)?(?P<sender>[^:]{1,60}?):\s(?P<body>.*)$"
)
# Attachment markers in the message body
_ATTACH_ANDROID = re.compile(r"^(?P<name>.+?\.[A-Za-z0-9]{2,5})\s*(?:•.*?)?\((?:file attached)\)\s*(?P<rest>.*)$", re.I)
_ATTACH_IOS = re.compile(r"<attached:\s*(?P<name>[^>]+)>\s*(?P<rest>.*)$", re.I)
_ATTACH_PLAIN = re.compile(r"^(?P<name>\S+\.(?:pdf|jpe?g|png|webp|docx?|pptx?))\b\s*(?P<rest>.*)$", re.I)


def _clean_line(line: str) -> str:
    return line.translate(_INVISIBLE).replace(" ", " ").replace(" ", " ").rstrip("\r\n")


def _parse_time(ts: str):
    ts = ts.replace(".", "").strip()
    for fmt in ("%d/%m/%y, %I:%M %p", "%d/%m/%y, %I:%M:%S %p", "%d/%m/%Y, %I:%M %p",
                "%d/%m/%Y, %I:%M:%S %p", "%d/%m/%y, %H:%M", "%d/%m/%y, %H:%M:%S",
                "%d/%m/%Y, %H:%M", "%d-%m-%y, %H:%M", "%H:%M"):
        try:
            return datetime.strptime(ts.upper(), fmt)
        except ValueError:
            continue
    return None


def group_name_from_chat(path: str) -> str:
    """'WhatsApp Chat with OS_Lab_Section.txt' -> 'OS_Lab_Section'. Falls back to the folder name."""
    base = os.path.splitext(os.path.basename(path))[0]
    m = re.match(r"(?i)whatsapp chat (?:with|-)\s*(.+)", base)
    if m:
        return m.group(1).strip()
    if base.lower() in ("_chat", "chat", "whatsapp_chat"):
        return os.path.basename(os.path.dirname(path)) or base
    return base


def parse_chat(chat_txt_path: str) -> dict:
    """Returns {attachment_filename: {sender, timestamp, date, group, caption}}."""
    if not chat_txt_path or not os.path.exists(chat_txt_path):
        return {}
    group = group_name_from_chat(chat_txt_path)

    # 1. Split the file into messages (a line without a timestamp continues the previous message)
    messages = []
    with open(chat_txt_path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = _clean_line(raw)
            m = _MSG_START.match(line.strip())
            if m:
                messages.append({"ts": m.group("ts"), "sender": m.group("sender").strip(),
                                 "lines": [m.group("body").strip()]})
            elif messages and line.strip():
                messages[-1]["lines"].append(line.strip())

    # 2. Find attachments and their captions
    meta = {}
    for i, msg in enumerate(messages):
        first = msg["lines"][0]
        hit = _ATTACH_IOS.search(first) or _ATTACH_ANDROID.match(first) or _ATTACH_PLAIN.match(first)
        if not hit:
            continue
        name = hit.group("name").strip()
        caption_parts = [hit.group("rest").strip()] + msg["lines"][1:]
        caption = " ".join(p for p in caption_parts if p).strip().strip('"“”')
        # Caption sent as the very next message by the same person (common habit)
        if not caption and i + 1 < len(messages):
            nxt = messages[i + 1]
            nxt_first = nxt["lines"][0]
            is_attachment = (_ATTACH_IOS.search(nxt_first) or _ATTACH_ANDROID.match(nxt_first)
                             or _ATTACH_PLAIN.match(nxt_first))
            if nxt["sender"] == msg["sender"] and not is_attachment:
                caption = " ".join(nxt["lines"]).strip().strip('"“”')
        when = _parse_time(msg["ts"])
        meta[name] = {
            "sender": msg["sender"],
            "timestamp": msg["ts"],
            "date": when.strftime("%d %b") if when and when.year > 1900 else "",
            "group": group,
            "caption": caption,
        }
    return meta


def parse_whatsapp_captions(chat_txt_path: str) -> dict:
    """Backwards-compatible name used by the original pipeline and tests."""
    return parse_chat(chat_txt_path)


# ---------------------------------------------------------------- reading documents

def ocr_image(img) -> str:
    """OCR a PIL image. Returns '' if Tesseract is not installed."""
    try:
        import pytesseract
        from PIL import ImageOps
        if not configure_tesseract():
            return ""
        gray = ImageOps.autocontrast(img.convert("L"))
        return pytesseract.image_to_string(gray).strip()
    except Exception:
        return ""


def open_image(path: str):
    """Opens any photo Pillow understands (jpg, png, webp, animated webp/GIF: first frame) as RGB."""
    from PIL import Image, ImageOps
    with Image.open(path) as img:
        img.seek(0)
        img = ImageOps.exif_transpose(img)
        return img.convert("RGB")


def ocr_page(page) -> str:
    from PIL import Image
    pix = page.get_pixmap(dpi=200)
    return ocr_image(Image.open(io.BytesIO(pix.tobytes("png"))))


def image_to_pdf(image_path: str, work_dir: str = WORK_FOLDER) -> str:
    """Wraps a photo in a one-page PDF (the photo itself is embedded unchanged)."""
    os.makedirs(work_dir, exist_ok=True)
    out = os.path.join(work_dir, os.path.basename(image_path) + ".pdf")
    try:
        with fitz.open(image_path) as img:
            pdf_bytes = img.convert_to_pdf()
    except Exception:  # formats MuPDF cannot open (e.g. webp): convert the first frame with Pillow
        buf = io.BytesIO()
        open_image(image_path).save(buf, format="PNG")
        with fitz.open("png", buf.getvalue()) as img:
            pdf_bytes = img.convert_to_pdf()
    with fitz.open("pdf", pdf_bytes) as pdf:
        pdf.save(out)
    return out


def page_image(page, dpi: int = 200):
    from PIL import Image
    pix = page.get_pixmap(dpi=dpi)
    return Image.open(io.BytesIO(pix.tobytes("png")))


def _maybe_gemma(img, tess_text: str, gemma, budget: list):
    """Ask Gemma 4 to read the page when Tesseract's text looks like handwriting it could not read.
    Returns (text, reader). budget is a one-item list: pages this document may still send to Gemma."""
    if gemma is None or budget[0] <= 0 or not looks_unreadable(tess_text, MIN_TEXT_CHARS):
        return tess_text, ("tesseract" if tess_text else "none")
    budget[0] -= 1
    g = gemma.read_page(img)
    if g and len(g) > len(tess_text):
        return g, "gemma"
    return tess_text, ("tesseract" if tess_text else "none")


def extract_document(path: str, chat_meta: dict = None, work_dir: str = WORK_FOLDER, gemma=None) -> dict:
    """Reads one note (PDF or photo) and returns everything later stages need.
    gemma: an optional gemma.GemmaReader - reads handwritten pages Tesseract cannot."""
    orig_name = os.path.basename(path)
    ext = os.path.splitext(orig_name)[1].lower()
    page_texts, page_readers, ocr_used, kind = [], [], False, "pdf"
    budget = [MAX_GEMMA_PAGES]

    ocr_capped = 0
    if ext in IMAGE_TYPES:
        kind = "photo"
        img = open_image(path)
        text, reader = _maybe_gemma(img, ocr_image(img), gemma, budget)
        page_texts, page_readers = [text], [reader]
        ocr_used = bool(text)
        pdf_path = image_to_pdf(path, work_dir)
    else:
        pdf_path = path
        with fitz.open(path) as doc:
            ocr_pages = 0
            for page in doc:
                t = page.get_text().strip()
                reader = "pdf"
                if len(t) < MIN_PAGE_TEXT and ocr_pages >= MAX_OCR_PAGES:
                    ocr_capped += 1          # long scanned PDF: the first pages are enough to place it
                    reader = "none"
                elif len(t) < MIN_PAGE_TEXT:
                    ocr_pages += 1
                    img = page_image(page)
                    o, reader = _maybe_gemma(img, ocr_image(img), gemma, budget)
                    if o:
                        ocr_used, t = True, o
                        kind = "scan"
                page_texts.append(t)
                page_readers.append(reader)

    info = (chat_meta or {}).get(orig_name, {})
    caption = info.get("caption", "")
    body = "\n".join(page_texts).strip()
    return {
        "path": path,               # the original file, never modified
        "pdf_path": pdf_path,       # PDF used for merging (same as path for PDFs)
        "orig_name": orig_name,
        "kind": kind,               # pdf | scan | photo
        "pages": len(page_texts),
        "page_texts": page_texts,
        "page_readers": page_readers,   # per page: pdf | tesseract | gemma | none
        "gemma_pages": page_readers.count("gemma"),
        "text": body,
        "chars": len(body),
        "ocr_used": ocr_used,
        "ocr_capped": ocr_capped,   # scanned pages not OCR-read (beyond MAX_OCR_PAGES)
        "sender": info.get("sender", ""),
        "timestamp": info.get("timestamp", ""),
        "date": info.get("date", ""),
        "group": info.get("group", ""),
        "caption": caption,
    }


def extract_pdf(path: str, chat_meta: dict = None) -> dict:
    """Backwards-compatible name used by the original tests."""
    return extract_document(path, chat_meta)


# ---------------------------------------------------------------- scanning the inbox

def unzip_exports(inbox: str, log=print, skip=()):
    """WhatsApp 'Export chat -> Attach media' gives a .zip. Unpack each into its own folder."""
    import zipfile
    for root, _, files in os.walk(inbox):
        for f in files:
            if f.lower().endswith(".zip"):
                zpath = os.path.join(root, f)
                target = os.path.join(root, os.path.splitext(f)[0])
                if os.path.isdir(target) or target in skip:
                    continue
                try:
                    with zipfile.ZipFile(zpath) as z:
                        z.extractall(target)
                    log(f"   [UNZIP] {f}")
                except zipfile.BadZipFile:
                    log(f"   [SKIP] {f}: not a valid zip")


_HASHES = {}


def file_hash(path: str) -> str:
    """SHA-256 of a file, remembered per (path, size, modified time) so big zips are hashed once."""
    import hashlib
    st = os.stat(path)
    key = (os.path.abspath(path), st.st_size, st.st_mtime)
    if key in _HASHES:
        return _HASHES[key]
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    _HASHES[key] = h.hexdigest()
    return _HASHES[key]


def duplicate_export_folders(inbox: str, log=print) -> set:
    """The same WhatsApp .zip added twice: read only the first copy (folders of later copies are ignored)."""
    seen, ignore = {}, set()
    zips = sorted(os.path.join(r, f) for r, _, fs in os.walk(inbox) for f in fs if f.lower().endswith(".zip"))
    for z in zips:
        key = (os.path.getsize(z), file_hash(z))
        if key in seen:
            ignore.add(os.path.splitext(z)[0])
            log(f"   [SKIP] {os.path.basename(z)}: same export as one already in the inbox")
        else:
            seen[key] = z
    return ignore


def scan_inbox(inbox: str, log=print):
    """Finds chat exports and notes. A chat file describes the media in the same folder.
    Returns (files, chat_meta_by_folder, skipped)."""
    ignore = duplicate_export_folders(inbox, log)
    unzip_exports(inbox, log, skip=ignore)
    files, skipped, meta_by_folder = [], [], {}
    for root, dirs, names in os.walk(inbox):
        dirs.sort()
        dirs[:] = [d for d in dirs if os.path.join(root, d) not in ignore]
        folder_meta = {}
        for n in sorted(names):
            if n.lower().endswith(CHAT_TYPES):
                folder_meta.update(parse_chat(os.path.join(root, n)))
        meta_by_folder[root] = folder_meta
        for n in sorted(names):
            low = n.lower()
            if n.startswith(STICKER_PREFIX) and low.endswith(IMAGE_TYPES):
                skipped.append(os.path.join(root, n))      # WhatsApp sticker, never a note
            elif low.endswith(PDF_TYPES + IMAGE_TYPES):
                files.append(os.path.join(root, n))
            elif not low.endswith(CHAT_TYPES + (".zip",)) and not n.startswith("."):
                skipped.append(os.path.join(root, n))
    return files, meta_by_folder, skipped
