"""Montage d'une vidéo longue en 16:9 (docs/63 §5).

1. La timeline : les paragraphes lus par Luca, bout à bout (un souffle entre deux paragraphes, une pause plus longue
   entre deux chapitres) ; chaque plan commence au mot que le réalisateur a choisi (at_word), retrouvé dans les mots que
   Whisper a horodatés dans la prise ; le premier plan d'un paragraphe commence dans le silence qui le précède, pour
   que l'image change entre deux phrases et pas au milieu d'un mot.
2. Les segments : un MP4 sans son par plan (motion.py), encodés pareil, mis bout à bout sans réencodage. Les durées se
   comptent en images à partir des temps cumulés : la fin de l'image tombe exactement avec la fin de la voix.
3. Le son : la voix (paragraphes posés à leur place), la musique de fond (pistes de la bibliothèque des vidéos longues
   enchaînées en fondu, baissée sous la voix par un compresseur commandé par la voix), le tout ramené à -14 LUFS.
"""

from __future__ import annotations

import hashlib
import subprocess
import wave
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..media import measure_loudness, probe_duration
from .motion import FPS, render_clip, render_still

PARA_GAP_S, CHAPTER_GAP_S = 0.45, 1.25
START_PAD_S, END_PAD_S = 0.35, 2.5
MIN_SHOT_S = 1.8
CUT_AFTER_S = 0.12  # le plan d'un nouveau paragraphe commence juste après la fin du précédent
SR = 48000
MUSIC_LUFS = -33.0  # musique seule, avant la baisse sous la voix (voix à -18 LUFS)
OUTPUT_LUFS = -14.0
CROSSFADE_S = 4.0
PARALLEL = 3


@dataclass
class Para:
    key: str
    chapter: int
    path: Path
    duration: float
    words: list[dict[str, Any]]
    script_words: int


@dataclass
class TimedShot:
    idx: int
    kind: str
    start: float
    end: float = 0.0
    image: Path | None = None
    clip: Path | None = None
    clip_s: float = 0.0
    move: str = "in"
    chapter: int = 0
    first_of_chapter: bool = False
    frames: int = 0
    segments: list[Path] = field(default_factory=list)


def place_paragraphs(paras: Sequence[Para]) -> tuple[dict[str, tuple[float, float]], float]:
    """Début et fin de chaque paragraphe sur la timeline ; durée totale."""
    t = START_PAD_S
    out: dict[str, tuple[float, float]] = {}
    prev_chapter: int | None = None
    for i, p in enumerate(paras):
        if i:
            t += CHAPTER_GAP_S if p.chapter != prev_chapter else PARA_GAP_S
        out[p.key] = (round(t, 3), round(t + p.duration, 3))
        t += p.duration
        prev_chapter = p.chapter
    return out, round(t + END_PAD_S, 3)


def word_time(p: Para, at_word: int) -> float:
    """Le moment (depuis le début du paragraphe) où la voix dit le mot n° at_word du texte écrit : le mot entendu à la
    même place relative (Luca peut reformuler), sinon une règle de trois sur la durée."""
    if at_word <= 0:
        return 0.0
    if p.words:
        j = min(len(p.words) - 1, round(at_word * len(p.words) / max(1, p.script_words)))
        return float(p.words[j]["start"])
    return p.duration * at_word / max(1, p.script_words)


def plan_shots(
    paras: Sequence[Para], shots: Sequence[dict[str, Any]], spans: dict[str, tuple[float, float]], total: float
) -> list[TimedShot]:
    """Les plans sur la timeline, du premier au dernier, chacun jusqu'au début du suivant ; un plan trop court (moins de
    MIN_SHOT_S) disparaît au profit de son voisin, sauf le premier d'un chapitre."""
    by_key = {p.key: p for p in paras}
    order = {p.key: i for i, p in enumerate(paras)}
    prev_end = {p.key: (spans[paras[i - 1].key][1] if i else 0.0) for i, p in enumerate(paras)}
    seen_chapters: set[int] = set()
    timed: list[TimedShot] = []
    for s in sorted(shots, key=lambda s: (order.get(s["para"], 10**6), s["at_word"], s["idx"])):
        p = by_key.get(s["para"])
        if p is None or not (s.get("image_path") or s.get("clip_path")):
            continue
        if s["at_word"] <= 0:
            start = 0.0 if order[p.key] == 0 else prev_end[p.key] + CUT_AFTER_S
        else:
            start = spans[p.key][0] + word_time(p, s["at_word"])
        first = p.chapter not in seen_chapters
        seen_chapters.add(p.chapter)
        timed.append(
            TimedShot(
                idx=s["idx"],
                kind=s["kind"] if s.get("clip_path") else "image",
                start=round(start, 3),
                image=Path(s["image_path"]) if s.get("image_path") else None,
                clip=Path(s["clip_path"]) if s.get("clip_path") else None,
                clip_s=float(s.get("clip_s") or 0.0),
                move=s.get("motion") if s.get("motion") in ("in", "out", "left", "right", "up", "down") else "in",
                chapter=p.chapter,
                first_of_chapter=first,
            )
        )
    if not timed:
        return []
    timed.sort(key=lambda t: t.start)
    timed[0].start = 0.0
    kept: list[TimedShot] = [timed[0]]
    for t in timed[1:]:
        if t.start - kept[-1].start >= MIN_SHOT_S:
            kept.append(t)
        elif t.first_of_chapter and len(kept) > 1:  # le premier plan d'un chapitre l'emporte sur un plan trop court
            kept[-1] = t
        # sinon : plan trop court, retiré
    for a, b in zip(kept, kept[1:], strict=False):
        a.end = b.start
    kept[-1].end = total
    # durées en images à partir des temps cumulés : aucune dérive entre l'image et la voix
    for t in kept:
        t.frames = max(1, round(t.end * FPS) - round(t.start * FPS))
    return kept


def chapter_marks(timed: Sequence[TimedShot], titles: dict[int, str]) -> list[tuple[float, str]]:
    """Horodatages des chapitres pour la description (00:00 d'abord, 10 s au moins entre deux)."""
    marks: list[tuple[float, str]] = []
    for t in timed:
        if t.first_of_chapter and t.chapter in titles:
            at = 0.0 if not marks else t.start
            if marks and at - marks[-1][0] < 10:
                continue
            marks.append((at, titles[t.chapter]))
    return marks


def fmt_ts(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


# ---------------------------------------------------------------------------------------------------------------------
# Son
# ---------------------------------------------------------------------------------------------------------------------


def _read_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == SR and w.getnchannels() == 1 and w.getsampwidth() == 2, (
            f"{path.name} : pas en 48 kHz mono 16 bits"
        )
        return w.readframes(w.getnframes())


def voice_track(paras: Sequence[Para], spans: dict[str, tuple[float, float]], total: float, out: Path) -> Path:
    """La voix sur toute la durée : chaque paragraphe à sa place, du silence ailleurs (48 kHz mono 16 bits)."""
    import numpy as np

    buf = np.zeros(int(total * SR) + SR, dtype=np.int16)
    for p in paras:
        pcm = np.frombuffer(_read_pcm(p.path), dtype=np.int16)
        at = int(spans[p.key][0] * SR)
        n = min(len(pcm), len(buf) - at)
        buf[at : at + n] = pcm[:n]
    buf = buf[: int(total * SR)]
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(buf.tobytes())
    return out


def playlist(tracks: Sequence[Path], total: float, key: str) -> list[Path]:
    """Assez de pistes, dans un ordre stable pour la vidéo, pour couvrir toute la durée (fondus compris)."""
    if not tracks:
        return []
    order = sorted(tracks, key=lambda p: hashlib.sha1(f"{key}{p.name}".encode()).hexdigest())
    out: list[Path] = []
    covered = 0.0
    i = 0
    while covered < total + CROSSFADE_S and len(out) < 40:
        t = order[i % len(order)]
        d = probe_duration(t) or 120.0
        out.append(t)
        covered += d - CROSSFADE_S
        i += 1
    return out


def music_track(tracks: Sequence[Path], total: float, out: Path) -> Path | None:
    """Les pistes enchaînées en fondus croisés, coupées à la durée, fondu d'entrée et de sortie, mises à MUSIC_LUFS."""
    if not tracks:
        return None
    raw = out.with_suffix(".brut.wav")
    inputs: list[str] = []
    for t in tracks:
        inputs += ["-i", str(t)]
    if len(tracks) == 1:
        graph = "[0:a]aresample=48000,aformat=channel_layouts=stereo[m0]"
        last = "m0"
    else:
        parts = [f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[s{i}]" for i in range(len(tracks))]
        prev = "s0"
        for i in range(1, len(tracks)):
            parts.append(f"[{prev}][s{i}]acrossfade=d={CROSSFADE_S}:c1=tri:c2=tri[x{i}]")
            prev = f"x{i}"
        graph = ";".join(parts)
        last = prev
    graph += f";[{last}]atrim=0:{total:.3f},afade=t=in:st=0:d=2,afade=t=out:st={max(0.0, total - 4):.3f}:d=4[m]"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            *inputs,
            "-filter_complex",
            graph,
            "-map",
            "[m]",
            "-ar",
            str(SR),
            "-c:a",
            "pcm_s16le",
            str(raw),
        ],
        check=True,
        capture_output=True,
    )
    measured = measure_loudness(raw, timeout=600).lufs
    gain = MUSIC_LUFS - measured if measured is not None else -16.0
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", f"volume={gain:.2f}dB", "-c:a", "pcm_s16le", str(out)],
        check=True,
        capture_output=True,
    )
    raw.unlink(missing_ok=True)
    return out


def mix(voice: Path, music: Path | None, out: Path) -> Path:
    """Voix + musique baissée sous la voix (compresseur commandé par la voix), ramené à -14 LUFS, AAC 192 kb/s."""
    pre = out.with_suffix(".mix.wav")
    if music:
        graph = (
            "[0:a]aformat=channel_layouts=stereo,asplit=2[v1][v2];"
            "[1:a][v2]sidechaincompress=threshold=0.02:ratio=5:attack=20:release=450:makeup=1[duck];"
            "[v1][duck]amix=inputs=2:normalize=0:duration=first[a]"
        )
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(voice), "-i", str(music), "-filter_complex", graph, "-map", "[a]"]
    else:
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(voice), "-af", "aformat=channel_layouts=stereo"]
    subprocess.run([*cmd, "-ar", str(SR), "-c:a", "pcm_s16le", str(pre)], check=True, capture_output=True)
    measured = measure_loudness(pre, timeout=900).lufs
    gain = OUTPUT_LUFS - measured if measured is not None else 0.0
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(pre),
            "-af",
            f"volume={gain:.2f}dB,alimiter=limit=0.89:level=false",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(out),
        ],  # fmt: skip
        check=True,
        capture_output=True,
    )
    pre.unlink(missing_ok=True)
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Image
# ---------------------------------------------------------------------------------------------------------------------


def render_segments(
    timed: Sequence[TimedShot],
    segdir: Path,
    cards: dict[int, Path],
    *,
    nvenc: bool,
    progress: Callable[[int, int], None],
) -> list[Path]:
    """Un segment par plan (en parallèle : Pillow et FFmpeg travaillent pendant que les autres plans attendent).
    `progress` est appelé dans le fil du job après chaque plan : un arrêt demandé depuis le dashboard y lève son
    exception, et les plans pas encore commencés sont abandonnés."""
    segdir.mkdir(parents=True, exist_ok=True)
    done = 0

    def one(t: TimedShot) -> list[Path]:
        out = segdir / f"seg_{t.idx:04d}.mp4"
        card = cards.get(t.chapter) if t.first_of_chapter else None
        if t.clip is not None and t.clip.exists():
            return render_clip(t.clip, out, t.frames, t.clip_s or (probe_duration(t.clip) or 0.0), card=card, nvenc=nvenc)
        assert t.image is not None, f"plan {t.idx} sans image"
        render_still(t.image, out, t.frames, t.move, card=card, nvenc=nvenc)
        return [out]

    results: dict[int, list[Path]] = {}
    pool = ThreadPoolExecutor(max_workers=PARALLEL)
    try:
        futures = {pool.submit(one, t): t.idx for t in timed}
        for fut, idx in futures.items():
            results[idx] = fut.result()
            done += 1
            progress(done, len(timed))
    except BaseException:
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    pool.shutdown(wait=True)
    return [p for t in timed for p in results[t.idx]]


def concat(segments: Sequence[Path], out: Path) -> Path:
    listing = out.with_suffix(".txt")
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in segments), encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(out)],
        check=True,
        capture_output=True,
    )
    return out


def mux(video: Path, audio: Path, out: Path) -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(video),
            "-i",
            str(audio),
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-c",
            "copy",
            "-shortest",
            "-movflags",
            "+faststart",
            str(out),
        ],  # fmt: skip
        check=True,
        capture_output=True,
    )
    return out


def poster(video: Path, out: Path, at_s: float = 1.0) -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-ss",
            f"{at_s:.2f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            "scale=1280:-2",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


def preview(video: Path, out: Path) -> Path:
    """Version légère (480p) pour regarder dans le dashboard sans attendre le gros fichier."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(video),
            "-vf",
            "scale=-2:480",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "28",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-movflags",
            "+faststart",
            str(out),
        ],  # fmt: skip
        check=True,
        capture_output=True,
    )
    return out
