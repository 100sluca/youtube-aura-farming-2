"""Contrôle automatique des images clés des formats visuels (docs/15 §10), par un modèle de vision.

Chaque image clé d'un chantier ou d'une visite est regardée par le LLM (Gemini gratuit par défaut, via
providers/llm.get_vision_llm) avec la liste des exigences de sa scène : pièce vraiment intérieure, personne à
l'image, bâtiment entier dans le cadre, ouvriers à l'échelle, retouche appliquée sans changer le cadre… Une image
refusée est refaite (nouvelle graine) ; si elle l'est encore, la production passe en revue humaine avec la liste
des problèmes. Quand tout passe, le rendu part seul : c'est ce qui rend la chaîne autonome.

Essais du 25/09 qui ont motivé chaque exigence : la « pièce secrète » d'un chalet sortie en façade extérieure,
des passants dans une maison vide, une cabane coupée par le bord de l'image, un ouvrier géant sur un chantier.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .models import ScriptV1
from .recipes import edit_instruction, edit_source
from .speaker import requirement as speaker_requirement

QC_SYSTEM = """Tu es le contrôleur qualité d'une chaîne YouTube de vidéos réalistes générées par IA. On te montre
une image clé (image 1), parfois l'image dont elle est tirée (image 2), et la liste des exigences qu'elle doit
remplir. Regarde l'image attentivement, en entier. Pour chaque exigence non remplie, écris un problème court et
précis, en français. ok = true seulement si TOUTES les exigences sont remplies. Sois strict sur ce qui casserait la
crédibilité (une pièce qui est en fait dehors, une personne là où il n'en faut pas, du texte, un bâtiment coupé par
le bord, une échelle absurde, une retouche non faite ou un cadre qui a changé) et indulgent sur le goût."""

PHOTO = "L'image est une photo réaliste (ni dessin, ni rendu 3D grossier), sans texte, logo ni filigrane."
NOBODY = "Aucune personne n'est visible, même au loin ou en reflet."


class KeyframeVerdict(BaseModel):
    ok: bool
    problems: list[str] = Field(default_factory=list)


# Gemini gratuit répond souvent 503 « high demand » le soir (4 contrôles sur 7 perdus le 25/09 vers 20 h) : le contrôle
# n'est pas pressé (le GPU travaille des minutes par image), on réessaie patiemment avant d'y renoncer.
PATIENCE_S = (30, 90, 180)
_TRANSIENT = re.compile(r"503|429|500|502|504|timed out|timeout|unavailable|overloaded|high demand|RESOURCE_EXHAUSTED", re.I)


def _ask(llm: Any, system: str, user: str, images: list[Path]) -> KeyframeVerdict:
    for wait in (*PATIENCE_S, None):
        try:
            return llm.complete_json(system, user, KeyframeVerdict, images=images)
        except Exception as exc:
            if wait is None or not _TRANSIENT.search(str(exc)):
                raise
            time.sleep(wait)
    raise AssertionError("inatteignable")


def requirements(script: ScriptV1, pos: int, recipe: str) -> list[str]:
    """Les exigences d'une image clé, d'après sa place dans le script (en français, lues par le modèle)."""
    sc = script.scenes[pos]
    what = sc.visual_prompt.strip()[:300]
    if recipe == "tour":
        if sc.interior is not False:
            reqs = ["La photo est prise À L'INTÉRIEUR d'une maison : on voit les murs et le plafond de la pièce ; ce "
                    "n'est ni une façade, ni une terrasse, ni un extérieur.",
                    f"On reconnaît la pièce décrite : {what}"]
        else:
            reqs = [f"Vue extérieure qui correspond à : {what}"]
        return [PHOTO, *reqs, NOBODY]
    if recipe == "timelapse":
        n = len(script.scenes)
        if pos == n - 2:  # le résultat fini : il fixe le cadre et l'échelle de tout le chantier
            return [PHOTO, f"L'image montre : {what}",
                    "C'est le résultat TERMINÉ : aucun échafaudage, engin, grue ni matériau de chantier.",
                    "La construction est ENTIÈRE dans l'image, pas coupée par les bords, avec de l'espace autour.",
                    "On lit l'échelle humaine (portes, fenêtres, garde-corps ou escaliers de taille normale).", NOBODY]
        if pos == n - 1:
            return [PHOTO, "C'est la même scène que l'image 2, au crépuscule, avec des lumières allumées ; même "
                    "construction, même cadrage.", NOBODY]
        if pos == 0:  # l'état d'origine : des ruines ou de la végétation EN PLUS vont dans le bon sens (faux refus du 25/09)
            return [PHOTO, f"L'image montre le lieu AVANT tout travaux : {what}",
                    "Même paysage, même point de vue et même cadrage que l'image 2 (le chantier à ses débuts) ; des "
                    "ruines, de la végétation ou des objets abandonnés en plus sont normaux, c'est l'état d'origine.",
                    "Aucun engin de chantier ni ouvrier."]
        reqs = [PHOTO, f"L'image montre cette étape du chantier : {what}",
                "Elle est MOINS avancée que l'image 2 (étape suivante) : ce qui n'est pas encore construit a été "
                "enlevé ; le paysage, le point de vue et le cadrage sont les mêmes que dans l'image 2.",
                "Les ouvriers éventuels sont petits, à l'échelle du bâtiment ; aucun n'est près de l'objectif, en gros "
                "plan ou coupé par le bord de l'image."]
        return reqs
    return [PHOTO]


CLIP_SYSTEM = """Tu es le contrôleur qualité d'une chaîne YouTube de vidéos réalistes générées par IA. On te montre
l'image de départ d'un clip vidéo (image 1) puis trois images tirées du clip généré, dans l'ordre (images 2 à 4). Le
modèle vidéo invente parfois des choses : des personnes, un appareil de tournage (caméra, trépied, stabilisateur,
grue, drone), un objet qui n'existait pas, des murs qui fondent. Vérifie chaque exigence sur les images 2 à 4 ; pour
chaque exigence non remplie, écris un problème court et précis, en français. ok = true seulement si TOUTES les
exigences sont remplies. Un léger mouvement de caméra, un changement de lumière, des nuages ou des flammes qui
bougent sont normaux."""

NO_RIG = "Aucun appareil de tournage ni machine étrangère n'apparaît (caméra, trépied, stabilisateur, grue, drone, perche)."
# Drame (docs/35) : MiniMax H3 écrivait parfois la réplique à l'image, comme un sous-titre, en plus de ceux du montage
# (« Mamie Pomme », 29/09). Seul le texte ajouté par le clip compte : celui de l'image de départ ne partirait pas en le
# refaisant (la consigne du scénariste et du prompt d'image l'interdit déjà).
NO_NEW_TEXT = ("Aucun texte n'apparaît sur les images 2 à 4 qui ne soit pas déjà dans l'image 1 : ni sous-titres, ni "
               "légende, ni lettres ou mots écrits sur l'image. Les personnages de film d'animation sont normaux.")


def clip_requirements(script: ScriptV1, pos: int, recipe: str) -> list[str]:
    """Les exigences d'un clip, d'après sa scène (en français, lues par le modèle)."""
    sc = script.scenes[pos]
    if recipe == "drama":  # et, à plusieurs dans le plan, la bonne bouche qui bouge (worker/speaker.py, docs/38 §5)
        return [NO_NEW_TEXT, *([req] if (req := speaker_requirement(script, sc)) else [])]
    if sc.passage:  # un passage d'une pièce à l'autre transforme l'image : seuls personnes et appareils comptent
        return ["Aucune personne n'apparaît, même au loin ou en reflet.", NO_RIG]
    if recipe == "timelapse" and sc.clip_mode == "flf" and pos < len(script.scenes) - 2:
        return ["Les ouvriers éventuels restent petits, à l'échelle du bâtiment : aucune personne géante, en gros plan, "
                "près de l'objectif ou coupée par le bord de l'image.", NO_RIG.replace(", grue", ""),
                "Le paysage, le point de vue et le cadrage restent ceux de l'image 1."]
    reqs = ["Aucune personne n'apparaît, même au loin ou en reflet.", NO_RIG]
    if recipe == "tour":
        reqs.append("Aucun objet étranger n'apparaît par rapport à l'image 1, et rien ne se déforme ni ne disparaît sur place ; "
                    "un meuble peut sortir du cadre quand la caméra avance ou tourne, ce n'est pas un défaut.")
    else:
        reqs.append("La construction reste la même que dans l'image 1, sans se déformer.")
    return reqs


def clip_frames(clip: Path, out_dir: Path, fractions: tuple[float, ...] = (0.3, 0.65, 0.97)) -> list[Path]:
    """Trois images tirées du clip (PNG), aux fractions de sa durée."""
    from .media import probe_duration, run

    out_dir.mkdir(parents=True, exist_ok=True)
    dur = probe_duration(clip) or 5.0
    frames = []
    for k, f in enumerate(fractions):
        p = out_dir / f"{clip.stem}_qc{k}.png"
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{dur * f:.3f}", "-i", str(clip), "-frames:v", "1", "-update", "1", str(p)])
        if p.exists() and p.stat().st_size:
            frames.append(p)
    return frames


def check_clip(llm: Any, clip: Path, start: Path, script: ScriptV1, pos: int, recipe: str, workdir: Path,
               system: str = CLIP_SYSTEM) -> KeyframeVerdict:
    """Verdict du modèle de vision sur un clip : son image de départ et trois images tirées du clip. `system` : le
    prompt actif de la clé clip_qc (onglet Agents du dashboard, worker/prompts.py)."""
    reqs = clip_requirements(script, pos, recipe)
    user = "Exigences pour les images 2 à 4 :\n" + "\n".join(f"{k + 1}. {r}" for k, r in enumerate(reqs))
    return _ask(llm, system, user, [start, *clip_frames(clip, workdir)])


def check_keyframe(llm: Any, image: Path, script: ScriptV1, pos: int, recipe: str, source: Path | None = None,
                   system: str = QC_SYSTEM) -> KeyframeVerdict:
    """Verdict du modèle de vision sur une image clé ; `source` = l'image retouchée pour l'obtenir (image 2). `system` :
    le prompt actif de la clé keyframe_qc (onglet Agents du dashboard, worker/prompts.py)."""
    reqs = requirements(script, pos, recipe)
    lines = "\n".join(f"{k + 1}. {r}" for k, r in enumerate(reqs))
    user = f"Exigences pour l'image 1 :\n{lines}"
    if source is not None and edit_source(script, pos) is not None:
        user += f"\n\nL'image 1 a été obtenue en retouchant l'image 2 avec cette consigne : {edit_instruction(script, pos, recipe)}"
    images = [image, source] if source is not None else [image]
    return _ask(llm, system, user, images)
