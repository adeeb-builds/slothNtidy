"""Stage 4 (match): embeds each surviving document and each syllabus topic,
then maps by cosine similarity. Confident -> covered. Borderline ->
needs-review. No good match -> missing. Uncertain files are FLAGGED,
never silently assigned."""
from engine import SlothEngine
from config import MATCH_COVERED, MATCH_REVIEW, MIN_TEXT_CHARS

def cosine(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)

def match(docs: list, syllabus: list, engine: SlothEngine, log=print):
    topic_emb = [
        engine.embed(f'{t["subject"]} unit {t["unit"]}: {t["topic"]} - {", ".join(t["subtopics"])}')
        for t in syllabus
    ]
    results = []
    for d in docs:
        if d.get("status") in ("circular", "exact_dup", "near_dup"):
            continue
        if d.get("chars", 0) < MIN_TEXT_CHARS and not d.get("ocr_used"):
            d.update(coverage="needs-review", topic=None,
                     reason="unreadable scan - no clean text, OCR unavailable")
            results.append(d)
            continue
        emb = engine.embed(d["text"][:2000])
        scores = [cosine(emb, te) for te in topic_emb]
        best_i = max(range(len(scores)), key=lambda i: scores[i])
        score = scores[best_i]
        d["score"] = round(score, 3)
        if score >= MATCH_COVERED:
            d["coverage"], d["topic"] = "covered", syllabus[best_i]
        elif score >= MATCH_REVIEW:
            d["coverage"] = "needs-review"
            d["topic"] = syllabus[best_i]
            d["reason"] = f"best topic '{syllabus[best_i]['topic']}' at {score:.2f}, below {MATCH_COVERED}"
        else:
            d["coverage"], d["topic"] = "missing", None
            d["reason"] = f"no syllabus topic above {MATCH_REVIEW} (best {score:.2f})"
        results.append(d)
        label = d["topic"]["topic"] if d["topic"] else "-"
        log(f"   [{d['coverage'].upper()}] {d['orig_name']} -> {label} ({score:.2f})")
    return results