"""Gemma 4 handwriting reader: turns a photo or scan of a handwritten page into text.

Why it exists: Tesseract (our OCR) reads printed text well but cannot read handwriting,
so handwritten notes used to land in "Needs review". Gemma 4 is Google's open-weight,
multimodal model - it looks at the page image and writes down what is on it.

What it does NOT do: Gemma never decides which unit a note belongs to. Its text goes
into the same keyword matching as every other page, so every tick on the dashboard is
still traceable to a page number ("read by Gemma 4, page 3").

Two ways to run the SAME model family:
  * "api"   - Google's Gemini API (model gemma-4-26b-a4b-it). Fast, needs internet and a
              free API key from aistudio.google.com. The page image is sent to Google.
  * "local" - Ollama on this laptop (model gemma4:e4b). Nothing leaves the computer;
              needs `ollama pull gemma4:e4b` once and is slow without a graphics card.

Safety nets (a demo must never crash):
  * every answer is cached on disk by image fingerprint -> a second run is instant and
    works even with no internet;
  * timeouts + one retry per page;
  * after 3 failures in a row Gemma switches itself off for the rest of the run and the
    pipeline carries on with Tesseract's text.
"""
import base64
import hashlib
import io
import json
import os
import re
import threading

import requests

from config import (GEMMA_API_MODEL, GEMMA_CACHE_FOLDER, GEMMA_LOCAL_MODEL, GEMMA_MAX_FAILURES,
                    GEMMA_MAX_SIDE, GEMMA_TIMEOUT, OLLAMA_HOST)

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT = (
    "This is one page of a college student's study notes (often handwritten). "
    "Transcribe ALL the text on the page exactly as written: headings, bullet points, "
    "definitions, formulas and the labels inside diagrams. Keep the original wording and "
    "spelling of technical terms. Do not explain, summarise or add anything. "
    "Output plain text only. If the page has no readable text, output exactly: EMPTY"
)


def _png_bytes(img) -> bytes:
    """Shrinks very large photos (keeps detail, saves upload time) and encodes as PNG."""
    img = img.convert("RGB")
    w, h = img.size
    scale = GEMMA_MAX_SIDE / max(w, h)
    if scale < 1:
        img = img.resize((int(w * scale), int(h * scale)))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _clean(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```[a-z]*\n?|```$", "", text).strip()     # some models wrap answers in code fences
    return "" if text.upper() == "EMPTY" else text


class GemmaReader:
    """One reader per sorting run. Safe to use from several threads at once."""

    def __init__(self, backend: str = "api", api_key: str = "", model: str = "",
                 cache_dir: str = GEMMA_CACHE_FOLDER, host: str = OLLAMA_HOST, post=None):
        if backend not in ("api", "local"):
            raise ValueError("backend must be 'api' or 'local'")
        if backend == "api" and not api_key:
            raise ValueError("The Gemini API needs an API key (free at aistudio.google.com).")
        self.backend = backend
        self.api_key = api_key
        self.model = model or (GEMMA_API_MODEL if backend == "api" else GEMMA_LOCAL_MODEL)
        self.host = host
        self.cache_dir = cache_dir
        self._post = post or requests.post          # tests pass a fake here (no internet needed)
        self._lock = threading.Lock()
        self.failures_in_a_row = 0
        self.disabled = False
        self.last_error = ""
        self.pages_read = 0      # answers that came from Gemma (cache or live)
        self.cache_hits = 0
        os.makedirs(cache_dir, exist_ok=True)

    @property
    def name(self) -> str:
        where = "Gemini API" if self.backend == "api" else "local, Ollama"
        return f"Gemma 4 ({self.model}, {where})"

    # ------------------------------------------------------------------ public
    def read_page(self, img) -> str:
        """Returns the text Gemma reads on this page image, or '' if it could not."""
        if self.disabled:
            return ""
        png = _png_bytes(img)
        key = hashlib.sha256(png + self.model.encode()).hexdigest()[:32]
        cached = self._cache_get(key)
        if cached is not None:
            with self._lock:
                self.cache_hits += 1
                self.pages_read += 1
            return cached
        for _attempt in range(2):                # one retry for a flaky network
            try:
                text = _clean(self._call(png))
                self._cache_put(key, text)
                with self._lock:
                    self.failures_in_a_row = 0
                    self.pages_read += 1
                return text
            except Exception as e:  # network down, bad key, quota used up, model not pulled...
                with self._lock:
                    self.last_error = f"{type(e).__name__}: {e}"[:300]
        with self._lock:
            self.failures_in_a_row += 1
            if self.failures_in_a_row >= GEMMA_MAX_FAILURES:
                self.disabled = True
        return ""

    # ------------------------------------------------------------------ backends
    def _call(self, png: bytes) -> str:
        return self.ask([png], PROMPT)

    def ask(self, pngs: list, prompt: str, timeout: float = GEMMA_TIMEOUT) -> str:
        """Sends page images + an instruction to Gemma 4 and returns its text answer (raises on errors)."""
        imgs = [base64.b64encode(png).decode() for png in pngs]
        if self.backend == "api":
            parts = [{"inline_data": {"mime_type": "image/png", "data": b}} for b in imgs] + [{"text": prompt}]
            body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"temperature": 0.0}}
            r = self._post(API_URL.format(model=self.model), json=body, timeout=timeout,
                           headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"})
            if r.status_code != 200:
                raise RuntimeError(f"Gemini API {r.status_code}: {r.text[:200]}")
            parts = r.json()["candidates"][0]["content"].get("parts", [])
            return "\n".join(p.get("text", "") for p in parts if not p.get("thought"))
        body = {"model": self.model, "prompt": prompt, "stream": False, "options": {"temperature": 0.0}}
        if imgs:
            body["images"] = imgs
        r = self._post(f"{self.host}/api/generate", timeout=timeout * 4, json=body)
        if r.status_code != 200:
            raise RuntimeError(f"Ollama {r.status_code}: {r.text[:200]}")
        return r.json().get("response", "")

    # ------------------------------------------------------------------ cache
    def _cache_path(self, key):
        return os.path.join(self.cache_dir, key + ".json")

    def _cache_get(self, key):
        try:
            with open(self._cache_path(key), encoding="utf-8") as f:
                return json.load(f)["text"]
        except (OSError, ValueError, KeyError):
            return None

    def _cache_put(self, key, text):
        tmp = self._cache_path(key) + f".{threading.get_ident()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"model": self.model, "text": text}, f, ensure_ascii=False)
        os.replace(tmp, self._cache_path(key))


# ---------------------------------------------------------------------- when to ask Gemma

_WORD = re.compile(r"[A-Za-z]{3,}")


def looks_unreadable(text: str, min_chars: int) -> bool:
    """True when Tesseract's text is too short or mostly garbage - typical for handwriting.
    Printed scans give mostly real words, so Gemma is not called for them (saves time and quota)."""
    text = (text or "").strip()
    if len(text) < min_chars:
        return True
    tokens = text.split()
    if not tokens:
        return True
    wordlike = [t for t in tokens if _WORD.fullmatch(t.strip(".,;:()[]'\"!?-")) and re.search(r"[aeiouyAEIOUY]", t)]
    return len(wordlike) / len(tokens) < 0.55


def check_connection(backend: str, api_key: str = "", host: str = OLLAMA_HOST, post=None, get=None) -> str:
    """Quick test for the Sort page button. Returns '' when Gemma answers, else a plain-English problem."""
    post, get = post or requests.post, get or requests.get
    try:
        if backend == "api":
            if not api_key:
                return "Paste your Gemini API key first."
            r = post(API_URL.format(model=GEMMA_API_MODEL), timeout=GEMMA_TIMEOUT,
                     headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                     json={"contents": [{"parts": [{"text": "Reply with the single word OK."}]}]})
            if r.status_code == 200:
                return ""
            if r.status_code in (400, 401, 403):
                return "Google rejected the API key. Copy it again from aistudio.google.com."
            if r.status_code == 429:
                return "The free Gemini quota is used up for now. Wait a minute or use the local model."
            return f"Gemini API answered {r.status_code}."
        r = get(f"{host}/api/tags", timeout=5)
        names = [m.get("name", "") for m in r.json().get("models", [])]
        if not any(n.startswith(GEMMA_LOCAL_MODEL.split(":")[0]) for n in names):
            return f"Ollama is running but Gemma is not downloaded. Run:  ollama pull {GEMMA_LOCAL_MODEL}"
        return ""
    except requests.exceptions.ConnectionError:
        return ("No internet connection to Google." if backend == "api"
                else "Ollama is not running. Open the Ollama app first.")
    except Exception as e:
        return f"{type(e).__name__}: {e}"[:200]


# ---------------------------------------------------------------------- syllabus reading

SYLLABUS_PROMPT = """These are photos/pages of a university course syllabus. Read them and return ONLY a JSON object:
{"subjects": [{"name": "full subject name", "code": "short code like CN or ML",
  "units": [{"unit": 1, "title": "unit title",
    "subtopics": [{"name": "subtopic as written", "keywords": ["...", "..."]}]}]}]}
Rules:
- Copy unit titles and subtopics from the page, fixing obvious misreadings and spelling (e.g. Intemet -> Internet).
- Split long comma-separated topic lists into separate subtopics. Skip textbooks, references, outcomes, hours, marks.
- keywords: 2-6 short lowercase words or phrases a student's notes on that subtopic would literally contain,
  including standard abbreviations (e.g. "tcp", "three way handshake", "dns"). No generic words like "introduction".
- code: 2-4 capital letters from the subject name (e.g. Computer Networks -> CN).
Return JSON only, no explanation."""


def parse_syllabus_json(text: str) -> dict:
    """Gemma's answer -> the app's syllabus format. Anything malformed is dropped, never guessed."""
    text = re.sub(r"^```[a-z]*\s*|```\s*$", "", (text or "").strip())
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return {"subjects": []}
    data = json.loads(text[start:end + 1])
    subjects, used = [], set()
    for s in data.get("subjects") or []:
        name = str(s.get("name") or "").strip()
        code = re.sub(r"[^A-Za-z0-9]", "", str(s.get("code") or "")).upper()[:6]
        if not code:
            code = "".join(w[0] for w in re.findall(r"[A-Za-z]+", name) if w.lower() not in ("and", "of", "the", "to"))[:4].upper() or "SUB"
        base, k = code, 2
        while code in used:
            code, k = f"{base}{k}", k + 1
        used.add(code)
        units, seen = [], set()
        for i, u in enumerate(s.get("units") or [], 1):
            try:
                n = int(u.get("unit") or i)
            except (TypeError, ValueError):
                n = i
            while n in seen:
                n += 1
            seen.add(n)
            subs = []
            for t in u.get("subtopics") or []:
                tname = str(t.get("name") if isinstance(t, dict) else t).strip()
                if not tname:
                    continue
                kws = t.get("keywords") if isinstance(t, dict) else []
                kws = [str(x).strip().lower() for x in (kws or []) if str(x).strip()]
                subs.append({"name": tname, "keywords": list(dict.fromkeys(kws))[:6]})
            title = str(u.get("title") or "").strip() or (subs[0]["name"] if subs else f"Unit {n}")
            if subs:
                units.append({"unit": n, "title": title, "subtopics": subs})
        if units:
            subjects.append({"code": code, "name": name or code, "units": units})
    return {"subjects": subjects}


def read_syllabus_with_gemma(files, reader: "GemmaReader") -> dict:
    """files: [(name, bytes)]. Photos and PDF pages go to Gemma 4 as images; Word files as text.
    Returns {"syllabus", "text", "warnings"} like syllabus_reader.read_syllabus, or raises on failure."""
    import pymupdf as fitz
    from PIL import Image
    pngs, texts = [], []
    for name, data in files:
        ext = os.path.splitext(name)[1].lower()
        if ext == ".pdf":
            with fitz.open("pdf", data) as doc:
                for page in list(doc)[:6]:
                    pix = page.get_pixmap(dpi=150)
                    pngs.append(_png_bytes(Image.open(io.BytesIO(pix.tobytes("png")))))
        elif ext == ".docx":
            from syllabus_reader import _read_docx
            texts.append(_read_docx(data))
        else:
            with Image.open(io.BytesIO(data)) as img:
                pngs.append(_png_bytes(img))
    prompt = SYLLABUS_PROMPT + ("\n\nSyllabus text:\n" + "\n".join(texts) if texts else "")
    answer = reader.ask(pngs, prompt, timeout=GEMMA_TIMEOUT * 3)
    syl = parse_syllabus_json(answer)
    warnings = [] if syl["subjects"] else ["Gemma 4 did not find any units."]
    return {"syllabus": syl, "text": "(read by " + reader.name + ")\n" + answer.strip(), "warnings": warnings}
