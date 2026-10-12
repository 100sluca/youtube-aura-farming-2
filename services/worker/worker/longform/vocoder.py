"""Méthode « naturelle » du modificateur de voix (docs/68) : la voix de Luca refaite par un vocodeur neuronal à hauteur
réglable, pc-NSF-HiFiGAN (OpenVPI, celui d'OpenUTAU et de DiffSinger).

Ce n'est pas une conversion vers une autre voix : le vocodeur reçoit le spectre de la voix de Luca (128 bandes mel) et
sa courbe de hauteur, et refait la forme d'onde. Pour changer la voix, on touche à ces deux entrées seulement :
- hauteur : la courbe multipliée (le spectre, donc les formants, ne bouge pas) ;
- intonation : la courbe resserrée ou élargie autour de sa médiane ;
- timbre : le spectre étiré sur l'axe des fréquences (formants déplacés) ;
- débit : les trames interpolées dans le temps.

Banc du 05/10 (prise c0p1 de Khéops, note de naturel UTMOS, original 3,15) : le vocodeur reste à 3,0-3,06 quelle que soit
la modification ; Praat 2,72-2,97 ; Rubber Band de FFmpeg 1,84-2,16 (le son « électrique »). Équilibre spectral de la
voix refaite : ±1 dB par bande jusqu'à 18 kHz.

Modèle : 57 Mo, sur le processeur (onnxruntime), environ 0,15 s de calcul par seconde de voix. Téléchargé au premier
usage dans <yt2_home>/models/voix/pc-nsf-hifigan. Licence CC BY-NC-SA 4.0 (poids du modèle).
"""

from __future__ import annotations

import io
import subprocess
import threading
import zipfile
from pathlib import Path
from typing import Any

import numpy as np

SR = 44100  # fréquence du vocodeur
HOP, NFFT, NMELS, FMIN, FMAX = 512, 2048, 128, 40.0, 16000.0
MODEL_NAME = "pc_nsf_hifigan_44.1k_hop512_128bin_2025.02"
MODEL_URL = f"https://github.com/openvpi/vocoders/releases/download/pc-nsf-hifigan-44.1k-hop512-128bin-2025.02/{MODEL_NAME}.zip"
F0_FLOOR, F0_CEIL = 60.0, 450.0

_lock = threading.Lock()
_session: Any = None
_session_path: Path | None = None


def model_path(settings: Any) -> Path:
    return Path(settings.yt2_home) / "models" / "voix" / "pc-nsf-hifigan" / f"{MODEL_NAME}.onnx"


def ensure_model(settings: Any) -> Path:
    """Le modèle sur le disque ; téléchargé depuis la publication officielle d'OpenVPI s'il manque."""
    path = model_path(settings)
    if path.exists():
        return path
    import httpx

    path.parent.mkdir(parents=True, exist_ok=True)
    r = httpx.get(MODEL_URL, follow_redirects=True, timeout=600)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        for name in z.namelist():
            if name.endswith(".onnx") or Path(name).name == "NOTICE.txt":
                (path.parent / Path(name).name).write_bytes(z.read(name))
    if not path.exists():
        raise RuntimeError(f"vocodeur introuvable dans {MODEL_URL}")
    return path


def session(settings: Any) -> Any:
    """Une seule session onnxruntime par processus (chargement : environ 1 s)."""
    global _session, _session_path
    path = ensure_model(settings)
    with _lock:
        if _session is None or _session_path != path:
            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            _session = ort.InferenceSession(str(path), sess_options=opts, providers=["CPUExecutionProvider"])
            _session_path = path
        return _session


# ---------------------------------------------------------------------------------------------------------------------
# Spectre mel et hauteur, au format du vocodeur (DiffSinger : hann 2048, pas 512, mel « slaney » 40-16 000 Hz, log népérien)
# ---------------------------------------------------------------------------------------------------------------------


def _hz_to_mel(f: np.ndarray) -> np.ndarray:
    f = np.asarray(f, dtype=np.float64)
    mel = f / (200.0 / 3)
    log_part = f >= 1000.0
    return np.where(log_part, 15.0 + np.log(np.maximum(f, 1e-9) / 1000.0) / (np.log(6.4) / 27.0), mel)


def _mel_to_hz(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=np.float64)
    return np.where(m >= 15.0, 1000.0 * np.exp((np.log(6.4) / 27.0) * (m - 15.0)), m * (200.0 / 3))


def mel_basis() -> np.ndarray:
    """Banc de filtres mel « slaney » normalisé (identique à librosa.filters.mel), (128, 1025)."""
    mel_f = _mel_to_hz(np.linspace(_hz_to_mel(FMIN), _hz_to_mel(FMAX), NMELS + 2))
    fft_f = np.linspace(0, SR / 2, 1 + NFFT // 2)
    fdiff = np.diff(mel_f)
    ramps = mel_f[:, None] - fft_f[None, :]
    lower = -ramps[:NMELS] / fdiff[:NMELS, None]
    upper = ramps[2 : NMELS + 2] / fdiff[1 : NMELS + 1, None]
    w = np.maximum(0, np.minimum(lower, upper))
    return w * (2.0 / (mel_f[2 : NMELS + 2] - mel_f[:NMELS]))[:, None]


_MEL = mel_basis()


def magnitude(x: np.ndarray) -> np.ndarray:
    """Spectre d'amplitude (1025, trames) : fenêtre de Hann de 2048, pas de 512, bords en miroir."""
    pad = (NFFT - HOP) // 2
    x = np.pad(x, (pad, pad), mode="reflect")
    n = 1 + (len(x) - NFFT) // HOP
    idx = np.arange(NFFT)[None, :] + HOP * np.arange(n)[:, None]
    win = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(NFFT) / NFFT)  # Hann périodique
    spec = np.fft.rfft(x[idx] * win, axis=1)
    return np.sqrt(spec.real**2 + spec.imag**2 + 1e-9).T


def pitch_curve(x: np.ndarray, frames: int) -> tuple[np.ndarray, np.ndarray]:
    """Hauteur (Hz) à chaque trame, interpolée à travers les consonnes et les silences ; masque des trames voisées."""
    import parselmouth

    snd = parselmouth.Sound(x, SR)
    p = snd.to_pitch_ac(time_step=HOP / SR, pitch_floor=F0_FLOOR, pitch_ceiling=F0_CEIL)
    freq = p.selected_array["frequency"]
    t = np.arange(frames) * HOP / SR
    f = np.interp(t, p.xs(), freq, left=0.0, right=0.0)
    near = np.interp(t, p.xs(), (freq > 0).astype(float), left=0.0, right=0.0) > 0.99
    voiced = near & (f > 0)
    if voiced.sum() < 2:
        return np.full(frames, 120.0), voiced
    idx = np.arange(frames)
    return np.exp(np.interp(idx, idx[voiced], np.log(f[voiced]))), voiced


def warp_frequencies(mag: np.ndarray, factor: float) -> np.ndarray:
    """Formants multipliés par factor : la case k reçoit l'énergie de la case k / factor."""
    if factor == 1:
        return mag
    k = np.arange(mag.shape[0], dtype=np.float64)
    src = k / factor
    i0 = np.clip(np.floor(src).astype(int), 0, mag.shape[0] - 1)
    i1 = np.clip(i0 + 1, 0, mag.shape[0] - 1)
    fr = (src - np.floor(src))[:, None]
    out = mag[i0] * (1 - fr) + mag[i1] * fr
    out[src > mag.shape[0] - 1] = 1e-5
    return out


def stretch_frames(a: np.ndarray, speed: float) -> np.ndarray:
    """Trames interpolées dans le temps (axe 0) : speed > 1 raccourcit."""
    n = a.shape[0]
    if speed == 1 or n < 2:
        return a
    pos = np.linspace(0, n - 1, max(2, int(round(n / speed))))
    i0 = np.floor(pos).astype(int)
    i1 = np.minimum(i0 + 1, n - 1)
    fr = (pos - i0).reshape(-1, *([1] * (a.ndim - 1)))
    return a[i0] * (1 - fr) + a[i1] * fr


def resynthesize(
    settings: Any, x: np.ndarray, pitch_st: float = 0.0, formant: float = 1.0, range_ratio: float = 1.0, speed: float = 1.0
) -> np.ndarray:
    """La voix x (mono, 44,1 kHz) refaite par le vocodeur avec la hauteur, le timbre, l'intonation et le débit voulus."""
    mag = magnitude(x)
    f0, voiced = pitch_curve(x, mag.shape[1])
    mel = np.log(np.clip(_MEL @ warp_frequencies(mag, formant), 1e-5, None)).T  # (trames, 128)
    lf = np.log(f0)
    med = float(np.median(lf[voiced])) if voiced.any() else float(np.median(lf))
    f0 = np.exp(med + (lf - med) * range_ratio) * 2 ** (pitch_st / 12)
    mel = stretch_frames(mel, speed)
    f0 = np.exp(stretch_frames(np.log(f0), speed))
    out = session(settings).run(None, {"mel": mel[None].astype(np.float32), "f0": f0[None].astype(np.float32)})[0]
    return np.asarray(out, dtype=np.float64).reshape(-1)


def shape_file(settings: Any, src: Path, dst: Path, p: dict[str, Any]) -> None:
    """Hauteur, timbre, intonation et débit d'un fichier (réglage normalisé de voice_mod), résultat à 48 kHz."""
    from .voice_mod import SR as OUT_SR
    from .voice_mod import write_wav

    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(src), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
        capture_output=True,
        check=True,
    ).stdout
    x = np.frombuffer(raw, dtype=np.float32).astype(np.float64)
    y = resynthesize(
        settings,
        x,
        pitch_st=p["pitch_st"],
        formant=1 + p["formant_pct"] / 100,
        range_ratio=p["range_pct"] / 100,
        speed=p["speed_pct"] / 100,
    )
    stage = dst.with_suffix(".44k.wav")
    write_wav(stage, y / max(1e-6, float(np.max(np.abs(y)))) * 0.9, SR)  # niveau refait ensuite
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(stage), "-af", f"aresample={OUT_SR}", "-ac", "1", "-c:a", "pcm_s16le", str(dst)],
        check=True, capture_output=True,
    )  # fmt: skip
    stage.unlink(missing_ok=True)
