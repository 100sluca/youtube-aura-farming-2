"""Recherche → Découverte (docs/63 §9) : les niches qui rapportent, au-delà de celles qu'on fait déjà.

Demande de Luca (04/10) : la veille (docs/60) suit des niches calibrées sur nos formats, en Shorts, et ne mesure que
des vues ; il veut découvrir les meilleures niches, celles qui font de l'argent, en vidéo longue surtout.

Chaque jour à 9 h 30 (avant le relevé de 10 h, qui prend ce qui reste des 100 recherches du jour), ou sur « Découvrir
maintenant » :
1. quelques sujets de départ larges (SEEDS : histoire, mystères, science, argent, psychologie, horreur, survie,
   ingénierie, géopolitique… en français et en anglais), ceux qui n'ont pas servi depuis le plus longtemps ;
2. pour chacun, les vidéos longues (plus de 20 min) ou moyennes (4 à 20 min) les plus vues des 45 derniers jours ;
3. leurs chaînes : on garde les chaînes RÉCENTES (moins de 18 mois) ou PETITES (moins de 150 000 abonnés) dont une
   vidéo récente dépasse 50 000 vues : c'est la preuve qu'une porte est ouverte (comme Nexlev, gratuitement) ;
4. l'agent classeur (research_discover) donne la niche en quelques mots, la catégorie (table des RPM), sans visage ou
   non, faite par IA ou non, l'effort pour la refaire chez nous et pourquoi elle marche ;
5. l'estimation : vues par mois (vues totales ÷ mois depuis la création) × RPM de la catégorie et de la langue
   (docs/61 §2 : estimations publiques, à prendre comme des ordres de grandeur).
La page Recherche → Découverte regroupe les chaînes par niche, classées par argent estimé ; « Sujets de vidéos
longues » demande à l'agent des vidéos longues des sujets dans cette niche.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from .prompts import prompt_text
from .providers.llm import get_llm
from .youtube import public as yp

log = structlog.get_logger(__name__)

SEARCH_CAP = 100
RESERVE = 10  # recherches laissées au relevé de la veille et aux explorations du jour
WINDOW_DAYS = 45
MIN_VIEWS = 50_000
YOUNG_MONTHS = 18
SMALL_SUBS = 150_000
SEED_REST_DAYS = 6  # un sujet de départ ne repasse pas avant

# (recherche, langue, pays, durée YouTube : long = plus de 20 min, medium = 4 à 20 min)
SEEDS: list[tuple[str, str, str, str]] = [
    # Histoire, mystères, civilisations
    ("mystères de l'histoire documentaire", "fr", "FR", "long"),
    ("civilisations disparues", "fr", "FR", "long"),
    ("histoire de France documentaire", "fr", "FR", "long"),
    ("ta vie au moyen âge", "fr", "FR", "long"),
    ("24h dans la peau de", "fr", "FR", "long"),
    ("égypte ancienne mystère", "fr", "FR", "long"),
    ("rome antique documentaire", "fr", "FR", "long"),
    ("histoire vraie incroyable", "fr", "FR", "medium"),
    ("lost civilizations documentary", "en", "US", "long"),
    ("your life as a medieval peasant", "en", "US", "long"),
    ("every rank explained", "en", "US", "long"),
    ("history documentary for sleep", "en", "US", "long"),
    ("ancient mysteries documentary", "en", "US", "long"),
    ("wild west history", "en", "US", "long"),
    # Faits divers, enquêtes, disparitions
    ("affaire non résolue", "fr", "FR", "long"),
    ("disparition mystérieuse", "fr", "FR", "long"),
    ("faits divers documentaire", "fr", "FR", "long"),
    ("unsolved mysteries documentary", "en", "US", "long"),
    ("cold case documentary", "en", "US", "long"),
    # Horreur, paranormal, histoires
    ("histoire d'horreur vraie", "fr", "FR", "long"),
    ("histoires reddit", "fr", "FR", "long"),
    ("scary stories true", "en", "US", "long"),
    ("camping horror stories", "en", "US", "long"),
    ("reddit stories revenge", "en", "US", "long"),
    # Science, espace, ingénierie, et si
    ("et si la terre", "fr", "FR", "medium"),
    ("espace documentaire", "fr", "FR", "long"),
    ("mégastructures documentaire", "fr", "FR", "long"),
    ("ingénierie incroyable", "fr", "FR", "medium"),
    ("what if scenario explained", "en", "US", "medium"),
    ("megaprojects documentary", "en", "US", "long"),
    ("how it was built engineering", "en", "US", "medium"),
    ("space documentary for sleep", "en", "US", "long"),
    ("deep ocean documentary", "en", "US", "long"),
    # Géopolitique, pays, guerre
    ("pourquoi ce pays", "fr", "FR", "medium"),
    ("géopolitique expliquée", "fr", "FR", "medium"),
    ("histoire militaire documentaire", "fr", "FR", "long"),
    ("why this country is", "en", "US", "medium"),
    ("military history documentary", "en", "US", "long"),
    # Argent, business, luxe
    ("finance personnelle", "fr", "FR", "medium"),
    ("histoire d'une entreprise", "fr", "FR", "medium"),
    ("milliardaire histoire", "fr", "FR", "medium"),
    ("business documentary rise and fall", "en", "US", "long"),
    ("how billionaires spend", "en", "US", "medium"),
    ("money explained documentary", "en", "US", "medium"),
    # Psychologie, philosophie, développement
    ("psychologie faits", "fr", "FR", "medium"),
    ("stoïcisme", "fr", "FR", "medium"),
    ("dark psychology", "en", "US", "medium"),
    ("stoicism documentary", "en", "US", "long"),
    # Survie, nature, animaux
    ("survie documentaire", "fr", "FR", "long"),
    ("animaux documentaire", "fr", "FR", "long"),
    ("survival skills documentary", "en", "US", "long"),
    ("prepping list", "en", "US", "long"),
    ("animal documentary", "en", "US", "long"),
    # Lieux, voyages, curiosités
    ("lieux interdits", "fr", "FR", "medium"),
    ("lieux abandonnés", "fr", "FR", "medium"),
    ("villes fantômes", "fr", "FR", "medium"),
    ("most dangerous places", "en", "US", "medium"),
    ("abandoned places documentary", "en", "US", "long"),
    # Cinéma, biographies, culture
    ("biographie documentaire", "fr", "FR", "long"),
    ("coulisses de films", "fr", "FR", "medium"),
    ("biography documentary", "en", "US", "long"),
    ("behind the scenes movie facts", "en", "US", "medium"),
    # Technologie, IA, santé, religion
    ("intelligence artificielle documentaire", "fr", "FR", "medium"),
    ("santé corps humain", "fr", "FR", "medium"),
    ("mythologie", "fr", "FR", "long"),
    ("bible histoire", "fr", "FR", "long"),
    ("ai explained documentary", "en", "US", "medium"),
    ("human body documentary", "en", "US", "long"),
    ("mythology explained", "en", "US", "long"),
]

# RPM (dollars pour 1 000 vues) par catégorie et langue d'audience : ordres de grandeur de docs/61 §2 (AIR, Nexlev,
# MilX) ; une vue française vaut environ la moitié d'une vue américaine. Shorts : partage des revenus Shorts.
RPM: dict[str, tuple[float, float]] = {
    "histoire": (3.2, 6.0),
    "mystere_crime": (3.0, 6.5),
    "horreur_histoires": (2.6, 3.0),
    "science_education": (4.0, 9.0),
    "espace_sommeil": (6.0, 14.0),
    "geopolitique_guerre": (2.5, 4.0),
    "argent_business": (6.0, 14.0),
    "tech_ia": (3.0, 7.0),
    "psychologie_sante": (3.0, 6.0),
    "survie_nature": (3.0, 6.0),
    "lieux_voyage": (3.0, 6.0),
    "culture_cinema": (2.4, 3.0),
    "divertissement": (1.8, 2.5),
}
SHORTS_RPM = (0.10, 0.25)
CATEGORIES = list(RPM)


class ChannelVerdict(BaseModel):
    index: int
    niche: str = ""  # la niche en quelques mots français (« mystères des civilisations »)
    category: str = "divertissement"
    faceless: bool = True
    ai_made: bool = False
    effort: int = Field(3, ge=1, le=5)  # 1 = nos recettes le font déjà, 5 = impossible sans tournage
    why: str = ""  # pourquoi ça marche, en une phrase
    format_name: str = ""  # le format (« ta vie à chaque rang », « enquête », « liste de 25 choses »…)


class ChannelVerdicts(BaseModel):
    channels: list[ChannelVerdict] = Field(default_factory=list)


CLASSIFY_PROMPT = f"""Tu es analyste de niches YouTube. On te donne des chaînes qui percent en ce moment (récentes ou petites, avec une
vidéo récente très vue) : leur nom, leur langue, leur âge, leurs abonnés et les titres de leurs vidéos qui marchent.
Pour chacune (index donné) :
- niche : la niche en 2 à 5 mots français, assez précise pour regrouper les chaînes qui font la même chose
  (« mystères des civilisations », « ta vie à chaque rang », « survie et listes du Far West », « documentaires pour
  dormir », « histoires Reddit de vengeance ») ; deux chaînes qui font la même chose reçoivent EXACTEMENT la même niche ;
- category : une de {", ".join(CATEGORIES)} ;
- faceless : true si la chaîne ne montre jamais son créateur ; ai_made : true si images ou voix sont visiblement
  générées par IA (titres, style) ;
- effort pour la refaire avec images et clips générés par IA et une voix de narrateur : 1 = facile, 3 = demande une
  nouvelle recette, 5 = impossible (tournage, visage, jeu vidéo, vraies archives) ;
- format_name : le format en quelques mots ; why : pourquoi elle marche, en une phrase.
Réponds uniquement en JSON : {{"channels": [{{"index": 0, "niche": "…", "category": "histoire", "faceless": true,
"ai_made": false, "effort": 2, "format_name": "…", "why": "…"}}]}}."""


def months_since(iso: str | None, now: datetime) -> float:
    if not iso:
        return 24.0
    try:
        created = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return 24.0
    return max(0.5, (now - created).days / 30.44)


def category_of(value: str | None) -> str:
    """La catégorie de la table des RPM la plus proche de celle écrite par le classeur (« mystere » → mystere_crime)."""
    v = (value or "").strip().lower()
    if v in RPM:
        return v
    for key in RPM:
        parts = key.split("_")
        if v and (key.startswith(v) or v.startswith(parts[0]) or v in parts):
            return key
    return "divertissement"


def estimate(views_total: int | None, months: float, category: str, lang: str | None, fmt: str) -> tuple[int, float, float]:
    """(vues par mois, RPM, revenu par mois) d'une chaîne, ordres de grandeur."""
    monthly = int((views_total or 0) / max(0.5, months))
    fr = (lang or "").startswith("fr")
    if fmt == "short":
        rpm = SHORTS_RPM[0] if fr else SHORTS_RPM[1]
    else:
        lo_hi = RPM[category_of(category)]
        rpm = lo_hi[0] if fr else lo_hi[1]
    return monthly, rpm, round(monthly / 1000 * rpm, 2)


def iso_duration_s(value: str | None) -> int:
    """« PT1H2M3S » → 3723."""
    import re

    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def next_seeds(db: Any, n: int, now: datetime) -> list[tuple[str, str, str, str]]:
    """Les sujets de départ qui n'ont pas servi depuis le plus longtemps (jamais d'abord)."""
    last = {r["seed"]: r["run_at"] for r in db.fetch_all("select seed, run_at from research_seed_runs")}
    rest = now - timedelta(days=SEED_REST_DAYS)
    fresh = [s for s in SEEDS if s[0] not in last or last[s[0]] < rest]
    fresh.sort(key=lambda s: last.get(s[0]) or datetime(2000, 1, 1, tzinfo=UTC))
    return fresh[:n]


def channel_stats(yt: Any, db: Any, ids: list[str]) -> dict[str, dict[str, Any]]:
    """Abonnés, vues totales, nombre de vidéos, création et langue de chaînes, par 50."""
    out: dict[str, dict[str, Any]] = {}
    uniq = list(dict.fromkeys(i for i in ids if i))
    for i in range(0, len(uniq), 50):
        res = yt.api.channels().list(part="snippet,statistics", id=",".join(uniq[i : i + 50])).execute()
        db.record_quota(None, "channels.list", 1)
        for it in res.get("items", []):
            st, sn = it.get("statistics", {}), it.get("snippet", {})
            out[it["id"]] = {
                "title": sn.get("title") or "",
                "created_at": sn.get("publishedAt"),
                "lang": sn.get("defaultLanguage") or sn.get("country"),
                "subs": None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0)),
                "views": int(st.get("viewCount", 0)),
                "videos": int(st.get("videoCount", 0)),
            }
    return out


def search_long(yt: Any, db: Any, q: str, lang: str, region: str, duration: str, after: datetime) -> list[str]:
    res = (
        yt.api.search()
        .list(
            part="id",
            q=q,
            type="video",
            videoDuration=duration,
            order="viewCount",
            publishedAfter=after.strftime("%Y-%m-%dT%H:%M:%SZ"),
            relevanceLanguage=lang,
            regionCode=region,
            maxResults=25,
        )
        .execute()
    )
    db.record_quota(None, yp.SEARCH_ENDPOINT, 1)
    return [it["id"]["videoId"] for it in res.get("items", []) if it.get("id", {}).get("videoId")]


def discover(ctx: Any, yt: Any, budget: int) -> dict[str, Any]:
    """Un passage de la Découverte : `budget` recherches au plus, puis fiches, chaînes, classement, estimations."""
    db = ctx.db
    now = datetime.now(UTC)
    used = yp.searches_today(db)
    budget = max(0, min(budget, SEARCH_CAP - RESERVE - used))
    seeds = next_seeds(db, budget, now)
    if not seeds:
        return {"searches": 0, "channels": 0, "reason": "quota du jour atteint ou sujets déjà relevés cette semaine"}
    after = now - timedelta(days=WINDOW_DAYS)
    found: dict[str, list[dict[str, Any]]] = {}  # chaîne → ses vidéos trouvées
    seed_of: dict[str, set[str]] = {}
    for i, (q, lang, region, duration) in enumerate(seeds):
        ctx.progress(int(50 * i / len(seeds)), f"Découverte : « {q} »")
        try:
            ids = search_long(yt, db, q, lang, region, duration, after)
        except Exception as exc:  # noqa: BLE001 — une recherche refusée n'arrête pas les autres
            ctx.log("decouverte.recherche_refusee", level="warn", q=q, erreur=str(exc)[:200])
            continue
        details = yp.video_details(yt, db, ids) if ids else []
        kept = 0
        for v in details:
            views = int(v.get("statistics", {}).get("viewCount", 0))
            if views < MIN_VIEWS:
                continue
            ch = v.get("snippet", {}).get("channelId")
            if not ch:
                continue
            dur = iso_duration_s(v.get("contentDetails", {}).get("duration"))
            found.setdefault(ch, []).append(
                {
                    "id": v["id"],
                    "title": v.get("snippet", {}).get("title", ""),
                    "views": views,
                    "duration_s": dur,
                    "published_at": v.get("snippet", {}).get("publishedAt"),
                    "lang": v.get("snippet", {}).get("defaultAudioLanguage") or lang,
                }
            )
            seed_of.setdefault(ch, set()).add(q)
            kept += 1
        db.execute(
            """insert into research_seed_runs (seed, run_at, found) values (%s, now(), %s)
               on conflict (seed) do update set run_at = now(), found = excluded.found""",
            (q, kept),
        )
    stats = channel_stats(yt, db, list(found))
    rows: list[dict[str, Any]] = []
    for ch, vids in found.items():
        st = stats.get(ch)
        if not st:
            continue
        months = months_since(st["created_at"], now)
        if months > YOUNG_MONTHS and (st["subs"] or 0) > SMALL_SUBS:
            continue  # grosse chaîne installée : ce n'est pas une porte ouverte
        durations = [v["duration_s"] for v in vids]
        fmt = "short" if max(durations) <= 180 else "long" if min(durations) >= 480 else "mixed"
        lang = (vids[0].get("lang") or st.get("lang") or "")[:2].lower() or None
        rows.append(
            {
                "id": ch,
                "title": st["title"],
                "lang": lang,
                "created_at": st["created_at"],
                "subs": st["subs"],
                "views": st["views"],
                "videos": st["videos"],
                "format": fmt,
                "months": months,
                "top": sorted(vids, key=lambda v: -v["views"])[:5],
                "seeds": sorted(seed_of.get(ch, set())),
            }
        )
    ctx.progress(60, f"Découverte : {len(rows)} chaînes à classer")
    verdicts = classify(ctx, rows)
    for r in rows:
        v = verdicts.get(r["id"])
        cat = category_of(v.category if v else None)
        monthly, rpm, revenue = estimate(r["views"], r["months"], cat, r["lang"], r["format"])
        db.execute(
            """insert into research_channels (channel_ext_id, title, lang, created_at_yt, subs, views_total, videos, format,
                                              top_videos, seeds, classification, monthly_views, rpm, monthly_revenue,
                                              last_seen_at, stats_at)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
               on conflict (channel_ext_id) do update set
                 title = excluded.title, lang = excluded.lang, subs = excluded.subs, views_total = excluded.views_total,
                 videos = excluded.videos, format = excluded.format, top_videos = excluded.top_videos,
                 seeds = (select array(select distinct unnest(research_channels.seeds || excluded.seeds))),
                 classification = coalesce(excluded.classification, research_channels.classification),
                 monthly_views = excluded.monthly_views, rpm = excluded.rpm, monthly_revenue = excluded.monthly_revenue,
                 last_seen_at = now(), stats_at = now()""",
            (
                r["id"],
                r["title"],
                r["lang"],
                r["created_at"],
                r["subs"],
                r["views"],
                r["videos"],
                r["format"],
                Jsonb(r["top"]),
                r["seeds"],
                Jsonb(v.model_dump(exclude={"index"})) if v else None,
                monthly,
                rpm,
                revenue,
            ),
        )
    return {"searches": len(seeds), "channels": len(rows), "classified": len(verdicts)}


def classify(ctx: Any, rows: list[dict[str, Any]]) -> dict[str, ChannelVerdict]:
    """L'agent classeur, par lots de 15 chaînes ; {chaîne : verdict} (vide si aucun modèle ne répond)."""
    out: dict[str, ChannelVerdict] = {}
    if not rows:
        return out
    llm = get_llm(ctx.settings, ctx.db)
    system = prompt_text(ctx.db, "research_discover", CLASSIFY_PROMPT)
    # les niches déjà nommées (base et lots précédents) : une chaîne qui fait la même chose reçoit le même nom
    known = {
        r["n"]
        for r in ctx.db.fetch_all(
            "select distinct classification->>'niche' as n from research_channels where classification ? 'niche' limit 200"
        )
        if r["n"]
    }
    for start in range(0, len(rows), 15):
        batch = rows[start : start + 15]
        lines = (
            [
                "NICHES DÉJÀ NOMMÉES (reprends exactement l'un de ces noms quand la chaîne fait la même chose) : "
                + " ; ".join(sorted(known)),
                "",
            ]
            if known
            else []
        )
        for k, r in enumerate(batch):
            titles = " | ".join(
                f"{v['title']} ({format(v['views'], ',').replace(',', ' ')} vues, {round(v['duration_s'] / 60)} min)"
                for v in r["top"][:4]
            )
            lines.append(
                f"{k}. {r['title']} — langue {r['lang'] or '?'}, {round(r['months'], 1)} mois, "
                f"{r['subs'] if r['subs'] is not None else '?'} abonnés, {r['videos']} vidéos — {titles}"
            )
        try:
            res: ChannelVerdicts = llm.complete_json(system, "\n".join(lines), ChannelVerdicts)
        except Exception as exc:  # noqa: BLE001
            ctx.log("decouverte.classement_impossible", level="warn", erreur=str(exc)[:300])
            continue
        for v in res.channels:
            if 0 <= v.index < len(batch):
                out[batch[v.index]["id"]] = v
                if v.niche:
                    known.add(v.niche)
    return out
