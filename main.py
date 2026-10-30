"""slothNtidy from the command line (the UI is app.py).

    python main.py            # sort whatever is in ./inbox
"""
import argparse

from config import INBOX_FOLDER, SYLLABUS_FILE
from embedder import load_embedder
from pipeline import run


def main():
    ap = argparse.ArgumentParser(description="Sort WhatsApp study notes by syllabus.")
    ap.add_argument("--inbox", default=None, help=f"folder to sort (default {INBOX_FOLDER})")
    ap.add_argument("--syllabus", default=SYLLABUS_FILE)
    ap.add_argument("--no-ai", action="store_true", help="keyword evidence only, skip the embedding model")
    args = ap.parse_args()

    inbox = args.inbox or INBOX_FOLDER
    print("slothNtidy - loading the local matching engine...")
    embedder = None if args.no_ai else load_embedder()
    try:
        r = run(inbox, args.syllabus, embedder)
    except FileNotFoundError as e:
        print(f"\n{e}\nDrop WhatsApp exports or PDFs into that folder and run again.")
        return
    c = r["counts"]
    print(f"\n{c['total']} files in -> {c['circulars']} circulars, {c['exact_dups'] + c['near_dups']} "
          f"duplicates removed -> {c['kept']} notes kept")
    for u in r["units"]:
        print(f"  {u['status']:<13} {u['subject_code']} U{u['unit']} {u['title']}"
              + (f"  (missing: {', '.join(u['missing'])})" if u["missing"] else ""))
    print("\nOpen output/SlothVault for your sorted notes and output/TopicPDFs for merged PDFs.")


if __name__ == "__main__":
    main()
