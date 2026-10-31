"""slothNtidy - the app.  Start it with:   streamlit run app.py   (or double-click run.bat)

Everything runs on this laptop. No notes, names or phone numbers leave the machine.
"""
import base64
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import time
from collections import defaultdict

import pandas as pd
import pymupdf as fitz
import streamlit as st

from config import (INBOX_FOLDER, OUTPUT_FOLDER, REPORT_JSON, REPORT_MD, SYLLABUS_FILE,
                    VAULT_FOLDER, configure_tesseract)
from embedder import load_embedder
from gemma import GemmaReader, check_connection
from config import GEMMA_API_MODEL, GEMMA_LOCAL_MODEL
from parser import file_hash, scan_inbox
from pipeline import STAGES, assign_to_unit, decide_many, mark_not_in_syllabus, restore_removed, run
from mascot import sloth_with_bubble
from syllabus import load_syllabus, load_syllabus_doc, save_syllabus_doc
from syllabus_reader import SYLLABUS_TYPES, read_syllabus
from syllabus_reader import _subject_code as subject_code

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)  # all paths in config.py are relative to the project folder

st.set_page_config(page_title="slothNtidy - Notes Sorter", page_icon="🦥", layout="wide",
                   initial_sidebar_state="expanded")

# ====================================================================== look & feel (from the pitch deck)

def _font_face(family, file, weight):
    path = os.path.join(HERE, "assets", "fonts", file)
    if not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return (f"@font-face{{font-family:'{family}';src:url(data:font/woff2;base64,{b64}) format('woff2');"
            f"font-weight:{weight};font-style:normal;font-display:swap;}}")


@st.cache_resource
def _css():
    faces = "".join([
        _font_face("Space Grotesk", "space-grotesk-latin-400-normal.woff2", 400),
        _font_face("Space Grotesk", "space-grotesk-latin-500-normal.woff2", 500),
        _font_face("Space Grotesk", "space-grotesk-latin-700-normal.woff2", 700),
        _font_face("Space Mono", "space-mono-latin-400-normal.woff2", 400),
        _font_face("Space Mono", "space-mono-latin-700-normal.woff2", 700),
        _font_face("Pixelify Sans", "pixelify-sans-latin-400-normal.woff2", 400),
        _font_face("Pixelify Sans", "pixelify-sans-latin-600-normal.woff2", 600),
        _font_face("Pixelify Sans", "pixelify-sans-latin-700-normal.woff2", 700),
    ])
    return faces + """
:root{--green:#2E4741;--green2:#3B5A52;--coral:#E0675E;--red:#D23F2B;--redbg:#F8DCD6;--cream:#F2EFE6;
--paper:#FBFAF5;--ink:#1F2A27;--muted:#5E6B67;--mustard:#E2A834;--shadow:#5A1E17;--blue:#2F5FA7;--ok:#2E6B4F;}
html,body,[class*="css"],.stApp,.stMarkdown,button,input,textarea,select{font-family:'Space Grotesk',system-ui,sans-serif!important;}
.stApp{background:var(--cream);}
code,pre,.mono{font-family:'Space Mono',ui-monospace,monospace!important;}
[data-testid="stSidebar"]{background:var(--green);}
[data-testid="stSidebar"] *{color:#EDEAE0;}
[data-testid="stSidebar"] .stRadio label p{font-size:15px;}
[data-testid="stSidebar"] [role="radiogroup"] label{padding:6px 8px;border-radius:0;}
[data-testid="stSidebar"] [role="radiogroup"] label > div > div:first-child{border-radius:0!important;width:12px!important;height:12px!important;
 border:2px solid #9FB5AE!important;background:transparent!important;}
[data-testid="stSidebar"] [role="radiogroup"] label > div > div:first-child > div{display:none!important;}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) > div > div:first-child{background:var(--coral)!important;border-color:var(--coral)!important;}
[data-testid="stSidebar"] hr{border:none!important;border-top:2px dashed var(--coral)!important;opacity:.85;}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){background:rgba(255,255,255,.10);box-shadow:inset 3px 0 0 var(--coral);}
.block-container{padding-top:2.2rem;max-width:1180px;}
h1,h2,h3{font-family:'Space Grotesk',sans-serif!important;letter-spacing:-.02em;color:var(--ink);}
.kicker{font-family:'Space Mono',monospace;font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:#B9802A;font-weight:700;}
.side-kicker{font-family:'Space Mono',monospace;font-size:10px;letter-spacing:.22em;color:var(--mustard)!important;font-weight:700;margin-top:.3rem;}
.brand{font-family:'Pixelify Sans',monospace!important;font-size:28px;font-weight:700;line-height:1.05;margin:.2rem 0 .1rem;color:#F4F1E8!important;letter-spacing:.01em;}
.brand span{color:var(--coral)!important;}
.page-title{font-family:'Pixelify Sans',monospace!important;font-size:44px;font-weight:700;line-height:1.05;margin:.25rem 0 .5rem;color:var(--ink);letter-spacing:.005em;}
.page-title span{color:var(--red);}
.lede{color:var(--muted);font-size:16px;max-width:760px;margin-bottom:1.2rem;}
.card{background:var(--paper);border:1.5px solid var(--ink);box-shadow:6px 6px 0 var(--shadow);padding:18px 20px;margin:0 6px 18px 0;}
.card.dark{background:var(--green);color:#EDEAE0;border-color:var(--green);}
.card.dark *{color:#EDEAE0;}
.note{background:var(--paper);border:2px dashed var(--ink);padding:12px 16px;font-size:14px;color:var(--ink);box-shadow:5px 5px 0 var(--shadow);margin:10px 6px 18px 0;}
.note .kicker{display:block;margin-bottom:4px;}
.stats{display:grid;grid-template-columns:repeat(6,1fr);gap:14px;margin:4px 6px 22px 0;}
.stat{background:var(--paper);border:1.5px solid var(--ink);padding:12px 14px;box-shadow:4px 4px 0 var(--shadow);}
.stat .n{font-size:30px;font-weight:700;line-height:1;}
.stat .l{font-family:'Space Mono',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-top:6px;}
.stat.red .n{color:var(--red);} .stat.ok .n{color:var(--ok);} .stat.blue .n{color:var(--blue);}
.thead{display:grid;grid-template-columns:2.1fr 2.2fr 2.6fr 1.35fr 1.45fr;background:var(--green);color:#F4F1E8;
 font-weight:600;font-size:14px;padding:12px 14px;border:1.5px solid var(--ink);border-bottom:none;margin-right:6px;}
[class*="st-key-row-"]{background:var(--paper);border:1.5px solid var(--ink);border-top:1px dashed #9AA39F;padding:10px 14px 12px;margin:-1rem 6px 0 0!important;}
[class*="st-key-row-"] .stMarkdown p,[class*="st-key-row-"] [data-testid="stMarkdownContainer"]{margin-bottom:0!important;}
[class*="st-key-row-"] .cell,[class*="st-key-row-"] .status{padding:2px 0;line-height:1.45;}
[class*="st-key-lastrow"]{height:0;border-top:1.5px solid var(--ink);margin:-1rem 6px 26px 0!important;box-shadow:0 6px 0 var(--shadow);}
[class*="st-key-row-MISSING"]{background:var(--redbg);}
.cell{font-size:14px;padding:6px 0;color:var(--ink);}
.cell b{font-weight:700;}
.cell.miss{color:var(--red);font-weight:600;}
.cell.review{color:var(--blue);font-weight:600;}
.cell.muted{color:var(--muted);}
.status{font-family:'Space Mono',monospace;font-size:12px;font-weight:700;letter-spacing:.06em;padding:6px 0;}
.status.READY{color:var(--ok);} .status.NEEDS{color:var(--blue);} .status.MISSING{color:var(--red);}
.funnel-row{display:grid;grid-template-columns:300px 1fr 150px;align-items:center;gap:14px;margin:10px 0;}
.funnel-row .lab{font-weight:600;font-size:15px;}
.funnel-row .bar{height:30px;background:#E4E0D3;border:1.5px solid var(--ink);position:relative;}
.funnel-row .fill{height:100%;}
.funnel-row .num{font-family:'Space Mono',monospace;font-size:13px;text-align:right;}
.chat{background:var(--green);color:#EDEAE0;font-family:'Space Mono',monospace;font-size:13px;line-height:1.75;padding:18px 20px;
 border:1.5px solid var(--green);box-shadow:6px 6px 0 var(--shadow);margin-right:6px;}
.chat .k{color:var(--mustard);font-size:10.5px;letter-spacing:.22em;display:block;margin-bottom:8px;font-weight:700;}
.chat .ts{color:#9FB5AE;} .chat .who{color:#F4C36B;} .chat .cap{color:#F4F1E8;}
.chat .cov{color:#8FD6A6;font-weight:700;} .chat .nc{color:#FF8C7A;font-weight:700;} .chat .rv{color:#9DBBF0;font-weight:700;}
.chat hr{border:none;border-top:1px dashed #5E7A72;margin:10px 0;}
.how{font-family:'Space Mono',monospace;font-size:12.5px;background:var(--paper);border:2px dashed var(--ink);padding:12px 16px;margin:16px 6px 16px 0;}
.how b{color:var(--red);}
.tag{display:inline-block;font-family:'Space Mono',monospace;font-size:11px;font-weight:700;letter-spacing:.06em;padding:2px 8px;border:1.3px solid var(--ink);margin:0 6px 4px 0;background:#fff;}
.tag.red{background:var(--redbg);color:var(--red);border-color:var(--red);}
.tag.blue{background:#E2EAF7;color:var(--blue);border-color:var(--blue);}
.tag.ok{background:#E0EFE6;color:var(--ok);border-color:var(--ok);}
.stagebar{display:grid;grid-template-columns:repeat(7,1fr);gap:8px;margin:8px 6px 16px 0;}
.stage{border:2px dashed var(--ink);padding:10px 8px;background:var(--paper);font-size:13px;font-weight:600;}
.stage .s{font-family:'Pixelify Sans',monospace;font-size:13px;letter-spacing:.06em;color:var(--muted);display:block;}
.stage.done,.stage.now{border-style:solid;}
.stage.done{background:var(--green);color:#F4F1E8;} .stage.done .s{color:var(--mustard);}
.stage.now{background:var(--coral);color:#fff;} .stage.now .s{color:#fff;}
.tree{font-family:'Space Mono',monospace;font-size:13px;background:var(--paper);border:1.5px solid var(--ink);padding:14px 18px;
 box-shadow:6px 6px 0 var(--shadow);line-height:1.7;white-space:pre;overflow-x:auto;margin-right:6px;}
div.stButton>button,div.stDownloadButton>button{border-radius:0;border:1.5px solid var(--ink);font-weight:600;box-shadow:3px 3px 0 var(--shadow);}
div.stButton>button[kind="primary"]{background:var(--coral);color:#fff;border-color:var(--ink);outline:2px dashed rgba(255,255,255,.75);outline-offset:-6px;}
div.stButton>button:hover,div.stDownloadButton>button:hover{transform:translate(1px,1px);box-shadow:2px 2px 0 var(--shadow);}
[data-testid="stExpander"]{border-radius:0;border:1.5px solid var(--ink);background:var(--paper);}
[data-testid="stFileUploaderDropzone"]{border-radius:0;border:2px dashed var(--green);background:var(--paper);}
.mascot{display:flex;align-items:center;gap:12px;margin:6px 0 4px;position:relative;}
.mascot .sloth{flex:none;image-rendering:pixelated;}
.mascot .sloth-working{animation:bob .5s steps(2) infinite;}
.mascot .sloth-happy{animation:hop 1.6s steps(2) infinite;}
@keyframes bob{50%{transform:translateY(-3px);}}
@keyframes hop{0%,70%{transform:none;}85%{transform:translateY(-4px);}}
.bubble{position:relative;background:#fff;color:var(--ink)!important;border:2px dashed var(--ink);font-family:'Space Mono',monospace;
 font-size:11.5px;line-height:1.45;padding:8px 10px;letter-spacing:.02em;}
.bubble *{color:var(--ink)!important;}
.bubble::before{content:"";position:absolute;left:-9px;top:50%;width:10px;height:10px;background:#fff;
 border-left:2px dashed var(--ink);border-bottom:2px dashed var(--ink);transform:translateY(-50%) rotate(45deg);}
[data-testid="stSidebar"] .bubble{background:#F4F1E8;border-color:#F4F1E8;}
[data-testid="stSidebar"] .bubble::before{background:#F4F1E8;border-color:#F4F1E8;}
.zz{position:absolute;left:62px;top:-6px;font-family:'Pixelify Sans',monospace;color:var(--mustard)!important;font-size:13px;
 animation:zz 2s steps(3) infinite;}
.zz b{font-size:16px;color:var(--mustard)!important;} .zz i{font-size:19px;font-style:normal;color:var(--mustard)!important;}
@keyframes zz{0%{opacity:.3;}50%{opacity:1;}100%{opacity:.3;}}
.hero-mascot{border:2px dashed var(--ink);background:var(--paper);padding:14px 18px;margin:0 6px 18px 0;box-shadow:5px 5px 0 var(--shadow);}
@media (max-width:900px){.stats{grid-template-columns:repeat(2,1fr);}.thead{display:none;}.stagebar{grid-template-columns:repeat(4,1fr);}
 .funnel-row{grid-template-columns:1fr;}}
"""


st.markdown(f"<style>{_css()}</style>", unsafe_allow_html=True)


def header(kicker, title, accent, lede=""):
    st.markdown((f'<div class="kicker">{kicker}</div>' if kicker else "") + f'<div class="page-title">{title} <span>{accent}</span></div>'
                + (f'<div class="lede">{lede}</div>' if lede else ""), unsafe_allow_html=True)


def esc(s):
    return (str(s or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ====================================================================== engine + state

@st.cache_resource(show_spinner="Loading the local AI model (first start takes a few seconds)...")
def get_engine():
    msgs = []
    emb = load_embedder(log=msgs.append)
    return emb, msgs


def ocr_available():
    return configure_tesseract()


def load_last_result():
    if os.path.exists(REPORT_JSON):
        try:
            with open(REPORT_JSON, encoding="utf-8") as f:
                r = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
        if "demo" in str(r.get("inbox", "")).lower():   # results left over from the old built-in demo
            return None
        return r
    return None


if "result" not in st.session_state:
    st.session_state.result = load_last_result()
if "log" not in st.session_state:
    st.session_state.log = []

embedder, engine_msgs = get_engine()
R = st.session_state.result


def units_by_id():
    return {u["id"]: u for u in load_syllabus()}


def unit_label(u):
    return f"{u['subject_code']} · Unit {u['unit']}: {u['title']}"


def selected_inboxes():
    return [INBOX_FOLDER]


def open_folder(path):
    path = os.path.abspath(path)
    try:
        if platform.system() == "Windows":
            os.startfile(path)  # noqa - Windows only
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        st.toast(f"Opened {path}")
    except Exception as e:
        st.warning(f"Could not open the folder automatically ({e}). It is here: {path}")


@st.cache_data(show_spinner=False, max_entries=200)
def page_png(pdf_path, page_no, mtime, dpi=70):
    with fitz.open(pdf_path) as d:
        page_no = max(0, min(page_no, d.page_count - 1))
        return d[page_no].get_pixmap(dpi=dpi).tobytes("png")


def preview(doc, page_index=0, dpi=70):
    p = doc.get("pdf_path") or doc.get("path")
    if not p or not os.path.exists(p):
        st.caption("(preview unavailable - the file was moved)")
        return
    st.image(page_png(p, page_index, os.path.getmtime(p), dpi), width="stretch")


def doc_by_name(name):
    return next((d for d in R["documents"] if d["orig_name"] == name), None) if R else None


def need_result():
    if not R:
        st.markdown('<div class="note"><span class="kicker">Nothing sorted yet</span>'
                    'Go to <b>3 · Sort</b> in the left menu and press <b>Sort my notes</b>.</div>',
                    unsafe_allow_html=True)
        return True
    return False


# ====================================================================== sidebar

PAGES = ["1 · Syllabus", "2 · Import chats", "3 · Sort", "Coverage dashboard", "Noise reduction",
         "Cluster inspector", "Review & duplicates", "Sorted vault"]
if "nav" not in st.session_state:
    st.session_state.nav = ("Coverage dashboard" if R else
                            "2 · Import chats" if load_syllabus_doc()["subjects"] else "1 · Syllabus")
if "goto" in st.session_state:  # page switches requested by buttons (must happen before the menu is drawn)
    st.session_state.nav = st.session_state.pop("goto")

with st.sidebar:
    st.markdown('<div class="brand">slothNtidy<br><span>Notes Sorter.</span></div>', unsafe_allow_html=True)
    st.caption("WhatsApp chaos → syllabus-mapped exam notes")
    if R:
        _miss = sum(u["status"] == "MISSING" for u in R["units"])
        _msg = (f"Sorted {R['counts']['kept']} notes! {_miss} unit{'s' if _miss != 1 else ''} still missing."
                if _miss else f"Sorted {R['counts']['kept']} notes. Every unit has notes!")
        st.markdown(sloth_with_bubble("happy", _msg, px=4), unsafe_allow_html=True)
    else:
        st.markdown(sloth_with_bubble("sleeping", "Wake me up: drop your class groups in.", px=4),
                    unsafe_allow_html=True)
    st.radio("Go to", PAGES, key="nav", label_visibility="collapsed")
    st.divider()
    st.markdown('<div class="side-kicker">LOCAL ENGINE</div>', unsafe_allow_html=True)
    st.markdown(f"**Matching:** {embedder.name if embedder else 'Keyword evidence only'}")
    st.markdown(f"**OCR:** {'Tesseract ready' if ocr_available() else 'Tesseract not found - photos cannot be read'}")
    if st.session_state.get("gemma_on"):
        _api = st.session_state.get("gemma_where", "Google Gemini API") == "Google Gemini API"
        st.markdown(f"**Handwriting:** Gemma 4 ({'Gemini API' if _api else 'local'})")
        st.markdown("**Internet:** " + ("only for handwritten pages (Gemini API)" if _api else "not used"))
    else:
        st.markdown("**Handwriting:** off (Gemma 4 can be switched on in 3 · Sort)")
        st.markdown("**Internet:** not used")
    if R:
        st.divider()
        st.markdown('<div class="side-kicker">LAST RUN</div>', unsafe_allow_html=True)
        c = R["counts"]
        st.markdown(f"{c['total']} files → **{c['kept']} notes kept** in {R.get('seconds', '?')} s")

page = st.session_state.nav


# ====================================================================== 1 · Syllabus

SYL_COLUMNS = ["Subject code", "Subject name", "Unit", "Unit title", "Subtopic", "Keywords"]


def syllabus_rows(data):
    """Syllabus document -> one table row per subtopic (the format of the editable table)."""
    rows = []
    for s in data["subjects"]:
        for u in s["units"]:
            for stp in u["subtopics"]:
                rows.append({"Subject code": s["code"], "Subject name": s["name"], "Unit": int(u["unit"]),
                             "Unit title": u["title"], "Subtopic": stp["name"],
                             "Keywords": ", ".join(stp.get("keywords", []))})
    return rows


def syllabus_upload_box():
    """Photo / PDF / Word syllabus -> a DRAFT in the table. Nothing is saved until the student presses Save."""
    has_draft = "syl_draft" in st.session_state
    with st.expander("Read my syllabus from a photo, PDF or Word file", expanded=not has_draft):
        st.markdown(
            "Take a clear, straight photo of each syllabus page (good light, whole page in the frame), or upload "
            "the PDF / Word file from your college. **Several pages or subjects at once is fine** - they are "
            "read in file-name order, and phone photos are named by the time they were taken, so photograph the "
            "pages in order. slothNtidy fills the table below; you check it and press **Save syllabus**.")
        files = st.file_uploader("Syllabus photos, PDF or Word file", accept_multiple_files=True,
                                 type=list(SYLLABUS_TYPES), key=f"syl_up_{st.session_state.get('syl_ver', 0)}")
        mode = st.radio("The table below should be", ["replaced by this syllabus", "kept, and this syllabus added"],
                        horizontal=True, key="syl_mode")
        if files and st.button(f"Read {len(files)} file(s)", type="primary"):
            try:
                with st.spinner("Reading your syllabus... (about 10 seconds per photo)"):
                    got = read_syllabus([(f.name, f.getvalue()) for f in sorted(files, key=lambda f: f.name)])
            except Exception as e:  # Tesseract missing, damaged file, unsupported type
                st.error(f"Could not read the syllabus: {e}")
                return
            new_rows = syllabus_rows(got["syllabus"])
            if not new_rows:
                st.error("No units were found in " + ", ".join(f.name for f in files) + ". The page should "
                         "have headings like 'UNIT I' or a Unit / Topic table. Is the photo sharp and the whole "
                         "page visible? You can also type the syllabus into the table.")
                with st.popover("Show the text that was read"):
                    st.code(got["text"] or "(no text)", language=None)
                return
            base = syllabus_rows(load_syllabus_doc()) if mode.startswith("kept") else []
            subs = got["syllabus"]["subjects"]
            st.session_state.syl_draft = base + new_rows
            st.session_state.syl_draft_info = {
                "summary": f"{len(subs)} subject(s), {sum(len(x['units']) for x in subs)} unit(s), "
                           f"{len(new_rows)} subtopic(s): " + ", ".join(f"{x['name']} ({x['code']})" for x in subs),
                "warnings": got["warnings"], "text": got["text"]}
            st.session_state.syl_ver = st.session_state.get("syl_ver", 0) + 1   # redraw the table with the draft
            st.rerun()

    if has_draft:
        info = st.session_state.syl_draft_info
        st.markdown('<div class="note"><span class="kicker">DRAFT - NOT SAVED YET</span>Read from your syllabus: '
                    f'{esc(info["summary"])}.<br>Check every row before saving: photos can misread a letter '
                    '(e.g. <b>SJF</b> read as <b>SJE</b>). Fix the <b>Subject code</b> (it becomes the folder name), '
                    'delete rows you do not need, then press <b>Save syllabus</b>.</div>', unsafe_allow_html=True)
        for w in info["warnings"]:
            st.warning(w)
        c1, c2, _ = st.columns([1.6, 1.4, 3])
        with c1.popover("Show the text that was read"):
            st.code(info["text"], language=None)
        if c2.button("Discard draft"):
            clear_syllabus_draft()
            st.rerun()


def subject_name_boxes(rows):
    """One 'Subject name' box per subject: type the name once and every row of that subject changes.
    Set the name first - pressing Apply redraws the table (edits made in the table before that are reset)."""
    subjects = list(dict.fromkeys((r["Subject code"], r["Subject name"]) for r in rows))
    if not subjects:
        return
    ver = st.session_state.get("syl_ver", 0)
    st.markdown('<div class="kicker">SUBJECT NAME</div>', unsafe_allow_html=True)
    st.caption("Check the subject name first (before editing the table below). The short code becomes the folder name.")
    for i, (code, name) in enumerate(subjects):
        unknown = name.startswith("Subject ") and code.startswith("SUB")
        c1, c2, c3 = st.columns([3, 1.3, 1])
        new_name = c1.text_input("Subject name", value="" if unknown else name, key=f"sn_{ver}_{i}",
                                 placeholder="Type the subject name, e.g. Computer Networks")
        new_code = c2.text_input("Short code", value="" if unknown else code, key=f"sc_{ver}_{i}",
                                 placeholder="e.g. CN")
        c3.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
        if c3.button("Apply", key=f"sa_{ver}_{i}", type="primary" if unknown else "secondary"):
            new_name = new_name.strip()
            if not new_name:
                st.error("Type the subject name first.")
                return
            new_code = (new_code.strip() or subject_code(new_name)).upper().replace(" ", "")
            for r in rows:
                if (r["Subject code"], r["Subject name"]) == (code, name):
                    r["Subject code"], r["Subject name"] = new_code, new_name
            st.session_state.syl_draft = rows
            st.session_state.setdefault("syl_draft_info", {"summary": "your saved syllabus, with a renamed subject",
                                                            "warnings": [], "text": ""})
            info = st.session_state.syl_draft_info
            info["warnings"] = [w for w in info["warnings"] if "subject name was not found" not in w]
            info["summary"] = info["summary"].replace(f"{name} ({code})", f"{new_name} ({new_code})")
            st.session_state.syl_ver = ver + 1
            st.rerun()


def clear_syllabus_draft():
    st.session_state.pop("syl_draft", None)
    st.session_state.pop("syl_draft_info", None)
    st.session_state.syl_ver = st.session_state.get("syl_ver", 0) + 1


def page_syllabus():
    header("Step 1 of 3", "Your", "syllabus.",
           "Upload a photo of your syllabus, or type it in. <b>Keywords</b> are the words that prove a page covers a "
           "subtopic (comma-separated). Leave them empty to use the subtopic's own name.")
    if "syl_saved" in st.session_state:
        st.success(st.session_state.pop("syl_saved"))
    syllabus_upload_box()
    rows = st.session_state.get("syl_draft") or syllabus_rows(load_syllabus_doc())
    if not rows:
        st.markdown('<div class="note"><span class="kicker">NO SYLLABUS YET</span>Upload a photo of your syllabus '
                    'above, or type it into the table below (click <b>+</b> to add a row), then press '
                    '<b>Save syllabus</b>.</div>', unsafe_allow_html=True)
    subject_name_boxes(rows)
    table = pd.DataFrame(rows, columns=SYL_COLUMNS)   # fixed columns, so an empty table still shows them
    edited = st.data_editor(
        table, num_rows="dynamic", hide_index=True, key=f"syl_editor_{st.session_state.get('syl_ver', 0)}", height=min(42 + 35 * (len(rows) + 2), 620),
        column_config={
            "Subject code": st.column_config.TextColumn(width="small", required=True),
            "Unit": st.column_config.NumberColumn(width="small", min_value=1, step=1, required=True),
            "Keywords": st.column_config.TextColumn(width="large"),
        })
    if st.button("Save syllabus", type="primary"):
        subjects = {}
        for r in edited.to_dict("records"):
            r = {k: ("" if (v is None or (isinstance(v, float) and v != v)) else v) for k, v in r.items()}
            r = {k: (v.strip() if isinstance(v, str) else v) for k, v in r.items()}
            if not (r.get("Subject code") and r.get("Unit title") and r.get("Subtopic")):
                continue
            s = subjects.setdefault(r["Subject code"].strip(), {"code": r["Subject code"].strip(),
                                    "name": (r.get("Subject name") or r["Subject code"]).strip(), "units": {}})
            u = s["units"].setdefault(int(r["Unit"] or 1), {"unit": int(r["Unit"] or 1),
                                      "title": r["Unit title"].strip(), "subtopics": []})
            kws = [k.strip() for k in (r.get("Keywords") or "").split(",") if k.strip()]
            u["subtopics"].append({"name": r["Subtopic"].strip(), "keywords": kws})
        out = {"subjects": [{**s, "units": [s["units"][k] for k in sorted(s["units"])]} for s in subjects.values()]}
        if not out["subjects"]:
            st.error("Nothing to save: every row needs a Subject code, a Unit title and a Subtopic.")
        else:
            save_syllabus_doc(out)
            was_draft = "syl_draft" in st.session_state
            clear_syllabus_draft()
            st.session_state.syl_saved = f"Saved {sum(len(s['units']) for s in out['subjects'])} units. Sort again to use it."
            if was_draft:
                st.rerun()
            st.success(st.session_state.pop("syl_saved"))
    st.markdown('<div class="how"><b>WHY KEYWORDS?</b> A subtopic is only ticked when its words are found on an actual '
                'page - so every tick can be traced back to a page. The local AI model (MiniLM) helps decide '
                'which unit a note belongs to, but it never ticks a subtopic on its own.</div>', unsafe_allow_html=True)


# ====================================================================== 2 · Import

def _uploaded_files():
    """Files added on this page (zips and loose files), not the folders unpacked from zips."""
    out = []
    if os.path.isdir(INBOX_FOLDER):
        for batch in os.listdir(INBOX_FOLDER):
            b = os.path.join(INBOX_FOLDER, batch)
            if os.path.isdir(b):
                out += [os.path.join(b, f) for f in os.listdir(b) if os.path.isfile(os.path.join(b, f))]
    return out


def _inbox_table(roots):
    rows = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        files, meta, skipped = scan_inbox(root, log=lambda *a: None)
        for f in files:
            m = meta.get(os.path.dirname(f), {}).get(os.path.basename(f), {})
            rows.append({"Group": m.get("group") or os.path.basename(os.path.dirname(f)),
                         "File": os.path.basename(f), "Sent by": m.get("sender", ""),
                         "When": m.get("timestamp", ""), "Caption": m.get("caption", "")})
    return rows


def page_import():
    header("Step 2 of 3", "Import your", "class groups.",
           "Export each WhatsApp group <b>with media</b> and drop the .zip files here. Loose PDFs and photos work too.")

    os.makedirs(INBOX_FOLDER, exist_ok=True)
    with st.expander("How to export a WhatsApp group (30 seconds)", expanded=True):
        st.markdown(
            "**Android:** open the group → ⋮ (top right) → **More** → **Export chat** → **Include media** → "
            "save the .zip to this laptop (e.g. send it to yourself on Google Drive or by USB).\n\n"
            "**iPhone:** open the group → tap the group name → **Export Chat** → **Attach Media** → save to Files "
            "and copy the .zip to this laptop.\n\n"
            "Do this for every class group, then drop all the .zip files below. Loose PDFs and photos work too.")
    ups = st.file_uploader("Drop WhatsApp export .zip files, chat .txt files, PDFs or photos",
                           accept_multiple_files=True, type=["zip", "txt", "pdf", "jpg", "jpeg", "png", "webp"])
    if ups and st.button(f"Add {len(ups)} file(s) to the inbox", type="primary"):
        # a file already in the inbox (same bytes) is not added again - sorting it twice only costs time
        have = {(os.path.getsize(p), file_hash(p)) for p in _uploaded_files()}
        new, again = [], []
        for u in ups:
            data = u.getbuffer()
            key = (len(data), hashlib.sha256(data).hexdigest())
            (again if key in have else new).append(u)
            have.add(key)
        if new:
            batch = os.path.join(INBOX_FOLDER, time.strftime("upload-%Y%m%d-%H%M%S"))
            os.makedirs(batch, exist_ok=True)
            for u in new:  # one folder per upload, so a chat .txt pairs with the media uploaded with it
                with open(os.path.join(batch, os.path.basename(u.name)), "wb") as f:
                    f.write(u.getbuffer())
        msg = f"Added {len(new)} file(s). Zips are unpacked automatically when you sort."
        if again:
            msg += f" Not added again (already in the inbox): {', '.join(u.name for u in again)}."
        st.success(msg)
        time.sleep(1.5 if again else 0.6)
        st.rerun()

    rows = _inbox_table([INBOX_FOLDER])
    st.markdown(f'<div class="kicker">INBOX · {len(rows)} NOTES READY TO SORT</div>', unsafe_allow_html=True)
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch", height=min(40 + 35 * len(rows), 480))
    else:
        st.caption("The inbox is empty. Drop files above, or copy them into the 'inbox' folder of the project.")
    c1, c2, _ = st.columns([1.3, 1.6, 3])
    if c1.button("Open inbox folder"):
        open_folder(INBOX_FOLDER)
    with c2.popover("Empty the inbox"):
        st.write("This deletes the copies inside slothNtidy's inbox folder. Your phone and WhatsApp are not touched.")
        if st.button("Yes, empty it"):
            shutil.rmtree(INBOX_FOLDER, ignore_errors=True)
            os.makedirs(INBOX_FOLDER, exist_ok=True)
            st.rerun()


# ====================================================================== 3 · Sort

def stagebar(active=-1, done_upto=-1):
    cells = []
    for i, s in enumerate(STAGES):
        cls = "done" if i <= done_upto else ("now" if i == active else "")
        tag = "✓ DONE" if i <= done_upto else f"STEP {i + 1}"
        cells.append(f'<div class="stage {cls}"><span class="s">{tag}</span>{s}</div>')
    return '<div class="stagebar">' + "".join(cells) + "</div>"


def gemma_panel():
    """Sort page: switch on Gemma 4 to read handwritten pages. Returns 'api', 'local' or None."""
    st.session_state.setdefault("gemma_key", os.environ.get("GEMINI_API_KEY", ""))
    with st.container(border=True):
        st.markdown("**Gemma 4 handwriting reader** · Tesseract cannot read handwriting, so handwritten notes "
                    "used to wait in *Needs review*. Gemma 4 (Google's open-weight, multimodal model) looks at "
                    "those pages and writes down what is on them. Its text then goes through the same keyword "
                    "matching as every other page, so every tick still points to a page number.")
        on = st.toggle("Read handwriting with Gemma 4", value=st.session_state.get("gemma_on", False),
                       key="gemma_on")
        if not on:
            return None
        where = st.radio("Where Gemma runs", ["Google Gemini API", "On this laptop (Ollama)"], key="gemma_where",
                         horizontal=True)
        backend = "api" if where == "Google Gemini API" else "local"
        if backend == "api":
            st.text_input("Gemini API key (free at aistudio.google.com)", type="password", key="gemma_key",
                          help="Kept only while this app is open. Never saved to a file or to GitHub.")
            st.caption(f"Model: {GEMMA_API_MODEL}. Only handwritten pages that Tesseract cannot read (at most a few "
                       "per file) are sent to Google. Everything else stays on this laptop.")
        else:
            st.caption(f"Model: {GEMMA_LOCAL_MODEL} through Ollama. Nothing leaves this laptop. One-time setup: "
                       f"ollama pull {GEMMA_LOCAL_MODEL}  (slow without a graphics card).")
        if st.button("Test Gemma connection", key="gemma_test"):
            with st.spinner("Asking Gemma..."):
                problem = check_connection(backend, st.session_state.get("gemma_key", "").strip())
            if problem:
                st.error(problem)
            else:
                st.success("Gemma 4 is answering. Ready to read handwriting.")
        st.caption("Answers are saved on this laptop (.gemma_cache), so sorting the same notes again is instant "
                   "and works without internet.")
        return backend


def page_sort():
    header("Step 3 of 3", "Sort my", "notes.",
           "Reads every file, removes circulars and duplicates, matches notes to your syllabus, files clean copies "
           "and builds one exam-ready PDF per unit. Your original files are never changed.")
    roots = selected_inboxes()
    n = len(_inbox_table(roots))
    n_units = len(load_syllabus())
    st.markdown(f'<div class="note"><span class="kicker">READY</span>{n} file(s) in your inbox · '
                f'syllabus with {n_units} units · '
                f'engine: {esc(embedder.name if embedder else "keyword evidence only")}</div>', unsafe_allow_html=True)
    buddy = st.empty()
    buddy.markdown('<div class="hero-mascot">' + sloth_with_bubble(
        "sleeping", f"Ready when you are. {n} file{'s' if n != 1 else ''} waiting - press <b>Sort my notes</b>.", px=7)
        + "</div>", unsafe_allow_html=True)
    bar = st.empty()
    bar.markdown(stagebar(), unsafe_allow_html=True)
    read_photos = st.toggle("Read photos too", value=st.session_state.get("read_photos", True), key="read_photos",
                            help="Photos (handwritten notes, board pictures) are read with OCR, which takes a few "
                                 "seconds each. Switch off to sort only the PDFs - much faster on a big group.")
    gemma_backend = gemma_panel()
    if not st.button("Sort my notes", type="primary", disabled=n == 0 or n_units == 0):
        if n_units == 0:
            st.caption("Add your syllabus first - go to 1 · Syllabus and upload a photo of it.")
        elif n == 0:
            st.caption("Nothing to sort yet - add files on the Import page.")
        return
    prog = st.progress(0.0, text="Starting...")
    log_box = st.expander("Live log", expanded=False)
    lines = []

    def log(msg=""):
        lines.append(str(msg))

    def progress(i, name, done, total, msg):
        bar.markdown(stagebar(active=i, done_upto=i - 1), unsafe_allow_html=True)
        buddy.markdown('<div class="hero-mascot">' + sloth_with_bubble(
            "working", f"Step {i + 1} of {len(STAGES)} · {esc(name)}<br>{esc(msg)[:70]}", px=7) + "</div>",
            unsafe_allow_html=True)
        frac = (i + (done / total if total else 1)) / len(STAGES)
        prog.progress(min(frac, 1.0), text=f"Stage {i + 1} · {name}: {msg}")

    gemma = None
    if gemma_backend:
        try:
            gemma = GemmaReader(gemma_backend, api_key=st.session_state.get("gemma_key", "").strip())
        except ValueError as e:
            st.error(str(e))
            return
    try:
        result = run(roots, SYLLABUS_FILE, embedder, progress=progress, log=log, read_photos=read_photos,
                     gemma=gemma)
    except FileNotFoundError as e:
        st.error(str(e))
        return
    except Exception as e:  # show the problem instead of a stack trace during a demo
        st.error(f"Something went wrong while sorting: {e}")
        log_box.code("\n".join(lines), language=None)
        return
    bar.markdown(stagebar(done_upto=len(STAGES) - 1), unsafe_allow_html=True)
    buddy.markdown('<div class="hero-mascot">' + sloth_with_bubble(
        "happy", f"All done! {result['counts']['total']} files → {result['counts']['kept']} notes "
                 f"in {result['seconds']} s. Opening your dashboard...", px=7) + "</div>", unsafe_allow_html=True)
    prog.progress(1.0, text=f"Done in {result['seconds']} s")
    log_box.code("\n".join(lines), language=None)
    st.session_state.result = result
    st.session_state.log = lines
    st.session_state.goto = "Coverage dashboard"
    time.sleep(0.8)
    st.rerun()


# ====================================================================== Coverage dashboard (deck slide 8)

def pack_buttons(where):
    """One 'exam pack' download per subject: all units in order, a divider + topic index before each unit."""
    packs = {k: v for k, v in (R.get("subject_packs") or {}).items() if v and os.path.exists(v)}
    if not packs:
        return
    st.markdown('<div class="kicker" style="margin-top:22px">EXAM PACK · ONE PDF PER SUBJECT, UNIT BY UNIT</div>',
                unsafe_allow_html=True)
    names = {u["subject_code"]: u["subject_name"] for u in R["units"]}
    for code, path in packs.items():
        a, b = st.columns([3, 1.4], vertical_alignment="center")
        with fitz.open(path) as p:
            n = p.page_count
        a.markdown(f"**{esc(names.get(code, code))}** · {n} pages · every unit starts with a divider page: "
                   "what is covered, what is missing, and a topic index with page numbers (overlapping topics "
                   "across units are listed together).")
        with open(path, "rb") as f:
            b.download_button("Download exam pack", f.read(), file_name=os.path.basename(path),
                              mime="application/pdf", type="primary", key=f"pack-{where}-{code}")


def request_message(row):
    return (f"Hi everyone! Does anyone have notes for {row['subject_name']} Unit {row['unit']} - {row['title']}? "
            f"I'm missing: {', '.join(row['missing'])}. Please share if you have them, thanks!")


def page_coverage():
    header("", "Coverage", "Dashboard.")
    if need_result():
        return
    if R.get("failed"):
        st.warning(f"{len(R['failed'])} file(s) could not be opened and were skipped (damaged or unusual format): "
                   + ", ".join(f["name"] for f in R["failed"][:8]) + (" ..." if len(R["failed"]) > 8 else ""))
    if R.get("photos_off"):
        st.info(f"{R['photos_off']} photo(s) were not read because \"Read photos too\" was switched off on the Sort page.")
    g = R.get("gemma")
    if g:
        if g.get("pages"):
            st.success(f"Gemma 4 read {g['pages']} handwritten page(s) in {g['docs']} file(s) "
                       f"({g['name']}). Open the Cluster Inspector to see each page next to Gemma's transcript.")
        if g.get("disabled"):
            st.warning("Gemma 4 stopped after repeated errors, so the remaining handwritten pages used Tesseract: "
                       + str(g.get("error", "")))
    c, units = R["counts"], R["units"]
    ready = sum(u["status"] == "READY" for u in units)
    missing = sum(u["status"] == "MISSING" for u in units)
    review = sum(u["status"] == "NEEDS REVIEW" for u in units)
    st.markdown(f"""<div class="stats">
      <div class="stat"><div class="n">{c['total']}</div><div class="l">Files in</div></div>
      <div class="stat"><div class="n">{c['circulars'] + c['exact_dups'] + c['near_dups']}</div><div class="l">Noise removed</div></div>
      <div class="stat"><div class="n">{c['kept']}</div><div class="l">Notes kept</div></div>
      <div class="stat ok"><div class="n">{ready}</div><div class="l">Units ready</div></div>
      <div class="stat blue"><div class="n">{review}</div><div class="l">Need review</div></div>
      <div class="stat red"><div class="n">{missing}</div><div class="l">Units missing</div></div>
    </div>""", unsafe_allow_html=True)

    subjects = list(dict.fromkeys(u["subject_name"] for u in units))
    pick = st.segmented_control("Subject", ["All subjects"] + subjects, default="All subjects",
                                label_visibility="collapsed") or "All subjects"
    shown = [u for u in units if pick == "All subjects" or u["subject_name"] == pick]

    st.markdown('<div class="thead"><div>Topic cluster</div><div>What is covered</div><div>What is not covered</div>'
                '<div>Status</div><div>Action</div></div>', unsafe_allow_html=True)
    for u in shown:
        st_cls = u["status"].split()[0]
        with st.container(key=f"row-{st_cls}-{u['unit_id']}"):
            cols = st.columns([2.1, 2.2, 2.6, 1.35, 1.45], vertical_alignment="center")
            title_cls = "cell miss" if u["status"] == "MISSING" else "cell"
            cols[0].markdown(f'<div class="{title_cls}"><b>{esc(u["subject_code"])} · Unit {u["unit"]}: '
                             f'{esc(u["title"])}</b></div>', unsafe_allow_html=True)
            cov = ", ".join(u["covered"]) if u["covered"] else "Zero matched files"
            cols[1].markdown(f'<div class="{"cell miss" if not u["covered"] else "cell muted"}">{esc(cov)}</div>',
                             unsafe_allow_html=True)
            if not u["missing"]:
                nc = '<div class="cell muted">All sub-topics present</div>'
            elif u["status"] == "MISSING":
                nc = f'<div class="cell miss">{esc(", ".join(u["missing"]))}</div>'
            else:
                extra = f' - {len(u["review_files"])} candidate match(es) to review' if u["review_files"] else ""
                nc = f'<div class="cell review">{esc(", ".join(u["missing"]))}{esc(extra)}</div>'
            cols[2].markdown(nc, unsafe_allow_html=True)
            label = {"READY": f"{u['pages']} PAGE{'S' if u['pages'] != 1 else ''} READY", "NEEDS REVIEW": "NEEDS REVIEW",
                     "MISSING": "MISSING (RED)"}[u["status"]]
            cols[3].markdown(f'<div class="status {st_cls}">{label}</div>', unsafe_allow_html=True)
            with cols[4]:
                if u.get("export_path") and os.path.exists(u["export_path"]):
                    with open(u["export_path"], "rb") as f:
                        st.download_button("Merge PDF →", f.read(), file_name=os.path.basename(u["export_path"]),
                                           mime="application/pdf", key=f"dl-{u['unit_id']}")
                if u["status"] == "MISSING":
                    with st.popover("Request notes !"):
                        st.caption("Copy this into your class group:")
                        st.code(request_message(u), language=None, wrap_lines=True)
                elif u["status"] == "NEEDS REVIEW":
                    if st.button("Inspect →", key=f"insp-{u['unit_id']}"):
                        st.session_state.inspect_unit = u["unit_id"]
                        st.session_state.goto = "Cluster inspector"
                        st.rerun()
    st.container(key="lastrow")
    pack_buttons("dash")

    st.markdown('<div class="how"><b>HOW A GAP IS DECIDED</b><br>After de-duplication, every subtopic '
                'is searched for on the pages of each note. COVERED = its keywords appear on a page (we show which '
                'page). MISSING = no note covers it. NEEDS REVIEW = some subtopics are still missing, or a note fits '
                'more than one unit - shown to you, never guessed.</div>', unsafe_allow_html=True)
    if os.path.exists(REPORT_MD):
        with open(REPORT_MD, "rb") as f:
            st.download_button("Download the report (COVERAGE.md)", f.read(), file_name="COVERAGE.md",
                               mime="text/markdown")


# ====================================================================== Noise reduction (deck slide 9)

def page_noise():
    header("", "Noise", "Reduction.")
    if need_result():
        return
    c, m = R["counts"], R["match_counts"]
    total = max(c["total"], 1)
    dups = c["exact_dups"] + c["near_dups"]
    rows = [("Raw files from your groups", c["total"], "#2E4741"),
            ("Circulars & official notices removed", c["circulars"], "#E2A834"),
            ("Duplicate & overlapping copies removed", dups, "#E0675E"),
            ("Notes kept", c["kept"], "#2E6B4F")]
    html = ""
    for lab, n, col in rows:
        pct = n / total
        html += (f'<div class="funnel-row"><div class="lab">{lab}</div><div class="bar">'
                 f'<div class="fill" style="width:{pct * 100:.1f}%;background:{col}"></div></div>'
                 f'<div class="num">{n} of {c["total"]} ({pct:.0%})</div></div>')
    st.markdown(f'<div class="card">{html}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="how"><b>METHOD</b> · {c["total"]} files from {len(R.get("groups", [])) or "your"} '
                f'group(s). Filters run in order - circulars first, then exact copies (SHA-256), then near-copies '
                f'(text similarity and pHash for photos) - so the categories never overlap: '
                f'{c["circulars"]} + {dups} + {c["kept"]} = {c["total"]}. Of the {c["kept"]} kept notes, '
                f'{m.get("sorted", 0)} were sorted into units, {m.get("needs-review", 0)} need your review and '
                f'{m.get("unmatched", 0)} matched nothing in the syllabus.</div>', unsafe_allow_html=True)

    removed = [d for d in R["documents"] if d.get("status") in ("circular", "exact_dup", "near_dup")]
    if removed:
        st.markdown('<div class="kicker">EVERY REMOVAL, WITH ITS REASON</div>', unsafe_allow_html=True)
        st.dataframe([{"File": d["orig_name"], "Group": d.get("group", ""),
                       "Removed because": d.get("removed_reason", ""), "Detail": d.get("dup_reason", "")}
                      for d in removed], hide_index=True, width="stretch")
        st.caption("Nothing is deleted - removed files are copied to SlothVault/_Removed so you can check them. "
                   "Use 'Review & duplicates' to bring any of them back.")


# ====================================================================== Cluster inspector (deck slide 7)

def _ts(d):
    t = d.get("timestamp", "")
    return t.split(",")[-1].strip() if t else "--:--"


READER_NAMES = {"pdf": "PDF text", "tesseract": "Tesseract OCR", "gemma": "Gemma 4", "none": "-"}


def read_by(file_name, pages):
    """Which reader produced the text on these pages (shown next to every piece of evidence)."""
    d = doc_by_name(file_name)
    readers = (d or {}).get("page_readers") or []
    names = {READER_NAMES.get(readers[p - 1], "?") for p in pages if 0 < p <= len(readers)}
    return ", ".join(sorted(names)) or "PDF text"


def page_inspector():
    header("", "Cluster", "Inspector.")
    if need_result():
        return
    units = R["units"]
    ids = [u["unit_id"] for u in units]
    default = ids.index(st.session_state.get("inspect_unit")) if st.session_state.get("inspect_unit") in ids else 0
    uid = st.selectbox("Unit", ids, index=default,
                       format_func=lambda i: next(f"{u['subject_code']} · Unit {u['unit']}: {u['title']}  ({u['status']})"
                                                  for u in units if u["unit_id"] == i))
    row = next(u for u in units if u["unit_id"] == uid)
    docs = [d for d in R["documents"] if d.get("unit_id") == uid]
    review = [d for d in R["documents"] if d["orig_name"] in row["review_files"]]

    left, right = st.columns([1.15, 1], gap="large")
    with left:
        lines = [f'<span class="k">CLUSTER INSPECTOR · {esc(row["subject_code"])} UNIT {row["unit"]} '
                 f'{esc(row["title"]).upper()}</span>']
        for d in docs + review:
            who = esc(d.get("sender") or "unknown sender")
            grp = f' <span class="ts">· {esc(d["group"])}</span>' if d.get("group") else ""
            lines.append(f'<span class="ts">[{esc(_ts(d))}]</span> <span class="who">{who}:</span> '
                         f'{esc(d["orig_name"])}{grp}')
            if d.get("caption"):
                lines.append(f'<span class="ts">[{esc(_ts(d))}]</span> <span class="who">{who}:</span> '
                             f'<span class="cap">"{esc(d["caption"])}"</span>')
            if d in review:
                lines.append(f'<span class="rv">[NEEDS REVIEW]</span> {esc(d.get("reason", ""))}')
        if not docs and not review:
            lines.append('<span class="ts">no messages matched this unit</span>')
        lines.append("<hr>")
        if row["covered"]:
            lines.append(f'<span class="cov">[COVERED]</span> {esc(", ".join(row["covered"]))}')
        if row["missing"]:
            lines.append(f'<span class="nc">[NOT COVERED]</span> {esc(", ".join(row["missing"]))} (0 pages)')
        st.markdown('<div class="chat">' + "<br>".join(lines) + "</div>", unsafe_allow_html=True)

        st.markdown('<div class="kicker" style="margin-top:22px">EVIDENCE · WHERE EACH SUBTOPIC WAS FOUND</div>',
                    unsafe_allow_html=True)
        ev = []
        for stp, srcs in row["evidence"].items():
            for s in srcs:
                ev.append({"Subtopic": stp, "File": s["file"], "Page(s)": ", ".join(map(str, s["pages"])),
                           "Read by": read_by(s["file"], s["pages"]),
                           "From": " · ".join(x for x in (s.get("sender"), s.get("group")) if x)})
        for stp in row["missing"]:
            ev.append({"Subtopic": stp, "File": "-", "Page(s)": "-", "Read by": "-", "From": "not found in any note"})
        st.dataframe(ev, hide_index=True, width="stretch")

    with right:
        pool = docs or review
        if not pool:
            st.markdown('<div class="note"><span class="kicker">NO NOTES YET</span>Nobody has shared notes for this '
                        'unit. Use <b>Request notes</b> on the dashboard to ask your class.</div>', unsafe_allow_html=True)
        else:
            options = []
            for d in pool:
                hit_pages = sorted({p for ps in d.get("hits", {}).get(uid, {}).values() for p in ps}) or [1]
                for p in hit_pages:
                    options.append((d["orig_name"], p))
            sel = st.selectbox("Original page", options, format_func=lambda o: f"{o[0]} - page {o[1]}")
            d = doc_by_name(sel[0])
            hits_here = [s for s, ps in d.get("hits", {}).get(uid, {}).items() if sel[1] in ps]
            st.markdown("".join(f'<span class="tag ok">{esc(h)}</span>' for h in hits_here) or
                        '<span class="tag blue">no keyword on this page</span>', unsafe_allow_html=True)
            preview(d, sel[1] - 1, dpi=80)
            readers = d.get("page_readers") or []
            if sel[1] - 1 < len(readers) and readers[sel[1] - 1] == "gemma":
                st.markdown('<span class="tag ok">handwriting read by Gemma 4</span>', unsafe_allow_html=True)
                with st.expander("What Gemma 4 read on this page", expanded=True):
                    st.text(d["page_texts"][sel[1] - 1][:3000])

    sc = ""
    if docs and docs[0].get("scores"):
        sc = f" + MiniLM similarity {docs[0]['scores'].get(uid, 0):.2f}"
    st.markdown('<div class="how"><b>HOW THE MATCH WORKS</b> · page text (OCR for photos) → keyword evidence per '
                f'subtopic{esc(sc)} → most evidence wins the unit → equal evidence for two units = NEEDS REVIEW. '
                'Captions help suggest a unit but never tick a subtopic ("recovery skipped" must not count as '
                'Recovery).</div>', unsafe_allow_html=True)


# ====================================================================== Review & duplicates

def review_bulk_bar(review, options, fmt):
    """Decide several files at once: tick them (or pick all unreadable ones) and file them in one go.
    Decisions apply to this sort only - nothing is remembered for the next one."""
    unreadable = [d for d in review if d.get("status") == "unreadable" or d.get("chars", 0) < 60]
    ticked = [d for d in review if st.session_state.get(f"tick-{d['path']}")]
    with st.container(border=True):
        st.markdown("**Several files at once** · tick files below, then file them together. "
                    "Handwritten or unreadable notes from other subjects can be cleared in one click.")
        c1, c2, c3 = st.columns([1, 1, 1.6])
        if c1.button("Tick all", key="tick-all"):
            for d in review:
                st.session_state[f"tick-{d['path']}"] = True
            st.rerun()
        if c2.button("Untick all", key="tick-none", disabled=not ticked):
            for d in review:
                st.session_state[f"tick-{d['path']}"] = False
            st.rerun()
        if unreadable and c3.button(f"Tick the {len(unreadable)} unreadable file(s)", key="tick-unreadable"):
            for d in review:
                st.session_state[f"tick-{d['path']}"] = d in unreadable
            st.rerun()
        d1, d2 = st.columns([2.2, 1.4], vertical_alignment="bottom")
        target = d1.selectbox("Put the ticked files in", options, index=options.index("__none__"),
                              format_func=fmt, key="bulk-target")
        if d2.button(f"Apply to {len(ticked)} ticked file(s)", type="primary", disabled=not ticked, key="bulk-apply"):
            decide_many(R, [d["path"] for d in ticked], None if target == "__none__" else target, log=lambda *a: None)
            for d in review:
                st.session_state.pop(f"tick-{d['path']}", None)
            st.toast(f"Filed {len(ticked)} file(s). Dashboard and merged PDFs updated.")
            st.rerun()


def page_review():
    header("", "Review &", "duplicates.",
           "Uncertain matches and removed files are shown to you - never silently assigned or deleted.")
    if need_result():
        return
    ub = units_by_id()
    options = list(ub) + ["__none__"]
    fmt = lambda i: "Not in syllabus" if i == "__none__" else unit_label(ub[i])  # noqa: E731

    review = [d for d in R["documents"] if d.get("coverage") == "needs-review" and d.get("status") in ("kept", "unreadable")]
    st.markdown(f'<div class="kicker">NEEDS YOUR DECISION · {len(review)}</div>', unsafe_allow_html=True)
    if not review:
        st.caption("Nothing to decide.")
    else:
        review_bulk_bar(review, options, fmt)
    for d in review:
        with st.container(border=True):
            st.checkbox("Tick to decide together with others", key=f"tick-{d['path']}")
            a, b = st.columns([1, 2.4], gap="medium")
            with a:
                preview(d, 0, dpi=45)
            with b:
                st.markdown(f"**{d['orig_name']}**  \n"
                            f"{esc(d.get('sender') or 'unknown sender')} · {esc(d.get('group') or 'no group')} · "
                            f"{esc(d.get('timestamp') or '')}")
                if d.get("caption"):
                    st.markdown(f'Caption: *"{esc(d["caption"])}"*')
                st.markdown(f'<span class="tag blue">NEEDS REVIEW</span> {esc(d.get("reason", ""))}',
                            unsafe_allow_html=True)
                sug = d.get("suggested_unit_id")
                c1, c2 = st.columns([2.2, 1])
                choice = c1.selectbox("Put it in", options, index=options.index(sug) if sug in options else 0,
                                      format_func=fmt, key=f"rv-{d['orig_name']}")
                c2.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if c2.button("Confirm", key=f"rvb-{d['orig_name']}", type="primary"):
                    if choice == "__none__":
                        mark_not_in_syllabus(R, d["orig_name"], log=lambda *a: None)
                    else:
                        assign_to_unit(R, d["orig_name"], choice, log=lambda *a: None)
                    st.toast("Filed. Dashboard and merged PDFs updated.")
                    st.rerun()

    dups = [d for d in R["documents"] if d.get("status") in ("exact_dup", "near_dup")]
    st.markdown(f'<div class="kicker" style="margin-top:26px">REMOVED AS DUPLICATES · {len(dups)}</div>',
                unsafe_allow_html=True)
    for d in dups:
        kept = doc_by_name(d.get("dup_of"))
        with st.container(border=True):
            st.markdown(f'<span class="tag {"red" if d["status"] == "exact_dup" else "blue"}">'
                        f'{"EXACT COPY" if d["status"] == "exact_dup" else "NEAR COPY"}</span> {esc(d.get("dup_reason", ""))}',
                        unsafe_allow_html=True)
            a, b, c = st.columns([1, 1, 1.1], gap="medium")
            with a:
                st.caption(f"KEPT · {kept['orig_name'] if kept else d.get('dup_of')}"
                           + (f" · {kept['pages']} p. · {kept.get('group', '')}" if kept else ""))
                if kept:
                    preview(kept, 0, dpi=40)
            with b:
                st.caption(f"REMOVED · {d['orig_name']} · {d['pages']} p. · {d.get('group', '')}")
                preview(d, 0, dpi=40)
            with c:
                st.markdown(f"Sent by **{esc(d.get('sender') or 'unknown')}**"
                            + (f" in {esc(d['group'])}" if d.get("group") else ""))
                st.caption("We keep the fuller copy (more pages, more text, sharper photo).")
                if st.button("Not a duplicate - keep both", key=f"keep-{d['orig_name']}"):
                    restore_removed(R, d["orig_name"], embedder, log=lambda *a: None)
                    st.toast(f"{d['orig_name']} is back and has been matched to your syllabus.")
                    st.rerun()

    circ = [d for d in R["documents"] if d.get("status") == "circular"]
    st.markdown(f'<div class="kicker" style="margin-top:26px">REMOVED AS CIRCULARS · {len(circ)}</div>',
                unsafe_allow_html=True)
    for d in circ:
        with st.container(border=True):
            a, b = st.columns([3, 1.1], vertical_alignment="center")
            a.markdown(f"**{d['orig_name']}** · {esc(d.get('group') or '')}  \n{esc(d.get('removed_reason', ''))}")
            if b.button("Not a circular - keep it", key=f"circ-{d['orig_name']}"):
                restore_removed(R, d["orig_name"], embedder, log=lambda *a: None)
                st.rerun()

    other = [d for d in R["documents"] if d.get("coverage") == "unmatched" and d.get("status") in ("kept", "unreadable")]
    if other:
        st.markdown(f'<div class="kicker" style="margin-top:26px">NOT IN YOUR SYLLABUS · {len(other)}</div>',
                    unsafe_allow_html=True)
        for d in other:
            with st.container(border=True):
                a, b = st.columns([1, 3], gap="medium")
                with a:
                    preview(d, 0, dpi=35)
                with b:
                    st.markdown(f"**{d['orig_name']}** · {esc(d.get('sender') or '')} · {esc(d.get('group') or '')}"
                                + (f'  \nCaption: *"{esc(d["caption"])}"*' if d.get("caption") else ""))
                    st.caption(d.get("reason", ""))
                    c1, c2 = st.columns([2.2, 1])
                    choice = c1.selectbox("Move to", list(ub), format_func=lambda i: unit_label(ub[i]),
                                          key=f"un-{d['orig_name']}")
                    c2.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                    if c2.button("Move", key=f"unb-{d['orig_name']}"):
                        assign_to_unit(R, d["orig_name"], choice, log=lambda *a: None)
                        st.rerun()


# ====================================================================== Sorted vault

def _tree(root, prefix=""):
    out = []
    try:
        entries = sorted(os.listdir(root), key=lambda n: (not os.path.isdir(os.path.join(root, n)), n.startswith("_"), n))
    except OSError:
        return out
    for i, n in enumerate(entries):
        last = i == len(entries) - 1
        p = os.path.join(root, n)
        out.append(f"{prefix}{'└── ' if last else '├── '}{n}{'/' if os.path.isdir(p) else ''}")
        if os.path.isdir(p):
            out += _tree(p, prefix + ("    " if last else "│   "))
    return out


def page_vault():
    header("", "Sorted", "vault.",
           "Clean, renamed copies of every note, filed by subject and unit. Your originals stay where they were.")
    if need_result():
        return
    c1, c2, c3, _ = st.columns([1.4, 1.4, 1.6, 2])
    if c1.button("Open SlothVault folder", type="primary"):
        open_folder(VAULT_FOLDER)
    if c2.button("Open merged PDFs folder"):
        open_folder(os.path.join(OUTPUT_FOLDER, "TopicPDFs"))
    if c3.button("Open output folder"):
        open_folder(OUTPUT_FOLDER)
    if os.path.isdir(VAULT_FOLDER):
        st.markdown('<div class="tree">SlothVault/\n' + esc("\n".join(_tree(VAULT_FOLDER))) + "</div>",
                    unsafe_allow_html=True)
    pack_buttons("vault")
    st.markdown('<div class="kicker" style="margin-top:22px">EXAM-READY PDFS · ONE PER UNIT, ORIGINAL PAGES</div>',
                unsafe_allow_html=True)
    for u in R["units"]:
        if u.get("export_path") and os.path.exists(u["export_path"]):
            a, b = st.columns([3, 1.2], vertical_alignment="center")
            a.markdown(f"**{u['subject_code']} · Unit {u['unit']}: {u['title']}** · {u['pages']} pages · "
                       f"{len(u['files'])} source(s)")
            with open(u["export_path"], "rb") as f:
                b.download_button("Download PDF", f.read(), file_name=os.path.basename(u["export_path"]),
                                  mime="application/pdf", key=f"vdl-{u['unit_id']}")
    st.markdown('<div class="how"><b>WHAT WE NEVER DO</b> · no OCR text replacing scans · no AI summaries of your notes '
                '· no re-rendering or recompression of pages. Each merged PDF starts with a cover page listing what '
                'is covered (with source and page) and what is missing.</div>', unsafe_allow_html=True)


# ====================================================================== router

{
    "1 · Syllabus": page_syllabus,
    "2 · Import chats": page_import,
    "3 · Sort": page_sort,
    "Coverage dashboard": page_coverage,
    "Noise reduction": page_noise,
    "Cluster inspector": page_inspector,
    "Review & duplicates": page_review,
    "Sorted vault": page_vault,
}[page]()
