"""Modificateur de voix réglé par Luca (docs/67) : une modification légère qui reste une voix humaine, essayée sur un
extrait avant de refaire une vidéo.

Demandé le 05/10 : les voix d'arrivée de Chatterbox (narrateur, récit mystérieux, vieil homme) « font trop IA », et
pour en juger il fallait remonter toute la vidéo. Ici, pas de conversion vers une autre voix :
- la forme de la voix : hauteur, timbre (formants), intonation, débit. Deux méthodes (docs/68) :
  - « naturel » (par défaut) : la voix de Luca refaite par le vocodeur pc-NSF-HiFiGAN (vocoder.py) avec une autre
    courbe de hauteur et un spectre étiré ; la texture reste, même pour le timbre ;
  - Praat (« Change gender », PSOLA) : la forme d'onde recopiée période par période ; juste pour la hauteur, un peu
    rêche dès qu'on touche au timbre.
  Rubber Band (vocodeur de phase de FFmpeg, moteur R2) a été retiré le 05/10 : c'était le son « électrique » que Luca
  entendait en bougeant le timbre (note de naturel 1,8-2,2 contre 3,0 pour le vocodeur) ;
- le son : chaleur (bas), présence (médium), brillance (aigus), densité (compresseur), pièce (petite réverbération).

Les réglages vivent dans app_settings.voice_mods ({"profiles": [{"id", "name", "params"}]}) ; une vidéo longue les
choisit par voice.modifier_voice = "reglage:<id>". Le Studio du modificateur (page /long/voix) essaie un réglage sur
une prise : job long_take, action voice_mod, voie preview (quelques secondes).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import wave
from pathlib import Path
from typing import Any

import numpy as np

from ..media import measure_loudness

SR = 48000
VOICE_LUFS = -18.0  # comme la voix nettoyée (voice.VOICE_LUFS) : l'essai et l'original s'écoutent au même niveau
PREVIEW_S = 25.0  # longueur de l'extrait essayé dans le Studio
PREFIX = "reglage:"
VERSION = 2  # change le nom des essais en cache quand le traitement change (2 : vocodeur, nettoyage du 05/10 après-midi)

# nom → (min, max, neutre) ; les mêmes bornes que les curseurs du Studio (apps/dashboard/src/lib/voice-mods.ts)
PARAMS: dict[str, tuple[float, float, float]] = {
    "pitch_st": (-4.0, 4.0, 0.0),  # hauteur, en demi-tons
    "formant_pct": (-12.0, 12.0, 0.0),  # timbre : formants décalés (négatif = voix plus ample)
    "range_pct": (50.0, 150.0, 100.0),  # intonation : amplitude de la mélodie
    "speed_pct": (85.0, 115.0, 100.0),  # débit
    "warmth_db": (-6.0, 6.0, 0.0),  # chaleur : étagère basse à 160 Hz
    "presence_db": (-6.0, 6.0, 0.0),  # présence : cloche à 3,2 kHz
    "air_db": (-6.0, 6.0, 0.0),  # brillance : étagère haute à 8,5 kHz
    "density": (0.0, 100.0, 0.0),  # compresseur
    "room": (0.0, 100.0, 0.0),  # réverbération d'une petite pièce
}
ENGINES = ("naturel", "praat")  # « rubberband » des réglages d'avant le 05/10 après-midi → naturel


def normalize(params: dict[str, Any] | None) -> dict[str, Any]:
    """Réglages complets et bornés (valeur manquante ou illisible : neutre)."""
    raw = params or {}
    out: dict[str, Any] = {}
    for name, (lo, hi, neutral) in PARAMS.items():
        try:
            v = float(raw.get(name, neutral))
        except (TypeError, ValueError):
            v = neutral
        out[name] = round(min(hi, max(lo, v)), 2) if v == v else neutral
    out["engine"] = raw.get("engine") if raw.get("engine") in ENGINES else "naturel"
    return out


def shape_is_neutral(p: dict[str, Any]) -> bool:
    return p["pitch_st"] == 0 and p["formant_pct"] == 0 and p["range_pct"] == 100 and p["speed_pct"] == 100


def eq_filters(p: dict[str, Any]) -> list[str]:
    """Égaliseur et compresseur (FFmpeg) ; rien pour un réglage neutre."""
    f: list[str] = []
    if p["warmth_db"]:
        f.append(f"lowshelf=f=160:g={p['warmth_db']:.2f}")
    if p["presence_db"]:
        f.append(f"equalizer=f=3200:t=q:w=0.9:g={p['presence_db']:.2f}")
    if p["air_db"]:
        f.append(f"highshelf=f=8500:g={p['air_db']:.2f}")
    if p["density"]:
        d = p["density"] / 100
        f.append(f"acompressor=threshold={-14 - 10 * d:.1f}dB:ratio={1 + 3 * d:.2f}:attack=6:release=140:knee=4")
    return f


def praat_shape(src: Path, dst: Path, p: dict[str, Any]) -> None:
    """Hauteur, timbre, intonation et débit par Praat (« Change gender ») : PSOLA, la voix garde sa texture."""
    import parselmouth
    from parselmouth.praat import call

    snd = parselmouth.Sound(str(src))
    median = 0.0  # 0 : hauteur d'origine
    if p["pitch_st"]:
        pitch = snd.to_pitch(pitch_floor=60.0, pitch_ceiling=450.0)
        med = call(pitch, "Get quantile", 0, 0, 0.5, "Hertz")
        if med == med and med > 0:  # NaN : aucune voix détectée
            median = float(med) * 2 ** (p["pitch_st"] / 12)
    out = call(snd, "Change gender", 60, 450, 1 + p["formant_pct"] / 100, median, p["range_pct"] / 100, 100 / p["speed_pct"])
    x = out.values.mean(axis=0)
    write_wav(dst, x / max(1e-6, float(np.max(np.abs(x)))) * 0.9, int(out.sampling_frequency))  # niveau refait ensuite


def room_ir(seconds: float = 0.45, seed: int = 7) -> np.ndarray:
    """Réponse d'une petite pièce : quelques réflexions précoces puis une queue de bruit qui s'éteint (RT60 0,45 s),
    adoucie dans les aigus."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    tail = rng.normal(0, 1, n) * np.exp(-6.9 * t / seconds)
    tail[: int(0.012 * SR)] = 0
    for ms, g in ((7, 0.5), (13, 0.35), (19, 0.28), (29, 0.2)):
        tail[int(ms * SR / 1000)] += g * 8
    a = 0.55  # passe-bas d'un pôle : les murs absorbent les aigus
    for i in range(1, n):
        tail[i] = a * tail[i - 1] + (1 - a) * tail[i]
    return tail / np.sqrt(np.sum(tail**2))


def add_room(x: np.ndarray, amount: float) -> np.ndarray:
    if amount <= 0:
        return x
    ir = room_ir()
    size = 1 << int(np.ceil(np.log2(len(x) + len(ir))))
    wet = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[: len(x)]
    return x + wet * 0.35 * amount / 100


def read_mono(path: Path) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def write_wav(path: Path, x: np.ndarray, sr: int = SR) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def apply(src: Path, dst: Path, params: dict[str, Any], lufs: float = VOICE_LUFS, settings: Any = None) -> float:
    """La voix src modifiée selon le réglage, dans dst (mono 48 kHz 16 bits, à `lufs`). Renvoie le rapport des durées
    (débit changé : les mots horodatés du montage se décalent d'autant). settings : pour trouver le vocodeur."""
    p = normalize(params)
    dst.parent.mkdir(parents=True, exist_ok=True)
    stage = dst.with_suffix(".forme.wav")
    if shape_is_neutral(p):
        shaped = src
    elif p["engine"] == "naturel" and settings is not None:
        from .vocoder import shape_file

        shape_file(settings, src, stage, p)
        shaped = stage
    else:
        praat_shape(src, stage, p)
        shaped = stage
    filters = eq_filters(p)
    cmd = ["ffmpeg", "-v", "error", "-i", str(shaped), *(["-af", ",".join(filters)] if filters else [])]
    raw = subprocess.run([*cmd, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    x = add_room(np.frombuffer(raw, dtype=np.float32).astype(np.float64), p["room"])
    tmp = dst.with_suffix(".brut.wav")
    write_wav(tmp, x * 0.5)  # marge : le niveau est refait juste après
    measured = measure_loudness(tmp).lufs
    gain = max(-12.0, min(24.0, lufs - measured)) if measured is not None else 0.0
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(tmp), "-af", f"volume={gain:.2f}dB,alimiter=limit=0.95:level=false",
         "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(dst)],
        check=True, capture_output=True,
    )  # fmt: skip
    tmp.unlink(missing_ok=True)
    stage.unlink(missing_ok=True)
    before = wav_seconds(src) if src.suffix.lower() == ".wav" else len(read_mono(src)) / SR
    return round(wav_seconds(dst) / before, 5) if before else 1.0


# ---------------------------------------------------------------------------------------------------------------------
# Réglages enregistrés et essais du Studio
# ---------------------------------------------------------------------------------------------------------------------


def profiles(db: Any) -> list[dict[str, Any]]:
    row = db.fetch_one("select value from app_settings where key = 'voice_mods'")
    return [p for p in ((row or {}).get("value") or {}).get("profiles") or [] if isinstance(p, dict) and p.get("id")]


def profile_params(db: Any, voice_id: str) -> dict[str, Any] | None:
    """Les réglages d'une voix « reglage:<id> », None si ce réglage n'existe plus."""
    if not voice_id.startswith(PREFIX):
        return None
    pid = voice_id[len(PREFIX) :]
    found = next((p for p in profiles(db) if p["id"] == pid), None)
    return normalize(found.get("params")) if found else None


def studio_dir(settings: Any) -> Path:
    return Path(settings.data_dir).resolve() / "voix-studio"


def preview(settings: Any, source: Path, params: dict[str, Any]) -> dict[str, Any]:
    """Essai du Studio : les PREVIEW_S premières secondes de la prise, nettoyées comme pour le montage (l'original), puis
    modifiées (l'essai), au même niveau. Les fichiers restent en cache : rejouer un réglage déjà essayé est immédiat."""
    from .voice import clean_take, to_mono48

    data = Path(settings.data_dir).resolve()
    source = source.resolve()
    if data not in source.parents:
        raise RuntimeError("extrait hors du dossier de données")
    if not source.exists():
        raise RuntimeError("extrait introuvable")
    p = normalize(params)
    folder = studio_dir(settings) / "essais"
    folder.mkdir(parents=True, exist_ok=True)
    src_key = hashlib.sha1(f"{source}|{source.stat().st_mtime_ns}|{VERSION}".encode()).hexdigest()[:12]
    original = folder / f"{src_key}_original.wav"
    if not original.exists():
        whole = folder / f"{src_key}_entier.wav"
        to_mono48(source, whole, limit_s=PREVIEW_S)
        clean_take(whole, original, {}, settings)  # coupé d'après le son, comme pour le montage
        whole.unlink(missing_ok=True)
    key = hashlib.sha1(f"{src_key}|{json.dumps(p, sort_keys=True)}".encode()).hexdigest()[:12]
    modified = folder / f"{src_key}_{key}.wav"
    if not modified.exists():
        apply(original, modified, p, settings=settings)
    return {"original": original.name, "modified": modified.name, "seconds": round(wav_seconds(original), 2), "params": p}
