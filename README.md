# slothNtidy — Notes Sorter

**From WhatsApp chaos to syllabus-mapped exam notes — sorted by unit, de-duplicated, and traced back to the original page.**
100% local: no cloud, no API keys, works offline.

*Team CodeCrafters · Hacktoberfest [26] // Hack Day Dehradun × BFIT Dehradun*

![Coverage dashboard](docs/screenshots/coverage-dashboard.png)

---

## The problem

Before every internal exam, notes arrive across 4–5 WhatsApp groups: teachers' PDFs, friends' re-shares, photos of handwritten pages, fee circulars and memes, all with names like `DOC-2026-WA0041.pdf`. We timed one run: gathering a single OS unit's notes took **~45 minutes** of scrolling, renaming and re-downloading — before studying even started. Worse, you only find the missing topic at 2 AM.

## What slothNtidy does

You enter your syllabus once, drop in the WhatsApp exports, and press **Sort my notes**:

| Stage | What happens |
|---|---|
| 01 Import | Finds chat exports (`.zip` or `.txt`), PDFs and photos — any number of groups |
| 02 Parse | Pairs every file with its **sender, time, group and caption**; reads text with PyMuPDF, photos and scans with **Tesseract OCR** |
| 03 Clean | Drops circulars & notices, exact copies (**SHA-256**) and near-copies (text similarity + **pHash** for re-photographed pages) — keeping the *fuller* copy |
| 04 Match | Maps each note to a syllabus unit and ticks off subtopics **with the page they were found on** |
| 05 File | Copies everything into `output/SlothVault/<Subject>/<Unit>/` with clean names like `OS_U2_Deadlocks_Rohan_21Oct.pdf` |
| 06 Export | One exam-ready PDF per unit: a coverage cover page + the **original pages, unchanged** |
| 07 Report | The coverage dashboard: every unit **READY**, **NEEDS REVIEW** or **MISSING** |

Nothing is ever deleted: removed files are copied to `_Removed/`, and you can bring any of them back from the app.

| Cluster inspector | Review & duplicates |
|---|---|
| ![Cluster inspector](docs/screenshots/cluster-inspector.png) | ![Review](docs/screenshots/review-duplicates.png) |

---

## Quick start

### Windows (tested target: ThinkPad, 16 GB RAM, no GPU needed)
1. Download this repo: green **Code** button → **Download ZIP** → right-click the zip → **Extract All**.
2. Open the extracted folder and double-click **`setup.bat`** (one time, needs internet, 5–10 minutes).
   It installs Python libraries, downloads the MiniLM model (~90 MB) and Tesseract OCR, then runs the self-check.
3. Double-click **`run.bat`**. The app opens in your browser at `http://localhost:8501`.

### Mac / Linux
```bash
./setup.sh      # one time
./run.sh        # every time
```

### Command line (no UI)
```bash
python main.py --demo      # sort the built-in demo groups
python main.py             # sort whatever is in ./inbox
```

---

## Try the demo (built in)

`sample_data/demo_inbox/` holds four realistic class groups (`Official_CSE_Group`, `Unofficial_Class`, `OS_Lab_Section`, `Hostel_Wing`) with 13 files: teacher notes, a byte-identical re-share, a shorter re-typed copy, two photos of the same handwritten page, three circulars, a meme, and a note that fits both OS and DBMS. Nobody has shared Paging notes — so Unit 3 shows up **red**.

**Live moment:** on the Import page, switch on *"Include a late message"* and sort again — Rohan's Paging notes arrive and Unit 3 turns green.

Regenerate the demo any time: `python scripts/make_demo_data.py`

## Use it with your own groups

1. In WhatsApp, open a group → **⋮ → More → Export chat → Include media** (iPhone: group name → **Export Chat → Attach Media**).
2. Get the `.zip` onto your laptop, open **2 · Import chats → My own files**, and drop the zips in. Repeat for every group.
3. Edit your syllabus on **1 · Syllabus** (units, subtopics and the keywords that prove a subtopic).
4. **3 · Sort** → read your dashboard.

---

## How matching works (no black box)

* **A subtopic is ticked only when its keywords appear on a page** of a note — so every tick links to a page you can open. Captions never tick a subtopic: a caption saying *"recovery skipped"* must not count as covering Recovery.
* **The most evidence wins the unit.** If a note has equal evidence for two units (e.g. *two-phase locking* + *deadlock prevention* → DBMS or OS?), it goes to **Needs review** and you decide — never guessed.
* **MiniLM (all-MiniLM-L6-v2, local)** turns text into meaning-vectors. It ranks units and rescues notes whose keywords OCR could not read — but those are only *suggested* for your review.
* No generative AI, no summaries, no text sent anywhere. If no AI model is installed, keyword matching still works on its own.

| Status | Meaning |
|---|---|
| READY | every subtopic found on at least one page |
| NEEDS REVIEW | some subtopics still missing, or a note fits two units |
| MISSING | no note covers this unit at all — ask your class (the app writes the message for you) |

*Coverage means "covered in the notes you received" — it is not a guarantee of exam completeness.*

## Privacy

WhatsApp exports contain classmates' names and phone numbers. slothNtidy processes everything on your laptop and never uploads anything. `inbox/` and `output/` are git-ignored — **never commit a real chat export**; use the demo data to share examples.

---

## Project structure

```
app.py            the UI (Streamlit)              main.py        command-line runner
pipeline.py       runs all 7 stages + your review decisions
parser.py         WhatsApp chat parsing (Android, iPhone, short format) + PDF/photo reading + OCR
filters.py        circulars, SHA-256 exact copies, text/pHash near-copies (keeps the fuller copy)
matcher.py        keyword evidence per page + MiniLM unit ranking -> sorted / needs-review / unmatched
embedder.py       local embeddings: MiniLM, or Ollama nomic-embed-text, or none
filing.py         copies notes into SlothVault with clean names
exporter.py       one merged PDF per unit (cover page + original pages, bookmarks)
report.py         COVERAGE.md + report.json
syllabus.py       syllabus load/save         config.py      every folder and threshold
scripts/make_demo_data.py   builds the 4-group demo      tests/        pytest suite (no internet needed)
```

Outputs land in `output/`: `SlothVault/` (sorted copies), `TopicPDFs/` (merged PDFs), `COVERAGE.md`, `report.json`.

## Tests
```bash
python -m pytest -q
```
Covers caption pairing on real Android/iPhone exports (including WhatsApp's invisible U+200E mark), circular filtering, exact and near duplicates, subtopic evidence, ambiguous notes, and a full end-to-end run of the demo groups.

## Known limits & roadmap
* **Handwriting:** Tesseract reads neat handwriting; messy handwriting may land in *Needs review* (flagged, never lost). The demo uses a handwriting font so it is repeatable — try your own photos too. *Help wanted:* a local vision-OCR path.
* `.docx` / `.pptx` attachments are listed but not read yet.
* Keywords are per-subtopic; a future version could suggest them from the syllabus automatically.

## Earlier tools in this repo
`Tidy.py` (LLM-based PDF tidier) and `sloth.py` (offline Git commit helper via Ollama) are the team's earlier experiments and are not part of the notes-sorter pipeline. `engine.py` is their Ollama client.

## License
MIT — see [LICENSE](LICENSE).
