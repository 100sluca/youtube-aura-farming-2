import json
from types import SimpleNamespace

import pytest

from worker.config import WORKER_ROOT
from worker.providers.video import (
    ComfyVideo,
    WorkflowError,
    first_last_variant,
    frames_for,
    is_image_to_video,
    load_catalog,
    nodes_titled,
    output_node_id,
    patch_workflow,
    text_to_video_fallback,
)

WF_DIR = WORKER_ROOT / "workflows"
WORKFLOWS = sorted(p for p in WF_DIR.glob("*.json") if p.name != "catalog.json")


def _load(name: str) -> dict:
    return json.loads((WF_DIR / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.stem)
def test_workflows_have_conventional_titles_and_valid_links(path):
    wf = json.loads(path.read_text(encoding="utf-8"))
    for title in ("PROMPT", "NEGATIVE", "SEED", "SIZE", "OUTPUT"):
        assert nodes_titled(wf, title), f"{path.name} : nœud {title} manquant"
    for nid, node in wf.items():
        for value in node["inputs"].values():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                assert value[0] in wf, f"{path.name} : le nœud {nid} pointe vers {value[0]} inexistant"


def test_image_to_video_workflows_and_t2v_latent():
    assert is_image_to_video(_load("wan22_i2v_4step")) and is_image_to_video(_load("wan22_i2v_4step_fp8"))
    hq = _load("wan22_i2v_20step")  # qualité maximale : sans LoRA, 20 passes avec CFG (le négatif compte)
    assert is_image_to_video(hq) and not any(n["class_type"] == "LoraLoaderModelOnly" for n in hq.values())
    assert nodes_titled(hq, "SEED")[0]["inputs"]["cfg"] > 1
    t2v = _load("wan22_t2v_4step")
    assert not is_image_to_video(t2v)
    # Latent vidéo (et non EmptyLatentImage × 81 images indépendantes, défaut relevé dans OpenMontage)
    assert nodes_titled(t2v, "SIZE")[0]["class_type"] == "EmptyHunyuanLatentVideo"


def test_patch_workflow_sets_inputs_by_title():
    wf = _load("wan22_i2v_4step")
    out = patch_workflow(wf, prompt="slow dolly in", negative="blurry", seed=42, width=480, height=832, frames=81,
                         image_name="yt2_scene.png", prefix="yt2/scene_00")
    assert nodes_titled(out, "PROMPT")[0]["inputs"]["text"] == "slow dolly in"
    assert nodes_titled(out, "SEED")[0]["inputs"]["noise_seed"] == 42
    assert nodes_titled(out, "SIZE")[0]["inputs"]["length"] == 81
    assert nodes_titled(out, "IMAGE")[0]["inputs"]["image"] == "yt2_scene.png"
    assert out[output_node_id(out)]["inputs"]["filename_prefix"] == "yt2/scene_00"
    assert nodes_titled(wf, "PROMPT")[0]["inputs"]["text"] == ""  # l'original n'est pas modifié
    with pytest.raises(WorkflowError):
        patch_workflow(wf, prompt="x", negative="y", seed=1)  # image → vidéo sans image
    with pytest.raises(WorkflowError):
        patch_workflow(_load("wan22_t2v_4step"), prompt="x", negative="y", seed=1, image_name="a.png")
    flux = patch_workflow(_load("flux1_schnell_gguf"), prompt="x", negative="y", seed=7, width=768, height=1344)
    assert nodes_titled(flux, "SEED")[0]["inputs"]["seed"] == 7
    # Qwen-Image 2.1 : prompt et négatif passent par des nœuds PrimitiveStringMultiline (entrée `value`)
    qwen = patch_workflow(_load("qwen_image_21"), prompt="a hidden door", negative="blurry", seed=3, width=768, height=1344)
    assert nodes_titled(qwen, "PROMPT")[0]["inputs"]["value"] == "a hidden door"
    assert nodes_titled(qwen, "NEGATIVE")[0]["inputs"]["value"] == "blurry"
    assert nodes_titled(qwen, "SIZE")[0]["inputs"]["height"] == 1344


def test_frames_and_fallback():
    assert frames_for(5, 16, 81) == 81
    assert frames_for(8, 16, 81) == 81  # borné : au-delà, le montage ralentit le clip
    assert frames_for(3, 24, 257) == 73
    settings = SimpleNamespace(comfy_workflow_dir=WF_DIR)
    assert text_to_video_fallback(settings, "comfy_wan22_i2v_4step") == "comfy_wan22_t2v_4step"
    assert text_to_video_fallback(settings, "comfy_wan22_i2v_4step_fp8") is None
    assert text_to_video_fallback(settings, "comfy_ltx") is None


def test_minimax_h3_and_qwen_image_2512(tmp_path):
    h3 = _load("minimax_h3_i2v")  # le prompt passe par un PrimitiveStringMultiline relié au nœud MiniMaxH3ImageToVideo
    out = patch_workflow(h3, prompt="slow push-in", negative="", seed=5, width=768, height=1344, frames=124, image_name="a.png")
    assert nodes_titled(out, "PROMPT")[0]["inputs"]["value"] == "slow push-in"
    assert nodes_titled(out, "SIZE")[0]["class_type"] == "MiniMaxH3ImageToVideo"
    assert nodes_titled(out, "SIZE")[0]["inputs"]["length"] == 124
    assert nodes_titled(out, "SEED")[0]["inputs"]["noise_seed"] == 5
    settings = SimpleNamespace(comfy_workflow_dir=WF_DIR, comfy_base_url="http://127.0.0.1:1", comfy_timeout_s=1, video_size=None)
    assert first_last_variant(settings, "comfy_minimax_h3_i2v") == "comfy_minimax_h3_flf2v"
    video = ComfyVideo(settings, "minimax_h3_i2v")  # jamais moins de 124 images : H3 a appris de 124 à 362
    info = video.generate(prompt="p", style_preset=None, duration_s=1.5, out_path=tmp_path / "c.mp4",
                          on_progress=lambda _p: None, dry_run=True)
    assert (video.width, video.height, video.fps) == (480, 832, 24) and round(info.duration_s, 2) == 5.17  # 8 Go
    qwen = patch_workflow(_load("qwen_image_2512"), prompt="x", negative="y", seed=2, width=768, height=1344)
    assert nodes_titled(qwen, "SEED")[0]["inputs"]["steps"] == 8 and nodes_titled(qwen, "PROMPT")[0]["inputs"]["text"] == "x"


def test_minimax_h3_20step_is_the_official_setting():
    # Gabarit ComfyUI « video_minimax_h3_i2v », mode Turbo coupé : modèle sans LoRA, 20 passes, BasicGuider
    for name in ("minimax_h3_i2v_20step", "minimax_h3_flf2v_20step"):
        wf = _load(name)
        assert not any(n["class_type"] == "LoraLoaderModelOnly" for n in wf.values()), name
        assert nodes_titled(wf, "STEPS")[0]["inputs"]["steps"] == 20, name
    settings = SimpleNamespace(comfy_workflow_dir=WF_DIR)
    assert first_last_variant(settings, "comfy_minimax_h3_i2v_20step") == "comfy_minimax_h3_flf2v_20step"


def test_post_workflow_upscales_then_interpolates():
    wf = json.loads((WF_DIR / "post" / "seedvr2_rife.json").read_text(encoding="utf-8"))
    for title in ("VIDEO", "SEED", "FPS", "OUTPUT"):
        assert nodes_titled(wf, title), title
    assert nodes_titled(wf, "INTERP")[0]["inputs"]["images"][0] == "13"  # RIFE travaille sur la sortie de SeedVR2


def test_catalog_points_to_workflows_of_the_right_kind():
    catalog = load_catalog(WF_DIR)
    assert "zimage_turbo" in catalog["image"] and "wan22_i2v_20step" in catalog["video"]
    for name in catalog["image"]:  # une image de storyboard se génère à partir du texte seul
        assert not is_image_to_video(_load(name)), name
    for name in catalog["video"]:  # le storyboard fournit l'image : le modèle vidéo doit l'animer
        assert is_image_to_video(_load(name)), name
    assert catalog["voices"]["fr"] and catalog["voices"]["en"]
