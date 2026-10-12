"""Gemini regarde une vidéo YouTube publique, sans rien télécharger (page Recherche, docs/60-recherche-niches.md).

L'API Gemini accepte l'adresse d'une vidéo YouTube publique comme partie du message (`file_data.file_uri`) : gratuit
jusqu'à 8 h de vidéo par jour (https://ai.google.dev/gemini-api/docs/video-understanding). Résolution basse (≈ 100
jetons par seconde au lieu de 300) : un Short d'une minute coûte ≈ 6 000 jetons.

Même mécanique de repli que les autres agents (providers/llm.py) : toutes les clés Gemini de Réglages → IA, puis chaque
modèle Gemini de la chaîne d'écriture puis de la chaîne par défaut (chacun a son propre quota du jour).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..config import Settings
from ..settings_store import load_llm_config
from .llm import FallbackLLM, KeyedLLM, T, _parse, _post, _schema_hint, fingerprint, track_keys


class GeminiVideoLLM:
    name = "gemini"

    def __init__(self, api_key: str, model: str, video_url: str) -> None:
        self.key, self.model, self.url = api_key, model, video_url

    def complete_json(self, system: str, user: str, schema: type[T], images: Sequence[Path] = ()) -> T:
        r = _post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self.key or ""},
            json={
                "system_instruction": {"parts": [{"text": system + _schema_hint(schema)}]},
                "contents": [{"role": "user", "parts": [{"file_data": {"file_uri": self.url}}, {"text": user}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0.5,
                    "mediaResolution": "MEDIA_RESOLUTION_LOW",
                },
            },
            timeout=300,
        )
        data = r.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:  # vidéo refusée (privée, bloquée) : pas de candidat
            raise ValueError(f"Gemini n'a pas pu regarder la vidéo : {str(data)[:300]}") from exc
        return _parse(text, schema)


def gemini_models(chains: dict[str, list[Any]]) -> list[str]:
    """Les modèles Gemini des chaînes, écriture d'abord (plus forts), sans doublon."""
    out: list[str] = []
    for kind in ("writer", "default"):
        for e in chains.get(kind, []):
            if e.provider == "gemini" and e.model not in out:
                out.append(e.model)
    return out


def get_video_llm(settings: Settings, db: Any, video_url: str) -> FallbackLLM | None:
    """La chaîne qui regarde `video_url` ; None sans clé Gemini."""
    cfg = load_llm_config(settings, db)
    keys = cfg.keys_for("gemini")
    if not keys:
        return None
    models = gemini_models({k: cfg.chain(k) for k in ("writer", "default")}) or [cfg.model_for("gemini")]
    chain = [KeyedLLM("gemini", m, [(fingerprint(k), GeminiVideoLLM(k, m, video_url)) for k in keys]) for m in models]
    track_keys(chain, db)
    return FallbackLLM(chain)
