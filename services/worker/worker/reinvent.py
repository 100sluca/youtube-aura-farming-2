"""Réinventer une scène du storyboard (docs/27-reinventer-une-scene.md).

Luca relit le storyboard (une image par scène, avant l'animation) et juge qu'un plan ne va pas : hors sujet, sans lien
avec le reste de la vidéo. Essai du 28/09 (« Le miroir qui ouvre sur un dressing secret ») : la scène 4 disait « un
pivot invisible supporte tout le poids » sur le gros plan d'un mécanisme seul, sans le miroir dont parle la vidéo.
« Refaire » ne tire qu'une autre image du même prompt ; « Réinventer » fait réécrire la scène par le scénariste : une
autre idée de plan, sa première image, son mouvement, sa narration et son texte à l'écran, raccord avec les scènes
voisines, qui ne changent pas. Le step storyboard (payload « reinvent ») enregistre le script puis refait les images de
la scène.

Le scénariste reçoit (prompt système scene_rewrite, onglet Agents) : le thème et l'idée (faits et dossier des séries
documentaires), les consignes de qui a écrit les plans (version active de script_<recette>, ou du réalisateur des
récits, script_shots, depuis le 29/09 : docs/37), pour le sens des champs, les règles du récit et de l'image (récits),
le script scène par scène, la scène visée, ce qu'en dit Luca et les versions déjà
écartées de cette scène (payload « reinvented » des jobs précédents), pour ne pas y revenir. Rôle, durée et mécanique
de la scène restent ceux de l'ancienne ; le correcteur de la recette vérifie le résultat, et un écart nouveau fait
repartir la scène une fois au scénariste.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any
from uuid import UUID

from .drama import REWRITE_HINT as DRAMA_HINT
from .models import SceneDraft, SceneRewrite, ScriptScene, ScriptV1
from .prompts import code_prompts, prompt_text
from .providers.llm import LLM
from .recipes import has_prompt, is_visual, lint_recipe_script, normalize_script
from .storytelling import IMAGE_RULES, RULES, lint_script, normalize_story, scene_words_max

NOTE_MAX = 500  # caractères de la remarque de Luca
SAME_PLAN = 0.8  # part de mots communs (≥ 4 lettres) au-delà de laquelle deux visual_prompt décrivent la même image
DEFAULT_REASON = (
    "Luca la trouve hors sujet : son image ne se rattache ni au sujet de la vidéo ni aux autres scènes, elle casse "
    "l'enchaînement."
)
# Consignes du scénariste données pour le sens des champs : leur dernière phrase (jusqu'à la fin du texte) demande un
# script entier (ScriptV1) ou tous les plans d'un récit (ShotList)
_WHOLE_SCRIPT = re.compile(r"Réponds uniquement en JSON.*\Z", re.S)

FORMAT_HINTS = {
    "tour": (
        "VISITE : la nouvelle pièce reste sur le parcours. On y arrive par l'ouverture que décrit la pièce précédente "
        "(« mène à ») ; ton leads_to montre l'ouverture vers la pièce suivante, telle qu'elle est écrite ; même niveau "
        "(floor) sauf si un escalier y mène ; interior selon la pièce. Pas de narration."
    ),
    "timelapse": (
        "CHANTIER : la nouvelle étape reste entre l'étape précédente et la suivante, même lieu, même point de vue. "
        "edit_prompt dit ce qu'il faut ENLEVER de l'image de l'étape suivante (et ajouter : engins, échafaudages) pour "
        "obtenir celle-ci ; le compteur de jours (texte à l'écran) reste entre ceux des étapes voisines. Pas de narration."
    ),
    "drama": DRAMA_HINT,
    # Récit (docs/37) : les consignes reçues sont celles du réalisateur, qui ne touche pas à la narration ; la scène
    # réinventée, elle, la réécrit
    "story": (
        "RÉCIT : tu écris AUSSI la narration de la scène (champ narration), dans la langue de la vidéo, en suivant les "
        "règles du récit : une phrase de récit reliée à la scène d'avant par une conséquence ou un obstacle, jamais un "
        "fait posé seul ; les nombres en chiffres. Une scène carte (map) seulement si le script n'en a pas d'autre."
    ),
}

REWRITE_PROMPT = """Tu es le scénariste d'un YouTube Short (9:16) dont le script est écrit et le storyboard fait : une image
par scène, avant l'animation. En le relisant, Luca juge qu'UNE scène ne va pas : son plan est hors sujet, ne se
rattache pas au reste de la vidéo ou ne donne pas une image lisible. Tu RÉINVENTES cette scène : une autre idée de
plan, sa première image, son mouvement, sa narration et son texte à l'écran. Les autres scènes ne changent pas.
1. Même place dans le récit : même rôle, même durée. La narration part de la fin de la scène précédente et amène la
   suivante, telles qu'elles sont écrites ; elle apporte une information nouvelle, jamais la redite d'une autre scène.
   Garde l'information de l'ancienne scène si l'histoire en a besoin, dite autrement s'il le faut.
2. Une idée vraiment différente de la version actuelle et des versions déjà écartées, pas une variante de cadrage.
   Suis ce qu'en dit Luca quand il le dit.
3. Le sujet de la vidéo se voit : on reconnaît au premier coup d'œil de quoi parle la vidéo. Un détail (mécanisme,
   matière, outil) se montre SUR le sujet et dans son décor (la charnière dans la tranche du miroir entrouvert, pas un
   mécanisme seul sur fond neutre) : le modèle d'image ne sait du sujet que ce que dit visual_prompt.
4. Même lieu et mêmes objets que les autres scènes : reprends mot pour mot leurs descriptions des éléments communs
   (objet principal, matières, couleurs, lumière) pour que l'image ressemble aux autres ; change de valeur de plan par
   rapport aux scènes voisines (large, moyen, gros plan).
5. Une image qu'un modèle d'image réussit : une photo réaliste, un sujet clair, sans texte, sans visage
   reconnaissable ; un seul mouvement lent, possible depuis cette image : rien n'apparaît, rien ne se transforme.
6. Si la scène suivante prolonge celle-ci, elle partira de la dernière image de ton clip : ton plan doit pouvoir
   s'enchaîner avec elle.
Les champs suivent les consignes du scénariste que tu reçois (visual_prompt et motion_prompt en anglais, narration et
texte à l'écran dans les langues demandées, champs propres au format) ; le rôle, la durée et le numéro de la scène
sont repris par le code. idea : le nouveau plan en une phrase, en français, pour Luca (« Gros plan sur la tranche du
miroir entrouvert : l'axe en acier apparaît »).
Réponds uniquement en JSON : {"idea": "…", "scene": {"visual_prompt": "…", "motion_prompt": "…", "narration": {…},
"on_screen_text": {…}}}, avec les champs propres au format s'il en a."""


def shot_number(script: ScriptV1, index: int) -> int:
    """Numéro de la scène tel que Luca le voit dans le dashboard (StoryboardPanel) : rang parmi les scènes à image, sans
    les passages des visites ; les scripts numérotent leurs scènes à partir de 0 ou de 1."""
    shots = [s.index for s in script.scenes if not s.passage]
    return shots.index(index) + 1 if index in shots else index + 1


def production_brief(db: Any, pid: UUID | str) -> dict[str, Any]:
    """Thème, idée, format, durée cible et langues de la production : le cadre de la réécriture."""
    row = db.fetch_one(
        """select p.format, p.target_duration_s, c.title, c.hook, c.premise, c.angle, c.visual_beats, c.facts, c.sources,
                  s.name as series_name, s.brief as series_brief
           from productions p left join concepts c on c.id = p.concept_id left join series s on s.id = p.series_id
           where p.id = %s""",
        (pid,),
    )
    langs = sorted({r["lang"] for r in db.fetch_all("select lang from videos where production_id = %s", (pid,))})
    return {**(row or {}), "langs": langs}


def rejected_versions(db: Any, pid: UUID | str, index: int) -> list[dict[str, Any]]:
    """Versions de la scène déjà remplacées par une réinvention (payload « reinvented » des jobs storyboard)."""
    rows = db.fetch_all(
        """select payload->'reinvented' as done from jobs where production_id = %s and type = 'storyboard'
           and payload->'reinvented' is not null order by created_at""",
        (pid,),
    )
    entries = [e for r in rows for e in (r.get("done") or []) if isinstance(e, dict)]
    return [e.get("before") or {} for e in entries if e.get("scene") == index]


def version(scene: ScriptScene) -> dict[str, Any]:
    """Ce qui fait une version de la scène : gardé dans le job, montré au scénariste la fois suivante."""
    return {
        "visual_prompt": scene.visual_prompt,
        "motion_prompt": scene.motion_prompt,
        "narration": dict(scene.narration),
        "on_screen_text": dict(scene.on_screen_text),
        **({"characters": list(scene.characters), "lines": [ln.model_dump() for ln in scene.lines]} if scene.characters else {}),
    }


def script_listing(script: ScriptV1, recipe: str, lang: str, target: int) -> str:
    """Le script scène par scène, tel que le scénariste le relit ; la scène à réinventer est marquée."""
    lines: list[str] = []
    for s in script.scenes:
        if s.passage:
            lines.append("  (passage vers la pièce suivante, filmé par le code : rien à écrire)")
            continue
        head = f"{'>>> ' if s.index == target else ''}Scène {shot_number(script, s.index)} [{s.role or '—'}, {s.duration_s:g} s"
        head += (", prolonge le plan précédent]" if s.continues_previous else "]") + (" À RÉINVENTER" if s.index == target else "")
        parts = [f"image : {s.visual_prompt}"]
        if s.motion_prompt:
            parts.append(f"mouvement : {s.motion_prompt}")
        if s.is_map and s.map:
            parts.append(f"CARTE de « {s.map.place} »")
        if text := s.narration.get(lang, ""):  # type: ignore[call-overload]
            parts.append(f"narration : « {text} »")
        if ost := s.on_screen_text.get(lang, ""):  # type: ignore[call-overload]
            parts.append(f"texte à l'écran : {ost}")
        if recipe == "tour":
            parts.append(f"{'intérieur' if s.interior else 'extérieur'}, niveau {s.floor if s.floor is not None else '?'}"
                         + (f", mène à : {s.leads_to}" if s.leads_to else ""))
        if recipe == "timelapse" and s.edit_prompt:
            parts.append(f"retouche : {s.edit_prompt}")
        if recipe == "drama":
            parts.append(f"personnages à l'image : {s.characters or '—'}"
                         + "".join(f" ; réplique de {ln.who} ({ln.tone or '—'}) : « {ln.text} »" for ln in s.lines))
        if s.sfx:
            parts.append(f"bruitages : {s.sfx}")
        lines.append(head + "\n    " + "\n    ".join(parts))
    hook = script.hook_title.get(lang, "")  # type: ignore[call-overload]
    extra = [
        "Personnages (cast) : " + " ; ".join(f"{m.key} = {m.name} ({m.role or '—'}) : {m.look}" for m in script.cast)
        if script.cast else "",
        f"Titre d'accroche : {hook}" if hook else "",
        f"Bible du lieu (ajoutée à chaque image) : {script.design_bible}" if script.design_bible else "",
        f"Vue par les fenêtres : {script.view}" if script.view else "",
        f"Boucle : {script.loop_note}" if script.loop_note else "",
    ]
    return "\n".join([*lines, *(e for e in extra if e)])


def rewrite_request(brief: dict[str, Any], script: ScriptV1, recipe: str, pos: int, note: str, rejected: list[dict[str, Any]],
                    langs: list[str], consignes: str, rules: str = "", dossier: str = "") -> str:
    """Message de l'agent scene_rewrite : le cadre, le script, la scène visée, ce qu'en dit Luca, les versions écartées."""
    old = script.scenes[pos]
    lang = langs[0] if langs else "fr"
    narrated = brief.get("format") == "A_voiceover" and not has_prompt(recipe)  # drame : une réplique, pas de narration
    facts = "\n".join(
        f"- [{int(f.get('source', 0)) + 1}] {f.get('claim', '')}" for f in brief.get("facts") or [] if isinstance(f, dict)
    )
    sources = "\n".join(
        f"[{i + 1}] {s.get('title')} — {s.get('url')}" for i, s in enumerate(brief.get("sources") or []) if isinstance(s, dict)
    )
    tried: list[str] = []
    for k, v in enumerate([*rejected, version(old)]):
        name = "version actuelle" if k == len(rejected) else f"version écartée {k + 1}"
        said = (v.get("narration") or {}).get(lang)
        tried.append(f"- {name} : image « {v.get('visual_prompt') or ''} »" + (f" ; narration « {said} »" if said else ""))
    nxt = script.scenes[pos + 1] if pos + 1 < len(script.scenes) else None
    budget = f", narration de {max(4, round(old.duration_s * 2))} à {scene_words_max(old.duration_s)} mots" if narrated else ", sans voix"
    parts = [
        f"SÉRIE : {brief['series_name']}\nBrief : {brief.get('series_brief') or '—'}" if brief.get("series_name") else "",
        f"CONCEPT : {brief.get('title') or '—'}\nAccroche : {brief.get('hook') or '—'}\nAngle : {brief.get('angle') or '—'}\n"
        f"Prémisse : {brief.get('premise') or '—'}\nTemps visuels : {brief.get('visual_beats') or []}",
        f"FAITS SOURCÉS (avec le dossier, seule base des affirmations) :\n{facts}\nSources :\n{sources}" if facts else "",
        f"DOSSIER : les pages sources relues en entier.\n{dossier}" if dossier else "",
        f"CONSIGNES DU SCÉNARISTE, pour le sens de chaque champ (ta réponse, elle, ne contient qu'une scène) :\n{consignes}",
        rules,
        f"SCRIPT ACTUEL ({lang}, {script.duration_s:g} s) :\n{script_listing(script, recipe, lang, old.index)}",
        f"SCÈNE À RÉINVENTER : la scène {shot_number(script, old.index)} (rôle {old.role or '—'}, {old.duration_s:g} s{budget}).",
        f"CE QU'EN DIT LUCA : « {note} »" if note else f"POURQUOI : {DEFAULT_REASON}",
        "VERSIONS DE CETTE SCÈNE DÉJÀ ÉCARTÉES (n'y reviens pas, même autrement cadrées) :\n" + "\n".join(tried),
        "La scène suivante prolonge ce plan : elle partira de la dernière image de ton clip."
        if nxt is not None and nxt.continues_previous and not nxt.passage else "",
        FORMAT_HINTS.get(recipe, ""),
        f"Langues de la narration et du texte à l'écran : {langs}" if narrated else f"Langues du texte à l'écran : {langs}",
    ]
    return "\n\n".join(p for p in parts if p)


def _texts(values: dict[Any, str]) -> dict[Any, str]:
    return {k: v.strip() for k, v in values.items() if v and v.strip()}


def apply_rewrite(script: ScriptV1, pos: int, draft: SceneDraft, recipe: str) -> ScriptV1:
    """Copie du script où la scène `pos` prend ce que le scénariste a réécrit ; rôle, durée, index et mécanique restent,
    puis la recette remet la sienne (passages d'une visite, retouches d'un chantier, scène carte d'un récit)."""
    s = script.model_copy(deep=True)
    old = s.scenes[pos]
    other_map = any(sc.is_map for k, sc in enumerate(s.scenes) if k != pos)
    keep_map = recipe == "story" and draft.map is not None and bool(draft.map.place.strip()) and not other_map
    update: dict[str, Any] = {
        "visual_prompt": draft.visual_prompt.strip() or old.visual_prompt,
        "motion_prompt": (draft.motion_prompt or "").strip() or None,
        "narration": _texts(draft.narration),
        "on_screen_text": _texts(draft.on_screen_text),
        "sfx": (draft.sfx or "").strip() or old.sfx,
        "map": draft.map if keep_map else None,
    }
    if not is_visual(recipe):
        update["continues_previous"] = False  # un autre plan part de sa propre image
    if recipe == "timelapse":
        update["edit_prompt"] = (draft.edit_prompt or "").strip() or old.edit_prompt
    if recipe == "tour":
        update["interior"] = old.interior if draft.interior is None else draft.interior
        update["floor"] = old.floor if draft.floor is None else draft.floor
        update["leads_to"] = (draft.leads_to or "").strip() or old.leads_to
    if recipe == "drama":  # personnages et réplique réécrits (la narration en est recopiée par drama.normalize)
        update["characters"] = draft.characters or old.characters
        update["lines"] = draft.lines
    s.scenes[pos] = old.model_copy(update=update)
    return normalize_script(s, recipe) if has_prompt(recipe) else normalize_story(s)


def _words(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z]{4,}", text or "")}


def same_plan(a: str, b: str) -> bool:
    """Deux visual_prompt qui décrivent la même image (les mêmes mots, à quelques-uns près)."""
    wa, wb = _words(a), _words(b)
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= SAME_PLAN


def scene_issues(new: ScriptScene, old: ScriptScene, rejected: list[dict[str, Any]], shot: int, langs: list[str],
                 narrated: bool) -> list[str]:
    """Ce que le correcteur du script ne voit pas : une image déjà écartée, une narration perdue."""
    issues: list[str] = []
    if any(same_plan(new.visual_prompt, t) for t in [old.visual_prompt, *(str(r.get("visual_prompt") or "") for r in rejected)]):
        issues.append(f"scène {shot} : c'est la même image qu'une version écartée, propose une autre idée de plan")
    lost = [lang for lang in langs if old.narration.get(lang) and not new.narration.get(lang)] if narrated else []  # type: ignore[call-overload]
    if lost:
        issues.append(f"scène {shot} : narration manquante en {', '.join(lost)}")
    return issues


def _lint(script: ScriptV1, recipe: str, brief: dict[str, Any], langs: list[str]) -> list[str]:
    target = int(brief.get("target_duration_s") or 30)
    if has_prompt(recipe):
        return lint_recipe_script(script, recipe, langs, target)
    return lint_script(script, langs if brief.get("format") == "A_voiceover" else [], target)


def _shape(issue: str) -> str:
    return re.sub(r"\d+(?:[.,]\d+)?", "#", issue)


def new_issues(before: list[str], after: list[str], shot: int) -> list[str]:
    """Écarts du correcteur que la réécriture a créés : ceux de la scène réécrite (le correcteur numérote les scènes comme
    Luca), et les écarts d'ensemble qui n'existaient pas ; un écart d'ensemble déjà là dont seuls les chiffres changent
    avec la nouvelle narration (« narration trop maigre : 43 mots… ») n'en est pas un nouveau."""
    mine = re.compile(rf"\bscène {shot}\b")
    shapes = {_shape(i) for i in before}
    return [i for i in after if i not in before and (mine.search(i) or _shape(i) not in shapes)]


def reinvent_scene(db: Any, llm: LLM, pid: UUID | str, script: ScriptV1, recipe: str, index: int, note: str = "",
                   dossier: Callable[[list[dict[str, Any]]], str] | None = None) -> tuple[ScriptV1, dict[str, Any]]:
    """Le script où seule la scène `index` est réinventée, et ce qu'il faut en garder (job, dashboard) : la scène, son
    numéro vu par Luca, l'idée du nouveau plan, la remarque, les écarts restants, les versions d'avant et d'après.
    `dossier` : lecture des pages sources d'une série documentaire (aucune lecture sans lui)."""
    pos = next((k for k, s in enumerate(script.scenes) if s.index == index and not s.passage), None)
    if pos is None:
        raise ValueError(f"scène {index} absente du script (ou passage d'une visite : rien à réinventer)")
    note = note.strip()[:NOTE_MAX]
    brief = production_brief(db, pid)
    old = script.scenes[pos]
    langs = brief["langs"] or sorted(old.narration) or ["fr"]
    narrated = brief.get("format") == "A_voiceover" and not has_prompt(recipe)  # un drame n'a pas de narration écrite
    key = f"script_{recipe}" if has_prompt(recipe) else "script_shots"  # récit : le réalisateur, qui écrit les plans
    consignes = _WHOLE_SCRIPT.sub("", prompt_text(db, key, code_prompts().get(key, ""))).strip()
    rules = "" if has_prompt(recipe) else (f"{prompt_text(db, 'rules_storytelling', RULES)}\n\n"
                                           f"{prompt_text(db, 'rules_images', IMAGE_RULES)}")
    rejected = rejected_versions(db, pid, index)
    sources = brief.get("sources") or []
    user = rewrite_request(brief, script, recipe, pos, note, rejected, langs, consignes, rules,
                           dossier(sources) if dossier and sources else "")
    system = prompt_text(db, "scene_rewrite", REWRITE_PROMPT)
    shot = shot_number(script, index)
    before = _lint(script, recipe, brief, langs)
    best: tuple[ScriptV1, str, list[str]] | None = None
    request = user
    for _ in range(2):  # une reprise si la scène proposée pose un problème nouveau
        answer = llm.complete_json(system, request, SceneRewrite)
        candidate = apply_rewrite(script, pos, answer.scene, recipe)
        issues = scene_issues(candidate.scenes[pos], old, rejected, shot, langs, narrated)
        issues += new_issues(before, _lint(candidate, recipe, brief, langs), shot)
        if best is None or len(issues) < len(best[2]):
            best = (candidate, answer.idea.strip(), issues)
        if not issues:
            break
        request = (f"{user}\n\nTa scène pose ces problèmes, corrige-les en gardant ton idée si elle tient :\n- "
                   + "\n- ".join(issues) + f"\n\nScène proposée :\n{answer.scene.model_dump_json(exclude_none=True)}")
    assert best is not None
    new_script, idea, issues = best
    entry = {"scene": index, "shot": shot, "note": note, "idea": idea, "issues": issues,
             "before": version(old), "after": version(new_script.scenes[pos])}
    return new_script, entry
