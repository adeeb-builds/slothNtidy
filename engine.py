import json
import requests

class SlothEngine:
    """Handles offline, zero-cost inference via a local Ollama instance."""
    
    def __init__(self, model: str = "qwen2.5:7b", host: str = "http://localhost:11434"):
        self.model = model
        self.api_url = f"{host}/api/generate"

    def ask_json(self, system_prompt: str, user_content: str) -> dict:
        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_content,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_ctx": 2048  # Speeds up local inference significantly
            }
        }
        response = requests.post(self.api_url, json=payload, timeout=300)
        response.raise_for_status()
        return json.loads(response.json()["response"])

# Optional quick test if you run `python engine.py` directly:
if __name__ == "__main__":
    engine = SlothEngine(model="qwen2.5:7b")
    reply = engine.ask_json("Return a JSON object with key 'status'", "Say hello like a sloth")
    print("🦥 Engine test reply:", reply)