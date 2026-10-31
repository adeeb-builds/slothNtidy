"""Central configuration for the slothNtidy pipeline.
Every folder name and threshold lives here so it can be tuned and explained in one place."""
import os
import shutil

# ---------------------------------------------------------------- folders
INBOX_FOLDER = "./inbox"                    # drop WhatsApp exports (folders or .zip) + loose files here
OUTPUT_FOLDER = "./output"                  # everything the pipeline generates (wiped on every run)
VAULT_FOLDER = os.path.join(OUTPUT_FOLDER, "SlothVault")      # sorted, renamed copies of your notes
TOPIC_FOLDER = os.path.join(OUTPUT_FOLDER, "TopicPDFs")       # one merged exam-ready PDF per unit
WORK_FOLDER = os.path.join(OUTPUT_FOLDER, "_work")            # photos converted to PDF pages, etc.
REPORT_JSON = os.path.join(OUTPUT_FOLDER, "report.json")      # full results, read by the UI
REPORT_MD = os.path.join(OUTPUT_FOLDER, "COVERAGE.md")        # human-readable coverage dashboard
SYLLABUS_FILE = "./my_syllabus.json"     # your syllabus, made on the Syllabus page (starts empty)

# File types the pipeline reads. Photos are converted to PDF pages (pixels kept as-is).
PDF_TYPES = (".pdf",)
IMAGE_TYPES = (".jpg", ".jpeg", ".png", ".webp")
CHAT_TYPES = (".txt",)

# ---------------------------------------------------------------- reading
MAX_OCR_PAGES = 10            # a scanned PDF is OCR-read up to this many pages (enough to place it in a unit);
                              # the merged unit PDF still contains every page
PARSE_WORKERS = max(1, min(4, (os.cpu_count() or 2) - 1))   # files read at the same time
STICKER_PREFIX = "STK-"       # WhatsApp names stickers STK-<date>-WA<n>.webp - never notes
MIN_PAGE_TEXT = 30            # a PDF page with fewer characters than this is treated as a scan -> OCR
MIN_TEXT_CHARS = 60           # a document with less readable text than this is flagged "unreadable"

# ---------------------------------------------------------------- Gemma 4 (handwriting reader)
# Tesseract cannot read handwriting. When a scanned page or photo gives too little / garbled
# text, the page image is sent to Gemma 4, which writes down what is on it. See gemma.py.
GEMMA_BACKEND = "api"         # "api" = Google Gemini API (online); "local" = Ollama on this laptop
GEMMA_KEY_FILE = "./.gemini_key"         # the API key, saved on this laptop only (git-ignored)
GEMMA_API_MODEL = "gemma-4-26b-a4b-it"   # Gemma 4 on Google's Gemini API (also: gemma-4-31b-it)
GEMMA_LOCAL_MODEL = "gemma4:e4b"         # Gemma 4 on this laptop via Ollama (ollama pull gemma4:e4b)
MAX_GEMMA_PAGES = 2           # handwritten pages per document sent to Gemma (enough to place it in a unit;
                              # each page takes Gemma ~10-20 s over the internet)
GEMMA_MAX_SIDE = 1600         # page images are shrunk to at most this many pixels per side before sending
GEMMA_TIMEOUT = 60            # seconds to wait for one page
GEMMA_MAX_FAILURES = 3        # after this many failed pages in a row, Gemma switches off for the run
GEMMA_CACHE_FOLDER = "./.gemma_cache"    # Gemma's answers, kept between runs (NOT inside output/, which is wiped)

# ---------------------------------------------------------------- cleaning
DUP_TEXT_RATIO = 0.80         # text similarity (0-1) at which two documents count as the same notes
PHASH_MAX_DISTANCE = 6        # image fingerprint distance at which two scans/photos count as the same page
CIRCULAR_FILENAME_WORDS = ["circular", "notice", "fee", "timetable", "datesheet", "date_sheet", "holiday"]
CIRCULAR_PHRASES = [
    "circular", "notice", "dear students", "all students are", "informed that", "hereby",
    "fee", "fees", "last date", "principal", "registrar", "dean", "hod", "examination cell",
    "late fine", "submission deadline", "by order",
]
CIRCULAR_MIN_SIGNALS = 2      # a filename hit counts 2, each phrase hit counts 1
CIRCULAR_MAX_SYLLABUS_HITS = 2  # a document that hits 3+ syllabus subtopics is study material, not a circular

# ---------------------------------------------------------------- matching
# Subtopics are ticked off by exact keyword evidence on a page (traceable, deterministic).
# Embeddings (MiniLM) help decide WHICH unit a document belongs to and rescue notes
# whose keywords OCR could not read. If no embedding model is installed, keyword
# matching still works on its own.
EMBED_BACKEND = "auto"        # "auto" = MiniLM if installed, else Ollama if running, else keywords only
MINILM_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
OLLAMA_MODEL = "nomic-embed-text"
OLLAMA_HOST = "http://localhost:11434"
EMBED_SUGGEST = 0.45          # with no keyword hits, an embedding score above this -> "needs review" suggestion
WEIGHT_KEYWORDS = 0.6         # share of keyword evidence vs embedding similarity when ranking units


def configure_tesseract():
    """On Windows, Tesseract is usually not on PATH after installing it - point pytesseract at it."""
    try:
        import pytesseract
    except ImportError:
        return False
    if shutil.which("tesseract"):
        return True
    for candidate in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
        "/opt/homebrew/bin/tesseract",
        "/usr/local/bin/tesseract",
    ):
        if os.path.exists(candidate):
            pytesseract.pytesseract.tesseract_cmd = candidate
            return True
    return False
