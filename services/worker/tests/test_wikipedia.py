from datetime import date

from worker.models import Fact
from worker.series import Series, weighted_counts
from worker.sources.wikipedia import SourceDoc, WikipediaClient, clip_text, daily_material, material_text, sources_for

LONG = ("Le poisson-pierre vit dans l'océan Indien. " * 40).strip()

FEED = {
    "tfa": {"titles": {"normalized": "Poisson-pierre"}},
    "mostread": {
        "articles": [
            {"titles": {"normalized": "Catherine Ringer"}, "views": 55336, "description": "chanteuse française"},
            {"titles": {"normalized": "Saint-Pierre-et-Miquelon"}, "views": 31194, "description": "collectivité d'outre-mer"},
        ]
    },
    "onthisday": [
        {"year": 1930, "text": "brevet des ampoules de flash", "pages": [{"titles": {"normalized": "Flash (photographie)"}}]}
    ],
}
PAGES = {
    "Poisson-pierre": {
        "title": "Poisson-pierre",
        "canonicalurl": "https://fr.wikipedia.org/wiki/Poisson-pierre",
        "extract": LONG,
        "revisions": [{"revid": 237485590}],
        "description": "espèce de poissons",
    },
    "Catherine Ringer": {
        "title": "Catherine Ringer",
        "canonicalurl": "https://fr.wikipedia.org/wiki/Catherine_Ringer",
        "extract": LONG,
        "revisions": [{"revid": 1}],
        "description": "chanteuse française",
    },
    "Saint-Pierre-et-Miquelon": {
        "title": "Saint-Pierre-et-Miquelon",
        "canonicalurl": "https://fr.wikipedia.org/wiki/SPM",
        "extract": LONG,
        "revisions": [{"revid": 2}],
        "description": "collectivité",
    },
    "Flash (photographie)": {
        "title": "Flash (photographie)",
        "canonicalurl": "https://fr.wikipedia.org/wiki/Flash",
        "extract": "trop court.",
        "revisions": [{"revid": 3}],
    },
    "Monstre de Gila": {
        "title": "Monstre de Gila",
        "canonicalurl": "https://fr.wikipedia.org/wiki/Gila",
        "extract": LONG,
        "revisions": [{"revid": 4}],
        "description": "lézard venimeux",
    },
}


class FakeClient(WikipediaClient):
    def __init__(self):
        super().__init__("fr", pause_s=0)
        self.calls = []

    def _get(self, url, params=None):
        self.calls.append((url, params))
        if "feed/featured" in url:
            return FEED
        if params.get("list") == "search":
            return {"query": {"search": [{"title": "Monstre de Gila"}, {"title": "Poisson-pierre"}]}}
        if params.get("generator") == "random":
            return {"query": {"pages": []}}
        page = PAGES.get(params["titles"])
        return {"query": {"pages": [page or {"title": params["titles"], "missing": True}]}}


def test_daily_material_filters_and_orders():
    config = {
        "feeds": ["tfa", "onthisday", "mostread"],
        "queries": ["animal venimeux"],
        "queries_per_day": 1,
        "min_words": 100,
        "exclude": "(chanteuse|chanteur)",
    }
    docs = daily_material(FakeClient(), config, date(2026, 9, 21), exclude_urls={"https://fr.wikipedia.org/wiki/SPM"})
    titles = [d.title for d in docs]
    assert titles == ["Poisson-pierre", "Monstre de Gila"]  # Ringer exclue (regex), SPM déjà exploitée, Flash trop court
    assert docs[0].kind == "tfa" and docs[0].note == "Article du jour" and docs[0].revision == 237485590
    assert docs[1].kind == "search" and "animal venimeux" in docs[1].note
    assert docs[0].to_ref().url == "https://fr.wikipedia.org/wiki/Poisson-pierre"


def test_material_text_and_sources_mapping():
    docs = [
        SourceDoc("A", "https://a", "fr", LONG, kind="tfa", revision=1),
        SourceDoc("B", "https://b", "fr", LONG, kind="search"),
    ]
    text = material_text(docs, chars=80)
    assert text.startswith("[1] A — https://a") and "[2] B — https://b" in text and len(text) < 400
    refs, facts = sources_for(
        docs, [Fact(claim="x", source=2), Fact(claim="y", source=2), Fact(claim="z", source=9), Fact(claim="w", source=1)]
    )
    assert [r.title for r in refs] == ["B", "A"]
    assert [(f.claim, f.source) for f in facts] == [("x", 0), ("y", 0), ("w", 1)]


def test_clip_text_cuts_on_sentence():
    assert clip_text("Une phrase. Une autre phrase assez longue. Fin.", 45) == "Une phrase. Une autre phrase assez longue."
    assert clip_text("Une phrase. Une autre phrase assez longue. Fin.", 30) == "Une phrase. Une autre phrase…"
    assert clip_text("court", 30) == "court"


def _series(slug, weight):
    return Series(
        id=None,
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
        weight=weight,
        is_active=True,
        channel_id=None,
    )


def test_weighted_counts():
    series = [_series("a", 2), _series("b", 1), _series("c", 1), _series("d", 0)]
    assert weighted_counts(series, 8) == {"a": 4, "b": 2, "c": 2}
    counts = weighted_counts(series, 3)
    assert sum(counts.values()) == 3 and all(counts[s] >= 1 for s in ("a", "b", "c"))
    assert weighted_counts(series, 0) == {}
