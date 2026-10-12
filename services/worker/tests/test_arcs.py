from worker.arcs import ArcOutline, finish_part, judge, keep_cast, part_brief, part_title
from worker.models import ScriptV1

OUTLINE = ArcOutline.model_validate(
    {
        "premise": "Une mère couvre sa fille de boue et dore l'autre",
        "first_line": "Toi, l'école des riches. Toi, l'école des pauvres.",
        "planted": "Ne touche jamais à l'eau",
        "twist": "La fille couverte de boue est en diamant",
        "moral": "Ce qui brille n'est pas toujours d'or",
        "parts": [
            {"n": 1, "synopsis": "Deux écoles", "ends_on": "Bananita tombe dans la piscine"},
            {"n": 2, "synopsis": "La peinture part", "opens_with": "Dans l'eau", "ends_on": "Le directeur appelle l'académie"},
            {"n": 3, "synopsis": "La vraie famille", "ends_on": "La mère demande pardon"},
        ],
    }
)


def _script(cast_look: str = "a golden banana girl") -> ScriptV1:
    return ScriptV1.model_validate(
        {
            "cast": [
                {"key": "bananita", "name": "Bananita", "look": cast_look, "voice": "a sweet young girl voice"},
                {"key": "directeur", "name": "Le directeur", "look": "a banana in a black suit", "voice": "deep"},
            ],
            "scenes": [
                {
                    "index": i,
                    "duration_s": 3,
                    "visual_prompt": f"plan {i}",
                    "characters": ["bananita"],
                    "lines": [{"who": "bananita", "text": f"réplique {i}"}],
                    "on_screen_text": {"fr": "Partie 2 bientôt"} if i == 4 else {},
                }
                for i in range(5)
            ],
            "metadata": {"fr": {"title": "Une sœur en or, l'autre couverte de boue", "description": "d"}},
        }
    )


def test_verdict_against_the_channel_median():
    assert judge(900, [100, 200, 300, 400], 1.0)["verdict"] == "suggested"
    below = judge(100, [100, 200, 300, 400], 1.0)
    assert below["verdict"] == "below" and below["median"] == 250 and below["ratio"] == 0.4
    assert judge(260, [100, 200, 300, 400], 1.0)["verdict"] == "suggested"
    assert judge(260, [100, 200, 300, 400], 1.5)["verdict"] == "below"  # seuil relevé dans les réglages
    assert judge(5, [100], 1.0)["verdict"] == "suggested"  # pas assez de recul : la suite est proposée


def test_part_brief_opens_cuts_and_keeps_the_cast():
    first = part_brief(OUTLINE, 1)
    assert "PARTIE 1 SUR 3" in first and "Toi, l'école des riches" in first and "Partie 2 bientôt" in first
    second = part_brief(OUTLINE, 2, [_script()])
    assert "Dans l'eau" in second and "Le directeur appelle l'académie" in second
    assert "DISTRIBUTION IMPOSÉE" in second and "a golden banana girl" in second and "réplique 3" in second
    last = part_brief(OUTLINE, 3, [_script(), _script()])
    assert "DERNIÈRE partie" in last and "bientôt" not in last


def test_later_parts_keep_faces_voices_and_get_their_titles():
    redrawn = keep_cast(_script("a banana girl in a red dress"), [_script()])
    assert redrawn.cast[0].look == "a golden banana girl"
    two = finish_part(_script(), 2, 3)
    assert two.metadata["fr"].title.startswith("Partie 2 : ") and two.scenes[-1].on_screen_text["fr"] == "Partie 3 bientôt"
    three = finish_part(_script(), 3, 3)
    assert three.scenes[-1].on_screen_text == {}
    assert part_title("Une sœur en or", 1) == "Une sœur en or"
    assert part_title("Partie 2 : déjà", 2) == "Partie 2 : déjà"
    long = part_title("x" * 30 + " " + "y" * 40, 3)
    assert long.startswith("Partie 3 : ") and len(long) <= 70
