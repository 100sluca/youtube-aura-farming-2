"""Sous-titres des vidéos longues (docs/63 §12) : le texte du script, gravé sur l'image, calé mot à mot sur la voix.

- Le texte affiché est celui du script, pas ce que Whisper a cru entendre : l'orthographe des noms (Merer, Ouadi
  el-Jarf) et les nombres en chiffres (règle de Luca, docs/33) restent justes.
- Chaque mot prend le moment où Luca le dit. Les mots du script sont alignés sur les mots horodatés de sa prise
  (nombres dits en lettres des deux côtés, comme la vérification des prises, voice.compare). Un mot reformulé ou sauté
  prend sa place entre ses voisins, au prorata de sa longueur.
- Le style reprend celui des Shorts (Montserrat grasse, contour noir, mot prononcé en jaune), en plus petit, en bas de
  l'image 16:9, sans majuscules partout, 7 mots au plus : une légende se lit d'un coup d'œil pendant 20 minutes.
- Gravés une fois l'image montée (un passage de l'encodeur sur toute la vidéo, quelques minutes avec NVENC).
"""

from __future__ import annotations

import difflib
import math
import re
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from ..models import WordTiming
from ..numbers import NBSP, tokens
from ..subtitles import FontRegistry, SubtitleProfile, build_ass, write_subtitles
from .motion import FPS, H, W, segment_tail
from .voice import norm_words

# Le style des Shorts (profil « impact ») ramené au 16:9 : 66 en taille ASS ≈ 54 px de cadratin en 1080p, deux lignes
# au plus, centrées à 950 px (au-dessus de la barre de lecture de YouTube, sous l'écran de chapitre, motion.chapter_card).
PROFILE = SubtitleProfile(
    name="long",
    font_family="Montserrat",
    font_size=66,
    bold=True,
    text_transform="none",
    highlight_mode="word",
    highlight_color="#FFD400",
    outline_width=4,
    shadow_opacity=0.55,
    shadow_distance=3,
    shadow_blur=3,
    position="bottom",
    y=950,
    max_words=7,
    max_chars=36,
    animation="fade",
)

_OPENING = ("«", "(", "[", "“", "‘")
_TIGHT = (",", ".", "…", ")", "]", "”", "’")  # collés au mot d'avant ; le reste (» : ; ? ! —) avec une espace insécable


def display_tokens(text: str) -> list[str]:
    """Les mots affichés : ceux du script (un nombre par groupes, « 4 000 », reste un mot) ; une ponctuation isolée par
    des espaces (« Merer », « ici : ») se colle à son mot, pour ne jamais s'afficher seule en début ou fin de légende."""
    out: list[str] = []
    carry = ""
    for t in tokens(text):
        if any(ch.isalnum() for ch in t):
            out.append(carry + t)
            carry = ""
        elif t.startswith(_OPENING):
            carry += t + NBSP
        elif out:
            out[-1] += t if t.startswith(_TIGHT) else NBSP + t
        else:
            carry += t + NBSP
    if carry and out:
        out[-1] += NBSP + carry.strip(NBSP)
    elif carry:
        out.append(carry.strip(NBSP))
    return out


def _weight(token: str) -> float:
    return max(1, sum(ch.isalnum() for ch in token)) + 1.5


def align(text: str, heard: Sequence[dict[str, Any]], duration: float, lang: str = "fr") -> list[WordTiming]:
    """Les mots du script d'un paragraphe, horodatés (secondes depuis le début de sa voix finale) d'après les mots que
    Whisper a entendus (`heard` : {"w", "start", "end"}). Sans mots entendus : répartis sur toute la durée."""
    toks = display_tokens(text)
    if not toks:
        return []
    flat: list[str] = []
    owner: list[int] = []
    for i, t in enumerate(toks):
        for w in norm_words(t, lang):
            flat.append(w)
            owner.append(i)
    hflat: list[str] = []
    howner: list[int] = []
    for j, h in enumerate(heard):
        for w in norm_words(str(h.get("w", "")), lang):
            hflat.append(w)
            howner.append(j)
    n = len(toks)
    starts, ends = [math.nan] * n, [math.nan] * n
    if flat and hflat:
        sm = difflib.SequenceMatcher(None, flat, hflat, autojunk=False)
        for a, b, size in sm.get_matching_blocks():
            for k in range(size):
                i, h = owner[a + k], heard[howner[b + k]]
                starts[i] = float(h["start"]) if math.isnan(starts[i]) else min(starts[i], float(h["start"]))
                ends[i] = float(h["end"]) if math.isnan(ends[i]) else max(ends[i], float(h["end"]))
    lo = float(heard[0]["start"]) if heard else 0.0
    hi = float(heard[-1]["end"]) if heard else duration
    # les mots sans correspondance (reformulés, sautés, mal entendus) : entre leurs voisins, au prorata de leur longueur
    i = 0
    while i < n:
        if not math.isnan(starts[i]):
            i += 1
            continue
        j = i
        while j < n and math.isnan(starts[j]):
            j += 1
        left = ends[i - 1] if i else lo
        right = max(left, starts[j] if j < n else hi)
        weights = [_weight(t) for t in toks[i:j]]
        unit = (right - left) / sum(weights)
        t = left
        for k, w in zip(range(i, j), weights, strict=True):
            starts[k], ends[k] = t, t + w * unit
            t += w * unit
        i = j
    out: list[WordTiming] = []
    prev = 0.0
    for t, s, e in zip(toks, starts, ends, strict=True):
        s = max(prev, s)
        out.append(WordTiming(text=t, start=round(s, 3), end=round(max(s, e), 3)))
        prev = s
    return out


def timeline_words(
    paras: Sequence[Any], texts: dict[str, str], spans: dict[str, tuple[float, float]], lang: str = "fr"
) -> list[list[WordTiming]]:
    """Les mots de chaque paragraphe (render.Para) sur la timeline de la vidéo : une liste par paragraphe, pour qu'une
    légende ne chevauche jamais deux paragraphes."""
    out: list[list[WordTiming]] = []
    for p in paras:
        at = spans[p.key][0]
        words = align(texts.get(p.key, ""), p.words or [], p.duration, lang)
        out.append(
            [w.model_copy(update={"start": round(at + w.start, 3), "end": round(at + w.end, 3)}) for w in words if w.end > 0]
        )
    return out


_SENTENCE_END = re.compile(r"[.!?…]+[»\"')\]”\s]*$")
_CLAUSE_END = re.compile(r"[,;:—–]$")
MIN_CLAUSE = 3  # une virgule ne coupe la légende qu'après 3 mots (« En 2013, au fond… » reste ensemble)
# petits mots qui annoncent la suite : une légende ne finit pas sur eux (« font l'objet d'un » / « débat »)
_LEANING = {
    *"le la les l' un une des de du d' au aux à en et ou ni mais que qu' qui dont où sur sous dans par pour avec sans "
    "vers chez entre ce cet cette ces son sa ses leur leurs mon ma mes ton ta tes notre nos votre vos se s' ne n' il "
    "elle ils elles on nous vous je j' tu y plus moins très si comme près environ presque a ont est sont était avait "
    "d'un d'une l'un l'une c'est qu'il qu'elle".split()
}


def _leans(word: str) -> bool:
    """Un petit mot qui annonce la suite, ou un nombre sans son unité (« 2,3 » / « millions de blocs »)."""
    w = word.lower().strip(NBSP + "«»“”\"'()")
    return w in _LEANING or (w.endswith("'") and len(w) <= 3) or w[-1:].isdigit()


def chunks(words: Sequence[WordTiming], max_words: int = PROFILE.max_words) -> list[list[WordTiming]]:
    """Les légendes d'un paragraphe : coupées à chaque fin de phrase, à une virgule (ou : ; —) après MIN_CLAUSE mots ;
    un morceau trop long est partagé en parts égales, sans finir une part sur un petit mot qui annonce la suite."""
    clauses: list[list[WordTiming]] = []
    cur: list[WordTiming] = []
    for w in words:
        cur.append(w)
        text = w.text.rstrip(NBSP + "»”\"')")
        if _SENTENCE_END.search(w.text) or (_CLAUSE_END.search(text) and len(cur) >= MIN_CLAUSE):
            clauses.append(cur)
            cur = []
    if cur:
        clauses.append(cur)
    out: list[list[WordTiming]] = []
    for c in clauses:
        parts = math.ceil(len(c) / max_words)
        start = 0
        for k in range(1, parts):
            target = round(k * len(c) / parts)
            lo, hi = max(start + 1, len(c) - (parts - k) * max_words), min(len(c) - 1, start + max_words)
            cut = next(
                (t for t in (target, target + 1, target - 1, target + 2) if lo <= t <= hi and not _leans(c[t - 1].text)),
                max(lo, min(hi, target)),
            )
            out.append(c[start:cut])
            start = cut
        out.append(c[start:])
    return [c for c in out if c]


def write(words_by_para: Sequence[Sequence[WordTiming]], workdir: Path, fonts: FontRegistry) -> str:
    """Écrit subtitles.ass (et sa police) dans workdir ; renvoie le filtre FFmpeg à lancer avec cwd = workdir."""
    groups = [c for para in words_by_para for c in chunks(para)]
    ass = build_ass(groups, PROFILE, fonts=fonts, width=W, height=H)
    return write_subtitles(workdir, ass, PROFILE, fonts)


def burn(
    video: Path,
    workdir: Path,
    flt: str,
    out: Path,
    total_s: float,
    *,
    nvenc: bool,
    progress: Callable[[float], None] = lambda _f: None,
) -> Path:
    """Grave les sous-titres sur l'image montée (sans son). `progress` reçoit la part faite (0 à 1) ; une exception qu'il
    lève (arrêt demandé depuis le dashboard) arrête FFmpeg."""
    cmd = [
        "ffmpeg", "-y", "-v", "error", "-nostats", "-progress", "pipe:1", "-i", str(video.resolve()),
        "-vf", flt, *segment_tail(out.resolve(), nvenc),
    ]  # fmt: skip
    proc = subprocess.Popen(
        cmd,
        cwd=str(workdir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            if line.startswith("frame="):
                try:
                    progress(min(1.0, int(line.split("=", 1)[1]) / max(1.0, total_s * FPS)))
                except ValueError:
                    pass
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    err = proc.stderr.read() if proc.stderr else ""
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg n'a pas pu graver les sous-titres : {err[-500:]}")
    return out
