## [2026-10-30] - Real WhatsApp exports: no crashes, much faster
Tested on two real class exports (184 files, 125 PDFs, 307 scanned pages, 60 photos):
- WhatsApp stickers (STK-*.webp) are skipped; .webp photos now open (converted with Pillow)
- One damaged or unsupported file no longer stops the sort: it is listed on the dashboard and skipped
- The same zip added twice is read once (the Import page also refuses a file already in the inbox)
- Identical files shared in several groups are read once
- Scanned PDFs: only the first 10 pages are OCR-read (enough to place them; merged PDFs keep every page)
- Files are read several at a time (up to 4, depending on the laptop's cores)
- Near-duplicate check: a 3-word-phrase pre-check before the exact comparison (Clean 136 s -> 16 s)
- "Read photos too" switch on the Sort page: off = PDFs only, much faster on big groups

## [2026-10-30] - Syllabus from a photo, no built-in demo
- The app now starts empty: the sample syllabus and sample class groups are gone from the app (they live on in
  tests/demo_data for the automated tests only). Your syllabus is saved to my_syllabus.json; old demo results are ignored
- New on 1 · Syllabus: upload photos, a PDF or a Word file of the college syllabus; units and subtopics are read
  (Tesseract OCR, row by row) and shown as an editable draft that is saved only when the student presses Save
- Understands "UNIT I" heading layouts and Unit / Topic tables (including rows whose numeral OCR lost),
  several subjects and pages at once; skips lecture hours, page headers, book lists and course outcomes
- 10 new tests (21 in total), including a phone photo of a printed syllabus table
- Fixes from the first real syllabus: subject name taken from a heading line when there is no "Course Title:",
  "Unit $5" OCR noise and headings glued to the previous line, hyphenated words across lines, no splitting of
  "Error Detection and Correction Techniques" at "and", generic subtopics like "Introduction" left out
- Subject name read from a header table row ("PC303 | Computer Networks | 3L:0T:0P"); a warning when an
  uploaded image is small (screenshots misread letters) suggesting the PDF / Word file instead
- Subject name also found when OCR drops the course code ("Computer Networks 3L:0T:0P 3 Credits")
- New "Subject name" box above the syllabus table: type the name once, press Apply, every row updates


## [2026-10-30] - slothNtidy v2: the notes sorter app
- Added a Streamlit app (app.py) with Syllabus, Import, Sort, Coverage dashboard, Noise reduction, Cluster inspector, Review & duplicates and Sorted vault pages
- Fixed caption pairing on real WhatsApp exports (invisible U+200E mark; Android and iPhone formats)
- Added multiple group exports (.zip or .txt), photos of handwritten notes (OCR + converted to PDF pages)
- Fixed CPU *scheduling* notes being dropped as circulars ("schedule" keyword)
- Near-duplicates now keep the fuller copy; pHash runs on photos/scans before the unreadable check
- Subtopic-level coverage with page evidence; ambiguous notes go to Needs review
- New filing stage: sorted, renamed copies in output/SlothVault (originals never touched)
- Merged unit PDFs with a coverage cover page and bookmarks
- MiniLM local embeddings (Ollama and keyword-only fallbacks)
- Built-in 4-group demo data, Windows/Mac one-click setup and run scripts, 11 tests


## [2026-10-23]
- - Removed outdated DBMS definitions document
- - Added new notes on database indexing optimization
- - Updated Sloth Smart Document Index with latest content
