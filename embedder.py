"""Local embeddings: turn a piece of text into a list of numbers that captures its meaning.
Texts about similar things get similar numbers, so we can measure "how close is this
note to this syllabus unit" with cosine similarity.

Backends, tried in this order when EMBED_BACKEND = "auto":
  1. MiniLM (all-MiniLM-L6-v2) via sentence-transformers - 90 MB, runs on any laptop CPU
  2. Ollama's nomic-embed-text - if the Ollama app is running
  3. None - the pipeline still works using keyword evidence only

Everything runs on this computer. No text is sent to the internet.
"""
import os

from config import EMBED_BACKEND, MINILM_MODEL, OLLAMA_HOST, OLLAMA_MODEL


def cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return 0.0 if na == 0.0 or nb == 0.0 else dot / (na * nb)


class MiniLMEmbedder:
    name = "MiniLM (all-MiniLM-L6-v2, local)"

    def __init__(self):
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        from sentence_transformers import SentenceTransformer
        try:  # use the copy downloaded by setup; never touch the internet during a demo
            self.model = SentenceTransformer(MINILM_MODEL, device="cpu", local_files_only=True)
        except TypeError:  # very old sentence-transformers without local_files_only
            self.model = SentenceTransformer(MINILM_MODEL, device="cpu")

    def embed(self, texts: list) -> list:
        return [list(map(float, v)) for v in self.model.encode(texts, normalize_embeddings=True)]


class OllamaEmbedder:
    name = f"Ollama ({OLLAMA_MODEL}, local)"

    def __init__(self):
        import requests
        self.requests = requests
        tags = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=1.5).json()
        names = [m.get("name", "") for m in tags.get("models", [])]
        if not any(n.startswith(OLLAMA_MODEL) for n in names):
            raise RuntimeError(f"Ollama is running but '{OLLAMA_MODEL}' is not pulled")

    def embed(self, texts: list) -> list:
        out = []
        for t in texts:
            r = self.requests.post(f"{OLLAMA_HOST}/api/embeddings",
                                   json={"model": OLLAMA_MODEL, "prompt": t[:2000]}, timeout=120)
            r.raise_for_status()
            out.append(r.json()["embedding"])
        return out


def load_embedder(backend: str = EMBED_BACKEND, log=print):
    """Returns an embedder object, or None if no local model is available."""
    order = {"auto": [MiniLMEmbedder, OllamaEmbedder], "minilm": [MiniLMEmbedder],
             "ollama": [OllamaEmbedder], "none": []}.get(backend, [MiniLMEmbedder, OllamaEmbedder])
    for cls in order:
        try:
            emb = cls()
            log(f"   [AI] matching engine: {emb.name}")
            return emb
        except Exception as e:  # not installed / not downloaded / not running
            log(f"   [AI] {cls.name} unavailable ({type(e).__name__})")
    log("   [AI] no embedding model found - using keyword evidence only")
    return None
