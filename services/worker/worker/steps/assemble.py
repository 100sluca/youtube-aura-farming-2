"""Assemblage FFmpeg : clips → final 1080×1920 avec narration, sous-titres, titres, musique ; preview 480p, poster.

Les durées de scène viennent de la timeline de narration (videos.timeline) : une scène dont la phrase
déborde est allongée, et son clip légèrement ralenti (au plus ×1,35, puis dernière image tenue).
Sous-titres et titres de scène sont gravés depuis un fichier ASS (worker/subtitles.py), titre d'accroche compris,
selon le modèle de montage réglé dans l'onglet Montage du dashboard (worker/montage.py, docs/23-montage.md) : polices,
couleurs, fonds, positions, et formats où chaque couche s'affiche. La musique de fond vient de la bibliothèque de Luca
(dossier « music » du dépôt, worker/music.py, docs/26-musique.md) : voix et piste ramenées au même niveau, puis
niveaux du modèle (onglet Montage → Son) ; sous la voix, la musique baisse pendant chaque passage parlé et remonte
entre les phrases.

Formats visuels (worker/recipes.py, docs/15) : titre d'accroche gravé en haut (PNG façon MJClipIt,
worker/hooktitle.py), transitions entre scènes (coup de fouet flou, fondu, zoom : xfade), clips « première +
dernière image » accélérés plutôt que coupés (ils doivent finir sur l'image clé où commence le suivant),
images intermédiaires calculées pour une caméra fluide (minterpolate), bruitages placés sous l'image
(worker/sfx.py) et musique plus présente, sans voix.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from ..drama import build_dialogue_track, dialogue_timeline, is_drama
from ..hooktitle import build_png, overlay_filter
from ..media import measure_loudness, pick_music, run, video_encode_args
from ..models import NarrationTimeline, ScriptV1, WordTiming
from ..montage import AudioLayer, MontageTemplate, font_registry, hook_text, load_template
from ..music import (
    FADE_IN_S,
    FADE_OUT_S,
    OUTPUT_LUFS,
    Track,
    choose_track,
    duck_expression,
    mix_levels,
    music_start,
    speech_segments,
    sync_library,
)
from ..numbers import merge_timed, to_digits
from ..recipes import day_counter, is_visual, montage_format, recipe_for_production, spec
from ..retouch import MusicChoice, Retouch, forced_music, load_retouch
from ..sfx import WHOOSH_TRANSITIONS, SfxCue, parse_tags, pick_sfx, plan_cues
from ..subtitles import FontRegistry, SubtitleProfile, TitleStyle, build_ass, write_subtitles
from ..youtube.storage import upload_preview
from .base import Context, Step

W, H, FPS = 1080, 1920, 30
MAX_SLOWDOWN = 1.35
MAX_SPEEDUP = 2.0  # un clip « première + dernière image » est accéléré au plus ×2 pour tenir dans sa scène (défaut)
# Transitions FFmpeg (filtre xfade) ; push = on avance à travers l'ouverture vers la pièce suivante (visite)
XFADE = {"whip": "hblur", "fade": "fade", "zoom": "zoomin", "push": "zoomin"}
# Images intermédiaires compensées en mouvement, calculées à la résolution native du clip (peu coûteux),
# avant l'agrandissement : 16 i/s de Wan → 30 i/s sans saccade pour un mouvement de caméra lent
INTERPOLATE = f"minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"
# Chantier accéléré : quatre images consécutives fondues ensemble après l'accélération. Ce qui est immobile reste
# net, ce qui bouge (ouvriers, engins, nuages) laisse une traînée : la signature d'un vrai time-lapse (docs/15 §1.1)
TRAILS = "tmix=frames=4:weights='1 1 1 1'"
TRAILS_MIN_SPEEDUP = 1.5


@dataclass
class RenderPlan:
    clips: list[Path]
    clip_durations: list[float | None]  # durée native de chaque clip (None = inconnue)
    scene_durations: list[float]  # durées effectives sur la vidéo
    words_by_scene: list[list[WordTiming]] = field(default_factory=list)
    titles: list[tuple[float, float, str]] = field(default_factory=list)
    narration: Path | None = None
    voice_gain_db: float = 0.0  # gain de la voix : égalisation + réglage « Voix IA » (worker/music.py)
    music: Path | None = None
    music_start_s: float = 0.0  # la musique part de cet endroit du fichier
    music_gain_db: float = -18.0  # gain de la piste : égalisation + niveau du modèle + volume de la piste
    duck_db: float = 0.0  # baisse de la musique pendant que la voix parle
    speech: list[tuple[float, float]] = field(default_factory=list)  # passages parlés (s) : là où la musique baisse
    sfx_gain_db: float = 0.0
    profile: SubtitleProfile | None = None  # None = ni sous-titres ni titres
    title_style: TitleStyle | None = None  # textes à l'écran (modèle de montage) ; None = réglages title_* du profil
    # Formats visuels (docs/15)
    fit: list[str] = field(default_factory=list)  # par clip : trim (coupé, défaut) | speed (accéléré, finit sur son image)
    transitions: list[tuple[str, float]] = field(default_factory=list)  # passage scène i → i+1 : (cut|whip|fade|zoom, s)
    interpolate: bool = False
    hook_png: Path | None = None
    hook_filter: str = "overlay=(W-w)/2:150"
    sfx: list[SfxCue] = field(default_factory=list)
    max_speedup: float = MAX_SPEEDUP  # accélération maximale d'un clip « speed » (recette)
    trails: bool = False  # traînées des silhouettes sur les clips accélérés (chantier)
    ticks: list[tuple[float, float, str]] = field(default_factory=list)  # compteur qui défile, sans fondu

    @property
    def overlaps(self) -> list[float]:
        """Durée de chaque transition i → i+1 (0 = coupe), bornée à la moitié des deux scènes."""
        out = []
        for i in range(len(self.scene_durations) - 1):
            kind, d = self.transitions[i] if i < len(self.transitions) else ("cut", 0.0)
            ok = kind in XFADE and d > 0
            out.append(round(min(d, self.scene_durations[i] / 2, self.scene_durations[i + 1] / 2), 3) if ok else 0.0)
        return out

    @property
    def starts(self) -> list[float]:
        """Début de chaque scène sur la vidéo (une transition fait chevaucher deux scènes)."""
        out, t, ov = [], 0.0, self.overlaps
        for i, d in enumerate(self.scene_durations):
            out.append(round(t, 3))
            t += d - (ov[i] if i < len(ov) else 0.0)
        return out

    @property
    def total_s(self) -> float:
        return round(sum(self.scene_durations) - sum(self.overlaps), 3)


def scene_titles(script: ScriptV1, lang: str, starts: Sequence[float], durations: Sequence[float]) -> list[tuple[float, float, str]]:
    """Texte à l'écran de chaque scène ; il s'arrête quand la scène suivante commence (pendant une transition, deux
    titres superposés devenaient illisibles : « BIB SUITE · VUE SUR LE PIC INE », essai du 25/09)."""
    titles = []
    for i, (scene, start, d) in enumerate(zip(script.scenes, starts, durations, strict=True)):
        text = to_digits(scene.on_screen_text.get(lang, "").strip(), lang)  # type: ignore[call-overload]
        end = min(start + d, starts[i + 1]) if i + 1 < len(starts) else start + d
        if text:
            titles.append((round(start, 3), round(end, 3), text))
    return titles


def plan_from(script: ScriptV1, lang: str, timeline: NarrationTimeline | None) -> tuple[list[float], list[list[WordTiming]], list[tuple[float, float, str]]]:
    """Durées, mots par scène et titres de scène, depuis la timeline (ou le script en format B). Les nombres s'affichent
    en chiffres, même dits en lettres par une narration d'avant la règle (worker/numbers.py : « huit » « cent »
    « cinquante-deux » → « 852 »)."""
    if timeline and len(timeline.scenes) == len(script.scenes):
        durations = [s.duration for s in timeline.scenes]
        words = [merge_timed(s.words, lang) for s in timeline.scenes]
    else:
        durations = [s.duration_s for s in script.scenes]
        words = [[] for _ in script.scenes]
    starts, t = [], 0.0
    for d in durations:
        starts.append(t)
        t += d
    return durations, words, scene_titles(script, lang, starts, durations)


def _clip_chain(i: int, d: float, native: float | None, fit: str, interpolate: bool, max_speedup: float = MAX_SPEEDUP,
                trails: bool = False) -> str:
    """Filtre d'un clip : cadrage 9:16, calage sur la durée de la scène (ralenti, accéléré ou image tenue) ;
    un clip accéléré d'au moins ×1,5 reçoit les traînées du time-lapse si la recette le demande."""
    timing, held = "", 0.0
    if native and fit in ("speed", "fill") and native > d + 0.02:
        # « fill » (clip Gemini en ligne de 4 à 10 s, docs/17) : accéléré en entier pour finir sur l'image suivante,
        # au-delà de max_speedup ; « speed » : plafonné, la fin peut être coupée
        factor = d / native if fit == "fill" else max(1 / max_speedup, d / native)
        timing = f"setpts={factor:.4f}*PTS"
        if trails and 1 / factor >= TRAILS_MIN_SPEEDUP:
            timing += f",{TRAILS}"
    elif native and d > native + 0.02:
        factor = min(MAX_SLOWDOWN, d / native)
        timing = f"setpts={factor:.4f}*PTS"
        held = d - native * factor
    # format commun : xfade refuse deux clips de formats de pixels différents
    geom = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,format=yuv420p"
    tail = f"trim=duration={d:.3f},setpts=PTS-STARTPTS[v{i}]"
    hold = f"tpad=stop_mode=clone:stop_duration={held + 0.1:.3f}" if held > 0.02 else ""
    if interpolate:
        steps = [s for s in (timing, INTERPOLATE, hold, geom, f"fps={FPS}", tail) if s]
        return f"[{i}:v]" + ",".join(steps)
    stretch = f",{timing}" if timing else ""
    if hold:
        stretch += f",fps={FPS},{hold}"
    return f"[{i}:v]{geom}{stretch},fps={FPS},{tail}"


def _gain(db: float) -> str:
    return f",volume={db:.2f}dB" if abs(db) >= 0.01 else ""


def music_chain(plan: RenderPlan, total: float, *, ducked: bool) -> str:
    """Filtres de la musique : départ dans le fichier (après la boucle -stream_loop), gain, baisse pendant chaque passage
    parlé (volume évalué toutes les 256 échantillons, 5 ms : rampes sans escalier), longueur de la vidéo, fondus."""
    steps = [f"atrim=start={plan.music_start_s:.3f},asetpts=PTS-STARTPTS"] if plan.music_start_s > 0 else []
    steps.append(f"volume={plan.music_gain_db:.2f}dB")
    duck = duck_expression(plan.speech, plan.duck_db) if ducked else None
    if duck:
        steps.append(f"asetnsamples=n=256:p=0,volume='{duck}':eval=frame")
    steps.append(f"atrim=0:{total:.3f},afade=t=in:st=0:d={FADE_IN_S},afade=t=out:st={max(0.0, total - FADE_OUT_S):.3f}:d={FADE_OUT_S}")
    return ",".join(steps)


def _voice_music_inputs(plan: RenderPlan, k: int) -> tuple[list[str], int | None, int | None, int]:
    """Entrées FFmpeg de la narration et de la musique (en boucle) à partir de l'index k : arguments, index de la voix,
    index de la musique, prochain index libre."""
    args: list[str] = []
    nar_idx = mus_idx = None
    if plan.narration:
        nar_idx, k = k, k + 1
        args += ["-i", str(plan.narration)]
    if plan.music:
        mus_idx, k = k, k + 1
        args += ["-stream_loop", "-1", "-i", str(plan.music)]
    return args, nar_idx, mus_idx, k


def _sfx_inputs(plan: RenderPlan) -> list[str]:
    return [a for cue in plan.sfx for a in ([*(["-stream_loop", "-1"] if cue.loop else []), "-i", str(cue.path)])]


def build_command(plan: RenderPlan, out: Path, encoder_args: Sequence[str], subtitles_filter: str | None) -> list[str]:
    """Commande FFmpeg complète. À lancer avec cwd = dossier du fichier ASS (chemins relatifs, cf. subtitles.py)."""
    n = len(plan.clips)
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for c in plan.clips:
        cmd += ["-i", str(c)]
    args, nar_idx, mus_idx, k = _voice_music_inputs(plan, n)
    cmd += args
    hook_idx = None
    if plan.hook_png:
        hook_idx, k = k, k + 1
        cmd += ["-i", str(plan.hook_png)]
    sfx_idx = k
    cmd += _sfx_inputs(plan)

    fits = plan.fit or ["trim"] * n
    parts = [
        _clip_chain(i, d, native, fits[i] if i < len(fits) else "trim", plan.interpolate, plan.max_speedup, plan.trails)
        for i, (d, native) in enumerate(zip(plan.scene_durations, plan.clip_durations, strict=True))
    ]
    ov, starts = plan.overlaps, plan.starts
    if not any(ov):
        parts.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vcat]")
    else:  # transitions : xfade entre deux scènes, concat pour une coupe
        acc = "v0"
        for j in range(1, n):
            if ov[j - 1] > 0:
                kind = XFADE[plan.transitions[j - 1][0]]
                parts.append(f"[{acc}][v{j}]xfade=transition={kind}:duration={ov[j - 1]:.3f}:offset={starts[j]:.3f}[j{j}]")
            else:  # concat sort en base de temps 1/1 000 000 : xfade exige la même base que la scène suivante
                parts.append(f"[{acc}][v{j}]concat=n=2:v=1:a=0,settb=1/{FPS}[j{j}]")
            acc = f"j{j}"
        parts.append(f"[{acc}]null[vcat]")
    if hook_idx is None:
        parts.append(f"[vcat]{subtitles_filter}[vout]" if subtitles_filter else "[vcat]null[vout]")
    else:
        cur = "vcat"
        if subtitles_filter:
            parts.append(f"[vcat]{subtitles_filter}[vsub]")
            cur = "vsub"
        parts.append(f"[{cur}][{hook_idx}:v]{plan.hook_filter}[vout]")

    sound, audio = audio_filters(plan, nar_idx, mus_idx, sfx_idx)
    cmd += ["-filter_complex", ";".join(parts + sound), "-map", "[vout]"]
    cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"] if audio else ["-an"]
    cmd += [*encoder_args, "-pix_fmt", "yuv420p", "-r", str(FPS), "-t", f"{plan.total_s:.3f}", "-movflags", "+faststart", str(out)]
    return cmd


def sound_command(plan: RenderPlan, video: Path, out: Path) -> list[str]:
    """Remet le son d'une vidéo déjà montée avec le mixage du plan (même graphe que le montage) : l'image est copiée
    telle quelle, seul le son est recalculé. Sert à l'essai du son de l'onglet Montage (quelques secondes)."""
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(video)]
    args, nar_idx, mus_idx, sfx_idx = _voice_music_inputs(plan, 1)
    cmd += args + _sfx_inputs(plan)
    sound, audio = audio_filters(plan, nar_idx, mus_idx, sfx_idx)
    cmd += (["-filter_complex", ";".join(sound), "-map", "0:v", "-map", "[aout]", "-c:a", "aac", "-b:a", "192k"]
            if audio else ["-map", "0:v", "-an"])
    cmd += ["-c:v", "copy", "-t", f"{plan.total_s:.3f}", "-movflags", "+faststart", str(out)]
    return cmd


def audio_filters(plan: RenderPlan, nar_idx: int | None, mus_idx: int | None, sfx_idx: int) -> tuple[list[str], bool]:
    """Graphe du son (voix, musique baissée sous la voix, bruitages, mixage ramené à −14 LUFS) jusqu'à [aout] ; False
    si la vidéo n'a aucun son."""
    parts: list[str] = []
    total = plan.total_s
    fmt = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
    loud = f"loudnorm=I={OUTPUT_LUFS:g}:TP=-1:LRA=11"
    fade_out = f"afade=t=out:st={max(0.0, total - FADE_OUT_S):.3f}:d={FADE_OUT_S}"
    base: str | None = "main"
    if nar_idx is not None and mus_idx is not None:  # récit : la musique sous la voix, baissée pendant qu'elle parle
        parts += [
            f"[{nar_idx}:a]{fmt}{_gain(plan.voice_gain_db)}[nar]",
            f"[{mus_idx}:a]{fmt},{music_chain(plan, total, ducked=True)}[mus]",
            "[nar][mus]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[main]",
        ]
    elif nar_idx is not None:
        parts.append(f"[{nar_idx}:a]{fmt}{_gain(plan.voice_gain_db)}[main]")
    elif mus_idx is not None:  # format B : l'ambiance seule, plus présente
        parts.append(f"[{mus_idx}:a]{fmt},{music_chain(plan, total, ducked=False)}[main]")
    else:
        base = None
    sfx_gain = 10 ** (plan.sfx_gain_db / 20)
    sfx_labels = []
    for j, cue in enumerate(plan.sfx):
        fade = max(0.02, min(cue.fade, cue.duration / 3))
        parts.append(
            f"[{sfx_idx + j}:a]{fmt},atrim=0:{cue.duration:.3f},asetpts=PTS-STARTPTS,afade=t=in:st=0:d={fade:.3f},"
            f"afade=t=out:st={max(0.0, cue.duration - fade):.3f}:d={fade:.3f},volume={cue.volume * sfx_gain:.3f},"
            f"adelay=delays={round(cue.start * 1000)}:all=1[s{j}]"
        )
        sfx_labels.append(f"[s{j}]")
    audio = True
    if sfx_labels:
        mix = "" if len(sfx_labels) == 1 else f"amix=inputs={len(sfx_labels)}:duration=longest:normalize=0,"
        parts.append("".join(sfx_labels) + f"{mix}apad=whole_dur={total:.3f},atrim=0:{total:.3f}[sfx]")
        if base:
            parts.append(f"[{base}][sfx]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,{loud}[aout]")
        else:
            parts.append(f"[sfx]{fade_out},{loud}[aout]")
    elif base:
        parts.append(f"[{base}]{loud}[aout]")
    else:
        audio = False
    return parts, audio


def render(plan: RenderPlan, out: Path, *, fonts: FontRegistry, encoder: str = "auto") -> None:
    workdir = out.parent
    flt = None
    if plan.profile and (any(plan.words_by_scene) or plan.titles or plan.ticks):
        ass = build_ass(plan.words_by_scene, plan.profile, plan.titles, fonts=fonts, ticks=plan.ticks, title_style=plan.title_style)
        flt = write_subtitles(workdir, ass, plan.profile, fonts, plan.title_style)
    run(build_command(plan, out, video_encode_args(encoder), flt), cwd=workdir)


LEVEL_TOLERANCE_LU = 0.5  # écart toléré entre le niveau du final et OUTPUT_LUFS (le contrôle qualité accepte ±1 LU)


def level_fix_db(measured: float | None, target: float = OUTPUT_LUFS) -> float:
    """Gain qui ramène le final au niveau voulu ; 0 dans la tolérance, ou sans mesure (vidéo muette)."""
    if measured is None or abs(measured - target) <= LEVEL_TOLERANCE_LU:
        return 0.0
    return round(target - measured, 2)


def fix_level(final: Path) -> float:
    """Le loudnorm en une passe du mixage reste parfois sous la cible quand la voix est très dynamique (Pocket TTS, 28/09 :
    −16,1 LUFS au lieu de −14, refusé par le contrôle qualité). On mesure le final et on corrige d'un gain, avec un
    limiteur contre la saturation (crête à −1 dB) ; l'image est copiée. Renvoie le gain appliqué (0 : rien à corriger)."""
    gain = level_fix_db(measure_loudness(final).lufs)
    if gain:
        fixed = final.with_name(f"{final.stem}.niveau{final.suffix}")
        run(["ffmpeg", "-y", "-v", "error", "-i", str(final), "-map", "0:v", "-map", "0:a", "-c:v", "copy",
             "-af", f"volume={gain:.2f}dB,alimiter=limit=0.891:level=false:latency=true", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(fixed)])
        fixed.replace(final)
    return gain


def apply_template(
    plan: RenderPlan, template: MontageTemplate, recipe: str, *, hook: str, workdir: Path, fonts: FontRegistry,
) -> dict[str, Any]:
    """Habillage du modèle de montage (onglet Montage, worker/montage.py), après apply_recipe : style et position des
    sous-titres et des textes à l'écran, et, selon le format (récit, chantier, visite), textes à l'écran, compteur et
    titre d'accroche `hook` affichés ou non. Renvoie ce qui manque (pour le journal)."""
    report: dict[str, Any] = {}
    plan.profile = template.profile()
    plan.title_style = template.title_style()
    if not template.subtitles.enabled:
        plan.words_by_scene = []
    if not template.shows_titles(recipe):
        plan.titles, plan.ticks = [], []
    plan.hook_png = None
    if hook and template.shows_hook(recipe):
        style = template.hook_style(fonts)
        png = build_png(hook, workdir / "hook.png", style)
        if png:
            plan.hook_png, plan.hook_filter = png, overlay_filter(style, plan.total_s)
        else:
            report["hook_title"] = "Pillow absent : titre d'accroche non gravé"
    return report


def apply_audio(
    plan: RenderPlan, audio: AudioLayer, track: Track | None, *, narration_lufs: float | None = None,
    words: Sequence[WordTiming] = (),
) -> dict[str, Any]:
    """Son du modèle de montage (onglet Montage → Son, worker/music.py) : piste et départ, gains de la voix, de la musique
    et des bruitages, passages parlés où la musique baisse. Renvoie ce qui a été retenu (videos.audio_mix)."""
    with_voice = plan.narration is not None
    levels = mix_levels(audio, with_voice=with_voice, track_lufs=track.lufs if track else None,
                        track_gain_db=track.gain_db if track else 0.0, narration_lufs=narration_lufs)
    plan.voice_gain_db, plan.sfx_gain_db = levels.voice_gain_db, levels.sfx_gain_db
    plan.music = track.path if track else None
    plan.music_start_s = music_start(track, plan.total_s) if track else 0.0
    plan.music_gain_db, plan.duck_db = levels.music_gain_db, levels.duck_db
    plan.speech = speech_segments(words) if with_voice else []
    return {
        "track": track.id if track else None,
        "track_lufs": track.lufs if track else None,
        "track_gain_db": track.gain_db if track else None,
        "start_s": plan.music_start_s if track else None,
        "music_gain_db": plan.music_gain_db if track else None,
        "voice_gain_db": plan.voice_gain_db if with_voice else None,
        "narration_lufs": narration_lufs,
        "duck_db": plan.duck_db if track and with_voice else None,
        "sfx_gain_db": plan.sfx_gain_db if plan.sfx else None,
    }


def apply_recipe(plan: RenderPlan, script: ScriptV1, lang: str, recipe: str, *, sfx_dir: Path, key: str) -> dict[str, Any]:
    """Complète le plan d'un format visuel : transitions, accélération des clips première + dernière image (et
    traînées du time-lapse), interpolation, titres de scène recalés ou compteur de jours qui défile, bruitages.
    Le titre d'accroche et le style des textes viennent ensuite du modèle de montage (apply_template).
    Renvoie ce qui manque (pour le journal)."""
    rs = spec(recipe)
    plan.transitions = [(s.transition, rs.transition_s.get(s.transition, 0.0)) for s in script.scenes]
    plan.fit = ["speed" if s.clip_mode == "flf" else "trim" for s in script.scenes]
    plan.interpolate = rs.interpolate
    plan.max_speedup, plan.trails = rs.max_speedup, rs.trails
    plan.ticks = day_counter(script, lang, plan.starts, plan.scene_durations) if rs.counter else []
    plan.titles = [] if plan.ticks else scene_titles(script, lang, plan.starts, plan.scene_durations)
    report: dict[str, Any] = {}
    tags = [parse_tags(s.sfx) for s in script.scenes]
    effective = list(zip((t for t, _ in plan.transitions), [*plan.overlaps, 0.0], strict=True))
    plan.sfx = plan_cues(tags, plan.starts, plan.scene_durations, effective,
                         lambda tag, k: pick_sfx(sfx_dir, tag, k), key=key)
    moves = any(k in WHOOSH_TRANSITIONS for k, _ in plan.transitions)
    wanted = {t for ts in tags for t in ts} | ({"whoosh"} if moves else set())
    missing = sorted(t for t in wanted if not pick_sfx(sfx_dir, t, key))
    if missing:
        report["sfx_manquants"] = missing
    return report


@dataclass
class VideoMontage:
    """Ce que le montage d'une vidéo réunit avant l'habillage et le son : partagé par le montage et par l'essai du son de
    l'onglet Montage (steps/montage_preview.py), pour qu'un essai sonne exactement comme le montage."""

    plan: RenderPlan
    script: ScriptV1
    lang: str
    recipe: str
    timeline: NarrationTimeline | None
    music_track: str | None  # piste du montage précédent (videos.music_track)
    extras: dict[str, Any]  # ce qui manque à la recette (bruitages absents…)
    retouch: Retouch = field(default_factory=Retouch)  # corrections à la main de cette vidéo (docs/34-retouche.md)
    auto_subtitles: dict[str, str] = field(default_factory=dict)  # texte affiché de chaque scène, sans retouche


def prepare_video(db: Any, settings: Any, vid: Any, pid: Any) -> VideoMontage:
    """Clips, durées de la narration, mots, textes à l'écran, recette (transitions, accélération, bruitages)."""
    # to_jsonb : colonne music_track absente sans la migration 0018 (null, rien ne casse)
    v = db.fetch_one(
        "select v.lang, v.format, v.timeline, to_jsonb(v) ->> 'music_track' as music_track from videos v where v.id = %s",
        (vid,),
    )
    prod = db.fetch_one("select script from productions where id = %s", (pid,))
    assert v and prod and prod["script"], "vidéo ou script introuvable"
    script = ScriptV1.model_validate(prod["script"])
    clips = db.fetch_all(
        """select distinct on (scene_index) scene_index, local_path, duration_s, meta->>'provider' as provider,
                  meta->'dialogue' as dialogue from assets
           where production_id = %s and kind = 'clip' order by scene_index, created_at desc""",
        (pid,),
    )
    assert len(clips) == len(script.scenes), f"{len(clips)} clips pour {len(script.scenes)} scènes"
    recipe = recipe_for_production(db, pid)
    dialogue_track: Path | None = None
    # Drame en voix des clips (série en format B, docs/35) : les répliques dites par les clips font la timeline et la
    # piste de voix ; en voix constantes (format A), c'est la narration de l'étape voix, comme un récit
    if is_drama(recipe) and v["format"] == "B_visual":
        timeline = dialogue_timeline(script, v["lang"], [{"duration": c["duration_s"], "dialogue": c["dialogue"]} for c in clips])
        dialogue_track = settings.data_dir / "videos" / str(vid) / "dialogue.wav"
        if not settings.dry_run:
            build_dialogue_track([Path(c["local_path"]) for c in clips], [s.duration for s in timeline.scenes], dialogue_track)
        db.execute("update videos set timeline = %s where id = %s", (Jsonb(timeline.model_dump()), vid))
    else:
        timeline = NarrationTimeline.model_validate(v["timeline"]) if v["timeline"] else None
    durations, words, titles = plan_from(script, v["lang"], timeline)
    # Retouche (docs/34) : sous-titres corrigés à la main pour cette vidéo, recalés sur les temps de la voix ; le texte
    # automatique de chaque scène reste connu de l'écran de retouche (résultat du job)
    retouch = load_retouch(db, vid)
    auto_subtitles = {str(s.index): " ".join(w.text for w in ws) for s, ws in zip(script.scenes, words, strict=False) if ws}
    words = retouch.subtitle_words(words, [s.index for s in script.scenes])
    plan = RenderPlan(
        clips=[Path(c["local_path"]) for c in clips],
        clip_durations=[float(c["duration_s"]) if c["duration_s"] else None for c in clips],
        scene_durations=durations,
        words_by_scene=words,
        titles=titles,
        narration=dialogue_track or (settings.data_dir / "videos" / str(vid) / "narration.wav" if v["format"] == "A_voiceover" else None),
    )
    extras: dict[str, Any] = {}
    if is_visual(recipe):
        extras = apply_recipe(plan, script, v["lang"], recipe, sfx_dir=settings.effective_sfx_dir, key=str(vid))
        # Gemini en ligne rend 10 s pour une étape de 1,5 s : sans plafond, sinon la fin (l'image suivante) est coupée
        plan.fit = ["fill" if f == "speed" and c.get("provider") == "gemini_web" else f for f, c in zip(plan.fit, clips, strict=False)]
    return VideoMontage(plan, script, v["lang"], recipe, timeline, v["music_track"], extras, retouch, auto_subtitles)


def choose_music(
    db: Any, settings: Any, template: MontageTemplate, recipe: str, script: ScriptV1, pid: Any, current: str | None,
    forced: MusicChoice | None = None,
) -> tuple[Track | None, dict[str, Any]]:
    """Piste de la vidéo et pourquoi : celle du montage précédent si elle est toujours là et active (« Refaire le
    montage » garde la musique), sinon une piste de la bibliothèque de Luca tirée pour le format et l'ambiance du
    script ; sans bibliothèque (dossier ou migration 0018 absents), l'ancienne bibliothèque DATA_DIR/music. `forced` :
    musique choisie à la main pour cette vidéo (retouche, docs/34), même sur un format où le modèle n'en met pas."""
    if forced is not None:
        chosen = forced_music(sync_library(db, settings.effective_music_library_dir, measure=not settings.dry_run), forced)
        if chosen is not None:
            return chosen
    if not template.plays_music(recipe):
        return None, {"reason": "pas de musique sur ce format (modèle de montage)"}
    tracks = sync_library(db, settings.effective_music_library_dir, measure=not settings.dry_run)
    by_id = {t.id: t for t in tracks}
    if current and current in by_id and by_id[current].usable:
        return by_id[current], {"reason": "reprise du montage précédent"}
    if tracks:
        row = db.fetch_one("select s.music_moods from productions p join series s on s.id = p.series_id where p.id = %s", (pid,))
        track, mood = choose_track(tracks, recipe, script.music_mood, str(pid), (row or {}).get("music_moods") or ())
        if track:
            return track, {"mood": mood, "reason": f"ambiance « {mood} »" if mood else "aucune ambiance reconnue"}
        return None, {"reason": f"aucune piste active pour ce format ({recipe}) : onglet Montage → Son"}
    path = pick_music(settings.effective_music_dir, script.music_mood, str(pid))
    if not path:
        return None, {"reason": f"bibliothèque vide ({settings.effective_music_library_dir})"}
    loud = measure_loudness(path) if not settings.dry_run else None
    old = Track(id=f"{path.parent.name}/{path.stem}", file=path.name, title=path.stem, formats=(recipe,), path=path,
                lufs=loud.lufs if loud else None, duration_s=loud.duration_s if loud else None)
    return old, {"reason": "ancienne bibliothèque générée (DATA_DIR/music)"}


def narration_loudness(plan: RenderPlan, dry_run: bool = False) -> float | None:
    if plan.narration and plan.narration.is_file() and not dry_run:
        return measure_loudness(plan.narration).lufs
    return None


class AssembleStep(Step):
    type = "assemble"
    lane = "io"  # CPU / NVENC ; passer en "gpu" si upscale Real-ESRGAN sur GPU

    def run(self, ctx: Context) -> dict[str, Any]:
        vid, pid = ctx.job.video_id, ctx.job.production_id
        m = prepare_video(ctx.db, ctx.settings, vid, pid)
        plan, script, recipe, timeline, extras = m.plan, m.script, m.recipe, m.timeline, m.extras
        ctx.db.set_status("videos", vid, "rendering")
        ctx.db.set_status("productions", pid, "assembling")
        if extras:
            ctx.log("assemble.recette_incomplete", level="warn", recipe=recipe, **extras)
        # Modèle de montage lu maintenant : un modèle changé dans le dashboard sert dès ce montage
        template, template_name = load_template(ctx.db)
        fonts = font_registry(ctx.settings)
        vdir = ctx.video_dir(vid)
        final, preview, poster = vdir / "final.mp4", vdir / "preview.mp4", vdir / "poster.jpg"
        retouch = m.retouch  # corrections à la main de cette vidéo (Bibliothèque → Retoucher, docs/34) : elles priment
        if retouch:
            ctx.log("assemble.retouche", parts=retouch.parts())
        # Son (onglet Montage → Son) : piste de la bibliothèque, voix et musique ramenées au même niveau puis réglées
        fmt = montage_format(recipe)  # un drame se monte comme un récit (onglet Montage : récit, chantier, visite)
        track, why = choose_music(ctx.db, ctx.settings, template, fmt, script, pid, m.music_track, forced=retouch.music)
        nar_lufs = narration_loudness(plan, ctx.settings.dry_run)
        audio_mix = {**apply_audio(plan, retouch.audio_layer(template.audio), track, narration_lufs=nar_lufs,
                                   words=timeline.words if timeline else ()),
                     "title": track.title if track else None, **why, "template": template_name,
                     **({"retouch": retouch.parts()} if retouch else {})}
        if not track and retouch.music is None:  # aussi pour les récits : une ambiance sans piste se voit dans le journal
            ctx.log("assemble.sans_musique", level="warn", mood=script.music_mood, **why)
        auto_hook = hook_text(script, m.lang)
        dressing = apply_template(plan, template, fmt, hook=retouch.hook(auto_hook), workdir=vdir, fonts=fonts)
        if dressing:
            ctx.log("assemble.habillage_incomplet", level="warn", template=template_name, **dressing)
        extras.update(dressing)

        if ctx.settings.dry_run:
            for p in (final, preview, poster):
                p.write_bytes(b"")
        else:
            (vdir / "subtitles.ass").unlink(missing_ok=True)  # d'un montage précédent : ne pas l'enregistrer à tort
            ctx.progress(10, f"Montage · modèle « {template_name} »" + (f" · musique « {track.title} »" if track else "")
                         + (f" · {len(plan.sfx)} bruitages" if plan.sfx else "") + (" · retouche" if retouch else ""))
            render(plan, final, fonts=fonts, encoder=ctx.settings.video_encoder)
            if gain := fix_level(final):  # niveau final hors de −14 ± 0,5 LUFS : corrigé (docs/34 §5)
                audio_mix["level_fix_db"] = gain
                ctx.log("assemble.niveau_corrige", gain_db=gain)
            ctx.progress(70, "Preview + poster")
            run(["ffmpeg", "-y", "-v", "error", "-i", str(final), "-vf", "scale=480:-2", "-c:v", "libx264", "-crf", "28",
                 "-preset", "veryfast", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(preview)])
            run(["ffmpeg", "-y", "-v", "error", "-ss", "0.5", "-i", str(final), "-frames:v", "1", "-q:v", "3", str(poster)])

        ctx.progress(85, "Envoi de l'aperçu")
        preview_path = upload_preview(ctx.settings, preview, f"{vid}/preview.mp4", "video/mp4")
        poster_path = upload_preview(ctx.settings, poster, f"{vid}/poster.jpg", "image/jpeg")
        final_id = ctx.db.add_asset(
            video_id=vid, kind="final", local_path=str(final), width=W, height=H,
            duration_s=plan.total_s, bytes=final.stat().st_size,
        )
        preview_id = ctx.db.add_asset(
            video_id=vid, kind="preview", local_path=str(preview), storage_bucket="previews", storage_path=preview_path
        )
        poster_id = ctx.db.add_asset(
            video_id=vid, kind="poster", local_path=str(poster), storage_bucket="previews", storage_path=poster_path
        )
        if (vdir / "subtitles.ass").exists():
            ctx.db.add_asset(video_id=vid, kind="subtitles", local_path=str(vdir / "subtitles.ass"), meta={"template": template_name})
        ctx.db.execute(
            "update videos set final_asset_id = %s, preview_asset_id = %s, poster_asset_id = %s, duration_s = %s where id = %s",
            (final_id, preview_id, poster_id, plan.total_s, vid),
        )
        try:  # musique de la vidéo, pour les statistiques et pour qu'un nouveau montage la reprenne (migration 0018)
            ctx.db.execute("update videos set music_track = %s, audio_mix = %s where id = %s",
                           (track.id if track else None, Jsonb(audio_mix), vid))
        except Exception as exc:  # noqa: BLE001
            ctx.log("assemble.musique_non_enregistree", level="warn", error=str(exc)[:200])
        return {
            "final": str(final),
            "preview": preview_path,
            "duration_s": plan.total_s,
            "montage_template": template_name,
            "music": track.id if track else None,
            "music_title": track.title if track else None,
            "recipe": recipe,
            "sfx": len(plan.sfx),
            "hook_title": bool(plan.hook_png),
            "retouch": retouch.parts(),
            # textes du montage automatique, sans retouche : l'écran de retouche part de ce qui s'afficherait (docs/34)
            "texts": {"hook": auto_hook, "subtitles": m.auto_subtitles},
            **extras,
        }
