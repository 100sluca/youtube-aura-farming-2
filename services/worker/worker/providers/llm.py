"""LLM : sortie JSON validée par un modèle Pydantic.

Fournisseurs : gemini, anthropic, mistral, ollama (local). Les modèles à essayer, dans l'ordre, et les clés viennent
des réglages en base (dashboard → Réglages → IA, worker/settings_store.py) quand ils existent, sinon du .env
(`LLM_PROVIDER`, `LLM_FALLBACKS`, clés). Deux chaînes : « writer » (agent idées, scénaristes, relecteur :
get_llm(writer=True)) et « default » (tous les autres agents).

En cas d'erreur (demandé par Luca le 28/09, Gemini 3.8 Flash surchargé) :
- quota épuisé (429) ou clé refusée (401, 403, clé invalide) : la clé suivante du même fournisseur (KeyedLLM) ;
- surcharge (5xx, réseau : un seul nouvel essai après 4 s), modèle inconnu, réponse illisible, ou toutes les clés
  épuisées : le choix suivant de la chaîne (FallbackLLM) ;
- tout a échoué pour surcharge ou limite par minute : un second tour après 20 s.
Les pannes récentes sont retenues quelques minutes (quota du jour : une heure) : ce qui vient d'échouer passe après le
reste, sans être exclu.

Images (`images=`, contrôle qualité des images clés, worker/keyframe_qc.py) : envoyées réduites en JPEG aux seuls
fournisseurs qui voient (`sees_images`) ; un modèle texte seul répondrait à l'aveugle, il est sauté.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol, TypeVar

import httpx
import structlog
from pydantic import BaseModel

from ..config import Settings
from ..settings_store import LlmConfig, load_llm_config

log = structlog.get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLM(Protocol):
    name: str

    def complete_json(self, system: str, user: str, schema: type[T], images: Sequence[Path] = ()) -> T: ...


# Modèles Ollama qui voient les images (noms courants) ; les autres modèles locaux sont texte seul
_OLLAMA_VISION = re.compile(r"(llava|vision|[-_.]vl|minicpm-v|gemma3|moondream|bakllava|granite3\.2-vision|mistral-small3)", re.I)


def sees_images(provider: Any) -> bool:
    """Le fournisseur peut-il regarder une image ? Gemini et Claude : oui ; Mistral : les modèles Small, Medium,
    Pixtral ; Ollama : seulement un modèle de vision (llava, qwen2.5vl, gemma3…)."""
    name, model = getattr(provider, "name", ""), str(getattr(provider, "model", ""))
    if name in ("gemini", "anthropic"):
        return True
    if name == "mistral":
        return bool(re.search(r"(pixtral|small|medium)", model, re.I))
    if name == "ollama":
        return bool(_OLLAMA_VISION.search(model))
    return False


def encode_image(path: Path, max_side: int = 768) -> tuple[str, str]:
    """(type MIME, base64) : JPEG au côté long réduit à `max_side` (le contrôle n'a pas besoin de plus ; moins de
    jetons) ; sans Pillow, le fichier tel quel."""
    try:
        from PIL import Image
    except ImportError:
        mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        return mime, base64.b64encode(path.read_bytes()).decode()
    with Image.open(path) as im:
        rgb = im.convert("RGB")
    rgb.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    rgb.save(buf, "JPEG", quality=85)
    return "image/jpeg", base64.b64encode(buf.getvalue()).decode()


# Surcharge passagère : un nouvel essai, puis le choix suivant de la chaîne. Le 429 (quota) n'est pas réessayé ici : la
# clé suivante, puis le modèle suivant, répondent plus vite qu'une attente.
RETRY_STATUS = {500, 502, 503, 504}
RETRY_DELAYS_S = (4,)
SECOND_ROUND_WAIT_S = 20.0


def _post(url: str, **kwargs: Any) -> httpx.Response:
    """POST avec un nouvel essai sur une surcharge passagère (Gemini gratuit répond souvent 503 « high demand »)."""
    for delay in (*RETRY_DELAYS_S, None):
        try:
            r = httpx.post(url, **kwargs)
            if r.status_code not in RETRY_STATUS or delay is None:
                r.raise_for_status()
                return r
            log.warning("llm.retry", status=r.status_code, wait_s=delay)
        except httpx.TransportError as exc:
            if delay is None:
                raise
            log.warning("llm.retry", error=str(exc)[:200], wait_s=delay)
        time.sleep(delay)
    raise AssertionError("inatteignable")


def _parse(text: str, schema: type[T]) -> T:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"réponse sans JSON : {text[:200]}")
    data = json.loads(m.group(0))
    # Gemini Flash-Lite renvoie parfois la forme du schéma remplie ({"properties": {"ok": false, …}, "type": "object"},
    # contrôle d'un clip, 25/09) : on reprend l'objet qu'elle contient
    if isinstance(data, dict) and isinstance(data.get("properties"), dict) and not set(schema.model_fields) & set(data):
        data = data["properties"]
    return schema.model_validate(data)


def _schema_hint(schema: type[BaseModel]) -> str:
    return "\n\nRéponds uniquement avec un objet JSON conforme à ce schéma : " + json.dumps(
        schema.model_json_schema(), ensure_ascii=False
    )


class AnthropicLLM:
    name = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        from anthropic import Anthropic

        self.client = Anthropic(api_key=api_key)
        self.model = model

    def complete_json(self, system: str, user: str, schema: type[T], images: Sequence[Path] = ()) -> T:
        content: Any = user
        if images:
            content = [
                {"type": "image", "source": {"type": "base64", "media_type": m, "data": d}} for m, d in map(encode_image, images)
            ] + [{"type": "text", "text": user}]
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system + _schema_hint(schema),
            messages=[{"role": "user", "content": content}],
        )
        return _parse("".join(b.text for b in msg.content if getattr(b, "type", "") == "text"), schema)


class MistralLLM:
    name = "mistral"

    def __init__(self, api_key: str, model: str) -> None:
        self.key, self.model = api_key, model

    def complete_json(self, system: str, user: str, schema: type[T], images: Sequence[Path] = ()) -> T:
        content: Any = user
        if images:
            content = [{"type": "image_url", "image_url": f"data:{m};base64,{d}"} for m, d in map(encode_image, images)]
            content.append({"type": "text", "text": user})
        r = _post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.key}"},
            json={
                "model": self.model,
                "temperature": 0.7,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system + _schema_hint(schema)},
                    {"role": "user", "content": content},
                ],
            },
            timeout=120,
        )
        r.raise_for_status()
        return _parse(r.json()["choices"][0]["message"]["content"], schema)


class GeminiLLM:
    name = "gemini"

    def __init__(self, api_key: str, model: str) -> None:
        self.key, self.model = api_key, model

    def complete_json(self, system: str, user: str, schema: type[T], images: Sequence[Path] = ()) -> T:
        parts: list[dict[str, Any]] = [{"inline_data": {"mime_type": m, "data": d}} for m, d in map(encode_image, images)]
        parts.append({"text": user})
        r = _post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self.key or ""},
            json={
                "system_instruction": {"parts": [{"text": system + _schema_hint(schema)}]},
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7},
            },
            timeout=120,
        )
        return _parse(r.json()["candidates"][0]["content"]["parts"][0]["text"], schema)


class OllamaLLM:
    name = "ollama"

    def __init__(self, base_url: str, model: str) -> None:
        self.base, self.model = base_url, model

    def complete_json(self, system: str, user: str, schema: type[T], images: Sequence[Path] = ()) -> T:
        message: dict[str, Any] = {"role": "user", "content": user}
        if images:
            message["images"] = [d for _m, d in map(encode_image, images)]
        r = httpx.post(
            f"{self.base}/api/chat",
            timeout=300,
            json={
                "model": self.model,
                "stream": False,
                "format": schema.model_json_schema(),
                "keep_alive": 0,  # libère la VRAM pour ComfyUI après l'appel
                "messages": [{"role": "system", "content": system}, message],
            },
        )
        r.raise_for_status()
        return _parse(r.json()["message"]["content"], schema)


# ---------------------------------------------------------------------------
# Pannes : clé suivante, modèle suivant, mémoire des pannes récentes
# ---------------------------------------------------------------------------

_COOLING: dict[tuple[str, ...], float] = {}  # (quoi, …) → instant jusqu'où cela a échoué récemment


def _cool(key: tuple[str, ...], seconds: float) -> None:
    _COOLING[key] = time.monotonic() + seconds


def _cooling(key: tuple[str, ...]) -> bool:
    return _COOLING.get(key, 0.0) > time.monotonic()


def fingerprint(key: str) -> str:
    """Empreinte d'une clé API pour s'en souvenir (jamais la clé elle-même dans la mémoire ni dans le journal)."""
    return hashlib.sha1(key.encode()).hexdigest()[:10]


def failure_kind(exc: Exception) -> tuple[str, float]:
    """(nature de l'erreur, durée pendant laquelle s'en souvenir) : quota (429 ; quota du jour : 1 h, limite par minute :
    1 min), key (clé refusée : 1 h), overload (surcharge ou réseau : 3 min), model (modèle inconnu : 1 h), other."""
    if isinstance(exc, httpx.TransportError):
        return "overload", 180.0
    resp = getattr(exc, "response", None)
    status = getattr(resp, "status_code", None) or getattr(exc, "status_code", None)
    try:
        text = resp.text if resp is not None else str(exc)
    except Exception:  # noqa: BLE001 — réponse déjà consommée ou illisible
        text = str(exc)
    if status == 429:
        return "quota", 3600.0 if re.search(r"per ?day|PerDay|daily", text, re.I) else 60.0
    if status in (401, 403) or (status == 400 and re.search(r"API[_ ]?key|API_KEY_INVALID", text, re.I)):
        return "key", 3600.0
    if status == 404:
        return "model", 3600.0
    if isinstance(status, int) and status >= 500:
        return "overload", 180.0
    return "other", 0.0


# Appels en cours par (fournisseur, clé) : plusieurs scripts ou idées tournent en même temps (voie io, docs/43) ; chacun
# prend d'abord une clé que personne n'utilise, pour étaler la charge et les limites par minute sur toutes les clés
_BUSY: dict[tuple[str, str], int] = {}
_BUSY_LOCK = threading.Lock()


def _take(name: str, fp: str, delta: int) -> None:
    with _BUSY_LOCK:
        _BUSY[(name, fp)] = _BUSY.get((name, fp), 0) + delta


class KeyedLLM:
    """Un modèle et toutes les clés de son fournisseur : quota épuisé ou clé refusée → la clé suivante ; une autre panne
    remonte (le choix suivant de la chaîne la traite). Une clé qui vient d'échouer passe après les autres ; parmi les
    clés en état, la moins occupée par les autres appels en cours passe devant (à égalité, l'ordre des Réglages)."""

    def __init__(self, name: str, model: str, clients: list[tuple[str, LLM]]) -> None:
        self.name, self.model, self.clients = name, model, clients  # (empreinte de la clé, client)
        self.last_key = 1  # numéro de la clé qui a répondu en dernier

    def complete_json(self, system: str, user: str, schema: type[T], images: Sequence[Path] = ()) -> T:
        with _BUSY_LOCK:
            order = sorted(
                self.clients,
                key=lambda c: (
                    _cooling(("key", self.name, c[0])) or _cooling(("quota", self.name, self.model, c[0])),
                    _BUSY.get((self.name, c[0]), 0),
                ),
            )
        last: Exception | None = None
        for fp, client in order:
            _take(self.name, fp, 1)
            try:
                out = client.complete_json(system, user, schema, images) if images else client.complete_json(system, user, schema)
                self.last_key = next(i for i, c in enumerate(self.clients, start=1) if c[0] == fp)
                return out
            except Exception as exc:  # noqa: BLE001
                kind, seconds = failure_kind(exc)
                if kind not in ("quota", "key"):
                    raise
                last = exc
                _cool(("quota", self.name, self.model, fp) if kind == "quota" else ("key", self.name, fp), seconds)
                slot = next(i for i, c in enumerate(self.clients, start=1) if c[0] == fp)
                log.warning("llm.cle_suivante", provider=self.name, model=self.model, cle=slot, raison=kind, error=str(exc)[:200])
            finally:
                _take(self.name, fp, -1)
        assert last is not None
        raise last


class FallbackLLM:
    """La chaîne des choix (Réglages → IA) : le premier qui répond un JSON valide gagne. Un modèle surchargé ou inconnu
    il y a peu passe après les autres ; si tout échoue pour surcharge ou limite par minute, un second tour après 20 s."""

    def __init__(self, chain: list[LLM]) -> None:
        self.chain = chain
        self.name = " > ".join(p.name for p in chain)
        self.used: list[str] = []  # « fournisseur:modèle » de chaque appel réussi (journal des steps)

    @property
    def model(self) -> str:
        return str(getattr(self.chain[0], "model", "?")) if self.chain else "?"

    def complete_json(self, system: str, user: str, schema: type[T], images: Sequence[Path] = ()) -> T:
        last: Exception | None = None
        chain = [p for p in self.chain if sees_images(p)] if images else list(self.chain)
        if not chain:
            raise RuntimeError(f"aucun fournisseur LLM ne voit les images ({self.name})")
        chain.sort(key=lambda p: _cooling(("model", p.name, str(getattr(p, "model", "")))))
        for round_no in range(2):
            transient = False
            for i, provider in enumerate(chain):
                model = str(getattr(provider, "model", "?"))
                try:
                    out = (
                        provider.complete_json(system, user, schema, images)
                        if images
                        else provider.complete_json(system, user, schema)
                    )
                    key = getattr(provider, "last_key", 1)
                    self.used.append(f"{provider.name}:{model}" + (f" (clé {key})" if key > 1 else ""))
                    return out
                except Exception as exc:  # noqa: BLE001
                    last = exc
                    kind, seconds = failure_kind(exc)
                    if kind in ("overload", "model"):
                        _cool(("model", provider.name, model), seconds)
                    transient = transient or kind == "overload" or (kind == "quota" and seconds <= 60)
                    log.warning(
                        "llm.choix_suivant" if i + 1 < len(chain) else "llm.chaine_epuisee",
                        provider=provider.name,
                        model=model,
                        choix=i + 1,
                        raison=kind,
                        error=str(exc)[:300],
                    )
            if round_no or not transient:
                break
            log.warning("llm.second_tour", wait_s=SECOND_ROUND_WAIT_S)
            time.sleep(SECOND_ROUND_WAIT_S)
        raise RuntimeError(f"tous les modèles de la chaîne ont échoué ({self.name}) : {last}")


_CLIENTS = {"anthropic": AnthropicLLM, "mistral": MistralLLM, "gemini": GeminiLLM}


def build_provider(name: str, cfg: LlmConfig, settings: Settings, model: str | None = None, key: str | None = None) -> LLM | None:
    """Un modèle d'un fournisseur, avec toutes ses clés (KeyedLLM) ou la seule `key` donnée ; None sans clé."""
    model = model or cfg.model_for(name)
    if name == "ollama":
        return OllamaLLM(settings.ollama_base_url, model)
    if name not in _CLIENTS:
        return None
    if key:
        return _CLIENTS[name](key, model)
    keys = cfg.keys_for(name)
    if not keys:
        return None
    return KeyedLLM(name, model, [(fingerprint(k), _CLIENTS[name](k, model)) for k in keys])


def _chain(settings: Settings, cfg: LlmConfig, kind: str) -> list[LLM]:
    out: list[LLM] = []
    for e in cfg.chain(kind):
        p = build_provider(e.provider, cfg, settings, e.model)
        if p:
            out.append(p)
        else:
            log.info("llm.skipped", provider=e.provider, model=e.model, reason="pas de clé")
    return out


def get_llm(settings: Settings, db: Any | None = None, *, writer: bool = False) -> LLM:
    """La chaîne de modèles des réglages (en base si `db`, par-dessus le .env) : « writer » pour les agents qui écrivent
    (idées, scénaristes, relecteur), « default » pour les autres."""
    cfg = load_llm_config(settings, db)
    chain = _chain(settings, cfg, "writer" if writer else "default")
    if not chain:
        raise RuntimeError("aucun fournisseur LLM configuré : clé API dans Réglages → IA du dashboard, ou dans .env, ou Ollama")
    log.debug("llm.chain", providers=[p.name for p in chain], models=[getattr(p, "model", "?") for p in chain], source=cfg.source)
    return FallbackLLM(chain)


def get_vision_llm(settings: Settings, db: Any | None = None) -> LLM | None:
    """Les choix de la chaîne « default » qui voient les images, dans l'ordre ; None s'il n'y en a aucun (le contrôle des
    images clés est alors sauté et la revue humaine reste la règle)."""
    cfg = load_llm_config(settings, db)
    chain = [p for p in _chain(settings, cfg, "default") if sees_images(p)]
    return FallbackLLM(chain) if chain else None


class _Ping(BaseModel):
    ok: bool
    model_hint: str = ""


def test_provider(settings: Settings, db: Any | None, name: str, model: str | None = None, key_index: int | None = None) -> str:
    """Appel minimal pour vérifier une clé et un modèle ; `key_index` (1, 2…) : cette clé seule, dans l'ordre des
    réglages. Renvoie un message lisible, lève sinon."""
    cfg = load_llm_config(settings, db, use_cache=False)
    key = None
    if key_index is not None and name != "ollama":
        keys = cfg.keys_for(name)
        if not 1 <= key_index <= len(keys):
            raise RuntimeError(f"{name} : pas de clé n° {key_index} ({len(keys)} enregistrée(s))")
        key = keys[key_index - 1]
    p = build_provider(name, cfg, settings, model, key=key)
    if not p:
        raise RuntimeError(f"{name} : pas de clé enregistrée")
    out = p.complete_json(
        "Réponds uniquement en JSON.", 'Renvoie {"ok": true, "model_hint": "<ton nom de modèle si tu le connais>"}', _Ping
    )
    return f"{name} · {getattr(p, 'model', '?')}{f' · clé {key_index}' if key_index else ''} répond ({'ok' if out.ok else 'réponse inattendue'})"
