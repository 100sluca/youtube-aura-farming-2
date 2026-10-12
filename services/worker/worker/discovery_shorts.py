"""Recherche → Découverte → Shorts (docs/64 §2) : les niches Shorts qui marchent HORS de celles qu'on suit.

Demande de Luca (04/10) : la veille (docs/60) ne mesure que les 22 niches prévues au départ ; il veut voir ce qui marche
ailleurs (Minecraft, jeux vidéo, montres, voitures, cuisine…), quitte à ajouter de nouvelles niches au projet.

Chaque grand sujet de SEEDS devient une niche « découverte » (research_niches, origin = 'discover', status = 'proposed') ;
elle est mesurée exactement comme une niche suivie, sur le dernier mois jugé (les 50 Shorts les plus vus publiés ce
mois-là, une recherche YouTube) : vues médianes, tubes, porte ouverte, et la faisabilité d'après ses 6 Shorts les plus
vus, classés par l'agent classeur. Une recherche par sujet et par mois : un balayage complet coûte len(SEEDS)
recherches, puis rien jusqu'au mois suivant (un mois jugé ne change plus).
Sur la page : « Suivre » la fait entrer dans la veille de chaque jour (courbe sur 12 mois) ; « Écarter » l'archive, elle
n'est plus remesurée.
"""

from __future__ import annotations

from typing import Any

import structlog
from psycopg.types.json import Jsonb

from .steps.base import Context

log = structlog.get_logger(__name__)

CLASSIFY_TOP = 6  # Shorts classés par niche découverte : sa faisabilité se lit sur eux
DEFAULT_BUDGET = 15  # recherches par passage quotidien (9 h 45) : un balayage complet en 5 à 6 jours, puis 1 par mois

# (clé, nom de la niche, recherche YouTube, langue, pays) : de grands sujets qui ne sont pas dans nos 22 niches suivies.
SEEDS: list[tuple[str, str, str, str, str]] = [
    # Jeux vidéo
    ("minecraft", "Minecraft", "minecraft", "en", "US"),
    ("minecraft_fr", "Minecraft (en français)", "minecraft", "fr", "FR"),
    ("roblox", "Roblox", "roblox", "en", "US"),
    ("fortnite", "Fortnite", "fortnite", "en", "US"),
    ("gta", "GTA", "gta 6", "en", "US"),
    ("jeux_video_faits", "Secrets et faits de jeux vidéo", "video game facts", "en", "US"),
    ("jeux_retro", "Jeux rétro et consoles", "retro gaming", "en", "US"),
    # Montres, bijoux, objets de luxe
    ("montres", "Montres", "luxury watch", "en", "US"),
    ("montres_fr", "Montres (en français)", "montre de luxe", "fr", "FR"),
    ("bijoux_or", "Or, bijoux et pierres précieuses", "gold jewelry", "en", "US"),
    ("sneakers", "Sneakers", "sneakers", "en", "US"),
    ("parfums", "Parfums", "fragrance perfume", "en", "US"),
    # Véhicules
    ("supercars", "Supercars", "supercar", "en", "US"),
    ("voitures_fr", "Voitures (en français)", "voiture", "fr", "FR"),
    ("restauration_voiture", "Restauration de voitures", "car restoration", "en", "US"),
    ("motos", "Motos", "motorcycle", "en", "US"),
    ("avions", "Avions et aviation", "airplane aviation", "en", "US"),
    ("trains", "Trains", "train", "en", "US"),
    ("bateaux", "Bateaux et navires", "ship cruise", "en", "US"),
    ("engins_chantier", "Engins de chantier", "excavator heavy machinery", "en", "US"),
    ("armee_tech", "Armes et engins militaires", "military technology", "en", "US"),
    # Cuisine
    ("recettes", "Recettes rapides", "easy recipe", "en", "US"),
    ("recettes_fr", "Recettes (en français)", "recette facile", "fr", "FR"),
    ("street_food", "Street food", "street food", "en", "US"),
    ("food_asmr", "Cuisine ASMR", "cooking asmr", "en", "US"),
    ("faits_nourriture", "Faits sur la nourriture", "food facts", "en", "US"),
    # Sport
    ("football", "Football", "football skills", "en", "US"),
    ("football_fr", "Football (en français)", "football", "fr", "FR"),
    ("basket", "Basket NBA", "nba", "en", "US"),
    ("combat", "MMA et boxe", "ufc mma", "en", "US"),
    ("f1", "Formule 1", "formula 1", "en", "US"),
    ("musculation", "Musculation et fitness", "gym workout", "en", "US"),
    # Animaux et nature (filmés)
    ("animaux_sauvages", "Animaux sauvages", "wild animals", "en", "US"),
    ("chiens", "Chiens", "dog", "en", "US"),
    ("chats", "Chats", "cat funny", "en", "US"),
    ("sauvetage_animaux", "Sauvetages d'animaux", "animal rescue", "en", "US"),
    ("dinosaures", "Dinosaures", "dinosaur", "en", "US"),
    ("insectes", "Insectes et araignées", "insects", "en", "US"),
    ("peche", "Pêche", "fishing", "en", "US"),
    ("catastrophes", "Catastrophes naturelles", "natural disaster", "en", "US"),
    # Fabriquer, réparer
    ("bois", "Travail du bois", "woodworking", "en", "US"),
    ("forge", "Forge et métal", "blacksmith forging", "en", "US"),
    ("restauration_objets", "Restauration d'objets anciens", "restoration rusty", "en", "US"),
    ("lego", "Lego", "lego", "en", "US"),
    ("dessin", "Dessin et peinture", "drawing art", "en", "US"),
    ("animation_3d", "Animation 3D", "3d animation", "en", "US"),
    ("comment_c_est_fait", "Comment c'est fabriqué", "how it's made factory", "en", "US"),
    ("astuces_maison", "Astuces de la maison", "life hacks", "en", "US"),
    # Savoirs
    ("experiences", "Expériences scientifiques", "science experiment", "en", "US"),
    ("corps_humain", "Corps humain et santé", "human body facts", "en", "US"),
    ("geographie", "Géographie, cartes et pays", "geography map", "en", "US"),
    ("faits_histoire", "Faits d'histoire", "history facts", "en", "US"),
    ("mythologie", "Mythologie", "mythology", "en", "US"),
    ("langues", "Langues et mots", "language learning", "en", "US"),
    ("tech_gadgets", "Gadgets et technologie", "tech gadgets", "en", "US"),
    ("ia_outils", "Outils d'IA", "ai tools", "en", "US"),
    ("telephone_astuces", "Astuces téléphone", "iphone tips", "en", "US"),
    # Argent
    ("argent_astuces", "Argent et finances perso", "money tips", "en", "US"),
    ("business_histoires", "Histoires de marques", "business story brand", "en", "US"),
    ("immobilier", "Immobilier", "real estate", "en", "US"),
    ("crypto", "Crypto", "crypto bitcoin", "en", "US"),
    # Histoires, divertissement
    ("histoires_reddit", "Histoires Reddit", "reddit stories", "en", "US"),
    ("horreur", "Histoires d'horreur", "scary story", "en", "US"),
    ("true_crime", "Faits divers et enquêtes", "true crime", "en", "US"),
    ("films_faits", "Secrets de films", "movie facts", "en", "US"),
    ("anime", "Anime", "anime", "en", "US"),
    ("magie", "Tours de magie", "magic trick", "en", "US"),
    ("musique", "Musique et instruments", "piano", "en", "US"),
    ("humour_fr", "Humour (en français)", "humour", "fr", "FR"),
    ("couple", "Couple et relations", "relationship advice", "en", "US"),
    # Voyages, lieux
    ("voyages", "Voyages et destinations", "travel destination", "en", "US"),
    ("hotels", "Hôtels insolites", "hotel room tour", "en", "US"),
    ("villes", "Villes du monde", "city", "en", "US"),
]


def seed_slug(key: str) -> str:
    return f"decouverte_{key}"


def ensure_seeds(db: Any) -> list[str]:
    """Une niche « découverte » par sujet de SEEDS (créée au besoin) ; les ids de celles encore à mesurer, c'est-à-dire
    proposées (pas suivies, en pause ni écartées)."""
    have = {r["slug"]: r for r in db.fetch_all("select id, slug, status from research_niches where origin = 'discover'")}
    ids = []
    for key, label, q, lang, region in SEEDS:
        row = have.get(seed_slug(key))
        if row is None:
            row = db.fetch_one(
                """insert into research_niches (slug, label, description, queries, status, origin)
                   values (%s, %s, %s, %s, 'proposed', 'discover')
                   on conflict (slug) do update set label = excluded.label returning id, status""",
                (
                    seed_slug(key),
                    label,
                    f"Découverte : les Shorts les plus vus de la recherche « {q} » ({lang}).",
                    Jsonb([{"q": q, "lang": lang, "region": region}]),
                ),
            )
            assert row
        if row["status"] == "proposed":
            ids.append(str(row["id"]))
    return ids


def discover_shorts(ctx: Context, budget: int | None = None) -> dict[str, Any]:
    """Mesure les niches découvertes pas encore mesurées sur le dernier mois jugé, `budget` recherches au plus."""
    from .steps.research import research_settings, scan

    cfg = research_settings(ctx.db)
    ids = ensure_seeds(ctx.db)
    n = int(budget or cfg.get("discover_shorts_searches") or DEFAULT_BUDGET)
    if not ids:
        return {"searches": 0, "seeds": len(SEEDS), "skipped": "aucune niche découverte à mesurer"}
    out = scan(ctx, niche_ids=ids, months=1, budget=n, weekly=False, classify_top=CLASSIFY_TOP)
    log.info("research.discover_shorts", searches=out.get("searches"), left=out.get("months_left"))
    return out | {"seeds": len(SEEDS)}
