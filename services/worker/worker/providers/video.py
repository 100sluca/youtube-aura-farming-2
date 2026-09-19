"""Génération vidéo : ComfyUI local (LTX-Video / Wan) ou fournisseur cloud. Sortie : mp4 9:16."""

from __future__ import annotations

import json
import random
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

from ..config import Settings


@dataclass
class ClipInfo:
    duration_s: float
    width: int
    height: int
    seed: int | None = None


class VideoProvider(Protocol):
    name: str

    def generate(
        self,
        *,
        prompt: str,
        style_preset: str | None,
        duration_s: float,
        out_path: Path,
        on_progress: Callable[[int], None],
        dry_run: bool = False,
    ) -> ClipInfo: ...


STYLE_PRESETS: dict[str, str] = {
    "modern_minimal": "photorealistic, architectural photography, soft daylight, clean lines, 35mm, shallow depth of field",
    "warm_wood": "photorealistic, warm oak textures, golden hour light through windows, cozy, cinematic",
    "night_led": "photorealistic, night interior, diffused LED strips, moody, high contrast, cinematic",
}
NEGATIVE = "text, watermark, logo, blurry, low quality, deformed, cartoon, people faces"


class ComfyVideo:
    """Pilote ComfyUI par son API HTTP : POST /prompt, GET /history/{id}, GET /view."""

    def __init__(self, settings: Settings, workflow: str) -> None:
        self.name = f"comfy_{workflow}"
        self.base = settings.comfy_base_url
        self.workflow_path = settings.comfy_workflow_dir / f"{workflow}_t2v.json"
        self.width, self.height, self.fps = (576, 1024, 24) if workflow == "ltx" else (480, 832, 16)

    def generate(self, *, prompt, style_preset, duration_s, out_path, on_progress, dry_run=False) -> ClipInfo:  # noqa: ANN001
        seed = random.randint(0, 2**31)
        if dry_run:
            out_path.write_bytes(b"")
            return ClipInfo(duration_s, self.width, self.height, seed)
        wf = json.loads(self.workflow_path.read_text(encoding="utf-8"))
        full_prompt = f"{prompt}, {STYLE_PRESETS.get(style_preset or '', STYLE_PRESETS['modern_minimal'])}"
        frames = int(duration_s * self.fps) // 8 * 8 + 1  # LTX/Wan : 8k+1 frames
        # Les nœuds du workflow portent un `_meta.title` conventionnel : PROMPT, NEGATIVE, SIZE, SEED
        for node in wf.values():
            title = node.get("_meta", {}).get("title", "")
            if title == "PROMPT":
                node["inputs"]["text"] = full_prompt
            elif title == "NEGATIVE":
                node["inputs"]["text"] = NEGATIVE
            elif title == "SIZE":
                node["inputs"].update(width=self.width, height=self.height, length=frames)
            elif title == "SEED":
                node["inputs"]["seed"] = seed
        client_id = uuid.uuid4().hex
        r = httpx.post(f"{self.base}/prompt", json={"prompt": wf, "client_id": client_id}, timeout=30)
        r.raise_for_status()
        pid = r.json()["prompt_id"]
        deadline = time.time() + 30 * 60
        while time.time() < deadline:
            h = httpx.get(f"{self.base}/history/{pid}", timeout=30).json().get(pid)
            if h:
                if h.get("status", {}).get("status_str") == "error":
                    raise RuntimeError(f"ComfyUI : {h['status']}")
                outputs = next(o for o in h["outputs"].values() if "gifs" in o or "videos" in o)
                f = (outputs.get("gifs") or outputs.get("videos"))[0]
                data = httpx.get(
                    f"{self.base}/view",
                    params={"filename": f["filename"], "subfolder": f.get("subfolder", ""), "type": f.get("type", "output")},
                    timeout=120,
                )
                out_path.write_bytes(data.content)
                on_progress(100)
                return ClipInfo(frames / self.fps, self.width, self.height, seed)
            q = httpx.get(f"{self.base}/queue", timeout=30).json()
            on_progress(50 if any(pid in str(x) for x in q.get("queue_running", [])) else 10)
            time.sleep(5)
        raise TimeoutError("ComfyUI : délai dépassé (30 min)")


class CloudVideo:
    """Squelette pour un fournisseur cloud (Higgsfield, fal.ai…) : à implémenter en phase 3."""

    def __init__(self, settings: Settings, name: str) -> None:
        self.name = name

    def generate(self, *, prompt, style_preset, duration_s, out_path, on_progress, dry_run=False) -> ClipInfo:  # noqa: ANN001
        if dry_run:
            out_path.write_bytes(b"")
            return ClipInfo(duration_s, 1080, 1920)
        raise NotImplementedError(f"fournisseur {self.name} non implémenté")


def get_video_provider(settings: Settings, override: str | None = None) -> VideoProvider:
    name = override or settings.video_provider
    if name.startswith("comfy_"):
        return ComfyVideo(settings, name.removeprefix("comfy_"))
    return CloudVideo(settings, name)
