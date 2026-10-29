# Contributing to slothNtidy

1. Fork the repository and create a branch: `git checkout -b feat/your-feature`
2. Set up: double-click `setup.bat` (Windows) or run `./setup.sh` (Mac/Linux)
3. Make your change. Thresholds and folder names live in `config.py`.
4. Run the tests - none of them need the internet or the AI model: `python -m pytest -q`
5. If you change the demo data, regenerate it with `python scripts/make_demo_data.py`
6. Open a Pull Request that references an issue.

**Privacy rule:** never commit a real WhatsApp export. Chats contain classmates' names and phone
numbers. The `inbox/` and `output/` folders are git-ignored for this reason; use the demo data instead.
