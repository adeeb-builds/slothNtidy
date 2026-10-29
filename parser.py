"""Stage 1 (import) + Stage 2 (parse): read WhatsApp .txt exports to pair
attachments with captions, and extract PDF text with PyMuPDF; if a page looks
scanned, fall back to OCR. A file the pipeline cannot read is FLAGGED for
review - never silently dropped."""
import os
import io
import re
import pymupdf as fitz

CHAT_LINE_RE = re.compile(r"^\[?(\d{1,2}:\d{2}(?:[^\]]*)?)\]?\s*([^:]+):\s*(.+)$")

def parse_whatsapp_captions(chat_txt_path: str) -> dict:
    """Pairs attachment filenames in a WhatsApp .txt export with their caption."""
    if not chat_txt_path or not os.path.exists(chat_txt_path):
        return {}
    meta = {}
    last_file = None
    with open(chat_txt_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            m = CHAT_LINE_RE.match(line)
            if not m:
                continue
            ts, sender, body = m.group(1), m.group(2).strip(), m.group(3).strip()
            if ".pdf" in body.lower():
                fname = body.split()[0].strip()
                meta[fname] = {"timestamp": ts, "sender": sender, "caption": ""}
                last_file = fname
            elif last_file and meta[last_file]["sender"] == sender and not meta[last_file]["caption"]:
                meta[last_file]["caption"] = body.strip('"')
                last_file = None
    return meta

def ocr_page(page) -> str:
    try:
        import pytesseract
        from PIL import Image
        pix = page.get_pixmap(dpi=200)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        return pytesseract.image_to_string(img).strip()
    except Exception:
        return ""

def extract_pdf(path: str, chat_meta: dict = None) -> dict:
    doc = fitz.open(path)
    text, ocr_used = "", False
    for page in doc:
        t = page.get_text().strip()
        if len(t) > 30:
            text += t + "\n"
        else:
            t = ocr_page(page)
            if t:
                ocr_used = True
                text += t + "\n"
    pages = len(doc)
    doc.close()

    orig_name = os.path.basename(path)
    info = (chat_meta or {}).get(orig_name, {})
    caption = info.get("caption", "")
    combined_text = f"{caption}\n{text}".strip() if caption else text.strip()

    return {
        "path": path,
        "orig_name": orig_name,
        "pages": pages,
        "text": combined_text,
        "chars": len(combined_text),
        "ocr_used": ocr_used,
        "sender": info.get("sender", ""),
        "timestamp": info.get("timestamp", ""),
        "caption": caption,
    }