"""Loads and saves the syllabus that notes are mapped against.

File format (sample_data/syllabus.json):
{
  "subjects": [
    {"code": "OS", "name": "Operating Systems",
     "units": [
       {"unit": 1, "title": "CPU Scheduling",
        "subtopics": [{"name": "FCFS", "keywords": ["fcfs", "first come first serve"]}, ...]}
     ]}
  ]
}
"keywords" are optional: they are the words that prove a page covers that subtopic.
If none are given, the subtopic's own name is used. The older flat format
([{"subject", "unit", "topic", "subtopics": [..]}]) is still accepted.
"""
import json
import re

from config import SYLLABUS_FILE


def norm(text: str) -> str:
    """Lowercase, drop apostrophes, turn everything that is not a letter/digit into one space."""
    text = text.lower().replace("'", "").replace("’", "")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _from_legacy(items: list) -> dict:
    subjects = {}
    for t in items:
        s = subjects.setdefault(t["subject"], {"code": t["subject"], "name": t["subject"], "units": []})
        s["units"].append({"unit": t["unit"], "title": t["topic"],
                           "subtopics": [{"name": st, "keywords": []} for st in t["subtopics"]]})
    return {"subjects": list(subjects.values())}


def load_syllabus_doc(path: str = SYLLABUS_FILE) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return _from_legacy(data) if isinstance(data, list) else data


def save_syllabus_doc(data: dict, path: str = SYLLABUS_FILE):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def flatten(data: dict) -> list:
    """One entry per unit, each subtopic carrying the normalised phrases that prove it."""
    units = []
    for s in data.get("subjects", []):
        code = s.get("code") or s.get("name", "SUBJ")
        for u in s.get("units", []):
            subtopics = []
            for st in u.get("subtopics", []):
                if isinstance(st, str):
                    st = {"name": st, "keywords": []}
                phrases = [norm(k) for k in (st.get("keywords") or []) if norm(k)]
                if not phrases:
                    phrases = [norm(st["name"])]
                subtopics.append({"name": st["name"], "phrases": phrases})
            units.append({
                "id": f"{code}-U{u['unit']}",
                "subject_code": code,
                "subject_name": s.get("name", code),
                "unit": u["unit"],
                "title": u["title"],
                "subtopics": subtopics,
            })
    return units


def load_syllabus(path: str = SYLLABUS_FILE) -> list:
    return flatten(load_syllabus_doc(path))
