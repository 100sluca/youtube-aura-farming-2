"""Gemini 3.8 Flash TTS (Google, en ligne) : une voix du studio Gemini, le ton de chaque réplique en consigne de style
(docs/41-voix-emotion.md).

Retenu par Luca le 30/09 après le banc « émotion » (la voix la plus expressive, deux fois plus rapide que Qwen). Gratuit
avec une clé Google AI Studio, quota non publié : les clés réservées à la voix (Réglages → Modèles de génération) passent
d'abord, puis celles du LLM (Réglages → IA) ; quota épuisé partout : l'étape voix passe au repli local (docs/41 §8).

Durée visée (request.json → targets, docs/41 §8) : le temps où la bouche du clip dit la réplique. Une prise trop longue
ou trop courte pour se caler sans sonner faux (lipsync : ×0,8-×1,4) est refaite avec une consigne de débit, deux fois
au plus ; on garde la prise la plus proche de la bouche.

Tourne avec le Python du worker (« python »: « worker » dans catalog.json) : les clés viennent de la base. Voix : un nom
de voix Gemini (« Gacrux ») ou une voix du catalogue dont params.gemini donne ce nom ; params.persona précède le ton dans
le style. Options : model.

Langue (01/10, docs/49 §5) : le style est écrit en anglais (personnage, ton, débit), et Gemini disait parfois la
réplique française EN ANGLAIS, traduite. La langue de la vidéo (request.json → lang) part donc en tête du style (« dis
le texte tel quel, en français, sans jamais le traduire ») et en code de langue dans speech_config ; si l'API refuse ce
champ, il est retiré pour la suite du job.
"""

from __future__ import annotations

import base64
import io
import math
import re
import sys
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np
from _common import run, voiced_seconds

URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
LANGS = {"fr": ("French", "fr-FR"), "en": ("English", "en-US")}
STATE: dict[str, Any] = {}
MIN_GAP_S = 2.0  # quota par minute non publié : un appel toutes les 2 s au plus
FIT = (0.85, 1.3)  # bouche / voix acceptable (marge dans le ×0,8-×1,4 du calage sur les lèvres)
RETAKES = 2  # prises refaites au plus pour tenir la durée de la bouche


def prepare(req: dict[str, Any]) -> None:
    from worker.config import Settings
    from worker.db import Db
    from worker.settings_store import load_llm_config, voice_keys

    # le sous-processus ne tourne pas dans services/worker : le .env du worker est lu à son adresse
    env_file = Path(__file__).resolve().parents[1] / ".env"
    settings = Settings(_env_file=str(env_file)) if env_file.exists() else Settings()
    db = Db(settings.database_url, max_size=1)  # gardée ouverte : suivi des clés à chaque appel (docs/49 §9)
    dedicated = voice_keys(settings, db)
    shared = load_llm_config(settings, db, use_cache=False).keys_for("gemini")
    # (clé, liste, numéro, nombre de clés de la liste) : clés de la voix d'abord, puis celles de Réglages → IA
    slots = [(k, "voix", i, len(dedicated)) for i, k in enumerate(dedicated, start=1)]
    slots += [(k, "ia", j, len(shared)) for j, k in enumerate(shared, start=1) if k not in dedicated]
    keys = [k for k, *_ in slots]
    if not keys:
        raise RuntimeError("aucune clé Gemini (Réglages → Modèles de génération → Clés de la voix, ou Réglages → IA)")
    print(f"Gemini TTS : {len(dedicated)} clé(s) de la voix, {len(keys) - len(dedicated)} du LLM", file=sys.stderr, flush=True)
    params = req.get("voice_params") or {}
    STATE.update(
        keys=keys,
        slots=slots,
        db=db,
        dead=set(),  # numéros des clés au quota du jour épuisé ou refusées : sautées jusqu'à la fin du job
        model=(req.get("options") or {}).get("model", "gemini-3.8-flash-tts"),
        voice=params.get("gemini") or req["voice"],
        persona=" ".join(str(params.get("persona") or "").split()),
        speed=float(req.get("speed") or 1.0),
        lang=str(req.get("lang") or "fr"),
        lang_field=True,
        last=0.0,
    )


def language_rule(lang: str) -> str:
    name = LANGS.get(lang, (lang, lang))[0]
    return f"Speak {name} with a native {name} accent; say the text exactly as written, word for word, never translate it"


def style(tone: str, pace: str = "") -> str:
    parts = (language_rule(STATE.get("lang", "fr")), STATE["persona"], " ".join((tone or "").split()), pace)
    return "; ".join(p for p in parts if p)


def pace_hint(ratio: float, target: float) -> str:
    """Consigne de débit pour la prise suivante : `ratio` = durée de la bouche / durée de la voix."""
    if ratio < FIT[0]:
        return f"a faster pace: the whole line must fit in about {target:.1f} seconds"
    return f"an unhurried pace with natural pauses, filling about {target:.1f} seconds"


def synthesize(req: dict[str, Any], text: str, tone: str, target: float | None) -> tuple[np.ndarray, int]:
    audio, rate = _call(text, style(tone))
    if not target:
        return audio, rate
    # la vitesse de la chaîne (atempo, après ce script) raccourcit la voix : on compare ce que le montage recevra
    takes = []
    for attempt in range(1 + RETAKES):
        if attempt:
            audio, rate = _call(text, style(tone, pace_hint(takes[-1][3], target)))
        ratio = target / max(0.1, voiced_seconds(audio, rate) / STATE["speed"])
        takes.append((abs(math.log(ratio)), audio, rate, ratio))
        if FIT[0] <= ratio <= FIT[1]:
            break
    best = min(takes, key=lambda t: t[0])
    print(
        f"« {text[:40]} » : bouche {target:.1f} s, prises × {', '.join(f'{t[3]:.2f}' for t in takes)} → × {best[3]:.2f}",
        file=sys.stderr,
        flush=True,
    )
    return best[1], best[2]


def _call(text: str, instruction: str) -> tuple[np.ndarray, int]:
    import httpx

    content: dict[str, Any] = {"type": "text", "text": text}
    if instruction:
        content["annotations"] = [{"type": "speech_metadata", "style": instruction}]
    speech: dict[str, Any] = {"voice": STATE["voice"]}
    if STATE.get("lang_field", True) and STATE.get("lang") in LANGS:
        speech["language"] = LANGS[STATE["lang"]][1]
    body = {
        "model": STATE["model"],
        "input": [{"type": "user_input", "content": [content]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [speech]},
    }
    errors = []
    keys = STATE["keys"]
    dead: set[int] = STATE.setdefault("dead", set())
    # quota dépassé (429) ou serveur occupé : clé suivante ; deux tours de clés au plus (≈ 1 min), puis on rend la main
    # à l'étape voix, qui passe au repli local (Réglages → Jeu des voix). Une clé au quota du jour épuisé ou refusée
    # n'est plus essayée dans ce job.
    for attempt in range(2 * len(keys)):
        n = attempt % len(keys)
        if n in dead:
            continue
        time.sleep(max(0.0, STATE["last"] + MIN_GAP_S - time.monotonic()))
        STATE["last"] = time.monotonic()
        r = httpx.post(URL, headers={"x-goog-api-key": keys[n], "Content-Type": "application/json"}, json=body, timeout=180)
        _note(n, r.status_code, r.text if r.status_code != 200 else "")
        if r.status_code == 200:
            return _audio(r.json())
        errors.append(f"{r.status_code} {r.text[:200]}")
        if r.status_code in (401, 403) or (r.status_code == 429 and re.search(r"per ?day|PerDay", r.text, re.I)):
            dead.add(n)
        if r.status_code == 400 and "language" in speech and "language" in r.text.lower():
            STATE["lang_field"] = False  # champ inconnu de l'API : la consigne du style suffit
            print("Gemini TTS : champ language refusé, consigne de langue seule", file=sys.stderr, flush=True)
            return _call(text, instruction)
        if r.status_code not in (429, 500, 503):
            break
        if attempt % len(keys) == len(keys) - 1:
            time.sleep(20)
    raise RuntimeError(f"Gemini TTS en échec : {errors[-1] if errors else '?'}")


def _note(n: int, code: int, text: str) -> None:
    """Suivi de la clé n (worker/keyusage.py) : appel réussi ou refus, avec la limite que Google annonce."""
    if not STATE.get("db") or not STATE.get("slots"):
        return
    from worker.keyusage import record
    from worker.providers.llm import fingerprint

    key, pool, slot, slots = STATE["slots"][n]
    record(
        STATE["db"],
        provider="gemini",
        model=STATE["model"],
        fingerprint=fingerprint(key),
        pool=pool,
        slot=slot,
        slots=slots,
        ok=code == 200,
        status_code=code,
        text=text,
    )


def _audio(data: dict[str, Any]) -> tuple[np.ndarray, int]:
    for step in data.get("steps") or []:
        for part in step.get("content") or []:
            if part.get("type") == "audio" and part.get("data"):
                with wave.open(io.BytesIO(base64.b64decode(part["data"])), "rb") as w:
                    rate, width = w.getframerate(), w.getsampwidth()
                    frames = w.readframes(w.getnframes())
                x = np.frombuffer(frames, dtype="<i2" if width == 2 else "<i4").astype(np.float32)
                return x / (32768.0 if width == 2 else 2147483648.0), rate
    raise RuntimeError(f"réponse sans audio : {str(data)[:300]}")


if __name__ == "__main__":
    run(synthesize, prepare=prepare)
