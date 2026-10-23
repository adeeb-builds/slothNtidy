```text
  _     _   _           _   _   _         _   _       
 | |   (_) | |_   _   _  | | | \ | |  ___  | |_| |_   _ 
 | |   | | | __| | | | | | | |  \| | / __| | __| | | | |
 | |___| | | |_  | |_| | | | | |\  | \__ \ | |_| | |_| |
 |_____|_|  \__|  \__, | |_| |_| \_| |___/  \__|_|  \__, |
                  |___/                             |___/

```

# 🦥 SlothSuite (`GIT tidyNsloth`)

### Zero-Friction, Privacy-First Local AI Document Management & Git Automation Suite

*Built for local-first developers, students, and privacy advocates.*

---

## 🌿 The Sloth Ethos

Sloths survive by conserving energy. You shouldn't waste yours manually renaming messy downloads, figuring out which PDF version has the extra page, or writing repetitive Conventional Commit messages.

**SlothSuite** is a dual-engine local AI toolkit powered by a 7-billion-parameter open-weight model (`qwen2.5:7b`) running 100% locally via Ollama. It does not just move files—it **deduplicates PDFs, diffs their contents, cleans your vaults, and automates your Git workflows offline**.

* 🔒 **100% Local Privacy:** Bank statements, study materials, resumes, and private source code repositories never leave `localhost:11434`. Zero telemetry, zero cloud overhead.
* 💸 **Zero API Costs:** No paid API keys or rate limits. Fully powered by your local hardware.
* 🧠 **Structured AI Contracts:** Uses JSON schema enforcement to turn unstructured binary documents and raw code diffs into clean, actionable data.

---

## 🏗️ Architectural Flow & Pipeline

SlothSuite operates through two interconnected, offline pipelines designed to streamline both your file system and your code repository.

### Pipeline A: Smart PDF Deduplication & Vault Engine (`Tidy.py`)

```text
 [ ./Downloaded_PDFs ] 
         │
         ▼
 🔍 Step 1: Pre-Scan & Metadata Extraction (PyMuPDF)
         │
         ▼
 🧠 Step 2: Cross-File Similarity Match (difflib SequenceMatcher)
         ├── [ Unique File ] ──► Send to LLM for Categorization & Key Points
         └── [ Duplicate Match ] ──► Compare Character Counts & Page Lengths
                 │
                 ▼
 🤖 Step 3: Local LLM Diff Analysis (qwen2.5:7b)
         │
         ▼
 👤 Step 4: Interactive User Permission ([y/N] prompt)
         ├── [ Approved ] ──► Physically delete inferior file from disk
         └── [ Rejected ] ──► Keep both files safe
         │
         ▼
 📂 Step 5: Atomic Move to [ ./SlothVault/{Category}/ ] & Live Markdown Update

```

### Pipeline B: Offline Git Automation Agent (`sloth.py`)

```text
 [ Staged Git Changes (git add -A) ]
         │
         ▼
 🔍 Step 1: Read Local Diff & Stat Summary (--cached --stat)
         │
         ▼
 🧠 Step 2: Zero-Cloud Local Inference (engine.py -> Ollama)
         │
         ▼
 🤖 Step 3: LLM Parses Diff into Structured JSON Packet
         ├── Conventional Commit Message (e.g., refactor(tidy): ...)
         ├── CHANGELOG.md Bullet Points
         └── Custom "Lazy Score" Evaluation
         │
         ▼
 👤 Step 4: Developer Review & Approval [y/N]
         │
         ▼
 🚀 Step 5: Local Commit, CHANGELOG.md Append & Automated GitHub Push

```

---

## ⭐ Spotlight Feature: Git Sloth (`sloth.py`) — Why It's a Game-Changer

While file organization is handy, **`sloth.py`** is the crown jewel for developer automation. Writing descriptive commit messages and updating changelogs manually is tedious context-switching. Git Sloth solves this by acting as an intelligent local co-pilot for version control:

1. **Zero Cloud Risk:** Unlike online GitHub Actions or third-party AI extensions that inspect your proprietary codebase in the cloud, Git Sloth runs entirely on your machine. It reads your local `git diff` and pipes it straight into your local Ollama instance.
2. **Context-Aware Conventional Commits:** It doesn't just look at file names; it reads the *actual lines added and removed*. If you refactored a deduplication loop, it writes `refactor(tidy): optimize SequenceMatcher threshold and batch processing`.
3. **Automated Changelog Maintenance:** It automatically formats a clean markdown entry in your `CHANGELOG.md` with structured bullet points detailing what changed under today's date.
4. **Instant Productivity Metrics:** It evaluates your commit size and prints a fun "Lazy Score" highlighting how many lines of typing you just avoided.

---

## 🚀 Quickstart & Installation

### 1. Prerequisites

Ensure you have Python 3.11+ and **Ollama** installed and running locally with your preferred model:

```bash
# Pull the inference engine model
ollama pull qwen2.5:7b

```

### 2. Clone and Setup Environment

Clone the repository and set up your local virtual environment:

```bash
git clone https://github.com/akshat-bit420/Git_slothNtidy.git
cd "GIT tidyNsloth"

# Create virtual environment
python -m venv .venv
source .venv/Scripts/Activate.ps1  # On Windows PowerShell
# source .venv/bin/activate        # On Linux/macOS

# Install dependencies
pip install requests pymupdf watchdog

```

---

## 🖥️ Usage Guide

### 1. Smart PDF Deduplication & Tidying (`Tidy.py`)

1. Place your raw or duplicate PDFs into the **`./Downloaded_PDFs`** folder.
2. Run the tidy script:
```powershell
python Tidy.py

```


3. The engine pre-scans all files, detects overlapping content, queries `qwen2.5:7b` to generate a content diff between shorter and fuller versions, asks for your confirmation (`[y/N]`), safely deletes inferior copies, and organizes survivors into **`./SlothVault`** complete with an auto-updated **`SLOTH_INDEX.md`** dashboard.

### 2. Offline Git Automation Agent (`sloth.py`)

1. Stage your changes normally using Git:
```bash
git add -A

```


2. Run the Git Sloth automation agent:
```powershell
python sloth.py

```


3. Review the AI-generated Conventional Commit message, changelog items, and lazy score directly in your terminal. Press **`y`** to commit, append your changelog, and push straight to GitHub!

---

## 📂 Project Structure

```text
GIT tidyNsloth/
├── Downloaded_PDFs/         # Input drop folder for raw/unorganized PDFs
├── SlothVault/              # Organized output categories & SLOTH_INDEX.md
│   ├── Notes/               # Categorized subfolders
│   └── SLOTH_INDEX.md       # Master Markdown table of contents & diff reports
├── .venv/                   # Python virtual environment (ignored in git)
├── engine.py                # Local Ollama REST client & JSON schema handler
├── Tidy.py                  # Batch PDF pre-scanner, diff analyzer & deduplicator
├── sloth.py                 # Local Git diff parser, commit generator & auto-pusher
├── .gitignore               # Excludes virtual environments and cache
└── CHANGELOG.md             # Auto-generated changelog history

```

---

## 🤝 Contributing & License

Distributed under the **MIT License**. Created with ❤️ for Hacktoberfest 2026. Pull requests, bug reports, and feature enhancements are welcome!
