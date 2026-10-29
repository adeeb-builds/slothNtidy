"""Loads the syllabus that documents get mapped against."""
import json
from config import SYLLABUS_FILE

def load_syllabus(path=SYLLABUS_FILE) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)