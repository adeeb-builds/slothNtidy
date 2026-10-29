"""Stage 5 (file): every note lands in one sorted place with a clean name.

output/SlothVault/
  Operating Systems/
    Unit 1 - CPU Scheduling/   OS_U1_CPU-Scheduling_Priya_18Oct.pdf
    Unit 2 - Deadlocks/        OS_U2_Deadlocks_Rohan_21Oct.pdf
  _Needs_Review/               uncertain matches, with the suggested unit in the name
  _Not_In_Syllabus/            memes and anything that matched nothing
  _Removed/Circulars/          notices that were filtered out
  _Removed/Duplicates/         copies that were filtered out

Files are COPIED, never moved or deleted: the inbox stays exactly as you left it,
so a wrong decision is never a lost file.
"""
import os
import re
import shutil

from config import VAULT_FOLDER


_TITLES = {"prof", "professor", "dr", "mr", "mrs", "ms", "sir", "maam"}


def slug(text: str, max_len: int = 40) -> str:
    words = re.sub(r"[^A-Za-z0-9]+", " ", text).split()
    return "-".join(w[:1].upper() + w[1:] for w in words)[:max_len].strip("-") or "Notes"


def clean_name(d: dict, unit: dict) -> str:
    ext = os.path.splitext(d["orig_name"])[1].lower()
    parts = [unit["subject_code"], f"U{unit['unit']}", slug(unit["title"])]
    if d.get("sender"):
        words = [w for w in d["sender"].split() if w.lower().strip(".") not in _TITLES]
        parts.append(slug((words or d["sender"].split())[0], 15))
    if d.get("date"):
        parts.append(d["date"].replace(" ", ""))
    return "_".join(parts) + ext


def _unique(path: str) -> str:
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(path):
        path = f"{base}_{n}{ext}"
        n += 1
    return path


def _copy(src: str, dest_dir: str, name: str) -> str:
    os.makedirs(dest_dir, exist_ok=True)
    dest = _unique(os.path.join(dest_dir, name))
    shutil.copy2(src, dest)
    return dest


def file_notes(all_docs: list, units: list, vault: str = VAULT_FOLDER, log=print) -> dict:
    """Copies every document into the vault. Returns counts per destination."""
    by_id = {u["id"]: u for u in units}
    counts = {"sorted": 0, "needs_review": 0, "not_in_syllabus": 0, "removed": 0}
    for d in all_docs:
        status, coverage = d.get("status"), d.get("coverage")
        if status == "circular":
            d["vault_path"] = _copy(d["path"], os.path.join(vault, "_Removed", "Circulars"), d["orig_name"])
            counts["removed"] += 1
        elif status in ("exact_dup", "near_dup"):
            d["vault_path"] = _copy(d["path"], os.path.join(vault, "_Removed", "Duplicates"), d["orig_name"])
            counts["removed"] += 1
        elif coverage == "sorted":
            u = by_id[d["unit_id"]]
            folder = os.path.join(vault, u["subject_name"], f"Unit {u['unit']} - {u['title']}")
            d["vault_path"] = _copy(d["path"], folder, clean_name(d, u))
            counts["sorted"] += 1
        elif coverage == "needs-review":
            sug = by_id.get(d.get("suggested_unit_id"))
            name = (f"CHECK_{os.path.splitext(clean_name(d, sug))[0]}__{d['orig_name']}"
                    if sug else d["orig_name"])
            d["vault_path"] = _copy(d["path"], os.path.join(vault, "_Needs_Review"), name)
            counts["needs_review"] += 1
        else:
            d["vault_path"] = _copy(d["path"], os.path.join(vault, "_Not_In_Syllabus"), d["orig_name"])
            counts["not_in_syllabus"] += 1
        log(f"   [FILED] {d['orig_name']} -> {os.path.relpath(d['vault_path'], vault)}")
    return counts
