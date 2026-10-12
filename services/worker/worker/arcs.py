"""Mini-séries des drames (docs/52, demande de Luca du 01/10) : une histoire en 3 parties, la suite selon les vues.

1. Au script d'un drame (partie 1), le showrunner (prompt arc_outline, onglet Agents) écrit l'histoire ENTIÈRE en 3
   parties : la prémisse, ce que raconte chaque partie et le moment exact où elle coupe (story_arcs.outline). Le
   scénariste écrit la partie 1 avec ce plan (part_brief) : elle s'ouvre sur l'injustice, plante l'interdit et coupe
   en pleine action.
2. Seule la partie 1 est fabriquée et publiée. `tick` (toutes les 2 min) : 48 h après la sortie d'une partie, ses vues
   YouTube + TikTok à 48 h sont comparées à la médiane des autres vidéos de la chaîne au même âge
   (story_arcs.decisions). Au-dessus du seuil (app_settings « miniseries ».threshold × médiane), la suite est
   proposée dans Création ; pilote des mini-séries allumé : elle est fabriquée et programmée seule (production
   `autopilot`, comme docs/46). En dessous : rien ne part, Luca peut lancer la suite quand même (launch_request,
   écrit par Création → Mini-séries, à tout moment).
3. `launch_part` crée la production de la partie suivante (même idée, même chaîne, mêmes réglages) et y recopie les
   fiches des personnages de la partie 1 : mêmes visages ; `keep_cast` leur rend aussi leurs voix.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from .metrics import views_at
from .models import ScriptV1

log = structlog.get_logger(__name__)

KEY = "miniseries"
DEFAULTS: dict[str, Any] = {"autopilot": False, "threshold": 1.0, "eval_hours": 48, "parts": 3}
PARTS_MAX = 3
REFS_MIN = 3  # vidéos de comparaison au moins pour juger ; sinon la suite est proposée (« pas assez de recul »)
REFS_DAYS = 60  # vidéos de comparaison : sorties depuis 60 jours
SNAP_GAP = timedelta(hours=6)  # relevés encadrant l'instant visé : 6 h d'écart au plus


class ArcPart(BaseModel):
    n: int = Field(ge=1, le=PARTS_MAX)
    synopsis: str  # ce qui se passe dans la partie, en français, 2 à 4 phrases
    opens_with: str = ""  # partie 2 et 3 : la situation reprise, là où la partie d'avant a coupé
    ends_on: str  # le moment exact où la partie coupe (en pleine action) ; dernière partie : le dénouement


class ArcOutline(BaseModel):
    """L'histoire entière écrite avant la partie 1 (prompt arc_outline)."""

    premise: str  # en une phrase : l'injustice ou l'affaire absurde
    first_line: str = ""  # la première réplique de la partie 1 (l'injustice dite par un personnage)
    planted: str = ""  # l'interdit ou le détail posé tôt, qui déclenchera le retournement
    twist: str = ""  # le retournement de valeur (ce qui brille est faux, ce qui est sale est précieux…)
    moral: str = ""  # la morale courte que le public écrira en commentaire
    parts: list[ArcPart] = Field(min_length=2, max_length=PARTS_MAX)


ARC_PROMPT = """Tu es le showrunner d'une mini-série de Shorts « drame » (TikTok, YouTube, 60 à 80 s par partie) :
une histoire d'injustice jouée en dialogues par des personnages de film d'animation, en PLUSIEURS PARTIES, comme les
histoires qui font des millions de vues (« Une sœur en or, l'autre couverte de boue » : partie 1 6,7 M de vues, les
suites 1,7 M puis 1,1 M). Tu écris l'histoire ENTIÈRE avant la première partie, puis tu la découpes.
Ce qui fait regarder la suite :
1. La PREMIÈRE RÉPLIQUE de la partie 1 est une injustice ou une affaire absurde, dite par un personnage, sans mise en
   place (« Toi, tu iras à l'école des riches, je t'aime. Toi, à l'école des pauvres. », « Un manoir pour 1 € ? »,
   « Il me reste 4 minutes et ma maman est malade »).
2. Un INTERDIT ou un détail planté tôt dans la partie 1 (« Ne touche jamais à l'eau ») déclenche plus tard le
   retournement.
3. Un RETOURNEMENT DE VALEUR, montré par une image : ce qui brille est faux, ce qui est sale est précieux, le pauvre
   méprisé est le vrai héritier. Le spectateur veut voir l'injustice réparée.
4. CHAQUE PARTIE COUPE EN PLEINE ACTION, sur une question que le spectateur veut résoudre tout de suite, jamais
   résolue dans la même partie (« La porte ne s'ouvre plus… », « Ta sœur ! », « Elle demande un nouvel examen, devant
   toute l'école »). Pas de résumé ni de conclusion avant la coupe.
5. Les parties 2 et 3 s'ouvrent là où la précédente a coupé (une réplique, pas de narrateur) et se comprennent
   seules ; chacune apporte une révélation ou une montée nouvelle, jamais une redite.
6. La dernière partie donne le dénouement : justice proportionnée (déchéance, rôles inversés, excuses publiques ;
   jamais la mort, le sang ni l'horreur), qu'un enfant de 10 ans comprend, et une morale courte que le public pourra
   écrire en commentaire (« Le moins cher coûte cher »). Elle peut garder une porte entrouverte.
Mêmes personnages d'une partie à l'autre (un nouveau au plus par partie). Écris en français. Réponds uniquement en
JSON : premise, first_line, planted, twist, moral, parts (une entrée par partie : n, synopsis, opens_with, ends_on)."""


# ---------------------------------------------------------------------------
# Réglages
# ---------------------------------------------------------------------------


def load(db: Any) -> dict[str, Any]:
    row = db.fetch_one("select value from app_settings where key = %s", (KEY,))
    return {**DEFAULTS, **(dict(row["value"]) if row and row["value"] else {})}


def save(db: Any, value: dict[str, Any]) -> None:
    db.execute(
        """insert into app_settings (key, value) values (%s, %s)
           on conflict (key) do update set value = excluded.value, updated_at = now()""",
        (KEY, Jsonb({**load(db), **value})),
    )


# ---------------------------------------------------------------------------
# Plan de l'histoire et consignes du scénariste
# ---------------------------------------------------------------------------


def outline_request(series_name: str, brief: str, concept: dict[str, Any], parts: int) -> str:
    return "\n\n".join(
        [
            f"SÉRIE : {series_name}\nBrief : {brief}",
            f"IDÉE : {concept.get('title')}\nAccroche : {concept.get('hook')}\nAngle : {concept.get('angle') or '—'}\n"
            f"Prémisse : {concept.get('premise')}\nTemps visuels : {concept.get('visual_beats')}",
            f"Nombre de parties : {parts}.",
        ]
    )


def create_arc(db: Any, prod: dict[str, Any], outline: ArcOutline) -> UUID:
    """Enregistre l'histoire et rattache la production (partie 1)."""
    row = db.fetch_one(
        """insert into story_arcs (series_id, channel_id, concept_id, title, outline, parts_total)
           values (%s, %s, %s, %s, %s, %s) returning id""",
        (
            prod.get("series_id"),
            prod.get("channel_id"),
            prod.get("concept_id"),
            prod.get("title") or outline.premise[:120],
            Jsonb(outline.model_dump()),
            len(outline.parts),
        ),
    )
    db.execute("update productions set arc_id = %s, arc_part = 1 where id = %s", (row["id"], prod["id"]))
    return row["id"]


def get_arc(db: Any, arc_id: UUID | str) -> dict[str, Any] | None:
    return db.fetch_one("select * from story_arcs where id = %s", (arc_id,))


def previous_scripts(db: Any, arc_id: UUID | str, part: int) -> list[ScriptV1]:
    rows = db.fetch_all(
        """select script from productions where arc_id = %s and arc_part < %s and script is not null
           and status::text not in ('failed', 'archived', 'cancelled') order by arc_part""",
        (arc_id, part),
    )
    return [ScriptV1.model_validate(r["script"]) for r in rows]


def part_brief(outline: ArcOutline, part: int, previous: Sequence[ScriptV1] = ()) -> str:
    """Ce que le scénariste du drame reçoit en plus pour écrire la partie `part` (elle prime sur la fin « partie 1 ou
    histoire complète » de ses consignes)."""
    total = len(outline.parts)
    me = next((p for p in outline.parts if p.n == part), outline.parts[-1])
    plan = "\n".join(f"  Partie {p.n} : {p.synopsis} — coupe sur : {p.ends_on}" for p in outline.parts)
    lines = [
        f"MINI-SÉRIE EN {total} PARTIES : tu écris la PARTIE {part} SUR {total}. Ce plan prime sur la fin « partie 1 ou "
        "histoire complète » de tes consignes.",
        f"Prémisse : {outline.premise}",
        f"Interdit ou détail planté : {outline.planted or '—'} · Retournement : {outline.twist or '—'} · Morale : {outline.moral or '—'}",
        f"Le plan de toute l'histoire :\n{plan}",
        f"CETTE PARTIE : {me.synopsis}",
    ]
    if part == 1:
        lines.append(
            f"Première réplique (l'injustice, dès le premier plan) : « {outline.first_line or outline.premise} ». "
            "Plante l'interdit ou le détail avant la moitié."
        )
    else:
        lines.append(
            f"Elle s'ouvre là où la partie {part - 1} a coupé : {me.opens_with or outline.parts[part - 2].ends_on}. Le "
            "premier plan reprend la situation en UNE réplique (pas de narrateur, pas de « précédemment ») ; la "
            "partie se comprend seule."
        )
    if part < total:
        lines.append(
            f"Elle COUPE sur : {me.ends_on}. Coupe en pleine action, AVANT la réponse : le dernier plan est un visage "
            "ou un geste qui pose la question ; aucune conclusion. Le dernier plan a on_screen_text "
            f"« Partie {part + 1} bientôt »."
        )
    else:
        lines.append(f"C'est la DERNIÈRE partie : le dénouement ({me.ends_on}), puis la morale en une réplique courte.")
    if previous:
        cast = previous[0].cast
        lines.append(
            "DISTRIBUTION IMPOSÉE : reprends ces personnages à l'identique (mêmes key, name, look, voice, tts_voice) ; "
            f"un nouveau personnage au plus :\n{[m.model_dump(exclude_none=True) for m in cast]}"
        )
        said = [
            f"  Partie {k + 1} : " + " / ".join(f"{ln.who} : {ln.text}" for sc in s.scenes for ln in sc.lines)[:1800]
            for k, s in enumerate(previous)
        ]
        lines.append("Répliques des parties précédentes (pour la continuité, ne pas les répéter) :\n" + "\n".join(said))
    return "\n".join(lines)


def keep_cast(script: ScriptV1, previous: Sequence[ScriptV1]) -> ScriptV1:
    """Les personnages déjà vus gardent leur fiche et leur voix de la partie 1 (le scénariste les recopie parfois mal)."""
    if not previous:
        return script
    ref = {m.key: m for m in previous[0].cast}
    s = script.model_copy(deep=True)
    s.cast = [ref[m.key].model_copy(deep=True) if m.key in ref else m for m in s.cast]
    return s


def part_title(title: str, part: int | None, limit: int = 70) -> str:
    """« Partie 2 : … » devant le titre des suites (la partie 1 garde son titre : l'accroche avant tout)."""
    if not part or part < 2 or title.lower().startswith("partie"):
        return title
    prefix = f"Partie {part} : "
    base = title if len(prefix) + len(title) <= limit else title[: limit - len(prefix)].rsplit(" ", 1)[0].rstrip(" ,;:-–—")
    return prefix + base


def finish_part(script: ScriptV1, part: int, total: int) -> ScriptV1:
    """Le titre « Partie N : » des suites et « Partie N+1 bientôt » sur le dernier plan d'une partie qui n'est pas la
    dernière (et rien sur celui de la dernière)."""
    s = script.model_copy(deep=True)
    for meta in s.metadata.values():
        meta.title = part_title(meta.title, part, 100)
    langs = list(s.metadata) or ["fr"]
    last = s.scenes[-1]
    if part < total:
        last.on_screen_text = {
            lang: (f"Partie {part + 1} bientôt" if lang == "fr" else f"Part {part + 1} soon") for lang in langs
        }  # type: ignore[misc]
    else:
        last.on_screen_text = {k: v for k, v in last.on_screen_text.items() if "partie" not in v.lower()}  # type: ignore[misc]
    return s


# ---------------------------------------------------------------------------
# Évaluation d'une partie publiée et lancement de la suivante
# ---------------------------------------------------------------------------


def views_48h(db: Any, video_id: UUID | str, published_at: datetime, hours: float) -> int | None:
    """Vues YouTube + TikTok `hours` après la sortie, d'après les relevés horaires ; None si YouTube ne le dit pas."""
    at = published_at + timedelta(hours=hours)
    snaps = db.fetch_all(
        "select taken_at, views from video_snapshots where video_id = %s and taken_at between %s and %s order by taken_at",
        (video_id, at - SNAP_GAP, at + SNAP_GAP),
    )
    yt = views_at([(s["taken_at"], s["views"]) for s in snaps], published_at, at, SNAP_GAP)
    if yt is None:
        return None
    tt = 0
    for post in db.fetch_all(
        "select id, published_at from tiktok_posts where video_id = %s and published_at is not null", (video_id,)
    ):
        t_at = post["published_at"] + timedelta(hours=hours)
        ts = db.fetch_all(
            "select taken_at, views from tiktok_post_snapshots where post_id = %s and taken_at between %s and %s order by taken_at",
            (post["id"], t_at - SNAP_GAP, t_at + SNAP_GAP),
        )
        tt += views_at([(s["taken_at"], s["views"]) for s in ts], post["published_at"], t_at, SNAP_GAP) or 0
    return yt + tt


def judge(views: int, refs: Sequence[int], threshold: float) -> dict[str, Any]:
    """Verdict d'une partie : suggested (au-dessus du seuil × médiane, ou pas assez de vidéos pour comparer) ou below."""
    if len(refs) < REFS_MIN:
        return {
            "views": views,
            "median": None,
            "refs": len(refs),
            "ratio": None,
            "verdict": "suggested",
            "why": "pas assez de recul",
        }
    median = statistics.median(refs)
    ratio = round(views / median, 2) if median else None
    ok = median == 0 or views >= threshold * median
    return {"views": views, "median": round(median), "refs": len(refs), "ratio": ratio, "verdict": "suggested" if ok else "below"}


def evaluate(db: Any, arc: dict[str, Any], part: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any] | None:
    """Évaluation d'une partie publiée depuis eval_hours au moins ; None tant qu'il est trop tôt."""
    hours = float(cfg["eval_hours"])
    if part["published_at"] + timedelta(hours=hours) > datetime.now(UTC):
        return None
    views = views_48h(db, part["video_id"], part["published_at"], hours)
    if views is None:  # relevés manquants (PC éteint) : les compteurs actuels, faute de mieux
        row = db.fetch_one("select views from video_stats where video_id = %s", (part["video_id"],))
        views = int(row["views"]) if row and row.get("views") is not None else 0
    refs: list[int] = []
    for r in db.fetch_all(
        """select v.id, v.published_at from videos v join productions p on p.id = v.production_id
           where v.channel_id = %s and v.status = 'published' and v.published_at is not null and v.origin = 'app'
             and v.published_at between now() - make_interval(days => %s) and now() - make_interval(hours => %s)
             and p.arc_id is distinct from %s""",
        (arc["channel_id"], REFS_DAYS, int(hours), arc["id"]),
    ):
        got = views_48h(db, r["id"], r["published_at"], hours)
        if got is not None:
            refs.append(got)
    out = judge(views, refs, float(cfg["threshold"]))
    return {"part": part["arc_part"], "video_id": str(part["video_id"]), "at": datetime.now(UTC).isoformat(), **out}


def launch_part(db: Any, arc_id: UUID | str, *, autopilot: bool = False, priority: int = 90) -> UUID:
    """Production de la partie suivante d'une mini-série : même idée, même chaîne, mêmes réglages que la partie 1 (sauf
    le format, celui de la série : une partie 1 en voix de synthèse n'impose pas ces voix à la suite), les
    fiches des personnages de la partie 1 recopiées (le storyboard les reprend au lieu d'en dessiner de nouvelles)."""
    arc = get_arc(db, arc_id)
    if not arc:
        raise LookupError(f"mini-série introuvable : {arc_id}")
    parts = db.fetch_all(
        """select * from productions where arc_id = %s and status::text not in ('failed', 'archived', 'cancelled')
           order by arc_part""",
        (arc["id"],),
    )
    if not parts:
        raise LookupError("la partie 1 n'existe plus")
    nxt = max(p["arc_part"] for p in parts) + 1
    if nxt > int(arc["parts_total"]):
        raise ValueError(f"les {arc['parts_total']} parties sont déjà faites")
    first = parts[0]
    row = db.fetch_one(
        """insert into productions (concept_id, series_id, channel_id, format, target_duration_s, style_preset,
                                    video_provider, status, autopilot, arc_id, arc_part)
           values (%s, %s, %s, coalesce((select format from series where id = %s), %s), %s, %s, %s, 'draft', %s, %s, %s)
           returning id""",
        (
            first["concept_id"],
            first["series_id"],
            first["channel_id"],
            first["series_id"],  # le format de la série (drames en voix des clips depuis 0045), sinon celui de la partie 1
            first["format"],
            first["target_duration_s"],
            first["style_preset"],
            first["video_provider"],
            autopilot,
            arc["id"],
            nxt,
        ),
    )
    pid = row["id"]
    db.execute(
        """insert into assets (production_id, kind, local_path, storage_bucket, storage_path, width, height, bytes, meta, selected)
           select %s, kind, local_path, storage_bucket, storage_path, width, height, bytes,
                  meta || jsonb_build_object('from_part', 1), selected
           from assets where production_id = %s and kind = 'character' and selected""",
        (pid, first["id"]),
    )
    decisions = [
        {**d, "launched_at": datetime.now(UTC).isoformat(), "autopilot": autopilot} if d.get("part") == nxt - 1 else d
        for d in (arc["decisions"] or [])
    ]
    db.execute("update story_arcs set decisions = %s, updated_at = now() where id = %s", (Jsonb(decisions), arc["id"]))
    db.enqueue("script", production_id=pid, priority=priority)
    log.info("arc.part", arc=str(arc["id"]), part=nxt, production=str(pid), autopilot=autopilot)
    return pid


def tick(db: Any, settings: Any = None) -> list[str]:
    """Évalue chaque partie publiée depuis 48 h et, pilote allumé, lance la suite ; renvoie ce qui a été fait."""
    cfg = load(db)
    done: list[str] = []
    for arc in db.fetch_all("select * from story_arcs where status = 'active' order by created_at"):
        last = db.fetch_one(
            """select p.id, p.arc_part, v.id as video_id, v.published_at
               from productions p left join videos v on v.production_id = p.id and v.status = 'published'
                    and v.published_at is not null and v.archived_at is null
               where p.arc_id = %s and p.status::text not in ('failed', 'archived', 'cancelled')
               order by p.arc_part desc, v.published_at limit 1""",
            (arc["id"],),
        )
        if not last:
            continue
        request = arc.get("launch_request")
        if request:  # « Lancer la partie N » dans Création : quel que soit le verdict, même avant la sortie
            db.execute("update story_arcs set launch_request = null where id = %s", (arc["id"],))
            if request == last["arc_part"] + 1 and request <= int(arc["parts_total"]):
                launch_part(db, arc["id"])
                done.append(f"{arc['title']} : partie {request} lancée (Luca)")
            continue
        if last["arc_part"] >= int(arc["parts_total"]):
            if last["video_id"]:
                db.execute("update story_arcs set status = 'finished', updated_at = now() where id = %s", (arc["id"],))
                done.append(f"{arc['title']} : terminée")
            continue
        decisions = list(arc["decisions"] or [])
        decision = next((d for d in decisions if d.get("part") == last["arc_part"]), None)
        if decision is None:
            if not last["video_id"]:
                continue  # pas encore sortie
            decision = evaluate(db, arc, last, cfg)
            if decision is None:
                continue
            decisions.append(decision)
            db.execute("update story_arcs set decisions = %s, updated_at = now() where id = %s", (Jsonb(decisions), arc["id"]))
            arc = {**arc, "decisions": decisions}
            nxt = last["arc_part"] + 1
            if decision["verdict"] == "suggested" and not cfg.get("autopilot"):
                db.alert(
                    "info",
                    f"Mini-série : la partie {nxt} est proposée",
                    f"« {arc['title']} » : partie {last['arc_part']} à {decision['views']} vues en {cfg['eval_hours']} h"
                    + (f" (médiane {decision['median']})" if decision.get("median") is not None else "")
                    + ". Lancer la suite dans Création → Mini-séries.",
                )
            done.append(f"{arc['title']} : partie {last['arc_part']} {decision['verdict']}")
        if decision.get("verdict") == "suggested" and cfg.get("autopilot") and not decision.get("launched_at"):
            launch_part(db, arc["id"], autopilot=True, priority=80)
            done.append(f"{arc['title']} : partie {last['arc_part'] + 1} lancée (pilote)")
    return done


def adopt(db: Any, settings: Any, production_id: UUID | str) -> UUID:
    """Fait d'un drame déjà écrit la partie 1 d'une mini-série : le showrunner écrit la suite à partir de ses répliques
    (« La fille du gardien », 01/10 : fin ouverte, tout le monde voudra la suite)."""
    from .prompts import prompt_text
    from .providers.llm import get_llm

    prod = db.fetch_one(
        """select p.*, c.title, c.hook, c.premise, c.visual_beats, c.angle, s.name as series_name, s.brief
           from productions p left join concepts c on c.id = p.concept_id left join series s on s.id = p.series_id
           where p.id = %s""",
        (production_id,),
    )
    if not prod or not prod.get("script"):
        raise LookupError("production sans script")
    if prod.get("arc_id"):
        return prod["arc_id"]
    script = ScriptV1.model_validate(prod["script"])
    said = " / ".join(f"{ln.who} : {ln.text}" for sc in script.scenes for ln in sc.lines)
    parts = min(int(load(db).get("parts") or PARTS_MAX), PARTS_MAX)
    user = (
        outline_request(prod.get("series_name") or "", prod.get("brief") or "", prod, parts)
        + f"\n\nLA PARTIE 1 EST DÉJÀ ÉCRITE ET FILMÉE : garde-la telle quelle (sa première réplique, son interdit, sa "
        f"coupe finale) et écris la suite. Ses répliques, dans l'ordre :\n{said}"
    )
    outline = get_llm(settings, db, writer=True).complete_json(prompt_text(db, "arc_outline", ARC_PROMPT), user, ArcOutline)
    outline.parts = sorted(outline.parts, key=lambda p: p.n)[:PARTS_MAX]
    for k, p in enumerate(outline.parts):
        p.n = k + 1
    return create_arc(db, prod, outline)
