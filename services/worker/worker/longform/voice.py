"""La voix de Luca (docs/63 §4) : prises du Studio voix vérifiées par Whisper, puis voix finale nettoyée et, si Luca le
veut, passée dans le modificateur de voix.

1. Une prise (long_take, voie preview, dans les secondes qui suivent l'enregistrement) : Whisper large-v3-turbo sur le
   processeur (drama.transcribe, environnement d'évaluation) dit ce qu'il entend, mot par mot et horodaté ; on le
   compare au texte du paragraphe, nombres dits en lettres des deux côtés. « C'est ce que tu as dit qui fait foi » : une
   prise qui s'écarte du texte n'est pas refusée, Luca voit seulement les passages sautés pour refaire s'il le veut.
2. La voix finale (long_make, action voice) : chaque prise gardée est coupée juste avant la voix et juste après (d'après
   le son : les clics du micro restent dehors), le bruit des pauses baissé, débruitée par DeepFilterNet si la pièce est
   bruyante, mise au même niveau (clean_take, docs/68) ; puis, option, le modificateur réglé par Luca (voice_mod) ou
   une conversion vers une voix dessinée par Chatterbox VC (tts_runners/voice_convert.py, déjà installé pour les
   drames, docs/49 §12) : le jeu de Luca (rythme, émotion, respirations) reste, seul le timbre change. Jamais la voix
   d'une personne réelle : la référence est une voix Qwen dessinée du catalogue.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import tempfile
import wave
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from ..media import measure_loudness, probe_duration
from ..numbers import spoken

TAKE_OK_RATIO = 0.88  # ressemblance mot à mot au-dessus de laquelle la prise est bonne
MISSING_RUN_MAX = 3  # 4 mots du texte sautés d'affilée ou plus : passage manquant signalé (une phrase sautée en fait plus)
LEAD_S, TAIL_S = 0.12, 0.35  # marge gardée avant le premier mot et après le dernier
VOICE_LUFS = -18.0  # niveau de chaque paragraphe ; le montage remonte l'ensemble à -14 LUFS (YouTube)
SR = 48000

_WORD = re.compile(r"[\w]+", re.UNICODE)


SKIP_WORDS = {"virgule", "point"}  # « 146,58 » se lit souvent sans « virgule » : jamais un passage sauté


def norm_words(text: str, lang: str = "fr") -> list[str]:
    """Mots comparables : nombres dits en lettres (« 1937 » → mille neuf cent trente-sept), minuscules, sans
    ponctuation ; « l'or » → l, or ; « vingt-trois » → vingt, trois."""
    return [w for w in (x.lower() for x in _WORD.findall(spoken(text, lang).replace("-", " "))) if w not in SKIP_WORDS]


def compare(text: str, heard: str, lang: str = "fr") -> dict[str, Any]:
    """Ce que Whisper a entendu face au texte : ressemblance (0 à 1), passages du texte sautés, mots en plus."""
    a, b = norm_words(text, lang), norm_words(heard, lang)
    if not a:
        return {"ratio": 1.0, "missing": [], "extra": []}
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    missing: list[str] = []
    extra: list[str] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ("delete", "replace") and i2 - i1 > MISSING_RUN_MAX:
            missing.append(" ".join(a[i1:i2]))
        if op in ("insert", "replace") and j2 - j1 > MISSING_RUN_MAX:
            extra.append(" ".join(b[j1:j2]))
    matched = sum(t.size for t in sm.get_matching_blocks())
    return {"ratio": round(matched / len(a), 3), "missing": missing, "extra": extra}


def take_verdict(result: dict[str, Any]) -> str:
    return "ok" if result.get("ratio", 0) >= TAKE_OK_RATIO and not result.get("missing") else "problem"


def transcribe_one(settings: Any, path: Path, lang: str) -> dict[str, Any] | None:
    """Mots entendus dans un enregistrement (Whisper sur le processeur, drama.transcribe) ; None sans Whisper."""
    from ..drama import transcribe

    res = transcribe(settings, [path], lang, timeout_s=600)
    return res[0] if res else None


def check_take(settings: Any, path: Path, text: str, lang: str = "fr") -> dict[str, Any]:
    """Vérification d'une prise : ce qui est entendu, ressemblance, passages sautés, mots horodatés, bornes de la voix."""
    duration = probe_duration(path) or 0.0
    heard = transcribe_one(settings, path, lang)
    if heard is None:  # Whisper absent : la prise est gardée telle quelle, sans vérification
        return {"status": "ok", "unchecked": True, "duration_s": duration, "words": [], "heard": ""}
    words = [{"w": w["w"], "start": float(w["start"]), "end": float(w["end"])} for w in heard.get("words", [])]
    result = compare(text, heard.get("text", ""), lang)
    speech = heard.get("speech") or []
    start = min([w["start"] for w in words] + [s[0] for s in speech[:1]], default=0.0)
    end = max([w["end"] for w in words] + [s[1] for s in speech[-1:]], default=duration)
    return {
        **result,
        "status": take_verdict(result) if words else "problem",
        "heard": heard.get("text", ""),
        "words": words,
        "speech_start": round(start, 3),
        "speech_end": round(min(end, duration or end), 3),
        "duration_s": round(duration, 3),
        "silent": not words,
    }


# ---------------------------------------------------------------------------------------------------------------------
# Voix finale
# ---------------------------------------------------------------------------------------------------------------------


CLEANING_VERSION = 2  # 2 (05/10 après-midi) : coupe sur la voix, pauses baissées, DeepFilterNet ; le dashboard propose de
# refaire la voix d'une vidéo nettoyée par une version plus ancienne (voiceNeedsRedo)
QUIET_FLOOR_DB = -58.0  # plancher de bruit sous lequel la pièce est calme : pas de débruitage, seulement les pauses
GATE_OPEN_DB = 14.0  # niveau au-dessus du bruit à partir duquel c'est la voix (en dessous : une pause)
GATE_RANGE_DB = 24.0  # baisse du bruit dans les pauses (pas un silence total : la pièce reste, 24 dB plus bas)
SPEECH_DB = 20.0  # début et fin de la voix : 60 ms sur 100 ms à 20 dB au-dessus du bruit (un clic n'y suffit pas)
SPEECH_BELOW_DB = 25.0  # … et à moins de 25 dB sous le niveau de la voix (l'inspiration d'avant n'est pas la voix)
REC_HEAD_S, REC_TAIL_S = 0.12, 0.08  # début et fin de l'enregistrement : le « toc » du micro et le clic d'arrêt
DFN_LIMIT_DB = 18  # DeepFilterNet (pièce bruyante seulement) : jamais plus de 18 dB de baisse
DFN_URL = "https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/deep-filter-0.5.6-x86_64-pc-windows-msvc.exe"
GATE_FRAME_S = 0.005


def read_voice(src: Path, start: float | None = None, end: float | None = None) -> np.ndarray:
    """La prise en mono 48 kHz (flottants), coupe-bas à 70 Hz (grondements, chocs du micro), coupe-haut à 16 kHz."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", *(["-ss", f"{start:.3f}"] if start else []), *(["-to", f"{end:.3f}"] if end else []),
         "-i", str(src), "-af", "highpass=f=70,lowpass=f=16000", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
        capture_output=True, check=True, timeout=300,
    ).stdout  # fmt: skip
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def levels(x: np.ndarray, frame_s: float) -> np.ndarray:
    """Niveau (dBFS) de chaque tranche de frame_s secondes."""
    w = max(1, int(SR * frame_s))
    n = len(x) // w
    if n == 0:
        return np.zeros(0)
    return 20 * np.log10(np.sqrt(np.mean(x[: n * w].reshape(n, w) ** 2, axis=1)) + 1e-12)


def floor_of(x: np.ndarray) -> float | None:
    """Plancher de bruit : le 3e centile des niveaux sur 50 ms, silences numériques écartés ; None si trop court."""
    lv = levels(x, 0.05)
    lv = lv[lv > -100]  # sous -100 dBFS : silence numérique, pas du bruit
    return float(np.percentile(lv, 3)) if lv.size >= 20 else None


def noise_floor(src: Path, start: float, end: float) -> float | None:
    """Plancher de bruit de la prise entre start et end (dBFS) ; les pauses entre les phrases suffisent à le mesurer."""
    try:
        return floor_of(read_voice(src, start, end))
    except (OSError, subprocess.SubprocessError):
        return None


def sustained(lv: np.ndarray, threshold: float, need: int, window: int) -> np.ndarray:
    """Tranches où au moins `need` des `window` tranches autour dépassent le seuil : de la voix, pas un clic isolé."""
    above = (lv > threshold).astype(float)
    return np.convolve(above, np.ones(window), mode="same") >= need


def speech_bounds(
    x: np.ndarray, floor_db: float | None, first_word: float | None = None, last_word: float | None = None
) -> tuple[float, float] | None:
    """Début et fin de la voix dans x (secondes), d'après le son. Whisper place souvent le premier mot à 0,00 s : la
    coupe gardait alors le « toc » du micro qui s'allume, l'inspiration d'avant la phrase et le clic du bouton d'arrêt.
    - la voix : au moins 60 ms sur 100 ms au-dessus du bruit + 20 dB et à moins de 25 dB sous son propre niveau ;
    - first_word / last_word (Whisper, quand il les situe) : un son plus de 0,5 s avant le premier mot ou 0,6 s après
      le dernier n'est pas la phrase (bruit de bouche, « euh », souffle isolé) et reste dehors ;
    - marges : la montée douce avant (200 ms au plus) et l'extinction après (600 ms au plus), tant qu'on reste 8 dB
      au-dessus du bruit, puis 60 ms avant et 150 ms après ;
    - jamais les 120 premières ni les 80 dernières ms de l'enregistrement, sauf si la voix y est déjà.
    None si rien n'est sûr."""
    if floor_db is None:
        return None
    lv = levels(x, 0.01)
    if lv.size < 20:
        return None
    loud = lv[lv > floor_db + SPEECH_DB]
    if loud.size < 6:
        return None
    threshold = max(floor_db + SPEECH_DB, float(np.percentile(loud, 90)) - SPEECH_BELOW_DB)
    voice = np.flatnonzero(sustained(lv, threshold, 6, 10))
    if first_word is not None:
        voice = voice[voice * 0.01 >= first_word - 0.5]
    if last_word is not None:
        voice = voice[voice * 0.01 <= last_word + 0.6]
    if voice.size == 0:
        return None
    s, e = int(voice[0]), int(voice[-1])
    duration = len(x) / SR
    lo = REC_HEAD_S if s * 0.01 >= REC_HEAD_S + 0.06 else 0.0
    hi = duration - REC_TAIL_S if (e + 1) * 0.01 <= duration - REC_TAIL_S - 0.05 else duration
    soft = lv > floor_db + 8
    back = 0
    while s > 0 and soft[s - 1] and back < 20 and (s - 1) * 0.01 > lo:
        s, back = s - 1, back + 1
    fwd = 0
    while e + 1 < lv.size and soft[e + 1] and fwd < 60 and (e + 2) * 0.01 < hi:
        e, fwd = e + 1, fwd + 1
    return max(lo, s * 0.01 - 0.06), min(hi, (e + 1) * 0.01 + 0.15)


def pause_gain(x: np.ndarray, floor_db: float | None) -> np.ndarray:
    """Gain de chaque échantillon : 1 pendant la voix, -GATE_RANGE_DB dans les pauses. S'ouvre 60 ms avant la voix,
    reste ouvert 150 ms après (fins de mots douces) puis se referme en 200 ms : le bruit de la pièce ne s'entend plus
    entre les phrases ni aux bords du paragraphe, et la voix elle-même n'est pas touchée."""
    if floor_db is None or len(x) < SR // 10:
        return np.ones(len(x))
    lv = levels(x, GATE_FRAME_S)
    on = sustained(lv, floor_db + GATE_OPEN_DB, 5, 10).astype(float)
    hold, look = int(0.15 / GATE_FRAME_S), int(0.06 / GATE_FRAME_S)
    n = lv.size
    opened = np.convolve(on, np.ones(hold + look + 1), mode="full")[look : look + n] > 0  # voix entre t - hold et t + look
    up, down = np.exp(-GATE_FRAME_S / 0.015), np.exp(-GATE_FRAME_S / 0.2)
    env = np.empty(n)
    v = 0.0
    for i, target in enumerate(opened.astype(float)):
        a = up if target > v else down
        v = a * v + (1 - a) * target
        env[i] = v
    low = 10 ** (-GATE_RANGE_DB / 20)
    t = (np.arange(n) + 0.5) * GATE_FRAME_S * SR
    return np.interp(np.arange(len(x)), t, low + (1 - low) * env)


def denoiser(settings: Any) -> Path | None:
    """DeepFilterNet 3 (deep-filter.exe de la publication officielle), téléchargé au premier besoin ; None s'il manque."""
    if settings is None:
        return None
    path = Path(settings.yt2_home) / "models" / "voix" / "deep-filter.exe"
    if path.exists():
        return path
    try:
        import httpx

        r = httpx.get(DFN_URL, follow_redirects=True, timeout=600)
        r.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
        return path
    except Exception:  # noqa: BLE001 — hors ligne : la réduction de bruit de FFmpeg à la place
        return None


def write_mono(path: Path, x: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def deep_filter(exe: Path, x: np.ndarray, work: Path) -> np.ndarray:
    """La voix débruitée par DeepFilterNet (au plus DFN_LIMIT_DB de baisse), même longueur et même calage que x."""
    src = work / "avant.wav"
    write_mono(src, x)
    subprocess.run(
        [str(exe), "-D", "-a", str(DFN_LIMIT_DB), "-o", str(work / "apres"), str(src)],
        check=True, capture_output=True, timeout=1800, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )  # fmt: skip
    with wave.open(str(work / "apres" / src.name), "rb") as w:
        y = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32767
    return np.pad(y, (0, max(0, len(x) - len(y))))[: len(x)]


def denoise_filter(floor_db: float | None) -> str | None:
    """Repli sans DeepFilterNet : réduction de bruit de FFmpeg réglée sur le bruit mesuré, seulement si la pièce est
    bruyante. Réglée plus haut que le vrai bruit (le -35 dB d'avant le 05/10, pour une pièce à -72 dB), elle prenait
    les harmoniques et les consonnes pour du bruit et les baissait de 8 dB, case par case : le timbre « électrique »."""
    if floor_db is None or floor_db < QUIET_FLOOR_DB:
        return None
    return f"afftdn=nr=8:nf={max(-80, min(-20, round(floor_db))):d}"


def finish_command(src: Path, out: Path, duration: float, gain_db: float = 0.0, extra: Sequence[str] = ()) -> list[str]:
    """Petit compresseur, gain de niveau, limiteur et fondus très courts (la coupe tombe déjà dans une pause)."""
    filters = [
        *extra,
        "acompressor=threshold=-20dB:ratio=2.5:attack=8:release=120:makeup=1",
        f"volume={gain_db:.2f}dB",
        "alimiter=limit=0.95",
        f"afade=t=in:st=0:d=0.02,afade=t=out:st={max(0.0, duration - 0.05):.3f}:d=0.05",
    ]
    return [
        "ffmpeg", "-y", "-v", "error", "-i", str(src),
        "-af", ",".join(filters), "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(out),
    ]  # fmt: skip


def take_bounds(whole: np.ndarray, floor: float | None, check: dict[str, Any]) -> tuple[float, float]:
    """Où couper la prise : d'après le son (speech_bounds), guidé par les mots de Whisper quand il les situe ; jamais
    dans un mot qu'il a entendu (voix très douce) ; ses bornes seules si le son ne dit rien."""
    duration = len(whole) / SR
    words = check.get("words") or []
    w0 = float(words[0]["start"]) if words else 0.0
    w1 = float(words[-1]["end"]) if words else duration
    known_start = bool(words) and w0 > 0.05  # 0,00 : Whisper n'en sait rien
    known_end = bool(words) and w1 < duration - 0.05
    bounds = speech_bounds(whole, floor, w0 if known_start else None, w1 if known_end else None)
    if bounds is None:
        first = float(check.get("speech_start", w0))
        last = float(check.get("speech_end", w1))
        bounds = (max(0.0, first - LEAD_S), min(duration, last + TAIL_S))
    start, end = bounds
    if known_start and start > float(words[0]["end"]) - 0.1:  # la coupe tomberait dans le premier mot
        start = max(0.0, w0 - LEAD_S)
    if known_end and end < float(words[-1]["start"]) + 0.1:
        end = min(duration, w1 + TAIL_S)
    if end - start < 0.5:
        return 0.0, duration
    return start, end


def clean_take(src: Path, out: Path, check: dict[str, Any], settings: Any = None) -> dict[str, Any]:
    """Voix d'un paragraphe prête au montage (docs/68) :
    1. coupée juste avant le premier son de voix et juste après le dernier (take_bounds) : les clics du micro qui
       s'allume et du bouton d'arrêt restent dehors ;
    2. pièce bruyante (au-dessus de -58 dB) : DeepFilterNet, limité à 18 dB (repli : afftdn réglé sur le bruit) ;
    3. le bruit des pauses baissé de 24 dB (pause_gain), la voix elle-même intacte ;
    4. compresseur léger, niveau à -18 LUFS, limiteur, fondus de 20 et 50 ms.
    Renvoie le chemin, le début coupé, la durée et les mots décalés d'autant."""
    words = check.get("words") or []
    whole = read_voice(src)
    floor = floor_of(whole)
    start, end = take_bounds(whole, floor, check)
    x = whole[int(start * SR) : int(end * SR)]
    out.parent.mkdir(parents=True, exist_ok=True)
    gain_curve = pause_gain(x, floor)
    extra: list[str] = []
    method = "pauses"
    if floor is not None and floor >= QUIET_FLOOR_DB:
        exe = denoiser(settings)
        if exe is not None:
            with tempfile.TemporaryDirectory(prefix="dfn_", dir=out.parent) as work:
                try:
                    x = deep_filter(exe, x, Path(work))
                    method = "deepfilternet"
                except (OSError, subprocess.SubprocessError):
                    pass
        if method == "pauses":
            extra = [denoise_filter(floor) or "anull"]
            method = "afftdn"
    seg = len(x) / SR
    prep = out.with_suffix(".prep.wav")
    probe = out.with_suffix(".brut.wav")
    write_mono(prep, x * gain_curve)
    subprocess.run(finish_command(prep, probe, seg, extra=extra), check=True, capture_output=True)
    gain = 0.0
    try:
        measured = measure_loudness(probe).lufs
        if measured is not None:
            gain = max(-12.0, min(18.0, VOICE_LUFS - measured))
    except Exception:  # noqa: BLE001 — mesure impossible : gain nul
        gain = 0.0
    subprocess.run(finish_command(prep, out, seg, gain, extra), check=True, capture_output=True)
    prep.unlink(missing_ok=True)
    probe.unlink(missing_ok=True)
    shifted = [
        {"w": w["w"], "start": round(max(0.0, w["start"] - start), 3), "end": round(max(0.0, w["end"] - start), 3)} for w in words
    ]
    return {
        "path": str(out),
        "offset": round(start, 3),
        "duration_s": round(seg, 3),
        "words": shifted,
        "noise_floor_db": None if floor is None else round(floor, 1),
        "denoised": method != "pauses",
        "cleaning": method,
    }


def modifier_reference(settings: Any, voice_id: str) -> Path | None:
    """La voix d'arrivée du modificateur : l'enregistrement de référence d'une voix Qwen dessinée du catalogue."""
    from ..providers.tts import tts_catalog, voice_entry

    entry = voice_entry(tts_catalog(settings), voice_id) if voice_id else None
    ref = ((entry or {}).get("params") or {}).get("ref")
    if not ref:
        return None
    path = Path(settings.yt2_home) / "tts" / "qwen3" / ref
    return path if path.exists() else None


def convert_voices(settings: Any, items: Sequence[tuple[Path, Path]], reference: Path, work: Path, timeout_s: int = 7200) -> None:
    """Chatterbox VC (environnement C:\\YouTube2\\tts\\vc) : chaque (voix nettoyée → voix convertie), même durée."""
    python = Path(settings.yt2_home) / "tts" / "vc" / "venv" / "Scripts" / "python.exe"
    runner = Path(__file__).resolve().parents[2] / "tts_runners" / "voice_convert.py"
    if not python.exists():
        raise RuntimeError("modificateur de voix absent : install_tts.ps1 -Engine vc (C:\\YouTube2\\tts\\vc)")
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vc_", dir=work) as tmp:
        req = Path(tmp) / "request.json"
        req.write_text(
            json.dumps(
                {
                    "items": [
                        {"clip": str(src), "out": str(dst), "reference": str(reference), "clean": True} for src, dst in items
                    ],
                    "work": str(Path(tmp) / "work"),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        env = {
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "HF_HOME": str(Path(settings.yt2_home) / "tts" / "hf-cache"),
        }
        proc = subprocess.run(
            [str(python), str(runner), str(req)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout_s,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0:
            raise RuntimeError(f"modificateur de voix en échec (code {proc.returncode}) : {(proc.stderr or '')[-1500:]}")


def to_mono48(src: Path, out: Path, limit_s: float | None = None) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src), *(["-t", f"{limit_s:.3f}"] if limit_s else []),
         "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(out)],
        check=True, capture_output=True,
    )  # fmt: skip
