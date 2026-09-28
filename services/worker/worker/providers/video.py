"""Génération image et vidéo par ComfyUI (local) ou un fournisseur cloud. Sorties 9:16.

Client ComfyUI inspiré de celui d'OpenMontage (tools/_comfyui/client.py, AGPL-3.0, réécrit ici) :
POST /prompt (erreurs de nœuds remontées), GET /history/{id}, GET /view, POST /upload/image.

Les workflows (services/worker/workflows/<nom>.json, format API) sont repérés par le titre de leurs
nœuds (`_meta.title`) : PROMPT, NEGATIVE, SIZE (width / height / length), SEED (seed ou noise_seed),
IMAGE (LoadImage, image → vidéo ou retouche), IMAGE_END (LoadImage, dernière image d'un clip première +
dernière image) et OUTPUT (nœud de sortie). Voir workflows/README.md.
"""

from __future__ import annotations

import copy
import json
import random
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx

from .. import cancel
from ..config import Settings
from ..system import ensure_comfy


@dataclass
class ClipInfo:
    duration_s: float
    width: int
    height: int
    seed: int | None = None


class VideoProvider(Protocol):
    name: str
    image_to_video: bool

    def generate(
        self,
        *,
        prompt: str,
        style_preset: str | None,
        duration_s: float,
        out_path: Path,
        on_progress: Callable[[int], None],
        dry_run: bool = False,
        image_path: Path | None = None,
        end_image_path: Path | None = None,
    ) -> ClipInfo: ...


STYLE_PRESETS: dict[str, str] = {
    # Chantiers en accéléré : photo d'architecture réaliste, point de vue fixe. Pas de « construction photography » :
    # l'image générée est celle du bâtiment FINI (le chantier se fait à rebours, docs/15 §10), le style ajoutait des
    # échafaudages et des engins
    "timelapse_site": "photorealistic architectural photography, static wide shot, 24mm lens, natural daylight, high "
                      "detail, realistic materials and scale, sharp focus, deep depth of field",
    # Visites de luxe : photographie immobilière haut de gamme
    "luxury_realestate": "photorealistic luxury real estate photography, wide angle 20mm, eye level, bright natural "
                         "light, high dynamic range, architectural digest style, crisp details, warm elegant palette",
    # Maisons de rêve
    "modern_minimal": "photorealistic, architectural photography, soft daylight, clean lines, 35mm, shallow depth of field",
    "warm_wood": "photorealistic, warm oak textures, golden hour light through windows, cozy, cinematic",
    "night_led": "photorealistic, night interior, diffused LED strips, moody, high contrast, cinematic",
    # Animaux étranges : documentaire animalier
    "wildlife_doc": "wildlife documentary photography, telephoto lens, natural light, shallow depth of field, "
                    "ultra detailed skin and fur textures, BBC Earth style, cinematic color grade",
    # Histoires vraies : reconstitution cinématographique
    "history_cinematic": "cinematic historical reconstruction, film still, anamorphic lens, volumetric light, "
                         "muted color grade, period-accurate props and materials, dramatic composition",
    # Minecraft : rendu du jeu avec shaders
    "minecraft": "Minecraft game render, blocky voxel world, cube characters, 16x16 pixel textures, "
                 "soft global illumination shaders, cinematic camera, vivid colors",
    # Drames (worker/drama.py, docs/35) : film d'animation, fruits, humains ou animaux (essai du 28/09, docs/31 §8)
    "pixar_fruit": "3D animated feature film still in the style of Pixar and Illumination. Stylized anthropomorphic fruit "
                   "characters: a realistic fruit forms the whole head, with big expressive cartoon eyes, eyebrows and a "
                   "mouth on the fruit skin, on a human body wearing clothes, with human hands. Detailed fruit skin with "
                   "subsurface scattering, cinematic lighting, rich saturated colors, soft depth of field, highly detailed",
    "pixar_human": "3D animated feature film still in the style of Pixar and Disney. Stylized characters with big "
                   "expressive eyes, soft skin shading, detailed hair and fabrics, cinematic lighting, rich colors, soft "
                   "depth of field, highly detailed",
    "dreamworks_animal": "3D animated feature film still in the style of DreamWorks (The Bad Guys, Zootopia). "
                         "Anthropomorphic animal characters standing and wearing clothes, expressive faces, detailed fur, "
                         "cinematic golden-hour lighting, rich colors, highly detailed",
    # Clip d'un drame : l'image de départ porte déjà le style, le prompt du clip dit le film (drama.clip_prompt)
    "animation_motion": "smooth expressive character animation, cinematic lighting",
}
# Styles de film d'animation : le négatif commun (« cartoon », « people faces ») les contredirait
ANIMATED_STYLES = frozenset({"pixar_fruit", "pixar_human", "dreamworks_animal", "animation_motion"})
ANIMATED_NEGATIVE = (
    "photo, photorealistic, live action, text, watermark, logo, subtitles, blurry, low quality, JPEG artifacts, "
    "deformed hands, extra fingers, extra limbs, cluttered background"
)
NEGATIVE = (
    "text, watermark, logo, subtitles, blurry, low quality, JPEG artifacts, deformed, cartoon, painting, "
    "static frame, still image, people faces, extra fingers, cluttered background"
)
# Négatif officiel des modèles Wan (celui de leur script generate.py et des gabarits ComfyUI) : le modèle a été
# entraîné avec, il pèse plus qu'une liste anglaise. Traduction : couleurs criardes, surexposé, statique, détails
# flous, sous-titres, style, œuvre, peinture, image figée, terne, pire qualité, basse qualité, artefacts JPEG,
# laid, incomplet, doigts en trop, mains et visages mal dessinés, difforme, membres déformés, doigts fusionnés,
# image immobile, fond encombré, trois jambes, foule en fond, marche à reculons.
WAN_NEGATIVE = (
    "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，"
    "丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，"
    "杂乱的背景，三条腿，背景人很多，倒着走, text, watermark, logo, subtitles"
)


def negative_for(workflow: str) -> str:
    return WAN_NEGATIVE if "wan" in workflow.lower() else NEGATIVE


def styled(prompt: str, style_preset: str | None) -> str:
    return f"{prompt}, {STYLE_PRESETS.get(style_preset or '', STYLE_PRESETS['modern_minimal'])}"


# ---------------------------------------------------------------------------
# Workflows : chargement et remplacement des entrées par titre de nœud
# ---------------------------------------------------------------------------


class WorkflowError(RuntimeError):
    pass


def workflow_path(workflow_dir: Path, name: str) -> Path:
    for p in (workflow_dir / f"{name}.json", workflow_dir / f"{name}_t2v.json"):
        if p.exists():
            return p
    raise WorkflowError(f"workflow {name!r} introuvable dans {workflow_dir} (voir workflows/README.md)")


def load_catalog(workflow_dir: Path) -> dict[str, Any]:
    """Modèles proposés dans Réglages → Modèles de génération (workflows/catalog.json) : image, vidéo, voix."""
    p = workflow_dir / "catalog.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"image": {}, "video": {}, "voices": {}}


def nodes_titled(wf: dict[str, Any], title: str) -> list[dict[str, Any]]:
    return [n for n in wf.values() if isinstance(n, dict) and n.get("_meta", {}).get("title") == title]


def is_image_to_video(wf: dict[str, Any]) -> bool:
    return bool(nodes_titled(wf, "IMAGE"))


def is_first_last(wf: dict[str, Any]) -> bool:
    """Workflow « première + dernière image » (nœud IMAGE_END) : le clip finit exactement sur une image donnée."""
    return bool(nodes_titled(wf, "IMAGE_END"))


def output_node_id(wf: dict[str, Any]) -> str | None:
    for nid, n in wf.items():
        if isinstance(n, dict) and n.get("_meta", {}).get("title") == "OUTPUT":
            return nid
    return None


def _text_input(node: dict[str, Any], *keys: str) -> str:
    """Nom de l'entrée texte d'un nœud : `text` (CLIPTextEncode), `value` (PrimitiveString), `prompt`…"""
    return next((k for k in keys if k in node["inputs"]), keys[0])


def patch_workflow(
    wf: dict[str, Any],
    *,
    prompt: str,
    negative: str,
    seed: int,
    width: int | None = None,
    height: int | None = None,
    frames: int | None = None,
    image_name: str | None = None,
    prefix: str | None = None,
    end_image_name: str | None = None,
) -> dict[str, Any]:
    """Copie du workflow avec les entrées remplacées. Erreur claire si un titre obligatoire manque."""
    w = copy.deepcopy(wf)
    for title in ("PROMPT", "SEED"):
        if not nodes_titled(w, title):
            raise WorkflowError(f"le workflow n'a pas de nœud titré {title}")
    for n in nodes_titled(w, "PROMPT"):
        n["inputs"][_text_input(n, "text", "value", "prompt")] = prompt
    for n in nodes_titled(w, "NEGATIVE"):
        n["inputs"][_text_input(n, "text", "value", "negative_prompt", "prompt")] = negative
    for n in nodes_titled(w, "SEED"):
        key = "noise_seed" if "noise_seed" in n["inputs"] else "seed"
        n["inputs"][key] = seed
    for n in nodes_titled(w, "SIZE"):
        inp = n["inputs"]
        if width:
            inp["width"] = width
        if height:
            inp["height"] = height
        if frames and "length" in inp:
            inp["length"] = frames
    if image_name is not None:
        nodes = nodes_titled(w, "IMAGE")
        if not nodes:
            raise WorkflowError("image fournie mais le workflow n'a pas de nœud titré IMAGE")
        for n in nodes:
            n["inputs"]["image"] = image_name
    elif is_image_to_video(w):
        raise WorkflowError("workflow image → vidéo : une image de storyboard est requise")
    if end_image_name is not None:
        nodes = nodes_titled(w, "IMAGE_END")
        if not nodes:
            raise WorkflowError("dernière image fournie mais le workflow n'a pas de nœud titré IMAGE_END")
        for n in nodes:
            n["inputs"]["image"] = end_image_name
    elif is_first_last(w):
        raise WorkflowError("workflow première + dernière image : la dernière image (IMAGE_END) est requise")
    if prefix:
        for n in nodes_titled(w, "OUTPUT"):
            if "filename_prefix" in n["inputs"]:
                n["inputs"]["filename_prefix"] = prefix
    return w


def supports_references(wf: dict[str, Any]) -> bool:
    """Le workflow d'image accepte-t-il des images de référence ? (Qwen-Image 2.1 : son encodeur TextEncodeQwenImage21
    prend jusqu'à 10 images, citées <image1>… dans le prompt ; gabarit officiel « image edit » de ComfyUI)"""
    return any(isinstance(n, dict) and n.get("class_type") == "TextEncodeQwenImage21" for n in wf.values())


def add_references(wf: dict[str, Any], image_names: list[str], resolution: int = 768) -> dict[str, Any]:
    """Branche des images de référence (déjà envoyées à ComfyUI) sur l'encodeur de Qwen-Image 2.1 : un LoadImage par
    image, entrées images.image_1… et le VAE (les références sont collées dans la séquence en latents). `resolution` :
    taille à laquelle l'encodeur réduit chaque référence (768 : fiches en 9:16, mesuré le 28/09 : + 10 à 60 s par image)."""
    enc = next((n for n in wf.values() if isinstance(n, dict) and n.get("class_type") == "TextEncodeQwenImage21"), None)
    if enc is None:
        raise WorkflowError("ce workflow d'image n'accepte pas d'images de référence (TextEncodeQwenImage21 absent)")
    vae = next((nid for nid, n in wf.items() if isinstance(n, dict) and n.get("class_type") == "VAELoader"), None)
    if vae is None:
        raise WorkflowError("workflow sans VAELoader : les références ne peuvent pas être encodées")
    enc["inputs"]["vae"] = [vae, 0]
    enc["inputs"]["resolution"] = resolution
    base = max((int(k) for k in wf if str(k).isdigit()), default=0) + 100
    for k, name in enumerate(image_names, 1):
        nid = str(base + k)
        wf[nid] = {"class_type": "LoadImage", "inputs": {"image": name}, "_meta": {"title": f"REF{k}"}}
        enc["inputs"][f"images.image_{k}"] = [nid, 0]
    return wf


def frames_for(duration_s: float, fps: int, max_frames: int) -> int:
    """Nombre d'images valide pour Wan / LTX (8k + 1), borné par ce que le modèle sait produire."""
    return min(max_frames, max(17, int(duration_s * fps) // 8 * 8 + 1))


# ---------------------------------------------------------------------------
# Client ComfyUI
# ---------------------------------------------------------------------------


class ComfyClient:
    def __init__(self, base_url: str, timeout_s: int = 3600) -> None:
        self.base = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.client_id = uuid.uuid4().hex

    def submit(self, workflow: dict[str, Any]) -> str:
        ensure_comfy(self.base)  # tombé (mémoire saturée) : relancé ici plutôt qu'un échec du job (docs/28)
        r = httpx.post(f"{self.base}/prompt", json={"prompt": workflow, "client_id": self.client_id}, timeout=30)
        try:
            data = r.json()
        except ValueError:
            data = {}
        if data.get("node_errors"):
            raise WorkflowError(f"ComfyUI refuse le workflow : {json.dumps(data['node_errors'], ensure_ascii=False)[:1500]}")
        if data.get("error"):
            raise WorkflowError(f"ComfyUI : {json.dumps(data['error'], ensure_ascii=False)[:1500]}")
        r.raise_for_status()
        return data["prompt_id"]

    def wait(self, prompt_id: str, on_progress: Callable[[int], None]) -> dict[str, Any]:
        deadline = time.time() + self.timeout_s
        while time.time() < deadline:
            if cancel.cancelled():  # arrêt demandé depuis le dashboard : libérer la carte graphique tout de suite
                self.cancel(prompt_id)
                raise cancel.JobCancelled(f"ComfyUI : prompt {prompt_id} annulé (tâche arrêtée depuis le dashboard)")
            try:
                h = httpx.get(f"{self.base}/history/{prompt_id}", timeout=30).json().get(prompt_id)
                if not h:
                    q = httpx.get(f"{self.base}/queue", timeout=30).json()
            except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError) as exc:
                # ComfyUI mort pendant le calcul (le 28/09 : RAM épuisée au chargement de MiniMax H3) : le prompt est
                # perdu ; on relance ComfyUI tout de suite pour que la reprise automatique du job le trouve debout
                ensure_comfy(self.base)
                raise RuntimeError("ComfyUI s'est arrêté pendant le calcul (mémoire saturée ?) : relancé, la tâche "
                                   "sera reprise") from exc
            if h:
                status = h.get("status", {})
                if status.get("status_str") == "error":
                    raise RuntimeError(f"ComfyUI : exécution en erreur : {status.get('messages')}")
                return h
            on_progress(50 if any(prompt_id in str(x) for x in q.get("queue_running", [])) else 10)
            time.sleep(5)
        raise TimeoutError(f"ComfyUI : délai dépassé ({self.timeout_s} s), prompt {prompt_id} toujours en cours")

    def download_output(self, entry: dict[str, Any], node_id: str | None, dest: Path) -> Path:
        outputs = entry.get("outputs", {})
        candidates = [outputs[node_id]] if node_id and node_id in outputs else list(outputs.values())
        for out in candidates:
            items = out.get("images") or out.get("gifs") or out.get("videos") or out.get("video") or out.get("audio") or []
            if items:
                f = items[0]
                r = httpx.get(
                    f"{self.base}/view",
                    params={"filename": f["filename"], "subfolder": f.get("subfolder", ""), "type": f.get("type", "output")},
                    timeout=300,
                )
                r.raise_for_status()
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(r.content)
                return dest
        raise RuntimeError(f"ComfyUI : aucune sortie trouvée (nœuds : {list(outputs)})")

    def cancel(self, prompt_id: str) -> None:
        """Annule un prompt, en cours ou en file, sans toucher aux autres (ComfyUI ≥ 0.37 : /api/jobs/<id>/cancel ;
        avant : /interrupt ciblé puis retrait de la file)."""
        try:
            r = httpx.post(f"{self.base}/api/jobs/{prompt_id}/cancel", timeout=30)
            if r.status_code != 404:
                return
            httpx.post(f"{self.base}/interrupt", json={"prompt_id": prompt_id}, timeout=30)
            httpx.post(f"{self.base}/queue", json={"delete": [prompt_id]}, timeout=30)
        except httpx.HTTPError:
            pass

    def free(self) -> None:
        """Décharge les modèles que ComfyUI garde en cache (RAM et VRAM). Utile avant un modèle lourd : Qwen-Image-Edit
        et son encodeur (≈ 24 Go) débordent sur le disque s'ils cohabitent avec Z-Image ou Wan (13 min par image
        au lieu de quelques minutes, mesuré le 25/09). Effet immédiat si la file est vide : on laisse 2 s au worker
        de ComfyUI pour vider la mémoire avant la tâche suivante."""
        try:
            httpx.post(f"{self.base}/free", json={"unload_models": True, "free_memory": True}, timeout=30)
            time.sleep(2)
        except httpx.HTTPError:
            pass

    def upload_image(self, path: Path) -> str:
        ensure_comfy(self.base)
        with path.open("rb") as fh:
            r = httpx.post(
                f"{self.base}/upload/image",
                files={"image": (f"yt2_{uuid.uuid4().hex[:8]}_{path.name}", fh, "image/png")},
                data={"overwrite": "true"},
                timeout=60,
            )
        r.raise_for_status()
        data = r.json()
        return f"{data['subfolder']}/{data['name']}" if data.get("subfolder") else data["name"]


# ---------------------------------------------------------------------------
# Fournisseurs
# ---------------------------------------------------------------------------


class ComfyVideo:
    """Vidéo par ComfyUI. Le workflow décide : nœud IMAGE présent = image → vidéo (storyboard requis)."""

    def __init__(self, settings: Settings, workflow: str) -> None:
        self.name = f"comfy_{workflow}"
        self.wf = json.loads(workflow_path(settings.comfy_workflow_dir, workflow).read_text(encoding="utf-8"))
        self.client = ComfyClient(settings.comfy_base_url, settings.comfy_timeout_s)
        self.image_to_video = is_image_to_video(self.wf)
        self.first_last = is_first_last(self.wf)
        # Résolutions natives 9:16 par famille (docs/08-benchmark-video.md) ; le workflow JSON reste maître.
        if "ltx" in workflow:
            self.width, self.height, self.fps, self.max_frames = 576, 1024, 24, 257
        elif "minimax_h3" in workflow:  # MiniMax H3 : 24 i/s, 124 images (5,2 s), voir generate ; 768 × 1344 natif, mais
            # sur 8 Go les retours donnent 480 × 832 (≈ 10 min par clip), 768 × 1344 à partir de 12 Go (VIDEO_SIZE pour forcer)
            self.width, self.height, self.fps, self.max_frames = 480, 832, 24, 124
        elif "5b" in workflow:  # Wan 2.2 TI2V-5B : 24 i/s
            self.width, self.height, self.fps, self.max_frames = 480, 832, 24, 121
        else:  # Wan 2.1 / 2.2 14B : 16 i/s, 81 images (5 s) au plus pour rester dans l'entraînement du modèle
            self.width, self.height, self.fps, self.max_frames = 480, 832, 16, 81
        if settings.video_size:  # VIDEO_SIZE=704x1280 : résolution forcée (voir config.py)
            w, h = settings.video_size.lower().replace("×", "x").split("x")
            self.width, self.height = int(w), int(h)
        self.negative = negative_for(workflow)

    def generate(self, *, prompt, style_preset, duration_s, out_path, on_progress, dry_run=False, image_path=None,  # noqa: ANN001
                 end_image_path=None) -> ClipInfo:
        seed = random.randint(0, 2**31)
        # Première + dernière image : toujours la longueur complète (le clip doit atteindre l'image finale,
        # le montage l'accélère au besoin, docs/15)
        frames = self.max_frames if self.first_last else frames_for(duration_s, self.fps, self.max_frames)
        if "minimax_h3" in self.name:  # H3 a appris de 124 à 362 images (grille 17k + 5) : jamais moins, le montage coupe
            frames = self.max_frames
        if dry_run:
            out_path.write_bytes(b"")
            return ClipInfo(frames / self.fps, self.width, self.height, seed)
        image_name = self.client.upload_image(image_path) if (self.image_to_video and image_path) else None
        end_name = self.client.upload_image(end_image_path) if (self.first_last and end_image_path) else None
        wf = patch_workflow(
            self.wf, prompt=styled(prompt, style_preset), negative=self.negative, seed=seed, width=self.width,
            height=self.height, frames=frames, image_name=image_name, prefix=f"yt2/{out_path.stem}",
            end_image_name=end_name,
        )
        entry = self.client.wait(self.client.submit(wf), on_progress)
        self.client.download_output(entry, output_node_id(wf), out_path)
        on_progress(100)
        return ClipInfo(frames / self.fps, self.width, self.height, seed)


class ComfyImage:
    """Image fixe 9:16 pour le storyboard (Flux schnell GGUF par défaut)."""

    def __init__(self, settings: Settings, workflow: str | None = None) -> None:
        name = workflow or settings.comfy_image_workflow
        self.name = f"comfy_{name}"
        self.wf = json.loads(workflow_path(settings.comfy_workflow_dir, name).read_text(encoding="utf-8"))
        self.client = ComfyClient(settings.comfy_base_url, settings.comfy_timeout_s)
        self.width, self.height = 768, 1344
        self.negative = negative_for(name)
        self.references = supports_references(self.wf)  # fiches des personnages d'un drame en références (docs/35)

    def generate(self, *, prompt: str, style_preset: str | None, out_path: Path, seed: int, dry_run: bool = False,
                 refs: list[Path] | None = None) -> Path:
        """`refs` : images de référence (fiches des personnages), citées <image1>… dans le prompt ; ignorées par un
        workflow qui n'en accepte pas (l'appelant décrit alors les personnages dans le prompt, self.references)."""
        if dry_run:
            out_path.write_bytes(b"")
            return out_path
        negative = ANIMATED_NEGATIVE if style_preset in ANIMATED_STYLES else self.negative
        wf = patch_workflow(
            self.wf, prompt=styled(prompt, style_preset), negative=negative, seed=seed,
            width=self.width, height=self.height, prefix=f"yt2/{out_path.stem}",
        )
        if refs and self.references:
            add_references(wf, [self.client.upload_image(p) for p in refs])
        entry = self.client.wait(self.client.submit(wf), lambda _p: None)
        return self.client.download_output(entry, output_node_id(wf), out_path)


class ComfyImageEdit:
    """Retouche d'une image clé (formats visuels, docs/15) : l'image de l'étape précédente + une instruction →
    l'étape suivante, même cadre. Qwen-Image-Edit-2511 (COMFY_EDIT_WORKFLOW) ; si ComfyUI refuse le workflow
    (modèle absent), repli sur COMFY_EDIT_FALLBACK : Z-Image en image → image, qui reçoit la description de
    l'étape plutôt que l'instruction (un modèle texte → image ne comprend pas « enlève la végétation »)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = ComfyClient(settings.comfy_base_url, settings.comfy_timeout_s)
        self.width, self.height = 768, 1344
        self.name = f"comfy_{settings.comfy_edit_workflow}"
        self.fallback_reason: str | None = None  # renseigné quand le repli a servi (à journaliser par l'appelant)
        self._freed = False

    def _load(self, name: str) -> dict[str, Any]:
        return json.loads(workflow_path(self.settings.comfy_workflow_dir, name).read_text(encoding="utf-8"))

    def edit(self, *, image_path: Path, instruction: str, description: str, style_preset: str | None, out_path: Path,
             seed: int, dry_run: bool = False) -> Path:
        if dry_run:
            out_path.write_bytes(b"")
            return out_path
        if not self._freed:  # la première retouche part d'une mémoire vide (le modèle d'image reste sinon en cache)
            self.client.free()
            self._freed = True
        name = self.client.upload_image(image_path)
        try:
            wf = patch_workflow(self._load(self.settings.comfy_edit_workflow), prompt=instruction, negative="", seed=seed,
                                width=self.width, height=self.height, image_name=name, prefix=f"yt2/{out_path.stem}")
            entry = self.client.wait(self.client.submit(wf), lambda _p: None)
        except WorkflowError as exc:
            fb = self.settings.comfy_edit_fallback
            if not fb or fb == self.settings.comfy_edit_workflow:
                raise
            self.fallback_reason, self.name = str(exc)[:300], f"comfy_{fb}"
            wf = patch_workflow(self._load(fb), prompt=styled(description, style_preset), negative=negative_for(fb), seed=seed,
                                width=self.width, height=self.height, image_name=name, prefix=f"yt2/{out_path.stem}")
            entry = self.client.wait(self.client.submit(wf), lambda _p: None)
        return self.client.download_output(entry, output_node_id(wf), out_path)


class CloudVideo:
    """Squelette pour un fournisseur cloud (Higgsfield, fal.ai…) : à implémenter en phase 3."""

    image_to_video = False
    first_last = False

    def __init__(self, settings: Settings, name: str) -> None:
        self.name = name

    def generate(self, *, prompt, style_preset, duration_s, out_path, on_progress, dry_run=False, image_path=None,  # noqa: ANN001
                 end_image_path=None) -> ClipInfo:
        if dry_run:
            out_path.write_bytes(b"")
            return ClipInfo(duration_s, 1080, 1920)
        raise NotImplementedError(f"fournisseur {self.name} non implémenté")


def get_video_provider(settings: Settings, override: str | None = None, db: Any | None = None) -> VideoProvider:
    name = override or settings.video_provider
    if name.startswith("comfy_"):
        return ComfyVideo(settings, name.removeprefix("comfy_"))
    if name == "gemini_web":  # appli Gemini pilotée dans Chrome, bouton Gemini de Création (docs/17)
        from .gemini_web import GeminiWebVideo

        return GeminiWebVideo(settings, db)
    return CloudVideo(settings, name)


def quality_variant(settings: Settings, provider_name: str, variant: str | None) -> str | None:
    """Variante du modèle 4 passes demandée par une recette, ex. comfy_wan22_i2v_4step → comfy_wan22_i2v_hybrid (2 passes
    avec CFG 3,5 où le négatif agit, puis la LoRA : visites sans passants, docs/15 §10) ; None si la production n'est pas
    en 4 passes (20 passes : le négatif agit déjà) ou si le workflow manque."""
    if not variant or "4step" not in provider_name:
        return None
    alt = provider_name.replace("4step", variant)
    try:
        workflow_path(settings.comfy_workflow_dir, alt.removeprefix("comfy_"))
        return alt
    except WorkflowError:
        return None


def first_last_variant(settings: Settings, provider_name: str) -> str | None:
    """Variante « première + dernière image » du modèle vidéo de la production (même qualité : 4 ou 20 passes),
    ex. comfy_wan22_i2v_4step → comfy_wan22_flf2v_4step ; None si elle n'existe pas."""
    if "i2v" not in provider_name:
        return None
    alt = provider_name.replace("i2v", "flf2v")
    try:
        workflow_path(settings.comfy_workflow_dir, alt.removeprefix("comfy_"))
        return alt
    except WorkflowError:
        return None


def text_to_video_fallback(settings: Settings, provider_name: str) -> str | None:
    """Pour une scène sans image validée : la variante texte → vidéo du même modèle, si elle existe."""
    if "i2v" not in provider_name:
        return None
    alt = provider_name.replace("i2v", "t2v")
    try:
        workflow_path(settings.comfy_workflow_dir, alt.removeprefix("comfy_"))
        return alt
    except WorkflowError:
        return None
