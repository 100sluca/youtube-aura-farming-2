"""Texte écrit DANS l'image par le générateur (docs/57 §5).

Règle de Luca du 02/10 : un texte écrit par le générateur d'images est permis seulement s'il est utile et nécessaire, et
bien réalisé de bout en bout, de l'image à la vidéo. Les vidéos modèles écrivent l'enjeu dans le décor (« PRIX : 1 € »
sur la grille d'un manoir, « 100 MILLIARDS » au-dessus d'une tête) ; le 29/09, au contraire, un panneau « SOLD » et des
répliques en sous-titres inventés par les générateurs avaient fait interdire tout texte (docs/38 §2). D'où :

- le scénariste ne demande un texte (scene.image_text) que pour l'enjeu, sur un plan SANS réplique, 2 par vidéo au plus,
  4 mots au plus, nombres en chiffres (`clean_script`) ;
- le prompt de l'image dit les mots exacts, leur support et leur place : dans le haut de l'image, sous le titre
  d'accroche et au-dessus des sous-titres du montage (`image_clause`) ; c'est le seul texte permis (`ONLY_TEXT`) ;
- l'image est relue par le modèle de vision, qui recopie ce qu'il lit SANS connaître le texte attendu ; le code compare
  lettre à lettre (`check_image`). Trois essais ; s'ils échouent tous, le plan est refait sans texte (storyboard) ;
- le clip garde le texte immobile (`motion_clause`), ses images sont relues de même (`check_clip`) ; s'il le déforme
  encore après le nouvel essai, le plan devient un plan fixe en lente avancée sur l'image vérifiée (`still_clip`) : le
  texte reste parfait, le plan n'a pas de réplique à perdre.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from .models import ImageText, ScriptScene, ScriptV1
from .numbers import to_digits

if TYPE_CHECKING:
    from .keyframe_qc import KeyframeVerdict

WORDS_MAX = 4
CHARS_MAX = 28
SCENES_MAX = 2
TEXT_TRIES = 3  # essais d'une image avec son texte ; ensuite, le plan est refait sans
# Place du texte, en % de la hauteur depuis le haut : sous le titre d'accroche (y = 150 sur 1920, deux lignes) et
# au-dessus des sous-titres (centrés à 52 %) et des textes du montage (69 %), réglages par défaut de l'onglet Montage
Y_RANGE = (14.0, 50.0)
EXTRA_CHARS_IGNORED = 2  # une marque de 1 ou 2 caractères (un chiffre sur un cadran) n'est pas un texte en trop

ONLY_TEXT = (
    'The only writing anywhere in the picture is "{text}": no other text, letters, subtitles, captions, logo or watermark.'
)


def lang_of(script: ScriptV1) -> str:
    return next(iter(script.metadata), "fr")


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text)


def clean_script(script: ScriptV1, lang: str | None = None) -> ScriptV1:
    """Ce que le code impose aux textes écrits dans l'image : mots exacts et support renseignés, 4 mots et 28 caractères
    au plus, nombres en chiffres, jamais sur un plan avec une réplique (le plan de secours, fixe, la perdrait), ni sur
    une carte, un passage, une retouche de chantier ou un plan qui prolonge le précédent ; 2 par vidéo au plus, les
    premiers gardés."""
    lang = lang or lang_of(script)
    kept = 0
    scenes: list[ScriptScene] = []
    for sc in script.scenes:
        it = sc.image_text
        keep: ImageText | None = None
        if it is not None:
            text = to_digits(" ".join(it.text.split()), lang).strip()
            on = " ".join(it.on.split()).strip()
            fits = bool(text and on) and len(text) <= CHARS_MAX and 0 < len(_words(text)) <= WORDS_MAX
            # le texte vient de l'image du storyboard : pas sur un plan qui part du clip précédent
            allowed = not sc.lines and not sc.is_map and not sc.passage and sc.edit_prompt is None and not sc.continues_previous
            if fits and allowed and kept < SCENES_MAX:
                keep = ImageText(text=text, on=on)
                kept += 1
        scenes.append(sc if keep == it else sc.model_copy(update={"image_text": keep}))
    return script.model_copy(update={"scenes": scenes})


def without_text(script: ScriptV1, pos: int) -> ScriptV1:
    """Le script où le plan `pos` n'a plus de texte écrit (plan refait sans, après trois essais ratés)."""
    scenes = list(script.scenes)
    scenes[pos] = scenes[pos].model_copy(update={"image_text": None})
    return script.model_copy(update={"scenes": scenes})


# ---- Prompts (anglais, lus par les modèles d'image et de vidéo) ------------------------------------------------------


def image_clause(it: ImageText) -> str:
    """Ce que le prompt de l'image dit du texte : les mots exacts, le support, la lisibilité et la place."""
    return (
        f'On {it.on}, exactly these words and nothing else are written: "{it.text}", in large bold clean letters, '
        "perfectly spelled, sharp and easy to read on a phone, facing the camera, in the upper part of the picture "
        "(between one sixth and two fifths of the height from the top), never at the very top, in the middle or near the "
        "bottom"
    )


def with_image_text(prompt: str, it: ImageText | None) -> str:
    return f"{prompt.rstrip(' .')}. {image_clause(it)}." if it else prompt


def only_text(text: str) -> str:
    return ONLY_TEXT.format(text=text)


def motion_clause(it: ImageText) -> str:
    """Ce que le prompt du clip dit du texte de l'image de départ : il ne bouge pas, ne change pas, rien ne s'ajoute."""
    return (
        f'The writing "{it.text}" ({it.on}) stays perfectly still, sharp and unchanged: its letters never move, morph or '
        "blur, the camera moves only slightly, and no other writing appears."
    )


# ---- Exigences lues par le contrôle des images (français) -----------------------------------------------------------


def keyframe_allowance(it: ImageText) -> str:
    """Remplace « sans texte » dans les exigences d'une image qui porte ce texte (le texte exact est relu à part)."""
    return f"Le seul texte écrit dans l'image est « {it.text} » ({it.on}) : aucun sous-titre, légende, titre ni autre mot."


# ---- Relecture par le modèle de vision -------------------------------------------------------------------------------

READ_SYSTEM = """Tu es correcteur d'imprimerie. On te montre une ou plusieurs images générées par IA. Pour chaque image,
recopie EXACTEMENT chaque texte écrit lisible (panneau, étiquette, écran, papier, chiffres flottants…), lettre par
lettre : accents, chiffres, symboles, espaces et majuscules compris. Ne corrige RIEN : une faute, une lettre en double
ou une lettre inventée doit rester dans ta copie, c'est ce qu'on cherche. Une lettre illisible s'écrit « ? ». Un même
support = un seul texte (ses lignes séparées par des espaces). Pour chaque texte : box_2d = [ymin, xmin, ymax, xmax], le
cadre du texte en millièmes de l'image (0 à 1000) ; clean = false si des lettres sont fondues, déformées, à moitié
effacées, doublées ou mal alignées. Une image sans texte a une liste vide."""


class WrittenText(BaseModel):
    text: str
    # cadre du texte [ymin, xmin, ymax, xmax] en millièmes de l'image, le format natif de Gemini : une hauteur demandée
    # en pourcentage revenait à 169 ou 200 % (banc du 02/10)
    box_2d: list[float] | None = None
    clean: bool = True

    @property
    def y_pct(self) -> float | None:
        """Hauteur du centre du texte, en % depuis le haut ; None si le cadre manque ou n'a pas de sens."""
        box = self.box_2d or []
        if len(box) != 4 or not (0 <= box[0] < box[2] <= 1000):
            return None
        return (box[0] + box[2]) / 20


class ImageReading(BaseModel):
    texts: list[WrittenText] = Field(default_factory=list)


class FramesReading(BaseModel):
    frames: list[ImageReading] = Field(default_factory=list)


def norm(text: str) -> str:
    """Pour comparer deux écritures : majuscules et espaces libres (autour de la ponctuation, entre les chiffres
    groupés) ; lettres, accents, chiffres et symboles stricts."""
    t = unicodedata.normalize("NFC", text).casefold()
    t = t.replace("’", "'").replace(" ", " ").replace(" ", " ")
    t = re.sub(r"\s*([:;!?,.€$%«»\"'/+-])\s*", r"\1", t)
    t = re.sub(r"(?<=\d) (?=\d)", "", t)
    return re.sub(r"\s+", " ", t).strip()


def judge(reading: ImageReading, it: ImageText, *, where: bool = True) -> list[str]:
    """Problèmes d'une image relue (vide = le texte est bon) : le texte attendu, lu à l'identique, une seule fois, net,
    à sa place ; aucun autre texte."""
    want = norm(it.text)
    found = [t for t in reading.texts if norm(t.text) == want]
    others = [t for t in reading.texts if norm(t.text) != want and len(norm(t.text)) > EXTRA_CHARS_IGNORED]
    problems: list[str] = []
    if not found:
        seen = " ; ".join(f"« {t.text} »" for t in reading.texts) or "aucun texte"
        problems.append(f"le texte « {it.text} » n'est pas écrit à l'identique (on lit : {seen})")
    else:
        if len(found) > 1:
            problems.append(f"« {it.text} » est écrit {len(found)} fois")
        if not all(t.clean for t in found):
            problems.append(f"des lettres de « {it.text} » sont déformées ou mal formées")
        y = found[0].y_pct
        if where and y is not None and not (Y_RANGE[0] <= y <= Y_RANGE[1]):
            problems.append(
                f"« {it.text} » est à {y:.0f} % de la hauteur : il doit être dans le haut de l'image, entre "
                f"{Y_RANGE[0]:.0f} et {Y_RANGE[1]:.0f} % (ni sous le titre d'accroche, ni sous les sous-titres)"
            )
    if others:
        problems.append("autre texte écrit : " + " ; ".join(f"« {t.text} »" for t in others[:3]))
    return problems


def _verdict(problems: list[str]) -> KeyframeVerdict:
    from .keyframe_qc import KeyframeVerdict

    return KeyframeVerdict(ok=not problems, problems=problems)


def check_image(llm: Any, image: Path, it: ImageText) -> KeyframeVerdict:
    """Relecture d'une image du storyboard : le modèle recopie ce qu'il lit, sans connaître le texte attendu."""
    from .keyframe_qc import _ask_model

    reading = _ask_model(llm, READ_SYSTEM, "Recopie les textes écrits dans l'image.", [image], ImageReading)
    return _verdict(judge(reading, it))


def check_clip(llm: Any, clip: Path, workdir: Path, it: ImageText) -> KeyframeVerdict:
    """Relecture de trois images du clip : le texte reste le même, net, et rien d'autre n'est écrit. La place n'est pas
    rejugée (une lente avancée de caméra le déplace un peu)."""
    from .keyframe_qc import _ask_model, clip_frames

    frames = clip_frames(clip, workdir)
    if not frames:
        return _verdict(["images du clip introuvables"])
    reading = _ask_model(
        llm,
        READ_SYSTEM,
        f"Voici {len(frames)} images tirées d'un clip, dans l'ordre. Réponds frames : une entrée par image, dans l'ordre.",
        frames,
        FramesReading,
    )
    problems: list[str] = []
    if len(reading.frames) < len(frames):
        problems.append(f"relecture incomplète ({len(reading.frames)} images sur {len(frames)})")
    for k, frame in enumerate(reading.frames[: len(frames)], 1):
        problems += [f"image {k} du clip : {p}" for p in judge(frame, it, where=False)]
    return _verdict(problems)


def merge(a: KeyframeVerdict | None, b: KeyframeVerdict | None) -> KeyframeVerdict | None:
    """Deux verdicts sur la même image (contrôle habituel + relecture du texte) : refusé si l'un refuse."""
    if a is None or b is None:
        return a or b
    from .keyframe_qc import KeyframeVerdict

    return KeyframeVerdict(ok=a.ok and b.ok, problems=[*a.problems, *b.problems])


# ---- Plan de secours : l'image vérifiée, en lente avancée -------------------------------------------------------------


def still_clip(image: Path, out: Path, duration_s: float, fps: int = 24, zoom: float = 0.05) -> tuple[float, int, int]:
    """Clip fixe en lente avancée (zoompan sur l'image agrandie, sans saccade) depuis l'image du storyboard dont le
    texte a été vérifié : (durée, largeur, hauteur). Muet : le plan n'a pas de réplique."""
    from PIL import Image

    from .media import run

    with Image.open(image) as im:
        w, h = im.size
    w, h = w - w % 2, h - h % 2
    seconds = max(1.0, duration_s + 0.5)  # un peu plus long que le plan : le montage coupe
    n = max(2, round(seconds * fps))
    zoompan = (
        f"scale={w * 4}:{h * 4},zoompan=z='1+{zoom}*on/{n - 1}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={n}:s={w}x{h}:fps={fps},format=yuv420p"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(image),
            "-vf",
            zoompan,
            "-frames:v",
            str(n),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "16",
            "-r",
            str(fps),
            "-an",
            str(out),
        ]
    )
    return n / fps, w, h
