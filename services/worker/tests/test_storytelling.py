from worker.dag import continuity_plan
from worker.models import ScriptV1
from worker.storytelling import HOOK_WORDS_MAX, feedback, lint_hook, lint_script, scene_words_max

ROLES = ["hook", "setup", "reveal", "escalation", "payoff", "loop"]
GOOD_FR = [
    "Ce poisson a tué plus de plongeurs que tous les requins réunis.",
    "Il vit à trois mètres du bord, sur les plages de l'océan Indien.",
    "Sa piqûre injecte un venin qui arrête le cœur en deux heures.",
    "Mais personne ne le voit : il ressemble exactement à une pierre.",
    "Un antidote existe, dans cinq hôpitaux au monde seulement.",
    "Alors regardez bien la prochaine pierre sur laquelle vous marchez.",
]


def _script(narrations=GOOD_FR, roles=ROLES, loop_note="Retour sur la pierre du plan 1", **overrides) -> ScriptV1:
    scenes = []
    for i, text in enumerate(narrations):
        scene = {"index": i, "duration_s": 5, "role": roles[i] if roles else None, "visual_prompt": "x",
                 "motion_prompt": "y", "narration": {"fr": text}, "continues_previous": i in (2, 3, 4)}
        scene.update(overrides.get(i, {}))
        scenes.append(scene)
    return ScriptV1.model_validate(
        {"version": 1, "scenes": scenes, "loop_note": loop_note,
         "metadata": {"fr": {"title": "t", "description": "d", "tags": []}}}
    )


def test_clean_script_passes():
    assert lint_script(_script(), ["fr"], 30) == []


def test_lint_catches_measurable_violations():
    bad = list(GOOD_FR)
    bad[0] = "Bonjour à tous, aujourd'hui je vais vous parler d'un poisson vraiment incroyable, dangereux et très mortel."
    bad[3] = "Abonnez-vous pour la suite."
    issues = lint_script(_script(bad), ["fr"], 30)
    text = "\n".join(issues)
    assert "formule interdite" in text
    assert "accroche de" in text and f"{HOOK_WORDS_MAX} au plus" in text
    assert "appel à l'action" in text
    assert "superlatif vide" in text


def test_lint_checks_structure_duration_and_overflow():
    late = ["hook", "setup", "escalation", "reveal", "payoff", "loop"]  # révélation à 15 s
    issues = lint_script(_script(roles=late), ["fr"], 30)
    assert any("révélation" in i and "15 s" in i for i in issues)
    assert any("aucun rôle" in i for i in lint_script(_script(roles=None), ["fr"], 30))
    long = list(GOOD_FR)
    long[2] = "Sa piqûre injecte un venin très puissant qui arrête le cœur en moins de deux heures chez un adulte."
    assert any("mots pour 5 s" in i for i in lint_script(_script(long), ["fr"], 30))
    assert any("durée" in i for i in lint_script(_script(), ["fr"], 60))
    assert any("loop_note" in i for i in lint_script(_script(loop_note=None), ["fr"], 30))
    assert lint_script(_script(), [], 30) == []  # format B : pas de narration à vérifier
    assert scene_words_max(5) == 15  # 3 mots/s (voix mesurée à 3,2 le 28/09)


def test_hook_and_feedback():
    assert lint_hook("Saviez-vous que ce poisson tue ?") and not lint_hook("Ce poisson tue en deux heures.")
    assert feedback(["a", "b"]).endswith("- a\n- b")


def test_continuity_plan_modes_and_drift_guard():
    s = _script()  # scènes 3, 4, 5 demandent la continuité
    assert continuity_plan(s, "script", 3) == [False, False, True, True, True, False]
    assert continuity_plan(s, "script", 2) == [False, False, True, True, False, False]
    assert continuity_plan(s, "cut", 3) == [False] * 6
    assert continuity_plan(s, "chain", 3) == [False, True, True, True, False, True]
