"""slothNtidy pipeline: import -> parse -> clean -> match -> report -> export.
Drop PDFs into ./Downloaded_PDFs, then run:  python main.py"""
import os
from config import DOWNLOAD_FOLDER, CHAT_EXPORT_FILE
from parser import extract_pdf, parse_whatsapp_captions
from filters import clean
from syllabus import load_syllabus
from matcher import match
from report import build_report
from exporter import export_topics
from engine import SlothEngine

def main():
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    files = [os.path.join(DOWNLOAD_FOLDER, f) for f in sorted(os.listdir(DOWNLOAD_FOLDER))
             if f.lower().endswith(".pdf")]
    if not files:
        print(f"slothNtidy: no PDFs in {DOWNLOAD_FOLDER}. Drop files there and rerun.")
        return

    chat_meta = parse_whatsapp_captions(CHAT_EXPORT_FILE) if os.path.exists(CHAT_EXPORT_FILE) else {}

    print(f"\n[STAGE 1-2] IMPORT + PARSE: reading {len(files)} PDF(s)...")
    docs = [extract_pdf(f, chat_meta) for f in files]

    print("\n[STAGE 3] CLEAN: circulars, duplicates, noise...")
    kept, counts = clean(docs)
    print(f"   Summary: {counts['total']} in -> {counts['kept']} kept "
          f"({counts['circulars']} circulars, {counts['exact_dups']} exact dups, "
          f"{counts['near_dups']} near-dups removed, {counts['unreadable']} flagged)")

    print("\n[STAGE 4] MATCH: mapping to syllabus topics (local embeddings)...")
    results = match(kept, load_syllabus(), SlothEngine())

    print("\n[STAGE 5] REPORT: building coverage dashboard...")
    build_report(results, load_syllabus())

    print("\n[STAGE 6] EXPORT: topic-wise merged PDFs...")
    export_topics(results)
    print("\nDone. Open SlothVault/COVERAGE.md and the TopicPDFs/ folder.")

if __name__ == "__main__":
    main()