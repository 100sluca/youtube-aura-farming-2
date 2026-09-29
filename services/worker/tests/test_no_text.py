"""Aucun texte écrit par les générateurs d'images et de vidéos (demande de Luca, 29/09) : sur « Mamie Pomme », MiniMax H3
écrivait la réplique à l'image comme un sous-titre, en plus de ceux du montage, et un panneau « SOLD » venait de
l'image. Le prompt du clip dit que la réplique s'entend sans s'écrire, le scénariste n'écrit plus de texte dans l'image,
et le contrôle des clips (modèle de vision) refait un clip de drame où du texte apparaît. L'interdiction dans le prompt
des modèles sans CFG est testée dans test_workflows.py."""

from __future__ import annotations

from worker import drama
from worker.keyframe_qc import NO_NEW_TEXT, clip_requirements
from worker.models import ScriptV1

CAST = [
    {
        "key": "pomme",
        "name": "Mamie Pomme",
        "role": "victime",
        "voice": "a warm fragile elderly female voice",
        "look": "an elderly woman whose head is a wrinkled red apple, round glasses, floral headscarf, beige cardigan",
    }
]


def _script() -> ScriptV1:
    scenes = [
        {
            "index": i,
            "duration_s": 4,
            "visual_prompt": f"shot {i}",
            "motion_prompt": f"move {i}",
            "characters": ["pomme"],
            "lines": [{"who": "pomme", "text": "Mais… je suis ta mère.", "tone": "whispering"}],
        }
        for i in range(4)
    ]
    return drama.normalize(
        ScriptV1.model_validate({"scenes": scenes, "cast": CAST, "metadata": {"fr": {"title": "t", "description": "d"}}})
    )


def test_the_line_is_heard_never_written_on_screen():
    p = drama.clip_prompt(_script(), 0, "fr", "pixar_fruit")
    assert '"Mais… je suis ta mère."' in p  # H3 doit toujours savoir quoi dire
    assert p.endswith("The words are only heard, never written on screen: no subtitles, no captions.")


def test_the_writer_puts_no_writing_in_the_pictures():
    assert "AUCUN TEXTE ÉCRIT dans l'image" in drama.SCRIPT_PROMPT and "« VENDU »" not in drama.SCRIPT_PROMPT
    assert "sans aucun texte écrit" in drama.REWRITE_HINT


def test_a_drama_clip_is_checked_for_text_the_video_model_wrote():
    s = _script()
    assert clip_requirements(s, 0, "drama") == [NO_NEW_TEXT]  # ni personne ni décor contrôlés : des personnages, c'est normal
    assert "sous-titres" in NO_NEW_TEXT and "déjà dans l'image 1" in NO_NEW_TEXT  # un texte de l'image de départ ne partirait pas
