"""Reads a college syllabus from a photo, PDF or Word file and turns it into the
syllabus table (subjects -> units -> subtopics) so the student does not have to type it.

How it works (no cloud, no large AI model):
  1. READ   - photos are read with Tesseract OCR (row by row, so tables keep their rows),
              PDFs with PyMuPDF (OCR only for scanned pages), .docx files from their XML.
  2. FIND   - subject names come from lines like "Course Title: ..." / "Subject: ...".
              Units start at "UNIT - I", "Unit 2", "Module III", a row that begins with a
              roman numeral, or (in tables where OCR lost the numeral) a short bold-style
              title followed by a colon, e.g. "Introduction: Data, Database, ...".
  3. SPLIT  - the topic text of each unit is split into subtopics at commas, semicolons
              and colons. Lecture hours, book lists and course outcomes are left out.
The result is only a DRAFT: the app shows it in the editable table and the student
checks it before pressing Save. Nothing is saved automatically.
"""
import io
import os
import re
import zipfile
from xml.etree import ElementTree

import pymupdf as fitz

from config import IMAGE_TYPES, MIN_PAGE_TEXT, configure_tesseract

SYLLABUS_TYPES = ("png", "jpg", "jpeg", "webp", "pdf", "docx")

# ------------------------------------------------------------------ 1. READ

def _ocr(img, psm: int) -> str:
    import pytesseract
    return pytesseract.image_to_string(img, config=f"--psm {psm}")


def _prepare(img):
    """Phone photos: apply the camera's rotation flag, grey + contrast, enlarge small images."""
    from PIL import ImageOps
    img = ImageOps.exif_transpose(img)
    img = ImageOps.autocontrast(img.convert("L"))
    if img.width < 1600:
        scale = 1600 / img.width
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    return img


SMALL_IMAGE_WIDTH = 1000   # below this, letters are often misread (e.g. "Intemet" for "Internet")


def _read_image(img) -> list:
    """Returns candidate texts, best reading mode first. psm 6 reads a page row by row
    (keeps table rows together); psm 4 is a fallback for unusual layouts."""
    if not configure_tesseract():
        raise RuntimeError("Tesseract (the photo reader) is not installed. Run setup again, "
                           "or upload the syllabus as a PDF / Word file instead.")
    img = _prepare(img)
    return [_ocr(img, 6), _ocr(img, 4)]


def _read_docx(data: bytes) -> str:
    """Word files: every paragraph (including table cells, in row order) becomes one line."""
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ElementTree.fromstring(z.read("word/document.xml"))
    lines = []
    for p in root.iter(ns + "p"):
        text = "".join(t.text or "" for t in p.iter(ns + "t")).strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def _read_pdf(data: bytes) -> list:
    texts, scanned = [], []
    with fitz.open(stream=data, filetype="pdf") as doc:
        for page in doc:
            t = page.get_text().strip()
            if len(t) >= MIN_PAGE_TEXT:
                texts.append(t)
            else:  # a scanned page: OCR it
                from PIL import Image
                img = Image.open(io.BytesIO(page.get_pixmap(dpi=250).tobytes("png")))
                scanned.append(_read_image(img)[0])
                texts.append(scanned[-1])
    return ["\n".join(texts)]


def image_width(name: str, data: bytes):
    if os.path.splitext(name)[1].lower() not in IMAGE_TYPES:
        return None
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(data)) as img:
        return ImageOps.exif_transpose(img).width


def read_file(name: str, data: bytes) -> list:
    """Returns a list of candidate texts for one uploaded file (best guess first)."""
    ext = os.path.splitext(name)[1].lower()
    if ext == ".docx":
        return [_read_docx(data)]
    if ext == ".pdf":
        return _read_pdf(data)
    if ext in IMAGE_TYPES:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            return _read_image(img)
    raise ValueError(f"{name}: upload a photo (jpg/png), a PDF or a Word (.docx) file.")


# ------------------------------------------------------------------ 2. FIND

ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
         "xi": 11, "xii": 12}
DASH = r"[\s\-–—:.|$§#*'\"]*"           # OCR noise between UNIT and its number, e.g. "Unit $5"
NUM = r"([ivxl|]{1,4}|\d{1,2})"   # OCR often reads I as l or |
UNIT_WORD = re.compile(rf"^\W*(?:unit|module|block)\b{DASH}{NUM}\b(.*)$", re.I)
ROW_NUMERAL = re.compile(rf"^\W*{NUM}\s*[|.)]?\s+(.+)$", re.I)        # table row: "IV Normalization: ..."
BARE_NUMERAL = re.compile(rf"^\W*{NUM}\W*$", re.I)                      # Word table cell: "III"
COLON_TITLE = re.compile(r"^\W*([A-Z][A-Za-z&/,'()\- ]{1,48}?)\s*[:–—]\s+(\S.*)$")
SUBJECT_LINE = re.compile(r"(?:course|subject|paper)\s*(?:title|name)?\s*[:\-–]\s*(.+)", re.I)
FIELD_END = re.compile(r"\s{2,}|\s+(?:course|subject|paper)\s*code\b|\s+l\s*-?\s*t\s*-?\s*p\b|\s+max\.?\s*marks"
                       r"|\s+credits?\b|\s+semester\b|\s+code\s*[:\-]|\s+marks\b", re.I)
STOP = re.compile(r"^\W*(?:text\s*books?|reference\s*books?|references|suggested\s+(?:readings?|books)"
                  r"|books?\s+recommended|recommended\s+books|course\s+outcomes?|co\s*\d|learning\s+outcomes?"
                  r"|course\s+objectives?|objectives?\s*:|note\s*:|list\s+of\s+(?:experiments|practicals)"
                  r"|e-?resources|web\s+links)", re.I)
HOURS = re.compile(r"[\[(]?\s*\d{1,2}\s*(?:hours?|hrs?\.?|lectures?|l|periods?)\s*[\])]?\.?\s*$"
                   r"|[\[(]\s*\d{1,2}\s*[\])]\s*$|(?<=[.\s])\d{1,2}\s*$", re.I)
PAGE_HEADER = re.compile(r"\b(?:university|vishwavidyalaya|institute of|college of|semester|b\.?\s?tech|m\.?\s?tech|"
                         r"b\.?\s?sc|m\.?\s?sc|bca|mca|b\.?\s?com|scheme of|syllabus for|evaluation scheme|"
                         r"page\s+\d|effective from|session\s*20\d\d|academic year)\b", re.I)
JUNK_NUMERAL = re.compile(r"^[ivxl|1]{1,4}[\s.)|]+(?=[A-Z])", re.I)
GENERIC = {"introduction", "overview", "basics", "basic concepts", "summary", "conclusion", "review",
           "revision", "applications", "examples", "case study", "case studies"}
NOT_A_TITLE = re.compile(r"^\W*(?:unit|units|topics?|contents?|hours?|hrs|lectures?|s\.?\s?no|sr\.?\s?no|syllabus|"
                         r"course\s+code|subject\s+code|paper\s+code|max|marks|credits?|l\s*-?\s*t\s*-?\s*p|"
                         r"proposed|no\.? of)\b", re.I)
HEADER_ROW = re.compile(r"^\W*[A-Z]{2,5}[\s\-]?\d{3,4}[A-Z]?\W+([A-Za-z][A-Za-z&,'()\- ]{3,60}?)\W+"
                        r"(?:\d\s*L\b|\d\s*-\s*\d\s*-\s*\d|\d+\s*credits?)", re.I)
SMALL = {"and", "of", "the", "&", "to", "in", "for", "with", "on", "a", "an"}


def _looks_like_title(line: str) -> bool:
    words = re.findall(r"[A-Za-z][A-Za-z&'-]*", line)
    return (2 <= len(words) <= 7 and "," not in line and ":" not in line and not NOT_A_TITLE.match(line)
            and not re.search(r"\d", line) and len(line) <= 70
            and line.lstrip(" |_-")[:1].isupper()          # a heading starts with a capital letter...
            and not line.rstrip().endswith((".", ";")))    # ...and is not the end of a sentence


def _title_case(line: str) -> str:
    line = re.sub(r"\s+", " ", line).strip(" .:-–|*")
    if line.isupper():   # "COMPUTER NETWORKS" -> "Computer Networks"
        line = " ".join(w if w.lower() in SMALL else w.capitalize() for w in line.lower().split())
        line = line[0].upper() + line[1:]
    return line


def _num(token: str):
    t = token.lower().replace("l", "i").replace("|", "i")
    if t.isdigit():
        return int(t)
    return ROMAN.get(t)


def _strip_hours(line: str) -> str:
    return HOURS.sub("", line).strip(" |")


def _subject_code(name: str) -> str:
    name = re.sub(r"\bdatabase", "Data Base", name, flags=re.I)   # Database Management System -> DBMS
    words = [w for w in re.findall(r"[A-Za-z]+", name) if w.lower() not in SMALL]
    if len(words) == 1:
        return words[0][:4].upper()
    return "".join(w[0] for w in words).upper()[:6] or "SUBJ"


def _clean_subject_name(raw: str) -> str:
    name = FIELD_END.split(raw.strip())[0]
    return re.sub(r"\s+", " ", name).strip(" :-–|,.")


class _Builder:
    def __init__(self):
        self.subjects = []
        self.unit = None          # the unit currently receiving topic text
        self.stopped = False      # inside "Text Books", "Course Outcomes", ...
        self.candidate = ""       # a short heading seen before the first unit, e.g. "COMPUTER NETWORKS"

    # subjects
    def subject(self, name: str):
        cur = self.subjects[-1] if self.subjects else None
        if cur and not cur["units"]:  # a header with no units yet: just rename it
            cur["name"] = name
        else:
            self.subjects.append({"name": name, "units": []})
        self.unit, self.stopped = None, False

    def _units(self):
        if not self.subjects:
            self.subjects.append({"name": "", "units": []})
        return self.subjects[-1]["units"]

    def last_no(self):
        u = self._units()
        return u[-1]["unit"] if u else 0

    # units
    def start_unit(self, number, title="", body=""):
        title = JUNK_NUMERAL.sub("", title.strip())   # "Vv Dynamic Programming": a misread IV in front
        if number is None:
            number = self.last_no() + 1
        if number == 1 and self.last_no() >= 2:   # numbering restarted: a new subject without a header
            self.subjects.append({"name": "", "units": []})
        units = self._units()
        if not units and not self.subjects[-1]["name"] and self.candidate:
            self.subjects[-1]["name"] = self.candidate          # no "Course Title:" line: use the heading
        self.candidate = ""
        self.unit = {"unit": number, "title": title.strip(" :-–|"), "body": []}
        self._units().append(self.unit)
        self.stopped = False
        if body:
            self.add(body)

    def add(self, text: str):
        if self.unit is not None and not self.stopped and text:
            self.unit["body"].append(text)

    def last_line_ended(self) -> bool:
        """True when the previous topic text finished a sentence (a new table row can start)."""
        if self.unit is None or not self.unit["body"]:
            return True
        return self.unit["body"][-1].rstrip().endswith((".", ")", "]"))


def _unit_from_rest(b: _Builder, number, rest: str):
    rest = _strip_hours(rest.lstrip(" :-–—.|"))
    m = re.match(r"^([^:,;]{2,60}?)\s*[:–—]\s*(.*)$", rest)
    if m:
        b.start_unit(number, m.group(1), m.group(2))
    elif rest and "," not in rest and len(rest.split()) <= 8:
        b.start_unit(number, rest)                   # "UNIT 2  Deadlocks" -> title only
    else:
        b.start_unit(number, "", rest)              # title is filled in later from the topics


def parse_text(text: str) -> dict:
    """Turns syllabus text into {"subjects": [{name, units: [{unit, title, body}]}]} (body = raw text)."""
    text = re.sub(r"(\w)-\n([a-z])", r"\1\2", text)        # "manage-\nment" -> "management"
    text = re.sub(r"(\w)-\n([A-Z])", r"\1-\2", text)       # "Packet-\nSwitched" keeps its hyphen
    # a UNIT heading that OCR glued onto the end of the previous line starts its own line
    text = re.sub(r"(?<=[.;,)\]])[ \t]+(?=(?:UNIT|Unit|MODULE|Module)\b[\s\-–—:.|$§#*]*(?:[IVXivxl|]{1,4}|\d{1,2})\b)",
                  "\n", text)
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.splitlines()]
    # Decide per subject section whether units are marked with the word UNIT (a photo of one
    # subject may be a table while the next subject's page uses "Unit-1" headings).
    has_unit_words, section, flags = [], [], []
    for l in lines:
        if SUBJECT_LINE.search(l) and not UNIT_WORD.match(l) and section:
            flags.extend([any(UNIT_WORD.match(x) for x in section)] * len(section))
            section = []
        section.append(l)
    flags.extend([any(UNIT_WORD.match(x) for x in section)] * len(section))
    b = _Builder()
    for line, has_unit_words in zip(lines, flags):
        if len(line) < 2 and not BARE_NUMERAL.match(line):
            continue
        sm = SUBJECT_LINE.search(line)
        if sm and not UNIT_WORD.match(line):
            name = _clean_subject_name(sm.group(1))
            if len(name) >= 3 and not re.match(r"^(?:code|outcomes?|objectives?)\b", name, re.I):
                b.subject(name)
                continue
        if PAGE_HEADER.search(line) and line.count(",") < 2 and not UNIT_WORD.match(line):
            continue                # "B.Tech CSE Semester IV", "Page 2 of 5": page headers, not topics
        if STOP.match(line):
            b.stopped = True
            continue
        if (b.unit is None or b.stopped) and not b.candidate and not UNIT_WORD.match(line):
            # the first heading-like line wins; in a header row "PC303 | Computer Networks | 3L:0T:0P"
            # each cell is tried on its own
            cells = [c for c in re.split(r"\s*[|\[\]]\s*", line) if c.strip()] if line.count("|") >= 2 else [line]
            hm = HEADER_ROW.match(line)      # "PC303 Computer Networks 3L:0T:0P 3 Credits" (no table lines)
            if hm:
                cells = [hm.group(1)] + cells
            for cell in cells:
                cell = cell.strip(" _—–-.")
                if _looks_like_title(cell):
                    b.candidate = _title_case(cell)
                    break
        m = UNIT_WORD.match(line)
        if m:
            _unit_from_rest(b, _num(m.group(1)), m.group(2))
            continue
        if has_unit_words:          # this syllabus marks units with the word UNIT: everything else is topic text
            if b.unit is not None and not b.stopped and not b.unit["body"] and not b.unit["title"] \
                    and "," not in line and len(line.split()) <= 8:
                b.unit["title"] = _strip_hours(line).strip(" :-–|")   # "UNIT-III" then "Deadlocks" below it
            else:
                b.add(_strip_hours(line))
            continue
        if b.stopped:               # book lists and outcomes: only a UNIT heading or a new subject ends them
            continue
        # Tables: "IV Normalization: ...", "III" on its own (Word), or "SQL: DDL, DML, ..." (OCR lost the numeral)
        bm = BARE_NUMERAL.match(line)
        if bm:
            n = _num(bm.group(1))
            if n is not None and n == b.last_no() + 1:
                b.start_unit(n)
            continue                # other lone numbers are lecture hours
        rm = ROW_NUMERAL.match(line)
        if rm and _num(rm.group(1)) is not None:
            n, rest = _num(rm.group(1)), rm.group(2)
            if b.unit is not None and n == b.unit["unit"] and not b.stopped:
                b.add(_strip_hours(rest))          # numeral printed in the middle of its own row
                continue
            if n == b.last_no() + 1 or (n == 1 and b.last_no() >= 2):
                _unit_from_rest(b, n, rest)
                continue
        fresh = b.unit is not None and not b.stopped and not b.unit["body"] and not b.unit["title"]
        cm = COLON_TITLE.match(line)
        if cm and len(cm.group(1).split()) <= 6:
            if fresh:                               # "III" in one cell, "SQL: DDL, ..." in the next
                b.unit["title"] = cm.group(1).strip()
                b.add(_strip_hours(cm.group(2)))
                continue
            if b.unit is None or b.stopped or b.last_line_ended():
                _unit_from_rest(b, None, line)      # a new table row whose numeral OCR could not read
                continue
        b.add(_strip_hours(line))
    return {"subjects": [s for s in b.subjects if s["units"]]}


# ------------------------------------------------------------------ 3. SPLIT

def _split_top(text: str, seps: str) -> list:
    """Split at separator characters that are not inside brackets."""
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if ch in seps and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def _tidy(item: str) -> str:
    item = re.sub(r"\s+", " ", item).strip(" .,;:-–—|•*\"'‘’“”")
    item = re.sub(r"^(?:and|&|etc)\s+", "", item, flags=re.I)
    item = re.sub(r"\s+(?:etc)\.?$", "", item, flags=re.I)
    return item.strip(" .,;:-–—|")


def split_subtopics(body: str) -> list:
    items, seen = [], set()
    for part in _split_top(body, ",;:"):
        # "LRU and FIFO" -> two subtopics; "Error Detection and Correction Techniques" stays one
        part = re.sub(r"^(\s*[A-Z][\w/+-]*)\s+(?:and|&)\s+([A-Z][\w/+-]*\s*)$", r"\1, \2", part)
        for sub in _split_top(part, ","):
            sub = _tidy(sub)
            if len(sub) < 2 or sub.isdigit() or not re.search(r"[A-Za-z]", sub):
                continue
            if sub.lower() in GENERIC:      # "Introduction" alone would be ticked by almost every note
                continue
            key = sub.lower()
            if key not in seen:
                seen.add(key)
                items.append(sub)
    return items


def keywords_for(name: str) -> list:
    """'Shortest Job First (SJF)' -> ['shortest job first', 'sjf']. Plain names need no keywords."""
    m = re.match(r"^(.*?)\s*\(([^)]{2,20})\)\s*$", name)
    if not m:
        return []
    full, short = m.group(1).strip(), m.group(2).strip()
    if "," in short or len(short.split()) > 3:   # "(Big O, Omega, Theta)" is a list, not a short form
        return []
    return [k for k in (full.lower(), short.lower()) if k]


def to_syllabus(parsed: dict) -> dict:
    """Parsed text -> the app's syllabus format, with subtopics split and codes filled in."""
    subjects, used_codes = [], set()
    for i, s in enumerate(parsed["subjects"], 1):
        name = s["name"] or f"Subject {i}"
        code = _subject_code(s["name"]) if s["name"] else f"SUB{i}"
        base, k = code, 2
        while code in used_codes:
            code, k = f"{base}{k}", k + 1
        used_codes.add(code)
        units, seen_units = [], set()
        for u in s["units"]:
            subs = split_subtopics(" ".join(u["body"]))
            title = u["title"] or (subs[0] if subs else f"Unit {u['unit']}")
            if not subs:
                subs = [title]
            n = u["unit"]
            while n in seen_units:   # never two "Unit 3"s in one subject
                n += 1
            seen_units.add(n)
            units.append({"unit": n, "title": title,
                          "subtopics": [{"name": t, "keywords": keywords_for(t)} for t in subs]})
        subjects.append({"code": code, "name": name, "units": units})
    return {"subjects": subjects}


def _score(syl: dict) -> int:
    """Units found. On a tie the first reading (row by row, the most faithful) is kept."""
    return sum(len(s["units"]) for s in syl["subjects"])


def read_syllabus(files) -> dict:
    """files: list of (name, bytes) in page order. Returns
    {"syllabus": {...}, "text": raw text read, "warnings": [...]}"""
    texts, warnings = [], []
    for name, data in files:
        w = image_width(name, data)
        if w is not None and w < SMALL_IMAGE_WIDTH:
            warnings.append(f"{name} is a small image ({w} pixels wide), so some letters may be misread "
                            "(e.g. 'Intemet' for 'Internet'). For an exact copy, upload your syllabus PDF or "
                            "Word file instead, or a full-size phone photo - not a screenshot of it.")
        candidates = read_file(name, data)
        # Several readings of a photo, most faithful first. Keep the first one unless a later
        # reading finds clearly more units (2+), e.g. on an unusual two-column layout.
        scores = [_score(to_syllabus(parse_text(t))) for t in candidates]
        best = next(t for t, sc in zip(candidates, scores) if sc >= max(scores) - 1)
        texts.append(best)
        if not best.strip():
            warnings.append(f"No text could be read from {name}. Is the photo sharp and well lit?")
    text = "\n".join(texts)
    syl = to_syllabus(parse_text(text))
    if not syl["subjects"]:
        warnings.append("No units were found. The page should contain headings like 'UNIT I' or a "
                        "Unit / Topic table. You can still type the syllabus into the table.")
    for s in syl["subjects"]:
        if s["name"].startswith("Subject "):
            warnings.append(f"The subject name was not found for '{s['name']}' - please type it in the table.")
    return {"syllabus": syl, "text": text, "warnings": warnings}
