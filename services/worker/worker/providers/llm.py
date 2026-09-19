"""LLM : sortie JSON validée par un modèle Pydantic.

Fournisseurs : anthropic (défaut), mistral, gemini, ollama (local).
`LLM_PROVIDER` choisit le principal, `LLM_FALLBACKS` la chaîne de secours (dans l'ordre) :
un fournisseur qui échoue (réseau, quota, JSON invalide) passe la main au suivant.
"""

from __future__ import annotations

import json
import re
from typing import Protocol, TypeVar

import httpx
import structlog
from pydantic import BaseModel

from ..config import Settings

log = structlog.get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLM(Protocol):
    name: str

    def complete_json(self, system: str, user: str, schema: type[T]) -> T: ...


def _parse(text: str, schema: type[T]) -> T:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"réponse sans JSON : {text[:200]}")
    return schema.model_validate(json.loads(m.group(0)))


def _schema_hint(schema: type[BaseModel]) -> str:
    return "\n\nRéponds uniquement avec un objet JSON conforme à ce schéma : " + json.dumps(
        schema.model_json_schema(), ensure_ascii=False
    )


class AnthropicLLM:
    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        from anthropic import Anthropic

        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    def complete_json(self, system: str, user: str, schema: type[T]) -> T:
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system + _schema_hint(schema),
            messages=[{"role": "user", "content": user}],
        )
        return _parse("".join(b.text for b in msg.content if getattr(b, "type", "") == "text"), schema)


class MistralLLM:
    name = "mistral"

    def __init__(self, settings: Settings) -> None:
        self.key, self.model = settings.mistral_api_key, settings.mistral_model

    def complete_json(self, system: str, user: str, schema: type[T]) -> T:
        r = httpx.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.key}"},
            json={
                "model": self.model,
                "temperature": 0.7,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system + _schema_hint(schema)},
                    {"role": "user", "content": user},
                ],
            },
            timeout=120,
        )
        r.raise_for_status()
        return _parse(r.json()["choices"][0]["message"]["content"], schema)


class GeminiLLM:
    name = "gemini"

    def __init__(self, settings: Settings) -> None:
        self.key, self.model = settings.gemini_api_key, settings.gemini_model

    def complete_json(self, system: str, user: str, schema: type[T]) -> T:
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self.key or ""},
            json={
                "system_instruction": {"parts": [{"text": system + _schema_hint(schema)}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7},
            },
            timeout=120,
        )
        r.raise_for_status()
        return _parse(r.json()["candidates"][0]["content"]["parts"][0]["text"], schema)


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


class FallbackLLM:
    """Essaie chaque fournisseur dans l'ordre ; le premier qui répond un JSON valide gagne."""

    def __init__(self, chain: list[LLM]) -> None:
        self.chain = chain
        self.name = " > ".join(p.name for p in chain)

    def complete_json(self, system: str, user: str, schema: type[T]) -> T:
        last: Exception | None = None
        for provider in self.chain:
            try:
                return provider.complete_json(system, user, schema)
            except Exception as exc:  # noqa: BLE001
                last = exc
                log.warning("llm.fallback", provider=provider.name, error=str(exc)[:300])
        raise RuntimeError(f"tous les fournisseurs LLM ont échoué ({self.name}) : {last}")


def _build(name: str, settings: Settings) -> LLM | None:
    """Instancie un fournisseur s'il est configuré (clé présente), sinon None."""
    if name == "anthropic" and settings.anthropic_api_key:
        return AnthropicLLM(settings)
    if name == "mistral" and settings.mistral_api_key:
        return MistralLLM(settings)
    if name == "gemini" and settings.gemini_api_key:
        return GeminiLLM(settings)
    if name == "ollama":
        return OllamaLLM(settings)
    return None


def get_llm(settings: Settings) -> LLM:
    names = [settings.llm_provider, *settings.llm_fallback_list]
    chain: list[LLM] = []
    for n in dict.fromkeys(names):  # dédoublonne en gardant l'ordre
        p = _build(n, settings)
        if p:
            chain.append(p)
        else:
            log.info("llm.skipped", provider=n, reason="non configuré")
    if not chain:
        raise RuntimeError("aucun fournisseur LLM configuré (ANTHROPIC_API_KEY, MISTRAL_API_KEY, GEMINI_API_KEY ou Ollama)")
    return chain[0] if len(chain) == 1 else FallbackLLM(chain)
