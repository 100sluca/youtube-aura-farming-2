"""Workflows des formats visuels (docs/15) : première + dernière image, retouche, repli image → image, audio."""

import json
from types import SimpleNamespace

import pytest

from worker.config import WORKER_ROOT
from worker.providers.audio import MUSIC_MOODS, load_audio_workflow, patch_audio_workflow, sfx_prompt
from worker.providers.video import (
    WorkflowError,
    first_last_variant,
    is_first_last,
    is_image_to_video,
    nodes_titled,
    patch_workflow,
    quality_variant,
)

WF_DIR = WORKER_ROOT / "workflows"
SETTINGS = SimpleNamespace(comfy_workflow_dir=WF_DIR)


def _load(name: str) -> dict:
    return json.loads((WF_DIR / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["wan22_flf2v_4step", "wan22_flf2v_20step", "wan22_flf2v_hybrid"])
def test_first_last_workflows_take_both_keyframes(name):
    wf = _load(name)
    assert is_image_to_video(wf) and is_first_last(wf)
    size = nodes_titled(wf, "SIZE")[0]
    assert size["class_type"] == "WanFirstLastFrameToVideo"
    assert size["inputs"]["start_image"][0] != size["inputs"]["end_image"][0]
    out = patch_workflow(wf, prompt="time-lapse", negative="n", seed=5, width=480, height=832, frames=81,
                         image_name="debut.png", end_image_name="fin.png")
    assert nodes_titled(out, "IMAGE")[0]["inputs"]["image"] == "debut.png"
    assert nodes_titled(out, "IMAGE_END")[0]["inputs"]["image"] == "fin.png"
    with pytest.raises(WorkflowError):
        patch_workflow(wf, prompt="x", negative="y", seed=1, image_name="debut.png")  # dernière image manquante
    with pytest.raises(WorkflowError):
        patch_workflow(_load("wan22_i2v_4step"), prompt="x", negative="y", seed=1, image_name="a.png", end_image_name="b.png")


@pytest.mark.parametrize("name", ["wan22_i2v_hybrid", "wan22_flf2v_hybrid"])
def test_hybrid_workflows_apply_the_negative_first(name):
    # 2 passes du modèle haut bruit SANS LoRA avec CFG 3,5 (le négatif agit : pas de passants), puis la LoRA en CFG 1
    wf = _load(name)
    samplers = sorted((n for n in wf.values() if isinstance(n, dict) and n.get("class_type") == "KSamplerAdvanced"),
                      key=lambda n: n["inputs"]["start_at_step"])
    assert [(n["inputs"]["start_at_step"], n["inputs"]["end_at_step"], n["inputs"]["cfg"]) for n in samplers] == [
        (0, 2, 3.5), (2, 4, 1.0), (4, 8, 1.0)]
    first_model = wf[samplers[0]["inputs"]["model"][0]]
    assert first_model["class_type"] == "ModelSamplingSD3" and wf[first_model["inputs"]["model"][0]]["class_type"] == "UnetLoaderGGUF"
    out = patch_workflow(wf, prompt="p", negative="person, people", seed=3, image_name="a.png",
                         end_image_name="b.png" if "flf2v" in name else None)
    assert nodes_titled(out, "NEGATIVE")[0]["inputs"]["text"] == "person, people"


def test_recipe_variant_picks_the_hybrid_for_tours():
    assert quality_variant(SETTINGS, "comfy_wan22_i2v_4step", "hybrid") == "comfy_wan22_i2v_hybrid"
    assert first_last_variant(SETTINGS, "comfy_wan22_i2v_hybrid") == "comfy_wan22_flf2v_hybrid"  # passages aussi
    assert quality_variant(SETTINGS, "comfy_wan22_i2v_20step", "hybrid") is None  # 20 passes : le négatif agit déjà
    assert quality_variant(SETTINGS, "comfy_wan22_i2v_4step", None) is None
    assert quality_variant(SETTINGS, "comfy_wan22_i2v_4step", "inconnu") is None


def test_first_last_variant_keeps_the_quality_level():
    assert first_last_variant(SETTINGS, "comfy_wan22_i2v_4step") == "comfy_wan22_flf2v_4step"
    assert first_last_variant(SETTINGS, "comfy_wan22_i2v_20step") == "comfy_wan22_flf2v_20step"
    assert first_last_variant(SETTINGS, "comfy_wan22_5b_i2v") is None  # pas de première + dernière image en 5B
    assert first_last_variant(SETTINGS, "comfy_ltx") is None


@pytest.mark.parametrize("name", ["qwen_image_edit_2511", "qwen_image_edit_2511_4step", "zimage_img2img"])
def test_edit_workflows_keep_the_9_16_frame(name):
    wf = _load(name)
    assert is_image_to_video(wf) and not is_first_last(wf)  # une image d'entrée, pas de dernière image
    out = patch_workflow(wf, prompt="Remove the vegetation.", negative="blurry", seed=9, width=768, height=1344,
                         image_name="etape_1.png")
    size = nodes_titled(out, "SIZE")[0]
    assert size["class_type"] == "ImageScale" and (size["inputs"]["width"], size["inputs"]["height"]) == (768, 1344)
    assert size["inputs"]["crop"] == "center"
    prompt, negative = nodes_titled(out, "PROMPT")[0]["inputs"], nodes_titled(out, "NEGATIVE")[0]["inputs"]
    key = "prompt" if "prompt" in prompt else "text"  # TextEncodeQwenImageEditPlus : entrée « prompt »
    assert prompt[key] == "Remove the vegetation." and negative[key] == "blurry"
    assert nodes_titled(out, "SEED")[0]["inputs"]["seed"] == 9


def test_edit_quality_levels_and_img2img_strength():
    hq, fast = _load("qwen_image_edit_2511"), _load("qwen_image_edit_2511_4step")
    assert nodes_titled(hq, "SEED")[0]["inputs"]["steps"] == 40 and nodes_titled(hq, "SEED")[0]["inputs"]["cfg"] > 1
    assert nodes_titled(fast, "SEED")[0]["inputs"]["steps"] == 4 and nodes_titled(fast, "LORA")
    assert 0.5 < nodes_titled(_load("zimage_img2img"), "SEED")[0]["inputs"]["denoise"] < 0.9  # garde le cadre


def test_audio_workflows_patch_prompt_duration_and_seed():
    music = patch_audio_workflow(load_audio_workflow(SETTINGS, "ace_step_15_music"), prompt=MUSIC_MOODS["luxury"].tags,
                                 seed=42, seconds=75, bpm=118, key="A minor", prefix="yt2/music_luxury")
    enc = nodes_titled(music, "PROMPT")[0]["inputs"]
    assert enc["tags"].startswith("Luxury real estate") and enc["duration"] == 75.0 and enc["bpm"] == 118
    assert enc["keyscale"] == "A minor" and enc["seed"] == 42 and enc["lyrics"] == "[Instrumental]"
    assert nodes_titled(music, "SIZE")[0]["inputs"]["seconds"] == 75.0
    assert nodes_titled(music, "OUTPUT")[0]["inputs"]["filename_prefix"] == "yt2/music_luxury"
    sfx = patch_audio_workflow(load_audio_workflow(SETTINGS, "stable_audio_3_sfx"), prompt=sfx_prompt("hammering nails.", 11.6),
                               negative="", seed=7, seconds=12)
    assert nodes_titled(sfx, "PROMPT")[0]["inputs"]["text"] == "hammering nails. Length: 12 seconds"
    assert nodes_titled(sfx, "MODEL")[0]["inputs"]["ckpt_name"] == "stable_audio_3_small_sfx.safetensors"
    assert nodes_titled(sfx, "SIZE")[0]["inputs"]["seconds"] == 12.0 and nodes_titled(sfx, "SEED")[0]["inputs"]["seed"] == 7
    for wf in (music, sfx):  # liens valides
        for nid, node in wf.items():
            for value in node["inputs"].values():
                if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                    assert value[0] in wf, f"le nœud {nid} pointe vers {value[0]} inexistant"
