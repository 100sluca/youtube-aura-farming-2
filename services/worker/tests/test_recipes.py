import pytest

from worker.models import ScriptV1
from worker.recipes import (
    DUSK,
    DUSK_MOTION,
    EARLIER,
    EMPTY_HOUSE,
    KEEP_FRAME,
    TIMELAPSE_MOTION,
    WALK_THROUGH,
    WORKER_SCALE,
    day_counter,
    edit_dependents,
    edit_instruction,
    edit_source,
    image_prompt,
    is_visual,
    keyframe_order,
    lint_recipe_script,
    motion_prompt,
    normalize_script,
    spec,
)
from worker.steps.storyboard import edit_chain_closure


def _script(n: int = 6, **extra) -> ScriptV1:
    scenes = [
        {"index": i, "duration_s": 5, "visual_prompt": f"stage {i}", "motion_prompt": f"move {i}", "sfx": "excavator, birds",
         "narration": {"fr": "une phrase"}, "edit_prompt": f"edit {i}" if i % 2 else None}
        for i in range(n)
    ]
    return ScriptV1.model_validate({
        "scenes": scenes,
        "metadata": {"fr": {"title": "t", "description": "d"}},
        "hook_title": {"fr": "« Personne ne voulait de ce terrain. »"},
        "design_bible": "an abandoned stone farmhouse on a hill, seen from the lower meadow",
        **extra,
    })


FINISHED = ("A restored stone farmhouse with a new slate roof, oak front door, tall black-framed windows, a stone "
            "terrace with a glass railing, a lawn and an olive tree, the whole house in the middle of the picture")


def _timelapse(n: int = 10) -> ScriptV1:
    """Chantier conforme : étapes numérotées « Jour … », retouches qui enlèvent, fini décrit en détail."""
    s = _script(n)
    for i, sc in enumerate(s.scenes):
        sc.duration_s = 1.5
        sc.on_screen_text = {"fr": f"Jour {1 + i * 10}"}
        sc.edit_prompt = f"Remove what is not built yet at stage {i}; two workers on the scaffolding"
    s.scenes[0].visual_prompt = "The abandoned stone farmhouse, overgrown with ivy and brambles"
    s.scenes[n - 2].visual_prompt = FINISHED
    return s


def test_timelapse_is_built_backwards_from_the_finished_building():
    s = normalize_script(_timelapse(), "timelapse")
    n = len(s.scenes)
    done, reveal = s.scenes[n - 2], s.scenes[n - 1]
    assert done.edit_prompt is None and edit_source(s, n - 2) is None  # le fini : la seule image générée
    assert [edit_source(s, i) for i in range(n - 2)] == list(range(1, n - 1))  # chaque étape retouche la SUIVANTE
    assert edit_source(s, n - 1) == n - 2 and reveal.edit_prompt  # le crépuscule retouche le fini
    assert keyframe_order(s)[0] == n - 2 and keyframe_order(s)[1:n - 1] == list(range(n - 3, -1, -1))
    assert [sc.clip_mode for sc in s.scenes] == ["flf"] * (n - 1) + ["i2v"]  # le fini → le crépuscule, puis la révélation
    assert {sc.transition for sc in s.scenes} == {"cut"}
    assert all(not sc.narration and not sc.continues_previous for sc in s.scenes)
    assert [sc.duration_s for sc in s.scenes[-3:]] == [1.5, 1.5, 3.0]  # durées bornées selon la place
    assert s.hook_title["fr"] == "Personne ne voulait de ce terrain"  # guillemets et point final retirés
    assert lint_recipe_script(s, "timelapse", ["fr"], 18) == []


def test_timelapse_defaults_fill_what_the_llm_forgot():
    raw = _timelapse()
    raw.scenes[-1].edit_prompt = None
    raw.scenes[2].edit_prompt = None
    raw.scenes[0].duration_s = 5
    s = normalize_script(raw, "timelapse")
    assert s.scenes[-1].edit_prompt == DUSK and s.scenes[2].edit_prompt == "stage 2"
    assert s.scenes[0].duration_s == 2.5  # une étape reste rapide : le clip de 5 s est accéléré ×2 au moins


def test_redoing_the_finished_building_redoes_the_whole_site():
    s = normalize_script(_timelapse(), "timelapse")
    n = len(s.scenes)
    assert edit_dependents(s, {n - 2}) == set(range(n))
    assert edit_dependents(s, {3}) == {0, 1, 2, 3}  # les étapes antérieures dérivent de l'étape 3
    assert edit_chain_closure(s, {n - 1}) == {n - 1}


def test_tour_follows_a_plan():
    raw = _script(7, view="a snowy pyramid-shaped peak above a larch forest")
    for i, sc in enumerate(raw.scenes):
        sc.duration_s = 3.5
        sc.leads_to = None if i == 6 else f"an opening to room {i + 1}"
        sc.floor = 0 if i < 4 else 1
    s = normalize_script(raw, "tour")
    rooms = [sc for sc in s.scenes if not sc.passage]
    passages = [sc for sc in s.scenes if sc.passage]
    assert len(s.scenes) == 13 and [sc.index for sc in s.scenes] == list(range(13))  # 7 pièces + 6 passages
    assert [sc.passage for sc in s.scenes] == [False, True] * 6 + [False]  # un passage entre deux pièces
    assert [sc.interior for sc in rooms] == [False] + [True] * 5 + [False]  # arrivée et clou dehors par défaut
    assert {sc.clip_mode for sc in rooms} == {"i2v"} and {sc.transition for sc in s.scenes} == {"cut"}
    assert all(p.continues_previous and p.clip_mode == "flf" and p.duration_s == 1.2 for p in passages)
    assert "an opening to room 3" in passages[2].motion_prompt  # le passage traverse l'ouverture vue dans la pièce
    assert rooms[1].edit_prompt == "edit 1" and edit_source(s, 2) == 0  # une variante retouche la pièce, pas le passage
    assert lint_recipe_script(s, "tour", ["fr"], 30) == []  # 7 pièces : les passages ne comptent pas comme des scènes
    again = normalize_script(s, "tour")  # idempotent : les passages sont recalculés, pas empilés
    assert len(again.scenes) == 13 and [sc.passage for sc in again.scenes] == [sc.passage for sc in s.scenes]


def test_tour_lint_catches_a_broken_plan():
    raw = _script(7)
    for i, sc in enumerate(raw.scenes):
        sc.duration_s = 3.5
        sc.floor = 1 if i in (2, 3) else 0  # redescend au rez-de-chaussée en scène 5
    issues = " | ".join(lint_recipe_script(normalize_script(raw, "tour"), "tour", ["fr"], 25))
    assert "view manquant" in issues and "leads_to manquant" in issues and "redescend" in issues


def test_story_scripts_are_untouched():
    s = _script()
    assert normalize_script(s, "story") is s and not is_visual("story") and is_visual("tour")
    assert spec("inconnue").name == "story"


def test_lint_catches_a_script_that_starts_with_the_finished_building():
    # Gemini l'a fait deux fois le 25/09 : scène 1 = le résultat fini, puis la ruine en scène 2
    s = _timelapse()
    s.scenes[0].visual_prompt = FINISHED
    issues = lint_recipe_script(normalize_script(s, "timelapse"), "timelapse", ["fr"])
    assert any("ÉTAT INITIAL" in i for i in issues)


def test_backward_edits_carry_the_target_description():
    s = normalize_script(_timelapse(), "timelapse")
    s.scenes[2].visual_prompt = "The bare timber frame of the new roof on the old stone walls"
    assert "The result shows: The bare timber frame of the new roof on the old stone walls." in edit_instruction(s, 2, "timelapse")


def test_lint_reports_missing_hook_title_bible_counter_and_unknown_sfx():
    s = normalize_script(_script(4), "timelapse")
    s.hook_title = {}
    s.design_bible = None
    for sc in s.scenes:
        sc.sfx = "bruit bizarre"
        sc.motion_prompt = None
    issues = " | ".join(lint_recipe_script(s, "timelapse", ["fr", "en"], 35))
    assert "4 scènes" in issues and "[fr] hook_title manquant" in issues and "[en] hook_title manquant" in issues
    assert "design_bible manquant" in issues and "bruitages inconnus" in issues and "motion_prompt manquant" in issues
    assert "compteur de jours manquant" in issues and "trop court" in issues and "doit ENLEVER" in issues
    assert "durée" in issues


def test_prompts_carry_the_bible_the_frame_lock_and_the_scale():
    s = normalize_script(_timelapse(), "timelapse")
    n = len(s.scenes)
    assert image_prompt(s, n - 2, "timelapse").startswith(FINISHED + ", the whole construction is fully visible")
    assert image_prompt(s, n - 2, "timelapse").endswith(s.design_bible)
    s.scenes[n - 2].visual_prompt = "A cabin on a cliff above the ocean, vertical framing, fixed camera on a tripod, wide angle shot"
    assert "tripod" not in image_prompt(s, n - 2, "timelapse").lower()  # sinon le modèle dessine un trépied (essai du 25/09)
    back = edit_instruction(s, 3, "timelapse")
    assert back.startswith(EARLIER) and WORKER_SCALE in back and back.endswith(KEEP_FRAME)
    assert not edit_instruction(s, n - 1, "timelapse").startswith(EARLIER)  # le crépuscule avance dans le temps
    assert motion_prompt(s, 0, "timelapse") == f"{TIMELAPSE_MOTION}, move 0"
    assert motion_prompt(s, n - 2, "timelapse") == DUSK_MOTION
    assert motion_prompt(s, n - 1, "timelapse") == f"move {n - 1}, {EMPTY_HOUSE}"  # révélation : seule la caméra bouge


def test_tour_prompts_say_inside_or_outside_and_repeat_materials_and_view():
    raw = _script(7, view="a snowy pyramid-shaped peak")
    raw.scenes[3].leads_to = "on the right, an oak staircase climbs to the upper floor"
    t = normalize_script(raw, "tour")
    assert [sc.passage for sc in t.scenes[:4]] == [False, True, False, True]  # pièce 3 = position 6
    inside = image_prompt(t, 6, "tour")
    assert inside.startswith("Interior photograph taken inside the house, walls and ceiling visible: stage 3")
    assert "On the right, an oak staircase climbs" in inside and f"Materials of the whole house: {raw.design_bible}" in inside
    assert "Seen through the windows: a snowy pyramid-shaped peak" in inside and inside.endswith("nobody, no people")
    assert image_prompt(t, 0, "tour").startswith("Exterior photograph of the house: stage 0")
    assert motion_prompt(t, 0, "tour") == f"move 0, {EMPTY_HOUSE}"
    t.scenes[2].motion_prompt = "Smooth gimbal glide into the library, empty house, nobody."  # sortie réelle du LLM
    assert motion_prompt(t, 2, "tour") == f"Smooth steady glide into the library, {EMPTY_HOUSE}"
    t.scenes[4].motion_prompt = "Slow dolly along the island, no people walking in, curtains moving"
    assert motion_prompt(t, 4, "tour") == f"Slow tracking along the island, curtains moving, {EMPTY_HOUSE}"
    assert motion_prompt(t, 5, "tour").endswith(WALK_THROUGH)  # un passage traverse, il ne reste pas figé
    assert "person" not in EMPTY_HOUSE and "nobody" not in EMPTY_HOUSE  # nommer les personnes les fait apparaître
    assert edit_instruction(t, 2, "tour").startswith("edit 1 Same house and same style:")


def test_day_counter_ticks_between_stages():
    s = normalize_script(_timelapse(4), "timelapse")  # Jour 1, 11, 21, 31 ; durées 1.5, 1.5, 1.5, 3
    ticks = day_counter(s, "fr", [0.0, 1.5, 3.0, 4.5], [1.5, 1.5, 1.5, 3.0])
    assert ticks[0] == (0.0, 0.15, "Jour 1") and ticks[-1][2] == "Jour 31" and ticks[-1][1] == 7.5
    values = [int(t[2].split()[1]) for t in ticks]
    assert values == sorted(values) and len(set(values)) == 31  # un jour après l'autre, jamais en arrière
    assert all(b[0] == pytest.approx(a[1]) for a, b in zip(ticks, ticks[1:], strict=False))  # sans trou
    assert day_counter(normalize_script(_script(), "timelapse"), "fr", [0.0] * 6, [1.5] * 6) == []  # pas de compteur


def test_llm_quirks_are_absorbed():
    # Gemini a renvoyé le titre d'accroche en texte seul (sortie réelle du 25/09) : rangé sous « fr »
    s = _script(hook_title="Le plus beau toit-terrasse de Paris")
    assert s.hook_title == {"fr": "Le plus beau toit-terrasse de Paris"}
    assert ScriptV1.model_validate({**s.model_dump(), "scenes": [
        {**sc.model_dump(), "on_screen_text": "Jour 1"} for sc in s.scenes]}).scenes[0].on_screen_text == {"fr": "Jour 1"}
    # … et il recopie parfois la bible du lieu dans chaque visual_prompt : pas deux fois dans l'image
    s.scenes[0].visual_prompt = f"A bare cliff. Design Bible: {s.design_bible}"
    assert image_prompt(s, 0, "tour").count(s.design_bible) == 1


def test_question_hooks_get_their_question_mark():
    s = _script(hook_title={"fr": "Tu paierais combien pour cette villa", "en": "How much would you pay for this villa"})
    t = normalize_script(s, "tour")
    assert t.hook_title == {"fr": "Tu paierais combien pour cette villa ?", "en": "How much would you pay for this villa?"}
    s.hook_title = {"fr": "Tu vas halluciner devant ce chantier"}  # une affirmation reste une affirmation
    assert normalize_script(s, "tour").hook_title["fr"] == "Tu vas halluciner devant ce chantier"


def test_camera_rig_words_are_not_drawn():
    # essai du 25/09 : « slow crane up » → une grue au-dessus du jacuzzi, « gimbal move » → un pied de stabilisateur
    t = normalize_script(_script(7), "tour")
    t.scenes[6].motion_prompt = "Slow crane up above the steaming jacuzzi revealing the peak"
    t.scenes[5].motion_prompt = "slow gimbal move around the stone bathtub, lateral dolly"
    assert motion_prompt(t, 6, "tour").startswith("Slow rising view above the steaming jacuzzi")
    assert "gimbal" not in motion_prompt(t, 5, "tour") and "dolly" not in motion_prompt(t, 5, "tour")
    s = normalize_script(_timelapse(), "timelapse")
    s.scenes[2].motion_prompt = "a small crane lifts the steel beams"  # sur un chantier, la grue est voulue
    assert "a small crane lifts" in motion_prompt(s, 2, "timelapse")


def test_keyframe_order_refuses_a_loop():
    s = _script(4)
    s.scenes[0].edit_prompt, s.scenes[0].edit_from = "x", 2
    s.scenes[2].edit_prompt, s.scenes[2].edit_from = "y", 0
    with pytest.raises(ValueError, match="boucle"):
        keyframe_order(s)


def test_llm_schema_echo_is_unwrapped():
    # Gemini Flash-Lite a renvoyé la forme du schéma remplie au lieu de l'objet (contrôle d'un clip, 25/09)
    from worker.keyframe_qc import KeyframeVerdict
    from worker.providers.llm import _parse

    v = _parse('{"properties": {"ok": false, "problems": ["un passant"]}, "type": "object"}', KeyframeVerdict)
    assert v.ok is False and v.problems == ["un passant"]
    assert _parse('{"ok": true, "problems": []}', KeyframeVerdict).ok
