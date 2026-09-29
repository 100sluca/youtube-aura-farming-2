"""Voix des personnages calées sur la bouche des clips : drame en voix constantes (format A, docs/35 §2, docs/38).

MiniMax H3 dit la réplique du plan, bouche comprise, avec sa propre voix. En voix constantes, cette voix est remplacée
par celle du personnage (Qwen3), qui était posée 0,15 s après le début du plan quoi qu'il arrive : la bouche parlait
avant, après ou plus longtemps que la voix (« Mamie Pomme », 29/09 : bouche ouverte à 2,8 s pour une voix partie à
0,15 s ; demande de Luca). Désormais, chaque réplique suit la bouche de son clip :
- le son du clip est horodaté (Whisper : les mots ; détecteur de voix Silero : les passages où la bouche parle, plus
  justes au début d'une phrase), la réplique de synthèse aussi ;
- la réplique de synthèse est coupée là où la bouche fait une pause, chaque morceau étiré ou resserré (FFmpeg atempo :
  la hauteur de la voix ne bouge pas ; ×0,8 à ×1,4) pour durer comme la phrase de la bouche, et posé quand elle s'ouvre ;
- le plan commence 0,35 s avant que la bouche s'ouvre (2 s au plus du début du clip coupées : le rythme) et finit
  0,35 s après la voix ; les sous-titres suivent la voix entendue.
Un clip où la réplique n'est pas reconnue mais où quelqu'un parle : la réplique entière va du premier au dernier
passage parlé. Un clip muet garde l'ancienne pose.

Tout se refait à chaque montage, à partir de caches : répliques de synthèse découpées une fois dans
DATA_DIR/videos/<vidéo>/lines (tant que narration.wav ne change pas), transcriptions des clips dans assets.meta.dialogue.
La piste calée (lipsync.wav) et sa timeline (videos.timeline, aligner « lipsync ») servent au montage, à la retouche
et aux essais du son comme une narration.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import structlog

from .drama import HEARD_MIN, _units, align_words, heard_ratio, line_text, transcribe
from .models import NarrationTimeline, SceneTiming, ScriptV1, WordTiming
from .timeline import LEAD_IN

log = structlog.get_logger(__name__)

F_MIN, F_MAX = 0.8, 1.4  # resserrée de 20 % au plus, étirée de 40 % au plus : au-delà la voix sonne faux
LEAD_S = 0.35  # le plan commence ce temps avant que la bouche s'ouvre
HEAD_MAX = 2.0  # début du clip coupé au plus (l'image de départ, validée au storyboard, reste proche)
TAIL_S = 0.35  # après la voix, avant la coupe
SCENE_MIN_S = 1.5
GAP_MIN = 0.05  # entre deux morceaux de voix
MERGE_GAP = 0.25  # deux passages parlés plus proches sont une seule phrase (un creux entre deux mots criés n'est pas une pause)
PHRASE_MIN = 0.12
SPLIT_TOL = 0.25  # un mot commence une phrase de la bouche s'il débute au plus 0,25 s avant elle
EDGE_FADE = 0.008  # fondu aux bords de chaque morceau : pas de clic à la coupe
ENERGY_HOP = 0.05  # énergie du son du clip par tranches de 50 ms
ENERGY_REL = 0.5  # une tranche est forte si son énergie dépasse la moitié du 90e centile du clip (cri, pas l'ambiance)
LOUD_GAP = 0.1  # deux tranches fortes plus proches font un seul passage
SNAP_S = 1.0  # un premier mot tombé dans un silence se rattache au passage parlé fini au plus 1 s avant lui
OVERLAP_S = 0.05  # un mot qui chevauche un passage du détecteur d'au moins 50 ms est dans ce passage
ALIGNER = "lipsync"

Span = tuple[float, float]


@dataclass(frozen=True)
class Heard:
    """Ce qu'on entend dans un son : mots de Whisper ({"w", "start", "end"}), passages parlés, ressemblance avec la
    réplique écrite."""

    words: tuple[dict[str, Any], ...] = ()
    speech: tuple[Span, ...] = ()
    ratio: float = 0.0
    energy: tuple[float, ...] = ()  # énergie (RMS) par tranche de ENERGY_HOP, pour les passages que le détecteur rate


@dataclass(frozen=True)
class Piece:
    src: Span  # extrait de la réplique de synthèse (s, dans son fichier)
    at: float  # début dans le plan (s)
    factor: float  # durée en sortie / durée en entrée

    @property
    def out_s(self) -> float:
        return (self.src[1] - self.src[0]) * self.factor

    @property
    def end(self) -> float:
        return self.at + self.out_s

    def map(self, t: float) -> float:
        """Instant de la réplique de synthèse → instant dans le plan."""
        return self.at + (min(max(t, self.src[0]), self.src[1]) - self.src[0]) * self.factor


@dataclass(frozen=True)
class ScenePlan:
    head: float  # début du clip coupé (s)
    duration: float
    pieces: tuple[Piece, ...] = ()
    words: tuple[tuple[str, float, float], ...] = ()  # mots affichés, temps dans le plan
    mode: str = "none"  # phrases : réplique reconnue dans le clip ; span : quelqu'un y parle ; none : ancienne pose


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, v))


def phrases(speech: Sequence[Span], a: float, b: float) -> list[Span]:
    """Phrases de la bouche entre a et b : passages parlés coupés à [a, b], réunis si moins de MERGE_GAP les sépare, sans
    les bribes de moins de PHRASE_MIN."""
    out: list[list[float]] = []
    for s, e in sorted(speech):
        s, e = max(s, a), min(e, b)
        if e - s <= 0:
            continue
        if out and s - out[-1][1] < MERGE_GAP:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(round(s, 3), round(e, 3)) for s, e in out if e - s >= PHRASE_MIN]


def unit_times(text: str, words: Sequence[dict[str, Any]], lang: str) -> list[Span] | None:
    """Début et fin de chaque mot affiché de la réplique dans un son transcrit ; None si la transcription ne la suit pas
    mot à mot (align_words répartit alors la phrase d'une autre façon)."""
    units = _units(text)
    timed = align_words(text, list(words), lang)
    if not units or len(timed) != len(units):
        return None
    return [(w.start, w.end) for w in timed]


def mouth_span(units: Sequence[Span], speech: Sequence[Span]) -> Span:
    """Quand la bouche dit la réplique : du début du premier mot à la fin du dernier, corrigés par le détecteur de voix
    (Whisper fait souvent partir le premier mot de 0 s ; un passage parlé qui couvre ce mot donne le vrai début)."""
    (s0, e0), (s1, e1) = units[0], units[-1]
    onset, offset = s0, e1
    first = next((r for r in sorted(speech) if r[1] > s0 - 0.1), None)
    if first and first[0] <= e0:
        onset = max(first[0], s0)
    last = next((r for r in sorted(speech, reverse=True) if r[0] < e1 + 0.1), None)
    if last and last[1] >= s1:
        offset = last[1]
    return round(onset, 3), round(max(offset, onset + 0.1), 3)


def loud_regions(energy: Sequence[float], hop: float = ENERGY_HOP) -> list[Span]:
    """Passages où le son est fort (au-dessus de ENERGY_REL × le 90e centile) : une réplique criée, mais aussi de la
    musique ; ils ne comptent que là où Whisper entend un mot que le détecteur de voix ne couvre pas (line_regions)."""
    if not energy:
        return []
    ref = sorted(energy)[int(0.9 * (len(energy) - 1))]
    thr = max(0.005, ENERGY_REL * ref)
    out: list[Span] = []
    start: int | None = None
    for i, e in enumerate([*energy, 0.0]):
        if e >= thr and start is None:
            start = i
        elif e < thr and start is not None:
            if out and start * hop - out[-1][1] < LOUD_GAP:
                out[-1] = (out[-1][0], i * hop)
            else:
                out.append((start * hop, i * hop))
            start = None
    return [(round(s, 3), round(e, 3)) for s, e in out if e - s >= PHRASE_MIN]


def line_regions(units: Sequence[Span], speech: Sequence[Span], energy: Sequence[float] = ()) -> list[Span]:
    """Phrases où la bouche du clip dit la réplique. Le détecteur de voix d'abord (Silero : juste au début d'une phrase) :
    ses passages qui chevauchent un mot de la réplique (les bornes des mots de Whisper sont approximatives ; son premier
    mot part souvent de 0 s). Un mot qu'il ne couvre pas est pris dans un passage fort du son (« Mamie Pomme », plan 7 :
    « Attention la vieille ! » crié sur de la musique, raté par le détecteur). Un premier mot tombé dans un silence
    (Whisper l'a mal placé : plan 3, « Maman, » à 2,26 s dans un blanc) se rattache au passage parlé qui finit juste
    avant la suite de la réplique. Les autres passages du détecteur entre le début et la fin restent (une bribe entre
    deux mots, « c'est… c'est… »)."""

    def overlap(r: Span, w: Span) -> float:
        return min(r[1], w[1]) - max(r[0], w[0])

    vad = [(float(s), float(e)) for s, e in speech]
    line = [r for r in vad if any(overlap(r, w) >= OVERLAP_S for w in units)]
    uncovered = [(s + e) / 2 for s, e in units if not any(overlap(r, (s, e)) >= OVERLAP_S for r in vad)]
    line += [r for r in loud_regions(energy) if holds_any([r], *uncovered)]
    if not line:
        return [mouth_span(units, speech)]
    if not any(overlap(r, units[0]) > 0 for r in line):
        first, s0 = min(r[0] for r in line), units[0][0]
        before = [r for r in vad if first >= r[1] >= s0 - SNAP_S]
        if before:
            line.append(max(before, key=lambda r: r[1]))
    onset, offset = min(r[0] for r in line), max(r[1] for r in line)
    return phrases([*line, *vad], onset, offset)


def holds_any(regions: Sequence[Span], *ts: float) -> bool:
    return any(s <= t <= e for s, e in regions for t in ts)


def voiced(speech: Sequence[Span], a: float, b: float) -> Span:
    """Partie parlée de [a, b] d'après les passages parlés (la réplique de synthèse a des blancs au bord des coupes)."""
    inside = [(max(s, a), min(e, b)) for s, e in speech if min(e, b) - max(s, a) > 0.02]
    return (inside[0][0], inside[-1][1]) if inside else (a, b)


def split_point(t: float, speech: Sequence[Span]) -> float:
    """Où couper la réplique de synthèse avant le mot qui commence à t : au milieu d'une pause proche s'il y en a une
    (coupe dans le silence), sinon au début du mot."""
    gaps = [(e1, s2) for (_, e1), (s2, _) in zip(sorted(speech), sorted(speech)[1:], strict=False)]
    near = [g for g in gaps if g[0] - SPLIT_TOL <= t <= g[1] + SPLIT_TOL]
    return round((near[0][0] + near[0][1]) / 2, 3) if near else t


def plan_scene(text: str, lang: str, clip: Heard, tts: Heard, clip_s: float, tts_s: float) -> ScenePlan:
    """Pose de la réplique de synthèse `tts` (durée tts_s) sur la bouche du clip `clip` (durée clip_s)."""
    tts_speech = tuple(tts.speech) or ((0.0, tts_s),)
    uh = unit_times(text, clip.words, lang) if clip.ratio >= HEARD_MIN else None
    if uh:
        mouth = line_regions(uh, clip.speech, clip.energy)
        mode = "phrases"
    else:
        mouth = phrases(clip.speech, 0.0, clip_s)
        speaking = sum(e - s for s, e in mouth)
        if not mouth or speaking < 0.5 * (tts_speech[-1][1] - tts_speech[0][0]):
            return ScenePlan(0.0, 0.0, mode="none")
        mouth, mode = [(mouth[0][0], mouth[-1][1])], "span"
    # coupes : le premier mot de chaque phrase de la bouche, retrouvé dans la réplique de synthèse
    ut = unit_times(text, tts.words, lang) if mode == "phrases" else None
    cuts: list[float] = []
    kept: list[Span] = [mouth[0]]
    for ps, pe in mouth[1:]:
        k = next((i for i, (s, _) in enumerate(uh or []) if s >= ps - SPLIT_TOL), None)
        t = split_point(ut[k][0], tts_speech) if ut and k else None
        if t is None or t <= (cuts[-1] if cuts else tts_speech[0][0]) + 0.1 or t >= tts_speech[-1][1] - 0.1:
            kept[-1] = (kept[-1][0], pe)  # coupe introuvable : les deux phrases n'en font qu'une
            continue
        cuts.append(t)
        kept.append((ps, pe))
    bounds = [tts_speech[0][0], *cuts, tts_speech[-1][1]]
    pieces: list[Piece] = []
    prev = 0.0
    for (a, b), (ps, pe) in zip(zip(bounds, bounds[1:], strict=False), kept, strict=True):
        a, b = voiced(tts_speech, a, b)
        f = _clamp((pe - ps) / max(0.05, b - a), F_MIN, F_MAX)
        at = max(ps, prev + GAP_MIN if pieces else ps)
        pieces.append(Piece((round(a, 3), round(b, 3)), round(at, 3), round(f, 3)))
        prev = pieces[-1].end
    head = round(_clamp(pieces[0].at - LEAD_S, 0.0, HEAD_MAX), 3)
    pieces = [replace(p, at=round(p.at - head, 3)) for p in pieces]
    duration = round(max(SCENE_MIN_S, pieces[-1].end + TAIL_S), 3)
    words = _mapped_words(text, lang, tts.words, pieces)
    return ScenePlan(head, duration, tuple(pieces), tuple(words), mode)


def _mapped_words(text: str, lang: str, tts_words: Sequence[dict[str, Any]], pieces: Sequence[Piece]) -> list[tuple[str, float, float]]:
    """Mots affichés de la réplique aux instants où la voix calée les dit (sous-titres)."""

    def where(t: float) -> float:
        for k, p in enumerate(pieces):
            nxt = pieces[k + 1].src[0] if k + 1 < len(pieces) else float("inf")
            if t < nxt or k + 1 == len(pieces):
                return p.map(t)
        return pieces[-1].end

    heard = [{"w": w["w"], "start": where(float(w["start"])), "end": where(float(w["end"]))} for w in tts_words]
    timed = align_words(text, heard, lang) if heard else []
    if not timed:  # voix non transcrite : la réplique répartie sur la voix calée
        timed = align_words(text, [{"w": text, "start": pieces[0].at, "end": pieces[-1].end}], lang)
    return [(w.text, round(w.start, 3), round(max(w.start, w.end), 3)) for w in timed]


# ---------------------------------------------------------------------------
# Son : morceaux étirés (FFmpeg atempo) et piste complète
# ---------------------------------------------------------------------------


def stretch(x: Any, rate: int, factor: float, work: Path) -> Any:
    """Extrait `x` rendu `factor` fois plus long (hauteur de la voix gardée : atempo), longueur exacte."""
    import numpy as np
    import soundfile as sf

    x = np.asarray(x, dtype=np.float32)
    n = max(1, int(round(len(x) * factor)))
    if abs(factor - 1.0) >= 0.02 and len(x) > rate // 20:
        src, dst = work / "piece.wav", work / "piece_out.wav"
        sf.write(str(src), x, rate, subtype="FLOAT")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-af", f"atempo={1 / factor:.5f}", "-ar", str(rate),
                        "-ac", "1", "-c:a", "pcm_f32le", str(dst)], check=True, capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        x, _ = sf.read(str(dst), dtype="float32")
        x = np.asarray(x, dtype=np.float32).reshape(-1)
    return np.pad(x, (0, max(0, n - len(x))))[:n]


def _faded(x: Any, rate: int) -> Any:
    import numpy as np

    k = min(len(x) // 4, int(EDGE_FADE * rate))
    if k > 1:
        ramp = np.linspace(0.0, 1.0, k, dtype=np.float32)
        x = x.copy()
        x[:k] *= ramp
        x[-k:] *= ramp[::-1]
    return x


def scene_voice(line: Any, rate: int, plan: ScenePlan, work: Path) -> Any:
    """Voix d'un plan : les morceaux de la réplique, étirés et posés sur la bouche (silence ailleurs)."""
    import numpy as np

    out = np.zeros(int(round(plan.duration * rate)) + 1, dtype=np.float32)
    for p in plan.pieces:
        seg = np.asarray(line, dtype=np.float32)[int(round(p.src[0] * rate)):int(round(p.src[1] * rate))]
        y = _faded(stretch(seg, rate, p.factor, work), rate)
        a = int(round(p.at * rate))
        m = max(0, min(len(y), len(out) - a))
        out[a:a + m] += y[:m]
    return out


# ---------------------------------------------------------------------------
# Une vidéo : répliques découpées (cache), transcriptions, plans, piste et timeline
# ---------------------------------------------------------------------------


@dataclass
class LipSync:
    timeline: NarrationTimeline
    track: Path
    heads: list[float]  # début coupé de chaque clip, dans l'ordre des scènes
    report: dict[str, Any] = field(default_factory=dict)


def clip_energy(path: Path, hop: float = ENERGY_HOP) -> tuple[float, ...]:
    """Énergie (RMS) du son d'un clip par tranches de `hop` secondes ; vide si le clip n'a pas de son."""
    import numpy as np

    proc = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                          capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    x = np.frombuffer(proc.stdout, dtype=np.float32) if proc.returncode == 0 else np.zeros(0, dtype=np.float32)
    n = int(16000 * hop)
    if len(x) < n:
        return ()
    frames = x[: len(x) // n * n].reshape(-1, n)
    return tuple(round(float(v), 5) for v in np.sqrt((frames**2).mean(axis=1)))


def _stamp(path: Path) -> dict[str, float]:
    st = path.stat()
    return {"mtime": round(st.st_mtime, 3), "size": st.st_size}


def _paths(settings: Any, vid: Any) -> tuple[Path, Path, Path, Path]:
    """narration.wav (étape voix), dossier des répliques, piste calée, et ce que le dernier calage a retenu."""
    vdir = Path(settings.data_dir) / "videos" / str(vid)
    return vdir / "narration.wav", vdir / "lines", vdir / "lipsync.wav", vdir / "lines" / "lipsync.json"


def last_sync(settings: Any, vid: Any, timeline: NarrationTimeline) -> LipSync | None:
    """Le dernier calage de la vidéo, sans rien recalculer (essai du son de l'onglet Montage ; calage impossible cette
    fois-ci) : `timeline` est la timeline calée (videos.timeline), la piste et les débuts coupés viennent du disque."""
    _, _, track, info = _paths(settings, vid)
    try:
        saved = json.loads(info.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if timeline.aligner != ALIGNER or not track.is_file() or len(saved.get("heads") or []) != len(timeline.scenes):
        return None
    return LipSync(timeline, track, [float(h) for h in saved["heads"]], dict(saved.get("report") or {}))


def tts_timeline(settings: Any, vid: Any) -> NarrationTimeline | None:
    """La timeline de l'étape voix, gardée au premier calage (calage coupé : DRAMA_LIPSYNC=false)."""
    narration, folder, _, _ = _paths(settings, vid)
    try:
        cache = json.loads((folder / "lines.json").read_text(encoding="utf-8"))
        return NarrationTimeline.model_validate(cache["tts_timeline"]) if cache.get("narration") == _stamp(narration) else None
    except (OSError, ValueError, KeyError):
        return None


def _heard(d: dict[str, Any] | None, expected: str) -> Heard:
    if not d:
        return Heard()
    text = d.get("heard") if d.get("heard") is not None else d.get("text", "")
    return Heard(tuple(d.get("words") or ()), tuple((float(s), float(e)) for s, e in d.get("speech") or ()),
                 float(d["ratio"]) if d.get("ratio") is not None else heard_ratio(expected, str(text or "")))


def _cut_lines(narration: Path, tts_timeline: NarrationTimeline, folder: Path) -> tuple[dict[str, str], int]:
    """Réplique de chaque scène, découpée dans la piste de l'étape voix (posée à speech_start, longue de sa voix)."""
    import numpy as np
    import soundfile as sf

    x, rate = sf.read(str(narration), dtype="float32")
    x = np.asarray(x, dtype=np.float32)
    if x.ndim > 1:
        x = x.mean(axis=1)
    folder.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    for sc in tts_timeline.scenes:
        if sc.speech_start is None or sc.speech_end is None or sc.speech_end <= sc.speech_start:
            continue
        name = f"scene_{sc.index:02d}.wav"
        sf.write(str(folder / name), x[int(round(sc.speech_start * rate)):int(round(sc.speech_end * rate))], rate)
        files[str(sc.index)] = name
    return files, int(rate)


def sync_drama(db: Any, settings: Any, vid: Any, script: ScriptV1, lang: str, clips: Sequence[dict[str, Any]],
               timeline: NarrationTimeline | None) -> LipSync | None:
    """Répliques de synthèse calées sur la bouche des clips d'un drame en voix constantes ; None si c'est impossible
    (voix pas encore faite, Whisper absent) : le montage garde alors la narration telle quelle. `clips[i]` : la ligne
    d'assets du clip de la scène i (id, local_path, duration_s, dialogue)."""
    import numpy as np
    import soundfile as sf

    narration, folder, track, info = _paths(settings, vid)
    vdir, cache_file = narration.parent, folder / "lines.json"
    if not narration.is_file() or timeline is None:
        return None

    def fallback() -> LipSync | None:  # calage impossible cette fois : celui du montage d'avant, s'il y en a un
        return last_sync(settings, vid, timeline)
    cache: dict[str, Any] = {}
    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.is_file() else {}
    except (OSError, ValueError):
        cache = {}
    if cache.get("narration") != _stamp(narration):
        if timeline.aligner == ALIGNER:  # timeline déjà calée, répliques perdues : on ne peut plus les redécouper
            log.warning("levres.repliques_perdues", video=str(vid))
            return fallback()
        files, rate = _cut_lines(narration, timeline, folder)
        cache = {"narration": _stamp(narration), "rate": rate, "tts_timeline": timeline.model_dump(), "files": files, "heard": {}}
    tts_timeline = NarrationTimeline.model_validate(cache["tts_timeline"])
    files, rate = cache["files"], int(cache["rate"])

    # Transcriptions manquantes, en un seul appel (le modèle se charge une fois) : clips sans passages parlés, répliques
    texts = {sc.index: line_text(sc) for sc in script.scenes}
    todo_clips = [c for sc, c in zip(script.scenes, clips, strict=True)
                  if texts[sc.index] and not (c.get("dialogue") or {}).get("speech") and Path(c["local_path"]).is_file()]
    todo_lines = [k for k in files if k not in cache["heard"]]
    if todo_clips or todo_lines:
        paths = [Path(c["local_path"]) for c in todo_clips] + [folder / files[k] for k in todo_lines]
        try:
            results = transcribe(settings, paths, lang)
        except Exception as exc:  # noqa: BLE001  le calage est un plus : sans lui, le montage garde la narration
            log.warning("levres.transcription_en_echec", video=str(vid), error=str(exc)[:300])
            return fallback()
        if results is None:
            log.warning("levres.whisper_absent", raison="environnement tts/eval non installé : install_tts.ps1 -Engine eval")
            return fallback()
        for c, r in zip(todo_clips, results[:len(todo_clips)], strict=True):
            sc = next(s for s in script.scenes if s.index == c["scene_index"])
            c["dialogue"] = {"expected": texts[sc.index], "heard": r["text"], "words": r["words"],
                             "speech": r.get("speech") or [], "ratio": heard_ratio(texts[sc.index], r["text"])}
            if c.get("id"):  # gardé avec le clip : un nouveau montage ne le retranscrit pas
                db.execute("update assets set meta = coalesce(meta, '{}'::jsonb) || jsonb_build_object('dialogue', %s::jsonb) "
                           "where id = %s", (json.dumps(c["dialogue"], ensure_ascii=False), c["id"]))
        for k, r in zip(todo_lines, results[len(todo_clips):], strict=True):
            cache["heard"][k] = {"text": r["text"], "words": r["words"], "speech": r.get("speech") or []}
        cache_file.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    by_index = {s.index: s for s in tts_timeline.scenes}
    scenes: list[SceneTiming] = []
    heads: list[float] = []
    parts: list[Any] = []
    report: dict[str, list[int]] = {"phrases": [], "span": [], "none": []}
    t = 0.0
    with tempfile.TemporaryDirectory(prefix="levres_", dir=vdir) as tmp:
        for sc, c in zip(script.scenes, clips, strict=True):
            old = by_index.get(sc.index)
            text, key = texts[sc.index], str(sc.index)
            clip_s = float(c.get("duration_s") or 5.1)
            if not text or key not in files or old is None:  # plan sans réplique : sa durée prévue, sans voix
                d = old.duration if old else sc.duration_s
                scenes.append(SceneTiming(index=sc.index, start=round(t, 3), duration=round(d, 3)))
                heads.append(0.0)
                parts.append(np.zeros(int(round(d * rate)), dtype=np.float32))
                t += d
                continue
            line, _ = sf.read(str(folder / files[key]), dtype="float32")
            line = np.asarray(line, dtype=np.float32).reshape(-1)
            heard = _heard(c.get("dialogue"), text)
            if Path(c["local_path"]).is_file():
                heard = replace(heard, energy=clip_energy(Path(c["local_path"])))
            plan = plan_scene(text, lang, heard, _heard(cache["heard"].get(key), text), clip_s, len(line) / rate)
            if plan.mode == "none":  # personne ne parle dans le clip : l'ancienne pose (voix 0,15 s après le début)
                plan = ScenePlan(0.0, old.duration, (Piece((0.0, len(line) / rate), LEAD_IN, 1.0),),
                                 tuple((w.text, w.start - old.start, w.end - old.start) for w in old.words))
            report[plan.mode if plan.mode in report else "none"].append(sc.index)
            voice = scene_voice(line, rate, plan, Path(tmp))
            parts.append(voice[:int(round(plan.duration * rate))])
            words = [WordTiming(text=w, start=round(t + a, 3), end=round(t + b, 3)) for w, a, b in plan.words]
            scenes.append(SceneTiming(index=sc.index, start=round(t, 3), duration=plan.duration,
                                      speech_start=round(t + plan.pieces[0].at, 3), speech_end=round(t + plan.pieces[-1].end, 3),
                                      words=words))
            heads.append(plan.head)
            t += plan.duration
    sf.write(str(track), np.clip(np.concatenate(parts), -1.0, 1.0), rate)
    synced = NarrationTimeline(lang=tts_timeline.lang, aligner=ALIGNER, scenes=scenes)
    summary = {"calees": report["phrases"], "bouche_seule": report["span"], "pose_ancienne": report["none"]}
    info.write_text(json.dumps({"heads": heads, "report": summary}, ensure_ascii=False), encoding="utf-8")
    log.info("levres.calees", video=str(vid), **{k: v for k, v in report.items() if v})
    return LipSync(synced, track, heads, summary)
