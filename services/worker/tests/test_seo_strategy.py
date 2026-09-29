from datetime import datetime

from worker.models import SeoPack, StrategyProposal
from worker.steps.seo import clean_title, finalize, normalize_hashtags, normalize_tags, pick_title, tags_length, truncate_bytes
from worker.strategy import VideoPerf, compute_stats, duration_bucket, guidance_text, time_slot, title_features, validate_proposal


def _pack(**kw) -> SeoPack:
    base = {
        "titles": [
            {"title": "Le miroir qui cache un dressing secret", "angle": "curiosité"},
            {"title": "12 m² cachés derrière un miroir ?", "angle": "chiffre"},
        ],
        "chosen": 0,
        "description": "Personne ne pousse jamais ce miroir.\nEt vous, vous oseriez ?",
        "tags": ["dressing secret", "#miroir", "Dressing Secret", "rangement caché"],
        "hashtags": ["#maison", "construction", "#aménagement", "#bonus"],
    }
    return SeoPack.model_validate({**base, **kw})


def test_titles_are_cleaned_and_kept_short():
    assert clean_title(' "Le <meilleur> miroir #Shorts" ') == "Le ‹meilleur› miroir"
    long = "Un titre beaucoup trop long qui dépasse largement les soixante-dix caractères autorisés ici"
    assert pick_title(_pack(titles=[{"title": long, "angle": "a"}, {"title": "Titre court", "angle": "b"}])) == "Titre court"
    only_long = pick_title(_pack(titles=[{"title": long, "angle": "a"}, {"title": long, "angle": "b"}]))
    assert len(only_long) <= 70 and long.startswith(only_long)


def test_hashtags_tags_and_description():
    assert normalize_hashtags(["#maison cachée", "Maison", "#construction!", "#a", "#b"]) == [
        "#maisoncachée",
        "#Maison",
        "#construction",
    ]
    tags = normalize_tags(["dressing secret", "#miroir", "Dressing Secret", "<rangement>"])
    assert tags == ["dressing secret", "miroir", "‹rangement›"]
    assert tags_length(["a b", "c"]) == 3 + 2 + 1 + 1
    assert tags_length(normalize_tags([f"tag numéro {i} assez long" for i in range(60)])) <= 500
    title, description, tags = finalize(_pack())
    assert title == "Le miroir qui cache un dressing secret"
    assert description.endswith("#maison #construction #aménagement")
    assert truncate_bytes("éééé", 5) == "éé"


def _row(title, cat, views, pct, hour, dur=30.0):
    return VideoPerf(
        title=title,
        category=cat,
        format="A_voiceover",
        duration_s=dur,
        published_local=datetime(2026, 9, 1, hour, 0),
        views_d7=views,
        average_view_pct=pct,
        subscribers_gained=views // 100,
        likes=views // 20,
        comments=views // 200,
        shares=views // 300,
    )


def test_compute_stats_groups_with_confidence_and_lift():
    rows = [_row(f"Piscine {i} ?", "pool", 10000 + i, 80.0, 18) for i in range(8)]
    rows += [_row(f"Cabane {i}", "treehouse", 1000 + i, 55.0, 9, dur=40) for i in range(2)]
    stats = compute_stats(rows)
    cats = {g["value"]: g for g in stats["par_categorie"]}
    assert stats["n"] == 10
    assert cats["pool"]["confidence"] == "bonne" and cats["treehouse"]["confidence"] == "faible"
    # 8 piscines sur 10 : la médiane de la chaîne est la leur, leur écart est donc nul
    assert cats["pool"]["lift_pct"] >= 0 and cats["treehouse"]["lift_pct"] < -80
    assert {g["value"] for g in stats["par_titre"]} >= {"question", "chiffre"}
    assert len(stats["meilleures"]) == 5 and stats["meilleures"][0]["catégorie"] == "pool"


def test_validate_proposal_guards_slots_and_weights():
    rows = [_row(f"v{i}", "pool", 5000, 70.0, 18) for i in range(4)] + [_row(f"w{i}", "pool", 3000, 60.0, 9) for i in range(4)]
    stats = compute_stats(rows)
    p = StrategyProposal.model_validate(
        {
            "summary": "s",
            "category_weights": [
                {"category": "pool", "weight": 3, "reason": "r"},
                {"category": "treehouse", "weight": 3, "reason": "r"},
            ],
            "publish_slots": ["18:00", "12:30", "09:00"],
        }
    )
    v = validate_proposal(p, stats, ["09:00", "13:00", "18:00"])
    assert v.publish_slots == ["09:00", "12:30", "18:00"]  # justifié : 18:00 a une confiance moyenne
    assert [w.weight for w in v.category_weights] == [3.0, 2.0]  # 3 seulement avec une confiance « bonne »
    bad = validate_proposal(p.model_copy(update={"publish_slots": ["25:00", "18:00"]}), stats, ["09:00", "13:00", "18:00"])
    assert bad.publish_slots is None  # mauvais format ou mauvais nombre de créneaux


def test_small_helpers():
    assert duration_bucket(20) == "moins de 25 s" and duration_bucket(30) == "25 à 35 s" and duration_bucket(None) is None
    assert time_slot(datetime(2026, 1, 1, 12)) == "midi (11-14 h)" and time_slot(datetime(2026, 1, 1, 23)) == "nuit (22-6 h)"
    assert title_features("12 idées ? 🔥")[:3] == ["question", "chiffre", "émoji"]
    assert "Aucune stratégie" in guidance_text({})
    g = guidance_text(
        {"fr": StrategyProposal(summary="Plus de piscines", title_patterns=["Chiffre + objet"], avoid=["listes"])}, for_seo=True
    )
    assert "Chiffre + objet" in g and "listes" in g
