"""Santé de la machine et relances (docs/28-sante-machine.md).

- Le worker publie toutes les 30 s un signe de vie (app_settings.worker_status) avec la mémoire du PC : le dashboard
  l'affiche dans la barre latérale (« Machine ») et sait si le worker tourne encore.
- Bouton « Redémarrer le worker » du dashboard : app_settings.worker_restart = {"requested_at": …} ; le worker finit ses
  tâches en cours, n'en prend plus, puis se fait relancer par son superviseur (comme après une modification du code).
- ComfyUI ne répond plus : le worker le relance lui-même (C:\\YouTube2\\comfyui.bat) et attend qu'il réponde avant
  d'envoyer un rendu, au lieu d'échouer.

Pourquoi (28/09/2026) : MiniMax H3 occupe 25 à 30 Go de RAM sur 32. Ce jour-là, le serveur du dashboard (next dev) avait
grossi jusqu'à 11 Go : ComfyUI est tombé pendant le chargement de H3 et 7 clips ont échoué pendant une heure sans que
personne ne le voie.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog
from psycopg.types.json import Jsonb

log = structlog.get_logger(__name__)

STATUS_KEY = "worker_status"
RESTART_KEY = "worker_restart"
STATUS_EVERY_S = 30.0
COMFY_START_S = 240.0  # ComfyUI démarre en ≈ 20 s ; ses nœuds personnalisés peuvent allonger le premier démarrage
COMFY_RELAUNCH_GAP_S = 300.0  # jamais deux relances en moins de 5 min (un ComfyUI qui démarre n'écoute pas encore)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ---- mémoire de la machine ------------------------------------------------------------------------------------------


def memory() -> dict[str, float]:
    """RAM totale et libre, mémoire encore réservable (RAM + fichier d'échange), en Go. Windows seulement.
    C'est la mémoire réservable qui, épuisée, fait tomber ComfyUI."""
    if os.name != "nt":
        return {}
    import ctypes

    class Status(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    s = Status()
    s.dwLength = ctypes.sizeof(Status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):
        return {}
    gb = 2**30
    return {
        "ram_total_gb": round(s.ullTotalPhys / gb, 1),
        "ram_free_gb": round(s.ullAvailPhys / gb, 1),
        "commit_total_gb": round(s.ullTotalPageFile / gb, 1),
        "commit_free_gb": round(s.ullAvailPageFile / gb, 1),
    }


def vram() -> dict[str, int]:
    """Mémoire de toute la carte graphique (Mo), d'après nvidia-smi."""
    if shutil.which("nvidia-smi") is None:
        return {}
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=_NO_WINDOW,
        ).stdout
        used, total = (int(x) for x in out.strip().splitlines()[0].split(","))
        return {"vram_used_mb": used, "vram_total_mb": total}
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return {}


# ---- signe de vie et relance demandée depuis le dashboard ------------------------------------------------------------


def publish_status(db: Any, worker_id: str, comfy_base: str, started_at: datetime, draining: bool) -> None:
    value = {
        "worker_id": worker_id,
        "pid": os.getpid(),
        "started_at": started_at.isoformat(),
        "draining": draining,
        "comfy_up": comfy_up(comfy_base),
        **memory(),
        **vram(),
    }
    db.execute(
        """insert into app_settings (key, value, updated_at) values (%s, %s, now())
           on conflict (key) do update set value = excluded.value, updated_at = now()""",
        (STATUS_KEY, Jsonb(value)),
    )


class StatusBeat:
    """Fil qui publie le signe de vie toutes les 30 s, même pendant un clip de 10 min (la boucle principale est alors
    bloquée dans le job GPU)."""

    def __init__(self, db: Any, worker_id: str, comfy_base: str) -> None:
        self.db, self.worker_id, self.comfy_base = db, worker_id, comfy_base
        self.started_at = datetime.now(UTC)
        self.draining = False
        self._stop = threading.Event()

    def start(self) -> StatusBeat:
        threading.Thread(target=self._run, name="status", daemon=True).start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while True:
            try:
                publish_status(self.db, self.worker_id, self.comfy_base, self.started_at, self.draining)
            except Exception:  # noqa: BLE001 — base injoignable un instant : on réessaie au battement suivant
                log.warning("worker.statut_impossible")
            if self._stop.wait(STATUS_EVERY_S):
                return


def restart_requested(db: Any, started_at: datetime) -> bool:
    """Le bouton « Redémarrer le worker » a-t-il été pressé depuis le lancement de ce worker ?"""
    row = db.fetch_one("select value->>'requested_at' as at from app_settings where key = %s", (RESTART_KEY,))
    return is_after(row["at"] if row else None, started_at)


def is_after(stamp: str | None, started_at: datetime) -> bool:
    if not stamp:
        return False
    try:
        at = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (at if at.tzinfo else at.replace(tzinfo=UTC)) > started_at


# ---- ComfyUI : vérifier, relancer ------------------------------------------------------------------------------------

_comfy_lock = threading.Lock()
_last_launch = 0.0


def comfy_up(base: str, timeout_s: float = 3.0) -> bool:
    try:
        return httpx.get(f"{base.rstrip('/')}/system_stats", timeout=timeout_s).status_code == 200
    except httpx.HTTPError:
        return False


def comfy_launcher(base: str) -> Path | None:
    """Lanceur de ComfyUI sur ce PC : COMFY_LAUNCHER, sinon <YT2_HOME>/comfyui.bat. Rien si ComfyUI tourne ailleurs."""
    if (urlparse(base).hostname or "") not in ("127.0.0.1", "localhost", "::1"):
        return None
    path = Path(os.environ.get("COMFY_LAUNCHER") or Path(os.environ.get("YT2_HOME") or "C:/YouTube2") / "comfyui.bat")
    return path if path.is_file() else None


def comfy_process_running() -> bool:
    """Un Python de ComfyUI (ComfyUI\\main.py) tourne-t-il déjà ? (en train de démarrer : il n'écoute pas encore)"""
    if os.name != "nt":
        return False
    script = (
        "@(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        "Where-Object { $_.CommandLine -match 'ComfyUI[\\\\/]main\\.py' }).Count"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=60, creationflags=_NO_WINDOW
        ).stdout
        return int(out.strip() or 0) > 0
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def ensure_comfy(base: str) -> bool:
    """ComfyUI répond-il ? Sinon, s'il est local et qu'on connaît son lanceur, on le relance (au plus une fois toutes les
    5 min, jamais s'il est déjà en train de démarrer) et on attend qu'il réponde (4 min au plus). True s'il répond."""
    global _last_launch
    if comfy_up(base):
        return True
    launcher = comfy_launcher(base)
    if launcher is None:
        return False
    from . import cancel

    with _comfy_lock:
        if comfy_up(base):
            return True
        if time.monotonic() - _last_launch > COMFY_RELAUNCH_GAP_S and not comfy_process_running():
            _last_launch = time.monotonic()
            log.warning("comfy.relance", lanceur=str(launcher), raison="ComfyUI ne répond plus")
            # par l'explorateur : fenêtre à part, indépendante du worker (elle survit à une relance du worker)
            subprocess.Popen(["explorer.exe", str(launcher)], creationflags=_NO_WINDOW)
        deadline = time.monotonic() + COMFY_START_S
        while time.monotonic() < deadline:
            time.sleep(3)
            cancel.check()
            if comfy_up(base):
                log.info("comfy.relance_ok")
                return True
    log.error("comfy.relance_echec", attente_s=COMFY_START_S)
    return False
