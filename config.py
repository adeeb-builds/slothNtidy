"""Central configuration for the slothNtidy pipeline.
Every threshold lives here so it can be tuned and documented in one place."""
DOWNLOAD_FOLDER = "./Downloaded_PDFs"
VAULT_FOLDER = "./SlothVault"
TOPIC_FOLDER = "./TopicPDFs"            # topic-wise merged PDFs land here
SYLLABUS_FILE = "./sample_data/syllabus.json"
CHAT_EXPORT_FILE = "./sample_data/whatsapp_chat.txt"
EMBED_MODEL = "nomic-embed-text"        # local, via Ollama

# Cleaning thresholds
DUP_TEXT_RATIO = 0.55        # difflib similarity to call two docs near-duplicates
PHASH_MAX_DISTANCE = 4       # 0 = identical image, <=4 = same scan re-saved
CIRCULAR_KEYWORDS = [
    "circular", "notice", "timetable", "holiday",
    "fee payment", "schedule", "important instructions", "fee_circular"
]

# Matching thresholds (cosine similarity)
MATCH_COVERED = 0.55         # >= this  -> covered
MATCH_REVIEW = 0.40          # between  -> needs-review; below -> missing
MIN_TEXT_CHARS = 60          # less than this without OCR -> "unreadable", flagged