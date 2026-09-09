from typing import Protocol

import httpx

MODEL = "qwen3:8b"
SETTINGS = {"temperature": 0.1, "num_ctx": 16384, "num_predict": 1200}


class Provider(Protocol):
    async def chat(self, messages: list, tools: list | None = None) -> dict: ...


class OllamaProvider:
    def __init__(self, model=MODEL):
        self.model = model

    async def chat(self, messages, tools=None):
        async with httpx.AsyncClient(timeout=100) as c:
            response = await c.post(
                "http://127.0.0.1:11434/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "tools": tools or [],
                    "stream": False,
                    "think": False,
                    "options": SETTINGS,
                    "keep_alive": "30m",
                },
            )
            response.raise_for_status()
            return response.json()

    async def metadata(self):
        async with httpx.AsyncClient(timeout=10) as c:
            tags = (await c.get("http://127.0.0.1:11434/api/tags")).json()["models"]
        model = next(m for m in tags if m["name"] == self.model)
        return {
            "provider": "ollama-local",
            "model": self.model,
            "digest": model["digest"],
            "settings": SETTINGS,
            "thinking": False,
        }
