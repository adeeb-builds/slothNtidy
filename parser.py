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

from config import (CHAT_TYPES, IMAGE_TYPES, MIN_PAGE_TEXT, PDF_TYPES, WORK_FOLDER,
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


def ocr_page(page) -> str:
    from PIL import Image
    pix = page.get_pixmap(dpi=200)
    return ocr_image(Image.open(io.BytesIO(pix.tobytes("png"))))


def image_to_pdf(image_path: str, work_dir: str = WORK_FOLDER) -> str:
    """Wraps a photo in a one-page PDF (the photo itself is embedded unchanged)."""
    os.makedirs(work_dir, exist_ok=True)
    out = os.path.join(work_dir, os.path.basename(image_path) + ".pdf")
    with fitz.open(image_path) as img:
        pdf_bytes = img.convert_to_pdf()
    with fitz.open("pdf", pdf_bytes) as pdf:
        pdf.save(out)
    return out


def extract_document(path: str, chat_meta: dict = None, work_dir: str = WORK_FOLDER) -> dict:
    """Reads one note (PDF or photo) and returns everything later stages need."""
    orig_name = os.path.basename(path)
    ext = os.path.splitext(orig_name)[1].lower()
    page_texts, ocr_used, kind = [], False, "pdf"

    if ext in IMAGE_TYPES:
        from PIL import Image
        kind = "photo"
        with Image.open(path) as img:
            img.load()
            text = ocr_image(img)
        page_texts = [text]
        ocr_used = bool(text)
        pdf_path = image_to_pdf(path, work_dir)
    else:
        pdf_path = path
        with fitz.open(path) as doc:
            for page in doc:
                t = page.get_text().strip()
                if len(t) < MIN_PAGE_TEXT:
                    o = ocr_page(page)
                    if o:
                        ocr_used, t = True, o
                        kind = "scan"
                page_texts.append(t)

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
        "text": body,
        "chars": len(body),
        "ocr_used": ocr_used,
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

def unzip_exports(inbox: str, log=print):
    """WhatsApp 'Export chat -> Attach media' gives a .zip. Unpack each into its own folder."""
    import zipfile
    for root, _, files in os.walk(inbox):
        for f in files:
            if f.lower().endswith(".zip"):
                zpath = os.path.join(root, f)
                target = os.path.join(root, os.path.splitext(f)[0])
                if os.path.isdir(target):
                    continue
                try:
                    with zipfile.ZipFile(zpath) as z:
                        z.extractall(target)
                    log(f"   [UNZIP] {f}")
                except zipfile.BadZipFile:
                    log(f"   [SKIP] {f}: not a valid zip")


def scan_inbox(inbox: str, log=print):
    """Finds chat exports and notes. A chat file describes the media in the same folder.
    Returns (files, chat_meta_by_folder, skipped)."""
    unzip_exports(inbox, log)
    files, skipped, meta_by_folder = [], [], {}
    for root, dirs, names in os.walk(inbox):
        dirs.sort()
        folder_meta = {}
        for n in sorted(names):
            if n.lower().endswith(CHAT_TYPES):
                folder_meta.update(parse_chat(os.path.join(root, n)))
        meta_by_folder[root] = folder_meta
        for n in sorted(names):
            low = n.lower()
            if low.endswith(PDF_TYPES + IMAGE_TYPES):
                files.append(os.path.join(root, n))
            elif not low.endswith(CHAT_TYPES + (".zip",)) and not n.startswith("."):
                skipped.append(os.path.join(root, n))
    return files, meta_by_folder, skipped
