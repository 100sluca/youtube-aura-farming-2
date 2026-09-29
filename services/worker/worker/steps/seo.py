"""Agent SEO : titre, description, tags et hashtags de chaque vidéo, dans la langue de la chaîne.

Inspiré de youtube-automation-agent (seo-optimizer-agent), en corrigeant ses défauts relevés à
l'étude : le LLM reçoit le vrai contenu (narration, textes à l'écran, accroche), connaît les titres
qui marchent sur la chaîne et la stratégie validée, propose plusieurs titres avec des leviers
différents ; les limites de YouTube sont ensuite appliquées en code (caractères < et > interdits,
description ≤ 5 000 octets, tags ≤ 500 caractères en comptant les guillemets implicites).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from psycopg.types.json import Jsonb

from ..drama import speaker_line
from ..lessons import lessons_text
from ..models import ScriptV1, SeoPack
from ..prompts import prompt_text
from ..providers.llm import get_llm
from ..strategy import active_strategies, guidance_text
from .base import Context, Step

TITLE_MAX = 70  # YouTube accepte 100, mais un titre de Short est coupé vers 40-60 caractères
DESCRIPTION_MAX_BYTES = 5000
TAGS_MAX_CHARS = 500
HASHTAGS_MAX = 3  # YouTube affiche les 3 premiers au-dessus du titre


class SeoStep(Step):
    type = "seo"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        vid = ctx.job.video_id
        v = ctx.db.fetch_one(
            """select v.id, v.lang, v.seo, v.channel_id, c.slug, c.name as channel_name, p.script,
                      co.title as concept_title, co.hook, co.category, co.premise, co.sources,
                      s.name as series_name, s.brief as series_brief, coalesce(s.recipe, 'story') as recipe
               from videos v join channels c on c.id = v.channel_id
               join productions p on p.id = v.production_id
               left join concepts co on co.id = p.concept_id
               left join series s on s.id = p.series_id where v.id = %s""",
            (vid,),
        )
        assert v and v["script"], "script manquant"
        if v["seo"] and not ctx.job.payload.get("force"):  # idempotence
            return {"skipped": True}
        lang = v["lang"]
        script = ScriptV1.model_validate(v["script"])
        visual = v["recipe"] in ("timelapse", "tour")  # formats sans voix (docs/15)
        top = ctx.db.fetch_all(
            """select title, views_d7, average_view_pct from v_video_performance
               where channel_id = %s and age_days >= 3 order by views_d7 desc limit 10""",
            (v["channel_id"],),
        )
        recent = [
            r["title"]
            for r in ctx.db.fetch_all(
                "select title from videos where channel_id = %s and title is not null and id <> %s order by created_at desc limit 30",
                (v["channel_id"], vid),
            )
        ]
        strategy = {k: s for k, s in active_strategies(ctx.db).items() if k == v["slug"]}
        draft = script.metadata.get(lang)
        user = "\n".join(
            [
                f"Langue de la chaîne : {lang} ({v['channel_name']}). Écris TOUT dans cette langue.",
                f"Série : {v['series_name']} — {(v['series_brief'] or '')[:400]}" if v.get("series_name") else "",
                f"Concept : {v['concept_title']} · catégorie {v['category']}",
                f"Accroche : {v['hook']}",
                f"Prémisse : {v['premise']}",
                *(
                    [
                        f"Vidéo sans voix (format visuel) ; titre d'accroche gravé à l'écran : « {script.hook_title.get(lang, '')} ». "  # type: ignore[call-overload]
                        "Ce qu'on voit, scène par scène :",
                        *[f"  {s.index + 1}. {s.visual_prompt[:160]}" for s in script.scenes],
                    ]
                    if visual
                    else [
                        "Narration, scène par scène :",
                        *[f"  {s.index + 1}. {speaker_line(script, s) or s.narration.get(lang, '')}" for s in script.scenes],
                    ]  # type: ignore[call-overload]
                ),
                "Textes à l'écran : " + " | ".join(t for s in script.scenes if (t := s.on_screen_text.get(lang))),
                f"Brouillon de l'agent script : titre « {draft.title if draft else ''} », tags {draft.tags if draft else []}",
                "Titres de la chaîne qui marchent (vues à J+7, rétention %) : "
                + ("; ".join(f"« {t['title']} » {t['views_d7']} vues, {t['average_view_pct']} %" for t in top) or "aucun encore"),
                "Titres récents à ne pas répéter : " + ("; ".join(recent) or "aucun"),
                "Stratégie validée :",
                guidance_text(strategy, for_seo=True),
                lessons_text(ctx.db, "seo", channel_id=v["channel_id"], recipe=v["recipe"]),  # leçons validées (docs/25)
            ]
        )
        ctx.progress(30, "Appel LLM")
        system = prompt_text(ctx.db, "seo", DEFAULT_PROMPT)  # version active (onglet Agents, worker/prompts.py)
        pack = get_llm(ctx.settings, ctx.db).complete_json(system, user, SeoPack)
        title, description, tags = finalize(
            pack, sources=v.get("sources") or [], lang=lang, ai_note=visual, map_credit=any(s.is_map for s in script.scenes)
        )
        ctx.db.execute(
            "update videos set title = %s, description = %s, tags = %s, seo = %s where id = %s",
            (title, description, tags, Jsonb(pack.model_dump()), vid),
        )
        return {"title": title, "tags": len(tags), "variants": len(pack.titles)}


# ---------------------------------------------------------------------------
# Règles YouTube appliquées en code
# ---------------------------------------------------------------------------


def clean_text(s: str) -> str:
    """YouTube refuse < et > dans les titres, descriptions et tags."""
    return s.replace("<", "‹").replace(">", "›").strip()


def clean_title(s: str) -> str:
    s = re.sub(r"\s+", " ", clean_text(s)).strip(" \"'«»")
    return re.sub(r"\s*#shorts\b", "", s, flags=re.I).strip()


def pick_title(pack: SeoPack) -> str:
    """Le titre choisi s'il tient en 70 caractères, sinon le premier qui tient, sinon coupé à un mot."""
    titles = [clean_title(t.title) for t in pack.titles]
    chosen = titles[min(max(pack.chosen, 0), len(titles) - 1)]
    if len(chosen) <= TITLE_MAX:
        return chosen
    for t in titles:
        if 0 < len(t) <= TITLE_MAX:
            return t
    cut = chosen[:TITLE_MAX].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-–—")


def normalize_hashtag(h: str) -> str | None:
    word = "".join(ch for ch in unicodedata.normalize("NFC", h) if ch.isalnum() or ch == "_")
    return f"#{word}" if word else None


def normalize_hashtags(items: list[str]) -> list[str]:
    out, seen = [], set()
    for h in items:
        tag = normalize_hashtag(h)
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            out.append(tag)
    return out[:HASHTAGS_MAX]


def tags_length(tags: list[str]) -> int:
    """Longueur comptée par YouTube : un tag avec espace compte ses guillemets, plus une virgule entre tags."""
    return sum(len(t) + (2 if " " in t else 0) for t in tags) + max(0, len(tags) - 1)


def normalize_tags(items: list[str]) -> list[str]:
    out, seen = [], set()
    for t in items:
        t = re.sub(r"\s+", " ", clean_text(t).lstrip("#").strip(" \"',"))[:60]
        if t and t.lower() not in seen and tags_length(out + [t]) <= TAGS_MAX_CHARS:
            seen.add(t.lower())
            out.append(t)
    return out


def truncate_bytes(s: str, max_bytes: int) -> str:
    b = s.encode("utf-8")
    if len(b) <= max_bytes:
        return s
    return b[:max_bytes].decode("utf-8", errors="ignore").rstrip()


def attribution(sources: list[dict[str, Any]], lang: str) -> str:
    """Mention des pages Wikipédia utilisées (textes sous CC BY-SA 4.0), ajoutée en fin de description."""
    label = "Sources (Wikipédia, CC BY-SA 4.0) :" if lang == "fr" else "Sources (Wikipedia, CC BY-SA 4.0):"
    lines = [f"- {s.get('title')} — {s.get('url')}" for s in sources[:6] if s.get("url")]
    return label + "\n" + "\n".join(lines) if lines else ""


MAP_CREDIT = {
    "fr": "",
    "en": "",
}

AI_NOTE = {
    "fr": "Made by Arzak Parker",
    "en": "Made by Arzak Parker",
}


def finalize(
    pack: SeoPack,
    sources: list[dict[str, Any]] | None = None,
    lang: str = "fr",
    ai_note: bool = False,
    map_credit: bool = False,
) -> tuple[str, str, list[str]]:
    title = pick_title(pack)
    hashtags = normalize_hashtags(pack.hashtags)
    description = clean_text(pack.description)
    missing = [h for h in hashtags if h.lower() not in description.lower()]
    if missing:
        description = f"{description}\n\n{' '.join(missing)}"
    credit = attribution(sources or [], lang)
    if credit:
        description = f"{description}\n\n{credit}"
    if ai_note:  # formats visuels photoréalistes : jamais pris pour une vraie annonce ou un vrai chantier (docs/15 §6)
        description = f"{description}\n\n{AI_NOTE.get(lang, AI_NOTE['en'])}"
    if map_credit:  # scène carte (worker/maps.py) : images EOX sous CC BY 4.0, tracés OpenStreetMap sous ODbL
        credit = MAP_CREDIT.get(lang, MAP_CREDIT["en"]).strip()
        description = f"{description}\n\n{credit}" if credit else description  # mention vide : rien à ajouter
    return title, truncate_bytes(description, DESCRIPTION_MAX_BYTES), normalize_tags(pack.tags)


DEFAULT_PROMPT = """Tu es l'expert SEO d'un réseau de chaînes YouTube Shorts organisées en séries (maisons de rêve et
passages secrets, histoires vraies tirées de Wikipédia, animaux étranges…). La série et son brief te sont indiqués.
Tu écris les métadonnées d'UN Short, dans la langue de la chaîne indiquée.

Titres : propose 3 à 5 variantes avec des leviers différents (curiosité, chiffre, question,
avant/après, défi). 60 caractères maximum, les mots concrets en tête (l'objet, le lieu), les nombres et
les années en chiffres (« 852 morts »), au plus un émoji, jamais tout en majuscules, jamais « #shorts ». Curiosité honnête : le titre ne promet
rien que la vidéo ne montre pas (YouTube sanctionne les pratiques trompeuses). « chosen » =
l'index de la variante que tu recommandes.
Description : première ligne = une accroche de moins de 100 caractères ; puis une ou deux phrases
concrètes sur le sujet (le lieu, l'animal, le fait, le chiffre) ; puis une question pour faire réagir en
commentaire. Les sources sont ajoutées par le code : ne les écris pas.
Tags : 10 à 15, du plus précis au plus large, sans #.
Hashtags : exactement 3, pertinents et sans espace (ex. #maison #construction #amenagement).
pinned_comment : une question courte à épingler.
Inspire-toi des titres qui marchent sur la chaîne sans les copier, et respecte la stratégie validée.
Réponds uniquement en JSON conforme au schéma SeoPack."""
