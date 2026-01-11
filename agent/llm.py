from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    model: str = "gpt-4o-mini"


class OpenAIChatLLM:
    """
    Minimal OpenAI Chat Completions client.
    We keep this tiny (no extra deps) and streaming-friendly for the UI.
    """

    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg

    @staticmethod
    def from_env() -> Optional["OpenAIChatLLM"]:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return None
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
        return OpenAIChatLLM(LLMConfig(api_key=api_key, model=model))

    def chat(self, messages: List[Dict[str, str]], *, temperature: float = 0.2, timeout: float = 30.0) -> str:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.cfg.api_key}", "Content-Type": "application/json"},
            json={"model": self.cfg.model, "messages": messages, "temperature": temperature},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def chat_stream(
        self, messages: List[Dict[str, str]], *, temperature: float = 0.2, timeout: float = 60.0
    ) -> Iterator[str]:
        with requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.cfg.api_key}", "Content-Type": "application/json"},
            json={"model": self.cfg.model, "messages": messages, "temperature": temperature, "stream": True},
            stream=True,
            timeout=timeout,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                    delta = obj["choices"][0].get("delta", {}).get("content")
                    if delta:
                        yield delta
                except Exception:
                    continue

