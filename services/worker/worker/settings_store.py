"""Réglages et clés API en base (table app_settings, app_secrets), modifiables depuis le dashboard.

Le worker lit ces réglages à chaque appel de LLM ; ils priment sur le fichier .env, qui reste le repli
(et la seule source quand la base n'est pas jointe, ex. tests, aperçus). Les clés sont chiffrées avec
CREDENTIALS_KEY (AES-GCM, même format que les jetons YouTube : base64(nonce + chiffré)), écrites par le
dashboard (Node, WebCrypto) ou par `yt2 settings key`, jamais renvoyées en clair au navigateur.

Clé « generation » (Réglages → Modèles de génération) : modèle d'image du storyboard, modèle vidéo, nombre
d'images par scène, voix. Même principe : la base prime sur le .env (COMFY_IMAGE_WORKFLOW, VIDEO_PROVIDER…).

Chaînes de modèles (demandé par Luca le 28/09, Gemini 3.8 Flash surchargé) : app_settings.llm.chains = {"writer": [...],
"default": [...]}, chaque liste ordonnée de {provider, model} (1er choix, 2e choix…). « writer » sert l'agent idées, les
scénaristes et le relecteur ; « default » tous les autres agents. En cas d'erreur, le choix suivant prend le relais
(providers/llm.py). Sans chaînes en base, elles se déduisent des anciens champs provider, models, fallbacks,
writer_models. Plusieurs clés par fournisseur : app_secrets gemini_api_key, gemini_api_key_2, gemini_api_key_3… ; quota
épuisé ou clé refusée → la clé suivante, avant de passer au modèle suivant.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from psycopg.types.json import Jsonb

from .config import Settings
from .youtube.auth import decrypt, encrypt

PROVIDERS = ("gemini", "anthropic", "mistral", "ollama")
SECRET_NAMES = {"gemini": "gemini_api_key", "anthropic": "anthropic_api_key", "mistral": "mistral_api_key"}
KEY_NAME = re.compile(r"^(gemini|anthropic|mistral)_api_key(?:_(\d+))?$")  # clé 1 sans suffixe, puis _2, _3…
CHAIN_KINDS = ("writer", "default")
CHAIN_MAX = 8


def secret_name(provider: str, slot: int) -> str:
    return SECRET_NAMES[provider] if slot <= 1 else f"{SECRET_NAMES[provider]}_{slot}"


@dataclass(frozen=True)
class ChainEntry:
    """Un choix de la chaîne : un modèle d'un fournisseur (toutes ses clés sont essayées)."""

    provider: str
    model: str


def parse_chain(raw: Any) -> list[ChainEntry]:
    out: list[ChainEntry] = []
    for e in raw or []:
        if not isinstance(e, dict):
            continue
        entry = ChainEntry(str(e.get("provider") or ""), str(e.get("model") or "").strip())
        if entry.provider in PROVIDERS and entry.model and entry not in out:
            out.append(entry)
    return out[:CHAIN_MAX]


# Modèles proposés par défaut dans le dashboard (liste vérifiée sur ai.google.dev le 2026-09-21 ; le bouton
# « Charger depuis Google » complète avec ce que la clé voit réellement). Le premier de chaque liste est le défaut.
PRESET_MODELS: dict[str, list[str]] = {
    "gemini": [
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-pro-preview",
        "gemini-3.1-flash-lite",
        "gemini-3-flash-preview",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-pro",
    ],
    "anthropic": ["claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5-20251001"],
    "mistral": ["mistral-small-latest", "mistral-medium-latest", "mistral-large-latest"],
    "ollama": ["qwen3:8b", "qwen2.5:7b", "llama3.1:8b"],
}
CACHE_TTL_S = 30.0


@dataclass
class LlmConfig:
    provider: str
    fallbacks: list[str]
    models: dict[str, str]
    api_keys: dict[str, str | None] = field(default_factory=dict)  # fournisseur → clé (déchiffrée) ou None
    custom_models: dict[str, list[str]] = field(default_factory=dict)
    source: str = "env"  # env | db
    # Ancien réglage (avant les chaînes) : modèle d'écriture par fournisseur ; ne sert plus qu'à déduire la chaîne
    # « writer » quand la base n'a pas encore de chaînes.
    writer_models: dict[str, str] = field(default_factory=dict)
    keys: dict[str, list[str]] = field(default_factory=dict)  # toutes les clés de chaque fournisseur, dans l'ordre
    chains: dict[str, list[ChainEntry]] = field(default_factory=dict)  # writer | default, en base

    def model_for(self, provider: str) -> str:
        return self.models.get(provider) or PRESET_MODELS[provider][0]

    def writer_model_for(self, provider: str) -> str | None:
        """Ancien modèle d'écriture s'il diffère du modèle principal, sinon None."""
        m = (self.writer_models.get(provider) or "").strip()
        return m if m and m != self.model_for(provider) else None

    def key_for(self, provider: str) -> str | None:
        keys = self.keys_for(provider)
        return keys[0] if keys else None

    def keys_for(self, provider: str) -> list[str]:
        """Les clés du fournisseur, clé 1 d'abord ; la clé du .env en dernier recours."""
        keys = [k for k in self.keys.get(provider, []) if k]
        env = self.api_keys.get(provider)
        return keys + ([env] if env and env not in keys else [])

    def chain(self, kind: str = "default") -> list[ChainEntry]:
        """Les choix de modèle dans l'ordre : la chaîne en base, sinon celle des anciens réglages (principal puis
        secours ; pour l'écriture, l'ancien modèle d'écriture en tête)."""
        explicit = self.chains.get(kind) or (self.chains.get("default") if kind == "writer" else None)
        if explicit:
            return list(explicit)
        base = [ChainEntry(p, self.model_for(p)) for p in dict.fromkeys([self.provider, *self.fallbacks]) if p in PROVIDERS]
        strong = self.writer_model_for(self.provider) if kind == "writer" else None
        return ([ChainEntry(self.provider, strong)] if strong else []) + base


def from_env(settings: Settings) -> LlmConfig:
    return LlmConfig(
        provider=settings.llm_provider,
        fallbacks=settings.llm_fallback_list,
        models={
            "gemini": settings.gemini_model,
            "anthropic": settings.anthropic_model,
            "mistral": settings.mistral_model,
            "ollama": settings.ollama_model,
        },
        api_keys={
            "gemini": settings.gemini_api_key,
            "anthropic": settings.anthropic_api_key,
            "mistral": settings.mistral_api_key,
        },
        source="env",
    )


_cache: dict[str, tuple[float, LlmConfig]] = {}


def load_llm_config(settings: Settings, db: Any | None, use_cache: bool = True) -> LlmConfig:
    """Réglages LLM effectifs : base (app_settings.llm + app_secrets) par-dessus le .env. Cache 30 s par processus."""
    base = from_env(settings)
    if db is None:
        return base
    now = time.monotonic()
    hit = _cache.get("llm")
    if use_cache and hit and now - hit[0] < CACHE_TTL_S:
        return hit[1]
    row = db.fetch_one("select value from app_settings where key = 'llm'")
    cfg = base
    if row and row["value"]:
        v = row["value"]
        models = {**base.models, **{k: m for k, m in (v.get("models") or {}).items() if m}}
        cfg = LlmConfig(
            provider=v.get("provider") or base.provider,
            fallbacks=[f for f in (v.get("fallbacks") or base.fallbacks) if f in PROVIDERS],
            models=models,
            api_keys=dict(base.api_keys),
            custom_models={k: list(x) for k, x in (v.get("custom_models") or {}).items()},
            source="db",
            writer_models={k: m for k, m in (v.get("writer_models") or {}).items() if m},
            chains={k: c for k in CHAIN_KINDS if (c := parse_chain((v.get("chains") or {}).get(k)))},
        )
    if settings.credentials_key:
        slots: dict[str, list[tuple[int, str]]] = {}
        for r in db.fetch_all("select name, value_encrypted from app_secrets"):
            m = KEY_NAME.match(r["name"])
            if m:
                try:
                    slots.setdefault(m.group(1), []).append((int(m.group(2) or 1), decrypt(settings, r["value_encrypted"])))
                except Exception:  # noqa: BLE001 — clé de chiffrement changée : on ignore ce secret
                    pass
        cfg.keys = {p: [k for _, k in sorted(v)] for p, v in slots.items()}
    _cache["llm"] = (now, cfg)
    return cfg


def save_llm_settings(db: Any, **changes: Any) -> dict[str, Any]:
    """Met à jour app_settings.llm (provider, fallbacks, models, custom_models, writer_models, chains) et renvoie la
    valeur. `chains` remplace les chaînes nommées ({"writer": [{"provider", "model"}, …]}), une liste vide la retire."""
    row = db.fetch_one("select value from app_settings where key = 'llm'")
    value = dict(row["value"]) if row and row["value"] else {}
    for k, v in changes.items():
        if v is None:
            continue
        if k in ("models", "custom_models", "writer_models"):
            value[k] = {**(value.get(k) or {}), **v}
        elif k == "chains":
            chains = dict(value.get("chains") or {})
            for kind, entries in v.items():
                parsed = parse_chain(entries)
                if parsed:
                    chains[kind] = [{"provider": e.provider, "model": e.model} for e in parsed]
                else:
                    chains.pop(kind, None)
            value["chains"] = chains
        else:
            value[k] = v
    db.execute(
        """insert into app_settings (key, value) values ('llm', %s)
           on conflict (key) do update set value = excluded.value, updated_at = now()""",
        (Jsonb(value),),
    )
    _cache.pop("llm", None)
    return value


def key_slots(db: Any) -> dict[str, list[tuple[int, str]]]:
    """Fournisseur → [(numéro de la clé, 4 derniers caractères)], dans l'ordre (pour l'affichage, jamais la clé)."""
    out: dict[str, list[tuple[int, str]]] = {}
    for r in db.fetch_all("select name, hint from app_secrets"):
        m = KEY_NAME.match(r["name"])
        if m:
            out.setdefault(m.group(1), []).append((int(m.group(2) or 1), r["hint"] or "…"))
    return {p: sorted(v) for p, v in out.items()}


def save_secret(settings: Settings, db: Any, provider: str, value: str, slot: int | None = None) -> int:
    """Enregistre une clé : dans l'emplacement `slot` (remplacée), sinon à la suite des clés existantes. Renvoie son
    numéro."""
    if slot is None:
        used = [s for s, _ in key_slots(db).get(provider, [])]
        slot = next(i for i in range(1, len(used) + 2) if i not in used)
    db.execute(
        """insert into app_secrets (name, value_encrypted, hint) values (%s, %s, %s)
           on conflict (name) do update set value_encrypted = excluded.value_encrypted, hint = excluded.hint, updated_at = now()""",
        (secret_name(provider, slot), encrypt(settings, value), value[-4:]),
    )
    _cache.pop("llm", None)
    return slot


def delete_secret(db: Any, provider: str, slot: int = 1) -> None:
    db.execute("delete from app_secrets where name = %s", (secret_name(provider, slot),))
    _cache.pop("llm", None)


def secret_hints(db: Any) -> dict[str, str]:
    """Fournisseur → 4 derniers caractères de sa première clé (affichage court) ; key_slots pour toutes."""
    return {p: slots[0][1] for p, slots in key_slots(db).items() if slots}


# ---------------------------------------------------------------------------
# Modèles de génération (images, vidéo, voix) : app_settings.generation
# ---------------------------------------------------------------------------


@dataclass
class GenerationConfig:
    image_workflow: str  # nom du workflow ComfyUI des images de storyboard (workflows/<nom>.json)
    video_workflow: str  # nom du workflow d'animation, sans le préfixe comfy_
    storyboard_candidates: int
    voices: dict[str, str]  # langue → voix Kokoro
    source: str = "env"  # env | db

    @property
    def video_provider(self) -> str:
        return f"comfy_{self.video_workflow}"


def generation_from_env(settings: Settings) -> GenerationConfig:
    return GenerationConfig(
        image_workflow=settings.comfy_image_workflow,
        video_workflow=settings.video_provider.removeprefix("comfy_"),
        storyboard_candidates=settings.storyboard_candidates,
        voices={"fr": settings.kokoro_voice_fr, "en": settings.kokoro_voice_en},
    )


_gen_cache: dict[str, tuple[float, GenerationConfig]] = {}


def load_generation_config(settings: Settings, db: Any | None, use_cache: bool = True) -> GenerationConfig:
    """Modèles effectifs : base (app_settings.generation) par-dessus le .env. Cache 30 s par processus."""
    base = generation_from_env(settings)
    if db is None:
        return base
    now = time.monotonic()
    hit = _gen_cache.get("generation")
    if use_cache and hit and now - hit[0] < CACHE_TTL_S:
        return hit[1]
    row = db.fetch_one("select value from app_settings where key = 'generation'")
    cfg = base
    if row and row["value"]:
        v = row["value"]
        cfg = GenerationConfig(
            image_workflow=v.get("image_workflow") or base.image_workflow,
            video_workflow=str(v.get("video_workflow") or base.video_workflow).removeprefix("comfy_"),
            storyboard_candidates=int(v.get("storyboard_candidates") or base.storyboard_candidates),
            voices={**base.voices, **{k: x for k, x in (v.get("voices") or {}).items() if x}},
            source="db",
        )
    _gen_cache["generation"] = (now, cfg)
    return cfg


def save_generation_settings(db: Any, **changes: Any) -> dict[str, Any]:
    """Met à jour app_settings.generation (image_workflow, video_workflow, storyboard_candidates, voices)."""
    row = db.fetch_one("select value from app_settings where key = 'generation'")
    value = dict(row["value"]) if row and row["value"] else {}
    for k, v in changes.items():
        if v is None:
            continue
        value[k] = {**(value.get(k) or {}), **v} if k == "voices" else v
    db.execute(
        """insert into app_settings (key, value) values ('generation', %s)
           on conflict (key) do update set value = excluded.value, updated_at = now()""",
        (Jsonb(value),),
    )
    _gen_cache.pop("generation", None)
    return value


# ---------------------------------------------------------------------------
# Gemini en ligne (vidéo) : app_settings.gemini (réglages) et app_settings.gemini_status (dernier résultat, quota),
# séparés des modèles locaux (docs/17-gemini-en-ligne.md)
# ---------------------------------------------------------------------------

GEMINI_DURATIONS = ("auto", "4", "6", "8", "10")


@dataclass
class GeminiConfig:
    authuser: int  # numéro du compte Google dans le profil Chrome dédié (…/u/<n>/app)
    model: str  # libellé du modèle à choisir dans l'appli (ex. « 3.5 Flash ») ; vide = celui proposé par Gemini
    duration: str  # auto | 4 | 6 | 8 | 10 (secondes)
    source: str = "env"  # env | db


def gemini_from_env(settings: Settings) -> GeminiConfig:
    duration = settings.gemini_video_duration if settings.gemini_video_duration in GEMINI_DURATIONS else "auto"
    return GeminiConfig(authuser=settings.gemini_authuser, model=(settings.gemini_video_model or "").strip(), duration=duration)


_gemini_cache: dict[str, tuple[float, GeminiConfig]] = {}


def load_gemini_config(settings: Settings, db: Any | None, use_cache: bool = True) -> GeminiConfig:
    """Réglages Gemini effectifs : base (app_settings.gemini) par-dessus le .env. Cache 30 s par processus."""
    base = gemini_from_env(settings)
    if db is None:
        return base
    now = time.monotonic()
    hit = _gemini_cache.get("gemini")
    if use_cache and hit and now - hit[0] < CACHE_TTL_S:
        return hit[1]
    row = db.fetch_one("select value from app_settings where key = 'gemini'")
    cfg = base
    if row and row["value"]:
        v = row["value"]
        duration = str(v.get("duration") or base.duration)
        cfg = GeminiConfig(
            authuser=int(v["authuser"]) if str(v.get("authuser", "")).strip().isdigit() else base.authuser,
            model=str(v["model"]).strip() if v.get("model") is not None else base.model,
            duration=duration if duration in GEMINI_DURATIONS else "auto",
            source="db",
        )
    _gemini_cache["gemini"] = (now, cfg)
    return cfg


def save_gemini_status(db: Any | None, **fields: Any) -> None:
    """Dernier résultat du pilote Gemini (ok, message, quota_until…), affiché dans Réglages et près du bouton Gemini."""
    if db is None:
        return
    try:
        row = db.fetch_one("select value from app_settings where key = 'gemini_status'")
        value = dict(row["value"]) if row and row["value"] else {}
        value.update(fields)
        value["at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        db.execute(
            """insert into app_settings (key, value) values ('gemini_status', %s)
               on conflict (key) do update set value = excluded.value, updated_at = now()""",
            (Jsonb(value),),
        )
    except Exception:  # noqa: BLE001 — l'état affiché ne doit jamais faire échouer un clip
        pass


def load_gemini_status(db: Any | None) -> dict[str, Any]:
    if db is None:
        return {}
    row = db.fetch_one("select value from app_settings where key = 'gemini_status'")
    return dict(row["value"]) if row and row["value"] else {}
