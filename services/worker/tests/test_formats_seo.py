from worker.models import SeoPack
from worker.steps.seo import AI_NOTE, finalize


def test_visual_formats_end_the_description_with_the_ai_note():
    pack = SeoPack.model_validate(
        {
            "titles": [
                {"title": "Cette villa à Ibiza coûte… 😳", "angle": "curiosité"},
                {"title": "Villa de rêve", "angle": "lieu"},
            ],
            "description": "Visite d'une villa méditerranéenne. #villa #luxe #maison",
            "hashtags": ["villa", "luxe", "maison"],
        }
    )
    _, plain, _ = finalize(pack, lang="fr")
    _, visual, _ = finalize(pack, lang="fr", ai_note=True)
    assert AI_NOTE["fr"] not in plain and visual.endswith(AI_NOTE["fr"])
    assert finalize(pack, lang="en", ai_note=True)[1].endswith(AI_NOTE["en"])
