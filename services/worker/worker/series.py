"""Séries de contenu et lien concept approuvé → production.

Une série = une ligne éditoriale (table `series`, migration 0003) : source de matière (llm ou wikipedia),
brief injecté dans les prompts idée et script, catégories, style visuel, format, durée cible, poids dans la
production quotidienne. Les agents idée et script lisent la série du concept ; le planificateur crée les
productions à partir des concepts approuvés, série par série selon les poids (create_production, qui
manquait jusqu'ici : rien ne transformait une idée validée en production).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

COLUMNS = (
    "id, slug, name, source, source_config, brief, categories, style_preset, format, target_duration_s, "
    "subtitle_profile, music_moods, video_provider, weight, is_active, channel_id, recipe"
)


@dataclass(frozen=True)
class Series:
    id: UUID
    slug: str
    name: str
    source: str  # llm | wikipedia
    source_config: dict[str, Any]
    brief: str
    categories: list[str]
    style_preset: str | None
    format: str
    target_duration_s: int
    subtitle_profile: str | None
    music_moods: list[str]
    video_provider: str | None
    weight: float
    is_active: bool
    channel_id: UUID | None
    recipe: str = "story"  # story | timelapse | tour (worker/recipes.py, migration 0005)

    @classmethod
    def from_row(cls, r: dict[str, Any]) -> Series:
        return cls(
            id=r["id"],
            slug=r["slug"],
            name=r["name"],
            source=r["source"],
            source_config=r["source_config"] or {},
            brief=r["brief"],
            categories=list(r["categories"] or []),
            style_preset=r["style_preset"],
            format=r["format"],
            target_duration_s=int(r["target_duration_s"]),
            subtitle_profile=r["subtitle_profile"],
            music_moods=list(r["music_moods"] or []),
            video_provider=r["video_provider"],
            weight=float(r["weight"]),
            is_active=bool(r["is_active"]),
            channel_id=r["channel_id"],
            recipe=r.get("recipe") or "story",
        )

    @property
    def lang(self) -> str:
        return str(self.source_config.get("lang", "fr"))


def active_series(db: Any) -> list[Series]:
    return [Series.from_row(r) for r in db.fetch_all(f"select {COLUMNS} from series where is_active order by slug")]


def get_series(db: Any, key: str | UUID) -> Series:
    row = db.fetch_one(f"select {COLUMNS} from series where slug = %s or id::text = %s", (str(key), str(key)))
    if not row:
        raise LookupError(f"série inconnue : {key}")
    return Series.from_row(row)


def series_of_concept(db: Any, concept_id: UUID | str) -> Series | None:
    row = db.fetch_one(
        f"select {', '.join('s.' + c.strip() for c in COLUMNS.split(','))} from series s join concepts c on c.series_id = s.id where c.id = %s",
        (concept_id,),
    )
    return Series.from_row(row) if row else None


def weighted_counts(series: Sequence[Series], total: int) -> dict[str, int]:
    """Répartit `total` entre les séries selon leur poids (plus forts restes) ; une série de poids > 0 reçoit
    au moins 1 si le total le permet."""
    live = [s for s in series if s.weight > 0]
    if not live or total <= 0:
        return {}
    weights = sum(s.weight for s in live)
    shares = {s.slug: total * s.weight / weights for s in live}
    counts = {slug: int(v) for slug, v in shares.items()}
    for slug in sorted(shares, key=lambda k: shares[k] - counts[k], reverse=True):
        if sum(counts.values()) >= total:
            break
        counts[slug] += 1
    if total >= len(live):
        for slug in counts:
            if counts[slug] == 0:
                donor = max(counts, key=counts.get)  # type: ignore[arg-type]
                if counts[donor] > 1:
                    counts[donor] -= 1
                    counts[slug] = 1
    return counts


def next_concepts(db: Any, n: int) -> list[dict[str, Any]]:
    """Concepts approuvés à produire, répartis entre séries actives selon les poids, meilleurs scores d'abord."""
    rows = db.fetch_all(
        """select c.id, c.title, c.score, coalesce(s.slug, '') as slug, coalesce(s.weight, 1) as weight, coalesce(s.is_active, true) as active
           from concepts c left join series s on s.id = c.series_id
           where c.status = 'approved' order by c.score desc nulls last, c.created_at"""
    )
    rows = [r for r in rows if r["active"]]
    by_series: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_series.setdefault(r["slug"], []).append(r)
    if not by_series:
        return []
    pseudo = [
        Series(
            id=UUID(int=0),
            slug=slug,
            name=slug,
            source="llm",
            source_config={},
            brief="",
            categories=[],
            style_preset=None,
            format="A_voiceover",
            target_duration_s=30,
            subtitle_profile=None,
            music_moods=[],
            video_provider=None,
            weight=float(items[0]["weight"]),
            is_active=True,
            channel_id=None,
        )
        for slug, items in by_series.items()
    ]
    picked: list[dict[str, Any]] = []
    for slug, k in weighted_counts(pseudo, min(n, len(rows))).items():
        picked.extend(by_series[slug][:k])
    return picked[:n]


def create_production(
    db: Any,
    concept_id: UUID | str,
    *,
    format: str | None = None,
    target_duration_s: int | None = None,
    style_preset: str | None = None,
    video_provider: str | None = None,
    priority: int = 100,
    channel_id: UUID | str | None = None,
) -> tuple[UUID, bool]:
    """Crée la production d'un concept (réglages de sa série par défaut) et met le script en file.
    Renvoie (id, créée) ; une production déjà en cours pour ce concept est renvoyée telle quelle.
    Chaîne visée (0008) : `channel_id`, sinon celle du concept, sinon la première chaîne active."""
    c = db.fetch_one("select id, status, series_id, channel_id from concepts where id::text like %s", (f"{concept_id}%",))
    if not c:
        raise LookupError(f"concept introuvable : {concept_id}")
    if c["status"] not in ("approved", "proposed", "used"):
        raise ValueError(f"concept {c['status']} : seul un concept approuvé (ou proposé) se produit")
    existing = db.fetch_one(
        """select id from productions where concept_id = %s and status::text not in ('failed', 'archived', 'cancelled')
           order by created_at desc limit 1""",
        (c["id"],),
    )
    if existing:
        return existing["id"], False
    s = series_of_concept(db, c["id"])
    row = db.fetch_one(
        """insert into productions (concept_id, series_id, channel_id, format, target_duration_s, style_preset, video_provider, status)
           values (%s, %s, coalesce(%s, %s, (select id from channels where is_active order by created_at limit 1)),
                   %s, %s, %s, %s, 'draft') returning id""",
        (
            c["id"],
            s.id if s else None,
            channel_id,
            c.get("channel_id"),
            format or (s.format if s else "A_voiceover"),
            target_duration_s or (s.target_duration_s if s else 30),
            style_preset or (s.style_preset if s else None),
            video_provider or (s.video_provider if s else None),
        ),
    )
    db.execute("update concepts set status = 'used' where id = %s", (c["id"],))
    db.enqueue("script", production_id=row["id"], priority=priority)
    return row["id"], True
