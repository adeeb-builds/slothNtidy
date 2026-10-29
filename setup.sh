#!/usr/bin/env bash
# slothNtidy one-time setup for Mac / Linux (needs internet).  Run:  ./setup.sh
set -e
cd "$(dirname "$0")"
PY=$(command -v python3 || command -v python || true)
if [ -z "$PY" ]; then
  echo "Python 3 not found. Install it from https://www.python.org/downloads/ and run ./setup.sh again."; exit 1
fi
[ -d .venv ] || "$PY" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu || python -m pip install torch
python -m pip install -r requirements.txt
python -c "from sentence_transformers import SentenceTransformer as S; S('sentence-transformers/all-MiniLM-L6-v2'); print('MiniLM ready')" \
  || echo "(Model download failed - the app still works with keyword matching)"
if ! python -c "import sys; from config import configure_tesseract as c; sys.exit(0 if c() else 1)"; then
  if command -v brew >/dev/null; then brew install tesseract
  else echo "Install Tesseract OCR: Mac -> 'brew install tesseract'; Ubuntu -> 'sudo apt install tesseract-ocr'"; fi
fi
python -m pytest -q || true
echo "Setup complete. Start the app with ./run.sh"
