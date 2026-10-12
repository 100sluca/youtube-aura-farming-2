"""Le bruiteur des drames (docs/49 §10) : choisit, plan par plan, les bruitages de la bibliothèque (worker/sfx.py) d'après ce
qu'on voit et ce qui se dit. Demandé par Luca le 01/10 devant « Tout le collège le détestait » : la cantine où tout le
monde regarde Durian (chuchotements, moqueries, couverts), le sac qu'on ouvre pour y glisser la montre, la professeure
qui le fouille. Les étiquettes vont dans ScriptScene.sfx de la production ; le montage les pose (steps/assemble.py :
drama_sound), avec l'ambiance du clip sous les plans sans réplique.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .drama import line_text
from .models import ScriptV1
from .sfx import TAGS, parse_tags

PICK_PROMPT = """Tu es le bruiteur d'un court drame animé (YouTube Short vertical, personnages en 3D façon Pixar). Les
voix sont déjà posées ; tu ajoutes les bruits qui donnent de la profondeur à chaque plan, comme au cinéma.

Pour chaque plan, choisis 0, 1 ou 2 étiquettes dans la liste fournie, rien d'autre :
- plan SANS réplique : deux étiquettes le plus souvent : le lieu (cantine, salle de classe, couloir) ET ce qui se passe
  à l'image : le geste (sac qu'on ouvre ou qu'on fouille, vêtements qui frottent, petit objet en métal, porte) ou la
  réaction des autres (chuchotements quand tout le monde regarde quelqu'un, rires moqueurs, stupeur). Exemples : toute
  la cantine regarde Durian → cafeteria, whispers ; il glisse une montre dans un sac → bag_rummage, small_metal ; la
  professeure fouille le sac et trouve la montre → bag_rummage, gasp ;
- plan AVEC réplique : seulement une ambiance discrète si le lieu l'appelle (cantine, classe, couloir), jamais un coup
  ni des voix (rires, chuchotements) qui couvriraient la réplique ;
- uniquement ce que l'image montre ou ce que le lieu implique : pas de cœur qui bat ni de rires sans raison ; le même
  lieu sur plusieurs plans de suite garde la même ambiance (elle devient un seul fond continu).
Réponds uniquement en JSON : {"scenes": [{"index": 0, "sfx": ["cafeteria"]}, …]}, une entrée par plan."""


class SceneSfx(BaseModel):
    index: int
    sfx: list[str] = Field(default_factory=list)


class SfxPicks(BaseModel):
    scenes: list[SceneSfx]


def scenes_listing(script: ScriptV1, lang: str) -> str:
    names = {m.key: m.name for m in script.cast} if script.cast else {}
    out = []
    for pos, s in enumerate(script.scenes, start=1):
        line = line_text(s)
        who = names.get(s.lines[0].who, s.lines[0].who) if s.lines else ""
        out.append(
            f"Plan {pos} (index {s.index}) · "
            + (f"{who} dit : « {line} »" if line else "sans réplique")
            + (f" · à l'image : {', '.join(names.get(c, c) for c in s.characters)}" if s.characters else "")
            + f"\n  image : {s.visual_prompt}\n  mouvement : {s.motion_prompt or '—'}"
        )
    return "\n".join(out)


def vocabulary() -> str:
    return "\n".join(f"- {k} ({v.label}, {'fond' if v.kind == 'bed' else 'ponctuel'})" for k, v in TAGS.items())


def pick_sfx(llm: Any, script: ScriptV1, lang: str, system: str = PICK_PROMPT) -> dict[int, str]:
    """{index de scène : « étiquette, étiquette »} ; les étiquettes inconnues sont écartées (parse_tags)."""
    user = f"BRUITAGES DISPONIBLES :\n{vocabulary()}\n\nPLANS :\n{scenes_listing(script, lang)}"
    picks = llm.complete_json(system, user, SfxPicks)
    known = {s.index for s in script.scenes}
    return {p.index: ", ".join(tags) for p in picks.scenes if p.index in known and (tags := parse_tags(", ".join(p.sfx))[:2])}


def with_sfx(script: ScriptV1, picks: dict[int, str]) -> ScriptV1:
    """Le script avec les bruitages choisis (les plans absents de `picks` n'en ont plus)."""
    return script.model_copy(update={"scenes": [s.model_copy(update={"sfx": picks.get(s.index) or None}) for s in script.scenes]})
