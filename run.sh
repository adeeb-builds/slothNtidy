#!/usr/bin/env bash
# Start slothNtidy on Mac / Linux:  ./run.sh   (then open http://localhost:8501 if it does not open by itself)
cd "$(dirname "$0")"
[ -d .venv ] || { echo "Run ./setup.sh first."; exit 1; }
source .venv/bin/activate
( sleep 4; (command -v open >/dev/null && open http://localhost:8501) || xdg-open http://localhost:8501 ) >/dev/null 2>&1 &
python -m streamlit run app.py
