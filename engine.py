import json
import requests

class SlothEngine:
    def __init__(self, model="qwen2.5:7b", host="http://localhost:11434"):
        self.model = model
        self.api_url = f"{host}/api/generate"
        self.embed_url = f"{host}/api/embeddings"

    def generate(self, prompt: str, system_prompt: str = "", json_mode: bool = True) -> str:
        """Sends prompt to local Ollama instance and returns the text response."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_ctx": 2048
            }
        }
        if system_prompt:
            payload["system"] = system_prompt
        if json_mode:
            payload["format"] = "json"

        response = requests.post(self.api_url, json=payload, timeout=300)
        response.raise_for_status()
        return response.json().get("response", "")

    def embed(self, text: str) -> list:
        """Local embeddings via Ollama - used by the syllabus matcher."""
        response = requests.post(
            self.embed_url,
            json={"model": "nomic-embed-text", "prompt": text[:2000]},
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["embedding"]

# Optional quick test if you run `python engine.py` directly:
if __name__ == "__main__":
    engine = SlothEngine(model="qwen2.5:7b")
    reply = engine.generate("Say hello like a sloth", "Return a JSON object with key 'status'")
    print("🦥 Engine test reply:", reply)