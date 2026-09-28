"""TTS : plusieurs moteurs de voix, choisis par langue dans Réglages → Modèles de génération (docs/18-voix.md).

Une voix se note « moteur:voix » (« kokoro:ff_siwis ») ; un nom seul reste une voix Kokoro (réglages d'avant le 25/09).
Deux sortes de moteurs :
- Kokoro 82M (ONNX, CPU) tourne dans le processus du worker ;
- les autres sont des modèles PyTorch installés chacun dans son environnement Python (<YT2_HOME>/tts/<moteur>/venv,
  scripts/install_tts.ps1) et lancés en sous-processus avec leur script tts_runners/<moteur>.py : le modèle est chargé
  une fois pour toutes les scènes d'une vidéo, puis toute sa mémoire est rendue à la fin du sous-processus. Avant un
  moteur sur GPU, on vide ComfyUI (les deux ne tiennent pas ensemble dans 8 Go).
Libellés, licences, voix proposées et leurs paramètres : workflows/catalog.json, sections « tts » et « voices ».
Sortie : échantillons mono float32 et leur fréquence. La vitesse vient de channels.voice_speed : native chez Kokoro,
appliquée après coup (FFmpeg atempo, hauteur conservée) pour un moteur qui ne sait pas la régler.
Les scripts écrivent les nombres en chiffres (ils s'affichent ainsi) : chaque moteur reçoit le texte avec les nombres en
toutes lettres (worker/numbers.py : spoken, « 1992 » → « mille neuf cent quatre-vingt-douze »).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..config import Settings
from ..numbers import spoken

RUNNERS_DIR = Path(__file__).resolve().parents[2] / "tts_runners"
Progress = Callable[[int, str], None]  # (pourcentage 0-100, libellé)


@dataclass
class Speech:
    samples: Any  # numpy.ndarray float32 mono
    rate: int
    voice: str

    @property
    def duration_s(self) -> float:
        return len(self.samples) / self.rate


def split_voice(voice_id: str) -> tuple[str, str]:
    """« moteur:voix » → (moteur, voix) ; un nom seul est une voix Kokoro."""
    engine, sep, voice = (voice_id or "").strip().partition(":")
    return (engine, voice) if sep else ("kokoro", engine)


def tts_catalog(settings: Settings) -> dict[str, Any]:
    from .video import load_catalog

    return load_catalog(settings.comfy_workflow_dir)


def voice_entry(catalog: dict[str, Any], voice_id: str) -> dict[str, Any] | None:
    """Entrée de catalog.json → voices.<langue> pour cette voix (paramètres propres au moteur, libellé)."""
    engine, voice = split_voice(voice_id)
    full = f"{engine}:{voice}"
    for entries in (catalog.get("voices") or {}).values():
        for e in entries:
            if isinstance(e, dict) and e.get("id") == full:
                return e
    return None


class TTS(Protocol):
    name: str
    gpu: bool

    def speak_many(self, texts: Sequence[str], *, voice: str, lang: str, speed: float,
                   on_progress: Progress | None = None) -> list[Speech]: ...


class KokoroTTS:
    name = "kokoro"
    gpu = False
    _engine: Any = None  # chargé une seule fois par processus (≈ 300 Mo)
    _lock = threading.Lock()

    def __init__(self, settings: Settings, voices: dict[str, str] | None = None) -> None:
        self.voices = {"fr": settings.kokoro_voice_fr, "en": settings.kokoro_voice_en, **(voices or {})}
        self.model_path: Path = settings.kokoro_model_path
        self.voices_path: Path = settings.kokoro_voices_path

    def voice_for(self, lang: str) -> str:
        return self.voices[lang]

    def _get_engine(self) -> Any:
        with KokoroTTS._lock:
            if KokoroTTS._engine is None:
                from kokoro_onnx import Kokoro

                if not self.model_path.exists() or not self.voices_path.exists():
                    raise FileNotFoundError(
                        f"Modèles Kokoro introuvables ({self.model_path}, {self.voices_path}). "
                        "Voir docs/06-local-stack.md."
                    )
                KokoroTTS._engine = Kokoro(str(self.model_path), str(self.voices_path))
            return KokoroTTS._engine

    def speak(self, text: str, *, lang: str, speed: float, voice: str | None = None) -> Speech:
        voice = voice or self.voice_for(lang)
        code = "fr-fr" if lang == "fr" else ("en-gb" if voice.startswith("b") else "en-us")  # bf_/bm_ : anglais britannique
        samples, rate = self._get_engine().create(spoken(text, lang), voice=voice, speed=float(speed), lang=code)
        return Speech(samples=samples, rate=int(rate), voice=voice)

    def speak_many(self, texts: Sequence[str], *, voice: str, lang: str, speed: float,
                   on_progress: Progress | None = None) -> list[Speech]:
        out = []
        for i, text in enumerate(texts):
            if on_progress:
                on_progress(int(100 * i / max(1, len(texts))), f"{i + 1}/{len(texts)} · kokoro")
            out.append(self.speak(text, lang=lang, speed=speed, voice=voice or None))
        return out


class TTSRunnerError(RuntimeError):
    pass


class VenvTTS:
    """Moteur PyTorch dans son propre environnement Python, un sous-processus par vidéo (ou par essai de voix).

    Échange par fichiers : request.json (textes, voix et ses paramètres, langue, vitesse, options du moteur) →
    <out_dir>/0000.wav… et result.json {"rate", "files", "speed_applied"} ; le script écrit « PROGRESS <fait> <total> »
    sur sa sortie standard (tts_runners/_common.py)."""

    def __init__(self, settings: Settings, name: str, spec: dict[str, Any], catalog: dict[str, Any]) -> None:
        self.settings = settings
        self.name = name
        self.spec = spec
        self.catalog = catalog
        self.gpu = bool(spec.get("gpu", True))
        self.home = Path(settings.yt2_home)
        self.engine_dir = self.home / spec.get("dir", f"tts/{name}")
        # « python » : interpréteur installé ailleurs que <dossier du moteur>/venv (chemin absolu)
        self.python = Path(spec["python"]) if spec.get("python") else self.engine_dir / "venv" / "Scripts" / "python.exe"
        self.runner = RUNNERS_DIR / spec.get("runner", f"{name}.py")
        self.online = False  # True : le script peut télécharger ses modèles (installation, `yt2 voice say --online`)

    def check(self) -> None:
        if not self.python.exists():
            raise FileNotFoundError(f"Moteur de voix « {self.name} » non installé ({self.python} absent) : "
                                    f"powershell -File services\\worker\\scripts\\install_tts.ps1 -Engine {self.name}")
        if not self.runner.exists():
            raise FileNotFoundError(f"Script du moteur absent : {self.runner}")

    def speak_many(self, texts: Sequence[str], *, voice: str, lang: str, speed: float,
                   on_progress: Progress | None = None) -> list[Speech]:
        import soundfile as sf

        from .. import cancel

        self.check()
        if self.gpu:
            _comfy_idle_then_free(self.settings, on_progress, cancel)
        entry = voice_entry(self.catalog, f"{self.name}:{voice}") or {}
        tmp_root = self.settings.data_dir / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f"tts_{self.name}_", dir=tmp_root) as tmp:
            work = Path(tmp)
            request = {
                "texts": [spoken(t, lang) for t in texts], "voice": voice, "voice_params": entry.get("params") or {}, "lang": lang,
                "speed": float(speed), "out_dir": str(work), "engine_dir": str(self.engine_dir), "home": str(self.home),
                "options": self.spec.get("options") or {},
            }
            (work / "request.json").write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
            self._run(work, len(texts), on_progress, cancel)
            result = json.loads((work / "result.json").read_text(encoding="utf-8"))
            rate = int(result["rate"])
            speeches = []
            for name in result["files"]:
                path = work / name
                if not result.get("speed_applied") and abs(float(speed) - 1.0) > 0.01:
                    path = _stretch(path, float(speed))
                samples, file_rate = sf.read(str(path), dtype="float32", always_2d=False)
                if samples.ndim > 1:
                    samples = samples.mean(axis=1)
                speeches.append(Speech(samples=samples, rate=int(file_rate or rate), voice=voice))
        return speeches

    def _run(self, work: Path, total: int, on_progress: Progress | None, cancel: Any) -> None:
        env = {
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            # Tout reste dans <YT2_HOME> ; pas de téléchargement pendant un rendu (modèles installés d'avance)
            "HF_HOME": str(self.home / "tts" / "hf-cache"),
            "HF_HUB_OFFLINE": "0" if self.online else "1",
            "TRANSFORMERS_OFFLINE": "0" if self.online else "1",
        }
        log_path = work / "runner.log"
        with log_path.open("w", encoding="utf-8") as log:
            proc = subprocess.Popen(
                [str(self.python), str(self.runner), str(work / "request.json")],
                stdout=subprocess.PIPE, stderr=log, text=True, encoding="utf-8", errors="replace", env=env,
                cwd=str(self.engine_dir if self.engine_dir.is_dir() else work),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            deadline = time.monotonic() + int(self.spec.get("timeout_s", 3600))
            try:
                assert proc.stdout is not None
                for line in proc.stdout:
                    if line.startswith("PROGRESS ") and on_progress:
                        done, _, n = line[9:].strip().partition(" ")
                        if done.isdigit():
                            on_progress(int(100 * int(done) / max(1, int(n or total))), f"{done}/{n or total} · {self.name}")
                    cancel.check()
                    if time.monotonic() > deadline:
                        raise TTSRunnerError(f"{self.name} : délai dépassé ({self.spec.get('timeout_s', 3600)} s)")
                code = proc.wait(timeout=60)
            except BaseException:
                proc.kill()
                raise
        if code != 0 or not (work / "result.json").exists():
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
            raise TTSRunnerError(f"Moteur de voix {self.name} en échec (code {code}) :\n{tail}")


def _comfy_idle_then_free(settings: Settings, on_progress: Progress | None, cancel: Any, max_wait_s: int = 4 * 3600) -> None:
    """Un moteur de voix sur GPU et un rendu ComfyUI ne tiennent pas ensemble dans 8 Go : on attend que la file de
    ComfyUI soit vide (prompts envoyés hors du worker : essais à la main, autres scripts), puis on vide sa mémoire
    (modèles gardés en VRAM et en RAM après chaque rendu). ComfyUI éteint : rien à attendre."""
    import httpx

    from .video import ComfyClient

    base = settings.comfy_base_url.rstrip("/")
    deadline = time.monotonic() + max_wait_s
    while time.monotonic() < deadline:
        try:
            q = httpx.get(f"{base}/queue", timeout=10).json()
        except (httpx.HTTPError, ValueError):
            return
        busy = len(q.get("queue_running") or []) + len(q.get("queue_pending") or [])
        if not busy:
            ComfyClient(base).free()
            return
        if on_progress:
            on_progress(0, f"attend la fin de {busy} rendu(s) ComfyUI")
        cancel.check()
        time.sleep(10)
    raise TTSRunnerError(f"ComfyUI occupé depuis {max_wait_s // 3600} h : voix non générée")


def _stretch(path: Path, speed: float) -> Path:
    """Vitesse de parole sans changer la hauteur (FFmpeg atempo, 0,5-2)."""
    from ..media import run

    out = path.with_name(f"{path.stem}_x{speed:.2f}.wav")
    run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-i", str(path), "-filter:a", f"atempo={min(2.0, max(0.5, speed)):.3f}", str(out)])
    return out


def get_engine(settings: Settings, engine: str) -> TTS:
    """Moteur de voix par son nom (clé de catalog.json → tts)."""
    if engine == "kokoro":
        return KokoroTTS(settings)
    catalog = tts_catalog(settings)
    spec = (catalog.get("tts") or {}).get(engine)
    if not spec or spec.get("runtime") != "venv":
        raise ValueError(f"Moteur de voix inconnu : « {engine} » (services/worker/workflows/catalog.json, section tts)")
    return VenvTTS(settings, engine, spec, catalog)


def resolve_voice(settings: Settings, voices: dict[str, str], lang: str) -> tuple[TTS, str]:
    """Moteur et nom court de la voix choisie pour une langue (réglages du dashboard, sinon .env)."""
    default = settings.kokoro_voice_fr if lang == "fr" else settings.kokoro_voice_en
    engine, voice = split_voice(voices.get(lang) or default)
    return get_engine(settings, engine), voice
