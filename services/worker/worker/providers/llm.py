"""LLM : sortie JSON validée par un modèle Pydantic. Anthropic (défaut) ou Ollama (local)."""

from __future__ import annotations

import json
import re
from typing import Protocol, TypeVar

import httpx
from pydantic import BaseModel

from ..config import Settings

T = TypeVar("T", bound=BaseModel)


class LLM(Protocol):
    name: str

    def complete_json(self, system: str, user: str, schema: type[T]) -> T: ...


def _parse(text: str, schema: type[T]) -> T:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"réponse sans JSON : {text[:200]}")
    return schema.model_validate(json.loads(m.group(0)))


class AnthropicLLM:
    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        from anthropic import Anthropic

        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    def complete_json(self, system: str, user: str, schema: type[T]) -> T:
        schema_hint = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=f"{system}\n\nSchéma JSON attendu : {schema_hint}",
            messages=[{"role": "user", "content": user}],
        )
        return _parse("".join(b.text for b in msg.content if getattr(b, "type", "") == "text"), schema)


class OllamaLLM:
    name = "ollama"

    def __init__(self, settings: Settings) -> None:
        self.base, self.model = settings.ollama_base_url, settings.ollama_model

    def complete_json(self, system: str, user: str, schema: type[T]) -> T:
        r = httpx.post(
            f"{self.base}/api/chat",
            timeout=300,
            json={
                "model": self.model,
                "stream": False,
                "format": schema.model_json_schema(),
                "keep_alive": 0,  # libère la VRAM pour ComfyUI après l'appel
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            },
        )
        r.raise_for_status()
        return _parse(r.json()["message"]["content"], schema)


def get_llm(settings: Settings) -> LLM:
    return OllamaLLM(settings) if settings.llm_provider == "ollama" else AnthropicLLM(settings)
