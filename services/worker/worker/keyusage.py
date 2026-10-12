"""Suivi des clés API (docs/49 §9, migration 0044) : à chaque appel d'un modèle de langue (providers/llm.KeyedLLM) ou de
la voix Gemini (tts_runners/gemini_tts.py), la clé utilisée (son empreinte et son numéro, jamais la clé), le modèle, la
réussite ou la raison de l'échec (quota du jour, limite par minute, clé refusée) et la limite que Google annonce dans
son refus (« limit: 10 requests per day »). Le gestionnaire des tâches montre la clé en service et celles qui sont
tombées ; Réglages → Quotas, les limites et la consommation du jour. Une clé qui tombe (quota du jour, refus) fait une
alerte, une fois par jour.

Demandé par Luca le 01/10 : plusieurs clés Gemini pour la voix, sans savoir laquelle tourne ni lesquelles sont épuisées.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import structlog

log = structlog.get_logger(__name__)

PACIFIC = ZoneInfo("America/Los_Angeles")  # les quotas par jour de Google repartent à minuit, heure du Pacifique
PARIS = ZoneInfo("Europe/Paris")
POOLS = {"voix": "voix", "ia": "IA"}
_LIMIT = re.compile(r"limit:\s*(\d+)", re.I)
_PER_DAY = re.compile(r"per ?day|PerDay|daily", re.I)
_BAD_KEY = re.compile(r"API[_ ]?key|API_KEY_INVALID|PERMISSION_DENIED", re.I)


def next_reset(now: datetime | None = None) -> datetime:
    """Prochain minuit à Los Angeles (9 h à Paris l'été)."""
    now = (now or datetime.now(PACIFIC)).astimezone(PACIFIC)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def classify(status_code: int | None, text: str) -> tuple[str, int | None, datetime | None]:
    """(état, limite par jour annoncée, jusqu'à quand) d'un refus : quota_day, quota_minute, invalid ou error."""
    m = _LIMIT.search(text or "")
    limit = int(m.group(1)) if m and _PER_DAY.search(text or "") else None
    if status_code == 429:
        if _PER_DAY.search(text or ""):
            return "quota_day", limit, next_reset()
        return "quota_minute", None, datetime.now(PACIFIC) + timedelta(minutes=1)
    if status_code in (401, 403) or (status_code == 400 and _BAD_KEY.search(text or "")):
        return "invalid", None, None
    return "error", None, None


def from_exception(exc: BaseException) -> tuple[int | None, str]:
    """(code HTTP, texte) d'une erreur httpx ; (None, message) sinon."""
    resp = getattr(exc, "response", None)
    code = getattr(resp, "status_code", None) or getattr(exc, "status_code", None)
    try:
        text = resp.text if resp is not None else str(exc)
    except Exception:  # noqa: BLE001 — réponse illisible
        text = str(exc)
    return code, text


def record(
    db: Any,
    *,
    provider: str,
    model: str,
    fingerprint: str,
    pool: str,
    slot: int,
    slots: int,
    ok: bool,
    status_code: int | None = None,
    text: str = "",
) -> None:
    """Un appel de la clé ; jamais bloquant (un relevé manqué ne doit pas faire échouer l'appel)."""
    status, limit, until = ("ok", None, None) if ok else classify(status_code, text)
    try:
        row = db.fetch_one(
            "select note_key_use(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) as before",
            (fingerprint, provider, model, pool, slot, slots, ok, status, text[:400] if not ok else None, limit, until),
        )
        before = (row or {}).get("before")
        if status in ("quota_day", "invalid") and before != status:
            db.alert("info", *alert_text(provider, model, pool, slot, slots, status, limit, until))
    except Exception as exc:  # noqa: BLE001 — migration 0044 absente, base indisponible
        log.warning("cles.releve_impossible", error=str(exc)[:200])


def alert_text(
    provider: str, model: str, pool: str, slot: int, slots: int, status: str, limit: int | None, until: datetime | None
) -> tuple[str, str]:
    who = f"Clé {POOLS.get(pool, pool)} n°{slot} sur {slots} ({model})"
    if status == "invalid":
        return f"{who} refusée", "Google refuse cette clé (supprimée ou mal copiée ?) : les appels passent à la clé suivante."
    local = until.astimezone(PARIS) if until else None
    back = (f"{local.hour} h" + (f" {local.minute:02d}" if local.minute else "")) if local else "demain"
    nxt = f"la clé n°{slot + 1}" if slot < slots else "la première clé encore en service, sinon le repli"
    lim = f" (limite : {limit} par jour et par clé)" if limit else ""
    return f"{who} : quota du jour épuisé", f"Les appels passent à {nxt}{lim}. Elle revient vers {back}."


def recorder(db: Any, provider: str, model: str, pool: str, slots: int) -> Callable[[str, int, BaseException | None], None]:
    """Relevé pour une liste de clés d'un modèle : (empreinte, numéro, erreur ou None)."""

    def note(fingerprint: str, slot: int, exc: BaseException | None) -> None:
        code, text = from_exception(exc) if exc is not None else (None, "")
        record(
            db,
            provider=provider,
            model=model,
            fingerprint=fingerprint,
            pool=pool,
            slot=slot,
            slots=slots,
            ok=exc is None,
            status_code=code,
            text=text,
        )

    return note
