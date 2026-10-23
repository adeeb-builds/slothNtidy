# import os
# import json
# import time
# import shutil
# from datetime import datetime
# from difflib import SequenceMatcher
# import pymupdf as fitz 
# from watchdog.observers import Observer
# from watchdog.events import FileSystemEventHandler
# from engine import SlothEngine

# SYSTEM_PROMPT = """
# You are an intelligent document deduplication and analysis agent.
# Analyze the provided document(s) and return ONLY a JSON object with these exact keys:
# - "category": One-word folder category (e.g., "Assignments", "ExamPrep", "Resumes", "Notes", "Finance")
# - "clean_name": A clean, snake_case filename (without extension or date), max 4 words.
# - "key_points": A JSON list of 3 to 4 crisp bullet points summarizing the document content (NO paragraphs).
# - "action_items": A JSON list of strings for deadlines, tasks, or important dates (return [] if none).
# - "deletion_reason": If "DELETED_PDF_TEXT" is provided, write 1 clear sentence explaining why the shorter PDF was deleted in favor of the fuller PDF. Otherwise return "".
# - "comparison_points": If "DELETED_PDF_TEXT" is provided, return a JSON list of 2 to 3 bullet points detailing the specific extra content/sections present in KEPT_PDF_TEXT that were missing from DELETED_PDF_TEXT. Otherwise return [].
# """

# class SlothPDFHandler(FileSystemEventHandler):
#     def __init__(self, watch_dir: str, engine: SlothEngine):
#         self.watch_dir = watch_dir
#         self.engine = engine
#         self.index_file = os.path.join(watch_dir, "SLOTH_INDEX.md")
#         self.memory_file = os.path.join(watch_dir, "sloth_memory.json")
#         self.memory = self.load_memory()

#     def load_memory(self) -> list:
#         if os.path.exists(self.memory_file):
#             with open(self.memory_file, "r", encoding="utf-8") as f:
#                 return json.load(f)
#         return []

#     def save_memory(self):
#         with open(self.memory_file, "w", encoding="utf-8") as f:
#             json.dump(self.memory, f, indent=2)

#     def on_created(self, event):
#         if event.is_directory or not event.src_path.lower().endswith(".pdf"):
#             return
#         time.sleep(1.5)
#         if os.path.exists(event.src_path):
#             self.process_pdf(event.src_path)

#     def extract_pdf_info(self, pdf_path: str) -> tuple[str, int]:
#         """Returns (extracted_text, page_count)."""
#         text = ""
#         with fitz.open(pdf_path) as doc:
#             page_count = len(doc)
#             for page in doc:
#                 text += page.get_text()
#         return text.strip(), page_count

#     def find_similar_pdf(self, new_text: str):
#         """Finds if a PDF on the same topic is already stored in memory."""
#         for item in self.memory:
#             # Check overlap on the first 1500 chars (usually Page 1)
#             sample_len = min(len(new_text), len(item["full_text"]), 1500)
#             if sample_len < 50:
#                 continue
#             ratio = SequenceMatcher(None, new_text[:sample_len], item["full_text"][:sample_len]).ratio()
#             if ratio >= 0.55:
#                 return item
#         return None

#     def process_pdf(self, pdf_path: str):
#         new_orig_name = os.path.basename(pdf_path)
#         print(f"\n🦥 Waking up to inspect: {new_orig_name}...")

#         new_text, new_pages = self.extract_pdf_info(pdf_path)
#         if not new_text:
#             print("⚠️ Scanned/empty PDF (no selectable text). Skipping.")
#             return

#         new_chars = len(new_text)
#         match = self.find_similar_pdf(new_text)

#         # CASE 1: Brand new unique PDF
#         if not match:
#             prompt = f"KEPT_PDF_TEXT ({new_pages} pages, {new_chars} chars):\n{new_text[:5000]}"
#             result = self.engine.ask_json(SYSTEM_PROMPT, prompt)
#             self.file_and_record(
#                 pdf_path=pdf_path,
#                 orig_name=new_orig_name,
#                 pages=new_pages,
#                 chars=new_chars,
#                 full_text=new_text,
#                 ai_result=result,
#                 deleted_info=None
#             )
#             return

#         # CASE 2: We found a matching PDF! Compare which one has more content.
#         old_pages = match["pages"]
#         old_chars = match["chars"]
#         old_orig_name = match["orig_name"]

#         if new_chars > old_chars:
#             print(f"🔼 Upgrade detected! '{new_orig_name}' ({new_pages}p, {new_chars} chars) > '{match['saved_name']}' ({old_pages}p, {old_chars} chars).")
#             print("🧠 Asking Qwen to compare the extra content (this may take 30-60s)...")

#             # Only send a short preview + the NEW extra characters so Qwen finishes 3x faster!
#             extra_text_slice = new_text[old_chars : old_chars + 2000]
#             prompt = (
#                 f"KEPT_PDF_OVERVIEW ({new_orig_name} - {new_pages} pages, {new_chars} chars):\n{new_text[:1500]}\n\n"
#                 f"EXTRA_CONTENT_ONLY_IN_KEPT_PDF:\n{extra_text_slice}\n\n"
#                 f"DELETED_PDF_STATS: {old_orig_name} ({old_pages} pages, {old_chars} chars, lacked the extra content above)."
#             )
            
#             # 1. Wait for Qwen FIRST before deleting anything!
#             result = self.engine.ask_json(SYSTEM_PROMPT, prompt)

#             # 2. Now safely delete the old 1-page PDF from disk
#             print(f"🗑️ Deleting older shorter PDF '{match['saved_name']}' from disk!")
#             if os.path.exists(match["path"]):
#                 os.remove(match["path"])
#             self.memory.remove(match)

#             deleted_info = {
#                 "deleted_name": old_orig_name,
#                 "deleted_pages": old_pages,
#                 "deleted_chars": old_chars,
#                 "reason": result.get("deletion_reason", "Contained less text than the updated version."),
#                 "comparison": result.get("comparison_points", [])
#             }
#             self.file_and_record(pdf_path, new_orig_name, new_pages, new_chars, new_text, result, deleted_info)

#         else:
#             # The NEW PDF (e.g., 1 page) is smaller/equal to the OLD PDF (e.g., 2 pages)
#             print(f"🗑️ Deleting newly dropped shorter PDF '{new_orig_name}' ({new_pages}p, {new_chars} chars) from disk!")
#             print(f"✅ Keeping existing fuller PDF '{match['saved_name']}' ({old_pages}p, {old_chars} chars) & logging comparison...")

#             # Physically delete the newly dropped 1-page PDF from SlothInbox
#             os.remove(pdf_path)

#             prompt = (
#                 f"KEPT_PDF_TEXT ({old_orig_name} - {old_pages} pages, {old_chars} chars):\n{match['full_text'][:4500]}\n\n"
#                 f"DELETED_PDF_TEXT ({new_orig_name} - {new_pages} pages, {new_chars} chars):\n{new_text[:3000]}"
#             )
#             result = self.engine.ask_json(SYSTEM_PROMPT, prompt)

#             match["deleted_info"] = {
#                 "deleted_name": new_orig_name,
#                 "deleted_pages": new_pages,
#                 "deleted_chars": new_chars,
#                 "reason": result.get("deletion_reason", "New file was a shorter/incomplete duplicate."),
#                 "comparison": result.get("comparison_points", [])
#             }
#             self.save_memory()
#             self.rebuild_index_md()

#     def file_and_record(self, pdf_path, orig_name, pages, chars, full_text, ai_result, deleted_info):
#         category = ai_result.get("category", "Unsorted")
#         clean_name = ai_result.get("clean_name", "document")
#         date_prefix = datetime.now().strftime("%Y-%m-%d")
#         saved_name = f"{date_prefix}_{clean_name}.pdf"

#         dest_dir = os.path.join(self.watch_dir, category)
#         os.makedirs(dest_dir, exist_ok=True)
#         dest_path = os.path.join(dest_dir, saved_name)

#         shutil.move(pdf_path, dest_path)

#         self.memory.append({
#             "saved_name": saved_name,
#             "orig_name": orig_name,
#             "category": category,
#             "path": dest_path,
#             "pages": pages,
#             "chars": chars,
#             "full_text": full_text[:5000],
#             "key_points": ai_result.get("key_points", []),
#             "action_items": ai_result.get("action_items", []),
#             "deleted_info": deleted_info
#         })
#         self.save_memory()
#         self.rebuild_index_md()
#         print(f"✅ Filed into {category}/{saved_name}. SLOTH_INDEX.md updated!")

#     def rebuild_index_md(self):
#         """Rewrites SLOTH_INDEX.md cleanly so deleted PDFs don't leave dead entries."""
#         lines = ["# 🦥 Sloth Smart Document Index\n\n"]
#         for item in self.memory:
#             lines.append(f"### 📄 [{item['saved_name']}](./{item['category']}/{item['saved_name']})\n")
#             lines.append(f"**Original File:** `{item['orig_name']}` | **Stats:** `{item['pages']} page(s), {item['chars']} chars`\n\n")

#             if item["key_points"]:
#                 lines.append("**📌 Key Content (Points):**\n")
#                 for pt in item["key_points"]:
#                     lines.append(f"* {pt}\n")
#                 lines.append("\n")

#             if item.get("deleted_info"):
#                 d = item["deleted_info"]
#                 lines.append(f"**🗑️ Auto-Deleted Inferior Duplicate:** `{d['deleted_name']}` (`{d['deleted_pages']} page(s), {d['deleted_chars']} chars`)\n")
#                 lines.append(f"* **Why it was deleted:** {d['reason']}\n")
#                 if d.get("comparison"):
#                     lines.append("* **Comparison (What this kept PDF has that the deleted PDF lacked):**\n")
#                     for comp in d["comparison"]:
#                         lines.append(f"  * ➕ {comp}\n")
#                 lines.append("\n")

#             actions = [a for a in item.get("action_items", []) if a and a.lower() != "none"]
#             if actions:
#                 lines.append("**⚡ Action Items & Deadlines:**\n")
#                 for act in actions:
#                     lines.append(f"* [ ] {act}\n")
#                 lines.append("\n")

#             lines.append("---\n\n")

#         with open(self.index_file, "w", encoding="utf-8") as f:
#             f.writelines(lines)

# if __name__ == "__main__":
#     WATCH_FOLDER = "./SlothInbox"
#     os.makedirs(WATCH_FOLDER, exist_ok=True)

#     engine = SlothEngine(model="qwen2.5:7b")
#     observer = Observer()
#     observer.schedule(SlothPDFHandler(WATCH_FOLDER, engine), WATCH_FOLDER, recursive=False)
#     observer.start()

#     print(f"🦥 Sloth Smart Dedup Daemon watching '{WATCH_FOLDER}' with {engine.model}!")
#     try:
#         while True:
#             time.sleep(1)
#     except KeyboardInterrupt:
#         observer.stop()
#     observer.join()

import os
import json
import shutil
from datetime import datetime
from difflib import SequenceMatcher
import pymupdf as fitz  # Clean import without deprecation warning
from engine import SlothEngine

# ==========================================
# HARDCODED PROJECT FOLDERS
# ==========================================
DOWNLOAD_FOLDER = "./Downloaded_PDFs"   # Put or download your raw PDFs here
VAULT_FOLDER = "./SlothVault"           # Sorted folders + SLOTH_INDEX.md live here

COMPARE_PROMPT = """
You are comparing two overlapping PDF documents (a SHORTER version and a FULLER version).
Return ONLY a JSON object with these exact keys:
- "shorter_summary": A JSON list of 1-2 short bullet points summarizing what is in SHORTER_PDF.
- "fuller_summary": A JSON list of 1-2 short bullet points summarizing what is in FULLER_PDF.
- "differences": A JSON list of 2-3 bullet points explaining the exact extra information/sections present in FULLER_PDF that are missing in SHORTER_PDF.
"""

INDEX_PROMPT = """
You are an elite document intelligence agent. Analyze the document text and return ONLY a JSON object with these exact keys:
- "category": One-word folder category (e.g., "Assignments", "ExamPrep", "Resumes", "Notes", "Finance")
- "clean_name": A clean, snake_case filename (without extension or date), max 4 words.
- "key_points": A JSON list of 3 to 4 crisp bullet points summarizing the document content (NO paragraphs).
- "action_items": A JSON list of strings for deadlines, tasks, or important dates (return [] if none).
"""


class SlothBatchAnalyzer:
    def __init__(self, download_dir: str, vault_dir: str, engine: SlothEngine):
        self.download_dir = download_dir
        self.vault_dir = vault_dir
        self.engine = engine
        self.index_file = os.path.join(vault_dir, "SLOTH_INDEX.md")
        self.memory_file = os.path.join(vault_dir, "sloth_memory.json")

        os.makedirs(self.download_dir, exist_ok=True)
        os.makedirs(self.vault_dir, exist_ok=True)
        self.memory = self.load_memory()

    def load_memory(self) -> list:
        if os.path.exists(self.memory_file):
            with open(self.memory_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def save_memory(self):
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(self.memory, f, indent=2)

    def extract_pdf_info(self, pdf_path: str) -> dict:
        """Extracts text, page count, and character length from a PDF."""
        text = ""
        with fitz.open(pdf_path) as doc:
            pages = len(doc)
            for page in doc:
                text += page.get_text()
        clean_text = text.strip()
        return {
            "orig_name": os.path.basename(pdf_path),
            "path": pdf_path,
            "pages": pages,
            "chars": len(clean_text),
            "text": clean_text,
            "deleted_history": None
        }

    def are_duplicates(self, text_a: str, text_b: str) -> bool:
        """Compares the overlapping prefix of two PDFs to see if one is an expanded version of the other."""
        compare_len = min(len(text_a), len(text_b), 1500)
        if compare_len < 50:
            return False
        ratio = SequenceMatcher(None, text_a[:compare_len], text_b[:compare_len]).ratio()
        return ratio >= 0.55

    def run_batch(self):
        pdf_files = [
            os.path.join(self.download_dir, f)
            for f in sorted(os.listdir(self.download_dir))
            if f.lower().endswith(".pdf")
        ]

        if not pdf_files:
            print(f"🦥 No PDFs found in '{self.download_dir}'.")
            print(f"👉 Drop or download your PDFs into '{os.path.abspath(self.download_dir)}' and run again!")
            return

        # ==========================================================
        # STEP 1: READ ALL PDFs FIRST TO BUILD REFERENCE TABLE
        # ==========================================================
        print(f"\n🔍 STEP 1: Pre-scanning all {len(pdf_files)} PDF(s) in '{self.download_dir}'...")
        docs = []
        for path in pdf_files:
            info = self.extract_pdf_info(path)
            if info["chars"] == 0:
                print(f"   ⚠️ Skipping '{info['orig_name']}' (no selectable text).")
                continue
            print(f"   📄 Loaded reference: {info['orig_name']} ({info['pages']}p, {info['chars']} chars)")
            docs.append(info)

        # ==========================================================
        # STEP 2: CROSS-COMPARE ALL FILES FOR DUPLICATES FIRST
        # ==========================================================
        print("\n🧠 STEP 2: Cross-comparing all files against each other for duplicates...")
        removed_paths = set()

        for i in range(len(docs)):
            if docs[i]["path"] in removed_paths:
                continue

            for j in range(i + 1, len(docs)):
                if docs[j]["path"] in removed_paths:
                    continue

                doc_a = docs[i]
                doc_b = docs[j]

                if self.are_duplicates(doc_a["text"], doc_b["text"]):
                    # Determine which one has LESS info (shorter) vs MORE info (fuller)
                    if doc_a["chars"] <= doc_b["chars"]:
                        shorter, fuller = doc_a, doc_b
                    else:
                        shorter, fuller = doc_b, doc_a

                    print("\n" + "=" * 65)
                    print(f"⚠️  DUPLICATE DETECTED: '{shorter['orig_name']}' vs '{fuller['orig_name']}'")
                    print("=" * 65)
                    print("🦥 Asking Qwen to summarize both and extract the differences...")

                    extra_slice = fuller["text"][shorter["chars"] : shorter["chars"] + 2000]
                    prompt = (
                        f"SHORTER_PDF ({shorter['orig_name']} - {shorter['pages']}p, {shorter['chars']} chars):\n"
                        f"{shorter['text'][:1500]}\n\n"
                        f"FULLER_PDF ({fuller['orig_name']} - {fuller['pages']}p, {fuller['chars']} chars):\n"
                        f"{fuller['text'][:1500]}\n\n"
                        f"EXTRA_TEXT_ONLY_IN_FULLER_PDF:\n{extra_slice}"
                    )

                    diff_data = self.engine.ask_json(COMPARE_PROMPT, prompt)

                    print(f"\n📉 SHORTER FILE: {shorter['orig_name']} ({shorter['pages']}p, {shorter['chars']} chars)")
                    for pt in diff_data.get("shorter_summary", ["No summary."]):
                        print(f"   • {pt}")

                    print(f"\n📈 FULLER FILE:  {fuller['orig_name']} ({fuller['pages']}p, {fuller['chars']} chars)")
                    for pt in diff_data.get("fuller_summary", ["No summary."]):
                        print(f"   • {pt}")

                    print(f"\n🔍 DIFFERENCE (What '{fuller['orig_name']}' has that '{shorter['orig_name']}' is missing):")
                    for diff in diff_data.get("differences", ["Contains expanded content."]):
                        print(f"   ➕ {diff}")

                    # Ask user for permission before deleting!
                    choice = input(f"\n👉 Delete shorter file '{shorter['orig_name']}'? [y/N]: ").strip().lower()
                    if choice in ("y", "yes"):
                        os.remove(shorter["path"])
                        removed_paths.add(shorter["path"])
                        fuller["deleted_history"] = {
                            "deleted_name": shorter["orig_name"],
                            "deleted_pages": shorter["pages"],
                            "deleted_chars": shorter["chars"],
                            "differences": diff_data.get("differences", [])
                        }
                        print(f"🗑️  Deleted '{shorter['orig_name']}'. Keeping '{fuller['orig_name']}'!")
                        if shorter == doc_a:
                            break  # doc_a was deleted, move to next i
                    else:
                        print(f"🛡️  Kept both '{shorter['orig_name']}' and '{fuller['orig_name']}'.")

        # ==========================================================
        # STEP 3: ORGANIZE SURVIVING FILES & UPDATE SLOTH_INDEX.MD
        # ==========================================================
        survivors = [d for d in docs if d["path"] not in removed_paths]
        print(f"\n📂 STEP 3: Indexing {len(survivors)} surviving PDF(s) into '{self.vault_dir}'...")

        for doc in survivors:
            print(f"   🦥 Generating bullet points for '{doc['orig_name']}'...")
            ai_res = self.engine.ask_json(INDEX_PROMPT, doc["text"][:4000])

            category = ai_res.get("category", "Unsorted")
            clean_name = ai_res.get("clean_name", "document")
            date_prefix = datetime.now().strftime("%Y-%m-%d")
            saved_name = f"{date_prefix}_{clean_name}.pdf"

            dest_dir = os.path.join(self.vault_dir, category)
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, saved_name)

            # Avoid overwriting if user chose to keep two identical-named files
            counter = 1
            while os.path.exists(dest_path):
                saved_name = f"{date_prefix}_{clean_name}_{counter}.pdf"
                dest_path = os.path.join(dest_dir, saved_name)
                counter += 1

            shutil.move(doc["path"], dest_path)

            self.memory.append({
                "saved_name": saved_name,
                "orig_name": doc["orig_name"],
                "category": category,
                "path": dest_path,
                "pages": doc["pages"],
                "chars": doc["chars"],
                "key_points": ai_res.get("key_points", []),
                "action_items": ai_res.get("action_items", []),
                "deleted_history": doc["deleted_history"]
            })
            print(f"   ✅ Moved to {category}/{saved_name}")

        self.save_memory()
        self.rebuild_index_md()
        print(f"\n🎉 All done! Open '{self.index_file}' to view your clean report.")

    def rebuild_index_md(self):
        lines = ["# 🦥 Sloth Smart Document Index\n\n"]
        for item in self.memory:
            lines.append(f"### 📄 [{item['saved_name']}](./{item['category']}/{item['saved_name']})\n")
            lines.append(f"**Original File:** `{item['orig_name']}` | **Stats:** `{item['pages']} page(s), {item['chars']} chars`\n\n")

            if item.get("key_points"):
                lines.append("**📌 Key Points:**\n")
                for pt in item["key_points"]:
                    lines.append(f"* {pt}\n")
                lines.append("\n")

            if item.get("deleted_history"):
                d = item["deleted_history"]
                lines.append(f"**🗑️ User-Approved Duplicate Deletion:** `{d['deleted_name']}` (`{d['deleted_pages']}p, {d['deleted_chars']} chars`)\n")
                for diff in d.get("differences", []):
                    lines.append(f"* ➕ {diff}\n")
                lines.append("\n")

            actions = [a for a in item.get("action_items", []) if a and a.lower() != "none"]
            if actions:
                lines.append("**⚡ Action Items & Deadlines:**\n")
                for act in actions:
                    lines.append(f"* [ ] {act}\n")
                lines.append("\n")

            lines.append("---\n\n")

        with open(self.index_file, "w", encoding="utf-8") as f:
            f.writelines(lines)


if __name__ == "__main__":
    engine = SlothEngine(model="qwen2.5:7b")
    analyzer = SlothBatchAnalyzer(
        download_dir=DOWNLOAD_FOLDER,
        vault_dir=VAULT_FOLDER,
        engine=engine
    )
    analyzer.run_batch()
    