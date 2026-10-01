"""Banc d'essai des voix de narration (docs/29-banc-voix.md) : la même narration dite par chaque voix du catalogue,
chronométrée, avec le débit, la mémoire, l'intelligibilité mesurée par Whisper et les fichiers à écouter côte à côte.

Trois étapes :
1. `run` (Python du worker, .env exporté) fait parler les voix. Par défaut chaque essai passe par la file du worker
   (job voice_preview, comme le bouton « Écouter » des Réglages, visible dans le panneau Tâches) : le worker l'intercale
   entre deux clips et vide ComfyUI avant un moteur sur la carte graphique ; rien ne se marche dessus, même pendant une
   production. Un essai « Bonjour. » par moteur donne le temps de chargement du modèle.
   `--direct` lance les moteurs sans le worker (machine au repos) : chargement et RAM mesurés pour chaque voix.
2. `eval` (environnement C:\\YouTube2\\tts\\eval : faster-whisper, num2words) : Whisper large-v3-turbo réécrit ce qu'il
   entend → taux d'erreur de mots (WER) et de caractères (CER) face au texte ; variation de hauteur de la voix.
3. `report` (n'importe quel Python) : README.md (tableau), index.html (lecteurs côte à côte), results.csv.

Depuis C:\\YouTube2 (Windows refuse à Python les écritures dans Documents) :
    set -a; . <dépôt>/services/worker/.env; set +a
    UV_PROJECT_ENVIRONMENT=C:/YouTube2/worker-venv uv run --project <dépôt>/services/worker \\
        python <dépôt>/services/worker/scripts/bench_voice.py run --out C:/YouTube2/bench
    C:/YouTube2/tts/eval/venv/Scripts/python.exe <dépôt>/services/worker/scripts/bench_voice.py eval <banc>
    C:/YouTube2/tts/eval/venv/Scripts/python.exe <dépôt>/services/worker/scripts/bench_voice.py report <banc>
`run --voices qwen3,pocket:estelle` : seulement ces moteurs ou ces voix ; `--dir <banc>` complète un banc existant.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

WORKER_ROOT = Path(__file__).resolve().parents[1]
RUNNERS_DIR = WORKER_ROOT / "tts_runners"

# Narration réelle (production dc8c681d, canal Rhin-Main-Danube, 28/09/2026), scènes 1 à 7 : nombres en toutes lettres
# comme les écrit l'agent script, noms propres, mots longs ; ≈ 570 caractères, soit un Short de 40 s environ.
TEXTS = {
    "fr": [
        "Soixante-dix ans de travaux ont été nécessaires pour relier le Rhin au Danube.",
        "Ce canal allemand long de cent soixante-dix kilomètres relie le Main au Danube.",
        "Seize écluses monumentales permettent de franchir la ligne de partage des eaux.",
        "Des chalands géants de treize cent cinquante tonnes traversent enfin l'Europe.",
        "Mais ce chantier pharaonique a provoqué de lourds dégâts écologiques dans la vallée.",
        "Déjà Charlemagne en sept cent quatre-vingt-treize rêvait de creuser cette brèche.",
        "Inauguré en dix-neuf cent quatre-vingt-douze, il a coûté plus de deux milliards d'euros.",
    ],
}
WARMUP = {"fr": "Bonjour.", "en": "Hello."}
SHORTS_PER_WEEK = 21
PREVIEW_MAX_CHARS = 600  # steps/voice_preview.py : texte tronqué au-delà


# ---------------------------------------------------------------------------------------------------------------------
# Fichier du banc
# ---------------------------------------------------------------------------------------------------------------------


def load_bench(folder: Path) -> dict[str, Any]:
    p = folder / "results.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_bench(folder: Path, bench: dict[str, Any]) -> None:
    tmp = folder / "results.json.tmp"
    tmp.write_text(json.dumps(bench, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    tmp.replace(folder / "results.json")


def safe_name(voice_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", voice_id)


# ---------------------------------------------------------------------------------------------------------------------
# Mesures : VRAM (toute la carte) et RAM (arbre de processus du moteur)
# ---------------------------------------------------------------------------------------------------------------------


def gpu_used_mb() -> int | None:
    if shutil.which("nvidia-smi") is None:
        return None
    r = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    lines = r.stdout.strip().splitlines()
    return int(lines[0]) if lines and lines[0].strip().isdigit() else None


class VramWindow:
    """Mémoire de la carte relevée toutes les 0,5 s : la hausse pendant l'essai est celle du moteur, les autres
    programmes (bureau, navigateurs) restant à peu près constants. ComfyUI est vidé en début d'essai GPU : on retient
    le plus bas niveau atteint, puis le pic qui le suit (ce que ComfyUI occupait avant d'être vidé ne compte pas)."""

    def __init__(self) -> None:
        self.lo: int | None = None
        self.hi: int | None = None
        self.best = 0  # plus forte hausse vue : le moteur rend sa mémoire en sortant, avant que le banc ne ferme la fenêtre
        self._stop = threading.Event()

    def __enter__(self) -> VramWindow:
        threading.Thread(target=self._run, daemon=True).start()
        return self

    def _run(self) -> None:
        while True:
            m = gpu_used_mb()
            if m is not None:
                if self.lo is None or m < self.lo:
                    self.lo = self.hi = m
                else:
                    self.hi = max(self.hi or m, m)
                self.best = max(self.best, (self.hi or m) - (self.lo or m))
            if self._stop.wait(0.5):
                return

    def __exit__(self, *exc: object) -> None:
        self._stop.set()

    @property
    def delta_mb(self) -> int | None:
        return None if self.lo is None else self.best


class ProcessRam:
    """Pic de RAM (ensemble de travail) des processus d'un moteur, sous Windows. Un environnement créé par uv lance le
    vrai Python en processus enfant : on suit tous les descendants. `pid` : processus lancé par le banc ; `exe_dir` :
    moteur lancé par le worker, repéré par le dossier de son exécutable (C:\\YouTube2\\tts\\<moteur>)."""

    def __init__(self, pid: int | None = None, exe_dir: Path | None = None) -> None:
        self.pid = pid
        self.exe_dir = str(exe_dir).lower() if exe_dir else None
        self.handles: dict[int, int] = {}
        self.peaks: dict[int, int] = {}
        self._paths: dict[int, str] = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> ProcessRam:
        if os.name == "nt":
            self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=5)
        self._read()
        for h in self.handles.values():
            _k32().CloseHandle(h)
        self.handles.clear()

    @property
    def peak_mb(self) -> int | None:
        return round(sum(self.peaks.values()) / 2**20) if self.peaks else None

    def _run(self) -> None:
        while True:
            try:
                self._track()
                self._read()
            except OSError:
                pass
            if self._stop.wait(0.3):
                return

    def _track(self) -> None:
        procs = _processes()
        children: dict[int, list[int]] = {}
        for pid, parent in procs:
            children.setdefault(parent, []).append(pid)
        roots = [self.pid] if self.pid else [pid for pid, _ in procs if self._image(pid).startswith(self.exe_dir or "\0")]
        todo, seen = list(roots), set()
        while todo:
            pid = todo.pop()
            if pid in seen:
                continue
            seen.add(pid)
            todo.extend(children.get(pid, []))
            if pid not in self.handles:
                h = _open(pid)
                if h:
                    self.handles[pid] = h

    def _read(self) -> None:
        for pid, h in self.handles.items():
            peak = _peak_working_set(h)
            if peak:
                self.peaks[pid] = max(self.peaks.get(pid, 0), peak)

    def _image(self, pid: int) -> str:
        if pid not in self._paths:
            self._paths[pid] = _image_path(pid).lower()
        return self._paths[pid]


def _k32() -> Any:
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    return k32


def _processes() -> list[tuple[int, int]]:
    """(pid, pid du parent) de tous les processus."""
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    k32 = _k32()
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    entry = Entry()
    entry.dwSize = ctypes.sizeof(Entry)
    out = []
    ok = k32.Process32FirstW(wintypes.HANDLE(snap), ctypes.byref(entry))
    while ok:
        out.append((int(entry.th32ProcessID), int(entry.th32ParentProcessID)))
        ok = k32.Process32NextW(wintypes.HANDLE(snap), ctypes.byref(entry))
    k32.CloseHandle(snap)
    return out


def _open(pid: int) -> int | None:
    return _k32().OpenProcess(0x1000 | 0x0010, False, pid) or None  # QUERY_LIMITED_INFORMATION | VM_READ


def _image_path(pid: int) -> str:
    import ctypes
    from ctypes import wintypes

    k32 = _k32()
    h = k32.OpenProcess(0x1000, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        return buf.value if k32.QueryFullProcessImageNameW(wintypes.HANDLE(h), 0, buf, ctypes.byref(size)) else ""
    finally:
        k32.CloseHandle(h)


def _peak_working_set(handle: int) -> int:
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    c = Counters()
    c.cb = ctypes.sizeof(Counters)
    ok = _k32().K32GetProcessMemoryInfo(wintypes.HANDLE(handle), ctypes.byref(c), c.cb)
    return int(c.PeakWorkingSetSize) if ok else 0


def ram_gb() -> tuple[float, float, float] | None:
    """(RAM totale, RAM libre, mémoire encore réservable : RAM + fichier d'échange) en Go, sous Windows. Quand la
    mémoire réservable s'épuise, c'est ComfyUI qui tombe (28/09, pendant un clip MiniMax H3)."""
    if os.name != "nt":
        return None
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
        return None
    return s.ullTotalPhys / 2**30, s.ullAvailPhys / 2**30, s.ullAvailPageFile / 2**30


def machine() -> dict[str, Any]:
    """Carte graphique, processeur, RAM totale et libre au lancement (conditions du banc)."""
    info: dict[str, Any] = {}
    if shutil.which("nvidia-smi"):
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True
        )
        if r.stdout.strip():
            name, _, total = r.stdout.strip().splitlines()[0].partition(",")
            info["gpu"] = f"{name.strip()} {round(int(total) / 1024)} Go"
    if os.name == "nt":
        import winreg

        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            info["cpu"] = str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    ram = ram_gb()
    if ram:
        info["ram"], info["ram_free_start"] = f"{ram[0]:.0f} Go", f"{ram[1]:.1f} Go".replace(".", ",")
    return info


# ---------------------------------------------------------------------------------------------------------------------
# 1. run : faire parler les voix
# ---------------------------------------------------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> None:
    from worker.config import Settings, utf8_console
    from worker.providers.tts import split_voice, tts_catalog

    utf8_console()
    settings = Settings()
    catalog = tts_catalog(settings)
    lang = args.lang
    text = " ".join(TEXTS[lang])
    assert len(text) <= PREVIEW_MAX_CHARS, "texte trop long pour un job voice_preview"
    folder = Path(args.dir) if args.dir else Path(args.out) / f"{datetime.now():%Y-%m-%d-%H%M}-voix"
    folder.mkdir(parents=True, exist_ok=True)
    bench = load_bench(folder) or {"lang": lang, "text": text, "scenes": TEXTS[lang], "voices": {}, "warmups": {}}
    bench.setdefault("started", datetime.now().isoformat(timespec="seconds"))
    bench["machine"] = machine()
    bench["speed"] = args.speed or channel_speed(settings, lang)

    wanted = [t.strip() for t in (args.voices or "").split(",") if t.strip()]
    voices = []
    for v in (catalog.get("voices") or {}).get(lang, []):
        engine, name = split_voice(v["id"])
        if wanted and engine not in wanted and v["id"] not in wanted:
            continue
        spec = (catalog.get("tts") or {}).get(engine) or {}
        if not installed(settings, spec, engine):
            print(f"  {v['id']} : moteur non installé, ignoré")
            continue
        voices.append(
            {
                **v,
                "engine": engine,
                "name": name,
                "spec": spec,
                "gpu": engine != "kokoro" and bool(spec.get("gpu", True)),
                "reloads": spec.get("runtime") == "venv",
            }
        )  # Kokoro reste chargé dans le worker
    if not voices:
        sys.exit("aucune voix à essayer")
    bench["engines"] = bench.get("engines", {}) | {
        v["engine"]: {
            "label": v["spec"].get("label", v["engine"]),
            "license": v["spec"].get("license", ""),
            "gpu": v["gpu"],
            "reloads": v["reloads"],
        }
        for v in voices
    }
    save_bench(folder, bench)
    print(f"Banc : {folder}\n{len(voices)} voix · {len(text)} caractères · vitesse {bench['speed']}")
    if args.direct:
        run_direct(settings, catalog, voices, lang, text, bench, folder)
    else:
        run_via_worker(settings, voices, lang, text, bench, folder)
    print(f"\nFini. Étapes suivantes : bench_voice.py eval {folder}, puis report {folder}")


def installed(settings: Any, spec: dict[str, Any], engine: str) -> bool:
    if not spec or not all((Path(settings.yt2_home) / rel).exists() for rel in spec.get("check", [])):
        return False
    if engine == "kokoro":
        return True
    from worker.providers.tts import get_engine

    return bool(getattr(get_engine(settings, engine), "python", Path("-")).exists())


def channel_speed(settings: Any, lang: str) -> float:
    """Vitesse de la chaîne de cette langue, comme en production (1,05 par défaut)."""
    try:
        import psycopg

        with psycopg.connect(settings.database_url) as conn:
            row = conn.execute("select voice_speed from channels where lang = %s limit 1", (lang,)).fetchone()
        return float(row[0]) if row and row[0] else float(settings.kokoro_speed)
    except Exception:  # noqa: BLE001 — base éteinte : vitesse par défaut
        return float(settings.kokoro_speed)


def run_via_worker(
    settings: Any, voices: list[dict[str, Any]], lang: str, text: str, bench: dict[str, Any], folder: Path
) -> None:
    """Un job voice_preview par essai, priorité 5 comme le bouton « Écouter » : le worker les prend l'un après l'autre
    entre deux jobs de sa voie GPU. Moteurs sur la carte d'abord : ils vident ComfyUI, et les moteurs sur le processeur
    passent ensuite avec la RAM libérée. Un essai « Bonjour. » par moteur mesure le chargement du modèle."""
    from psycopg.types.json import Jsonb

    from worker.db import Db

    db = Db(settings.database_url, max_size=2)
    plan: list[tuple[dict[str, Any], str]] = []
    for v in sorted(voices, key=lambda v: not v["gpu"]):
        if v["engine"] not in {p[0]["engine"] for p in plan}:
            plan.append((v, "warmup"))
        plan.append((v, "narration"))
    jobs = []
    for v, kind in plan:
        payload = {
            "voice": v["id"],
            "lang": lang,
            "text": WARMUP[lang] if kind == "warmup" else text,
            "speed": bench["speed"],
            "bench": folder.name,
        }
        row = db.fetch_one(
            "insert into jobs (type, priority, max_attempts, payload) values ('voice_preview', 5, 1, %s) returning id",
            (Jsonb(payload),),
        )
        assert row
        jobs.append({"id": row["id"], "voice": v, "kind": kind})
    print(f"{len(jobs)} essais en file (panneau Tâches : « Essai de voix ») ; le worker les prend entre deux clips.")

    pending = {j["id"]: j for j in jobs}
    current: dict[str, Any] | None = None
    vram: VramWindow | None = None
    ram: ProcessRam | None = None
    last_note = 0.0
    while pending:
        rows = {
            r["id"]: r
            for r in db.fetch_all(
                "select id, status::text as status, created_at, started_at, finished_at, result, error, progress_label "
                "from jobs where id = any(%s)",
                (list(pending),),
            )
        }
        # les essais finis d'abord : leurs relevés sont clos avant d'en ouvrir pour l'essai suivant
        for jid in list(pending):
            r = rows[jid]
            if r["status"] not in ("done", "failed", "cancelled"):
                continue
            j = pending.pop(jid)
            mine = current is not None and current["id"] == jid
            if mine:
                _close(vram, ram)
            record_worker_job(j, r, vram if mine else None, ram if mine else None, bench, folder)
            if mine:
                current, vram, ram = None, None, None
            save_bench(folder, bench)
        running = next((rows[i] for i in pending if rows[i]["status"] == "running"), None)
        if running and (current is None or current["id"] != running["id"]):
            _close(vram, ram)
            current = pending[running["id"]]
            v = current["voice"]
            vram = VramWindow().__enter__() if v["gpu"] else None
            ram = (
                ProcessRam(exe_dir=Path(settings.yt2_home) / v["spec"].get("dir", f"tts/{v['engine']}")).__enter__()
                if v["reloads"]
                else None
            )
            print(f"→ {v['id']} · {current['kind']}", flush=True)
        if not current and time.monotonic() - last_note > 60:
            last_note = time.monotonic()
            busy = db.fetch_one(
                "select type::text as type, progress_label from jobs where status = 'running' and locked_by like '%%/gpu' limit 1"
            )
            if busy:
                print(f"  en attente : le worker finit « {busy['type']} » ({busy['progress_label'] or '…'})", flush=True)
        time.sleep(0.3)
    db.pool.close()


def _close(*samplers: Any) -> None:
    for s in samplers:
        if s is not None:
            s.__exit__(None, None, None)


def record_worker_job(
    job: dict[str, Any], row: dict[str, Any], vram: VramWindow | None, ram: ProcessRam | None, bench: dict[str, Any], folder: Path
) -> None:
    v = job["voice"]
    res = row["result"] or {}
    wait_s = round((row["started_at"] - row["created_at"]).total_seconds(), 1) if row["started_at"] else None
    measures = {
        "mode": "worker",
        "job": str(row["id"]),
        "elapsed_s": res.get("elapsed_s"),
        "wait_s": wait_s,
        "vram_mb": vram.delta_mb if vram else None,
        "ram_mb": ram.peak_mb if ram else None,
        "error": (row["error"] or "")[-400:] if row["status"] != "done" else "",
    }
    if job["kind"] == "warmup":
        bench["warmups"][v["engine"]] = {**measures, "voice": v["id"], "audio_s": res.get("duration_s")}
        print(f"   chargement {v['engine']} : {res.get('elapsed_s')} s {measures['error']}", flush=True)
        return
    out = folder / f"{safe_name(v['id'])}.wav"
    if row["status"] == "done" and res.get("path") and Path(res["path"]).exists():
        shutil.copyfile(res["path"], out)
    bench["voices"][v["id"]] = {
        **measures,
        "engine": v["engine"],
        "label": v.get("label", v["id"]),
        "gpu": v["gpu"],
        "reloads": v["reloads"],
        "file": out.name if out.exists() else "",
        "audio_s": res.get("duration_s"),
        "rate": wav_rate(out),
    }
    print(
        f"   {res.get('duration_s')} s de voix en {res.get('elapsed_s')} s (attente {wait_s} s) {measures['error']}", flush=True
    )


def wav_rate(path: Path) -> int | None:
    import wave

    if not path.exists():
        return None
    with wave.open(str(path), "rb") as w:
        return w.getframerate()


def run_direct(
    settings: Any,
    catalog: dict[str, Any],
    voices: list[dict[str, Any]],
    lang: str,
    text: str,
    bench: dict[str, Any],
    folder: Path,
) -> None:
    """Moteurs lancés par le banc, avec le protocole des tts_runners (Kokoro compris) : une phrase d'échauffement,
    puis la narration scène par scène, comme l'étape « voix » des productions (un texte par scène, modèle chargé une
    fois). Un moteur sur la carte ne doit pas croiser un clip : machine au repos, ou worker sans job GPU. Les moteurs
    sur le processeur peuvent tourner pendant un clip (ils ne touchent pas à la carte)."""
    import tempfile

    from worker import cancel
    from worker.providers.tts import _comfy_idle_then_free, voice_entry

    for v in voices:
        if v["gpu"]:
            _comfy_idle_then_free(settings, None, cancel)
        with tempfile.TemporaryDirectory(prefix="bench_voice_", dir=Path(settings.yt2_home) / "bench") as tmp:
            work = Path(tmp)
            spec = v["spec"]
            if v["engine"] == "kokoro":
                python, cmd = Path(sys.executable), [str(Path(__file__).resolve()), "_kokoro"]
                engine_dir = Path(settings.yt2_home) / "models"
                options = {"model": str(settings.kokoro_model_path), "voices": str(settings.kokoro_voices_path)}
            else:
                engine_dir = Path(settings.yt2_home) / spec.get("dir", f"tts/{v['engine']}")
                python = Path(spec["python"]) if spec.get("python") else engine_dir / "venv" / "Scripts" / "python.exe"
                cmd, options = [str(RUNNERS_DIR / spec.get("runner", f"{v['engine']}.py"))], spec.get("options") or {}
            request = {
                "texts": [WARMUP[lang], *bench["scenes"]],
                "voice": v["name"],
                "voice_params": (voice_entry(catalog, v["id"]) or {}).get("params") or {},
                "lang": lang,
                "speed": float(bench["speed"]),
                "out_dir": str(work),
                "engine_dir": str(engine_dir),
                "home": str(settings.yt2_home),
                "options": options,
            }
            (work / "request.json").write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
            print(f"→ {v['id']}", flush=True)
            row = _direct_once(
                settings, python, [*cmd, str(work / "request.json")], engine_dir, work, v, bench, folder, len(request["texts"])
            )
        bench["voices"][v["id"]] = row
        save_bench(folder, bench)
        print(
            f"   chargement {row.get('load_s')} s · narration {row.get('synth_s')} s → {row.get('audio_s')} s de voix "
            f"· RAM {row.get('ram_mb')} Mo · VRAM {row.get('vram_mb')} Mo {row.get('error', '')}",
            flush=True,
        )


def _direct_once(
    settings: Any,
    python: Path,
    argv: list[str],
    engine_dir: Path,
    work: Path,
    v: dict[str, Any],
    bench: dict[str, Any],
    folder: Path,
    n_texts: int,
) -> dict[str, Any]:
    import numpy as np
    import soundfile as sf

    from worker.providers.tts import _stretch
    from worker.timeline import trim_silence

    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "HF_HOME": str(Path(settings.yt2_home) / "tts" / "hf-cache"),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }
    row: dict[str, Any] = {
        "mode": "direct",
        "engine": v["engine"],
        "label": v.get("label", v["id"]),
        "gpu": v["gpu"],
        "reloads": v["reloads"],
        "error": "",
    }
    marks: dict[int, float] = {}
    with (work / "runner.log").open("w", encoding="utf-8") as log, VramWindow() as vram:
        t0 = time.perf_counter()
        proc = subprocess.Popen(
            [str(python), *argv],
            stdout=subprocess.PIPE,
            stderr=log,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=str(engine_dir if engine_dir.is_dir() else work),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        with ProcessRam(pid=proc.pid) as ram:
            assert proc.stdout is not None
            for line in proc.stdout:
                if line.startswith("PROGRESS "):
                    done = line.split()[1]
                    if done.isdigit():
                        marks[int(done)] = time.perf_counter()
            code = proc.wait()
    if code != 0 or n_texts not in marks:
        row["error"] = (work / "runner.log").read_text(encoding="utf-8", errors="replace")[-400:]
        return row
    result = json.loads((work / "result.json").read_text(encoding="utf-8"))
    t1 = time.perf_counter()
    scenes, rate = [], 24000
    for name in result["files"][1:]:  # le premier fichier est la phrase d'échauffement
        path = work / name
        if not result.get("speed_applied") and abs(float(bench["speed"]) - 1.0) > 0.01:
            path = _stretch(path, float(bench["speed"]))
        samples, rate = sf.read(str(path), dtype="float32", always_2d=False)
        scenes.append(trim_silence(samples.mean(axis=1) if samples.ndim > 1 else samples, rate))
    synth_s = marks[n_texts] - marks[1] + time.perf_counter() - t1
    gap = np.zeros(int(0.3 * rate), dtype=np.float32)  # à l'écoute, un temps entre deux scènes, comme au montage
    out = folder / f"{safe_name(v['id'])}.wav"
    sf.write(str(out), np.concatenate([p for s in scenes for p in (s, gap)][:-1]), rate, subtype="PCM_16")
    row.update(
        load_s=round(marks[1] - t0, 2),
        synth_s=round(synth_s, 2),
        rate=int(rate),
        file=out.name,
        audio_s=round(sum(len(s) for s in scenes) / rate, 2),  # voix seule, sans les temps entre scènes
        vram_mb=vram.delta_mb if v["gpu"] else None,
        ram_mb=ram.peak_mb,
        per_scene=True,
    )
    return row


def kokoro_runner(request_path: str) -> None:
    """Kokoro lancé comme les moteurs des tts_runners (même protocole), pour le banc en mode direct ; en production il
    tourne dans le processus du worker (providers/tts.py, KokoroTTS)."""
    sys.path.insert(0, str(RUNNERS_DIR))
    sys.argv = [sys.argv[0], request_path]
    import _common  # type: ignore[import-not-found]

    state: dict[str, Any] = {}

    def prepare(req: dict[str, Any]) -> None:
        from kokoro_onnx import Kokoro

        state["engine"] = Kokoro(req["options"]["model"], req["options"]["voices"])

    def synthesize(req: dict[str, Any], text: str) -> tuple[Any, int]:
        voice = req["voice"]
        code = "fr-fr" if req["lang"] == "fr" else ("en-gb" if voice.startswith("b") else "en-us")
        samples, rate = state["engine"].create(text, voice=voice, speed=float(req["speed"]), lang=code)
        return samples, int(rate)

    _common.run(synthesize, prepare=prepare, speed_applied=True)


# ---------------------------------------------------------------------------------------------------------------------
# Mesures dérivées : ce que coûte un Short, une semaine
# ---------------------------------------------------------------------------------------------------------------------


def derive(bench: dict[str, Any]) -> list[dict[str, Any]]:
    """Une ligne par voix : chargement, calcul de la narration, débit, coût d'un Short et d'une semaine (21 Shorts).
    Un moteur « venv » recharge son modèle à chaque vidéo (sous-processus) ; Kokoro reste chargé dans le worker."""
    chars = len(bench["text"])
    words = len(bench["text"].split())
    out = []
    for vid, r in bench.get("voices", {}).items():
        d = {"voice": vid, **r, "chars": chars}
        if r.get("mode") == "worker":
            warm = bench.get("warmups", {}).get(r["engine"], {})
            load = warm.get("elapsed_s")
            elapsed = r.get("elapsed_s")
            d["load_s"] = load
            if elapsed is not None:
                d["synth_s"] = round(max(0.1, elapsed - (load or 0)), 2) if r.get("reloads") else elapsed
            d["ram_mb"] = r.get("ram_mb") or warm.get("ram_mb")
        load, synth, audio = d.get("load_s"), d.get("synth_s"), d.get("audio_s")
        if synth and audio:
            per_video_load = (load or 0) if r.get("reloads") else 0
            d["chars_per_s"] = round(chars / synth, 1)
            d["x_realtime"] = round(audio / synth, 2)
            d["short_s"] = round(synth + per_video_load, 1)
            d["chars_per_s_total"] = round(chars / d["short_s"], 1)  # chargement compris : ce que coûte vraiment un Short
            d["per_1000_s"] = round(per_video_load + 1000 / d["chars_per_s"], 1)
            d["week_min"] = round(d["short_s"] * SHORTS_PER_WEEK / 60, 1)
            d["speech_cps"] = round(chars / audio, 1)
            d["wpm"] = round(words / audio * 60)
        out.append(d)
    return out


# ---------------------------------------------------------------------------------------------------------------------
# 2. eval : intelligibilité (Whisper) et variation de hauteur
# ---------------------------------------------------------------------------------------------------------------------


def cmd_eval(args: argparse.Namespace) -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    folder = Path(args.dir)
    bench = load_bench(folder)
    model: Any = None
    if args.force or any(r.get("file") and not r.get("transcript") for r in bench.get("voices", {}).values()):
        os.environ.setdefault("HF_HOME", r"C:\YouTube2\tts\hf-cache")
        from faster_whisper import WhisperModel

        # Whisper prend ≈ 1,5 Go : pendant un clip MiniMax H3 la machine est au bord, on attend qu'il y ait de la place
        while (ram := ram_gb()) and (ram[1] < args.min_free_gb or ram[2] < 2 * args.min_free_gb):
            print(
                f"RAM libre {ram[1]:.1f} Go, mémoire réservable {ram[2]:.1f} Go : trop juste, nouvel essai dans 60 s", flush=True
            )
            time.sleep(60)
        t0 = time.perf_counter()
        model = WhisperModel(args.whisper, device="cpu", compute_type="int8", cpu_threads=args.threads)
        print(f"Whisper {args.whisper} chargé en {time.perf_counter() - t0:.0f} s")
    for vid, r in bench.get("voices", {}).items():
        path = folder / (r.get("file") or "")
        if not r.get("file") or not path.exists():
            continue
        t1 = time.perf_counter()
        if not r.get("transcript") or args.force:
            segments, _info = model.transcribe(
                str(path),
                language=bench.get("lang", "fr"),
                beam_size=5,
                temperature=0.0,
                condition_on_previous_text=False,
                vad_filter=False,
            )
            r["transcript"] = " ".join(s.text.strip() for s in segments).strip()
        score(bench, r)
        if r.get("f0_std_st") is None or args.force:
            r["f0_median_hz"], r["f0_std_st"] = pitch_stats(path)
        save_bench(folder, bench)
        print(
            f"{vid:<24} WER {r['wer']:.1%} · CER {r['cer']:.1%} · hauteur {r['f0_median_hz']} Hz ± {r['f0_std_st']} "
            f"demi-tons ({time.perf_counter() - t1:.0f} s)",
            flush=True,
        )


# Ce que Whisper écrit autrement sans que la voix se trompe : abréviation, homophone d'un mot rare (« chalands » est
# entendu « chalants » ou « chalons » pour les 18 voix du 28/09, voix natives comprises)
ASR_EQUIVALENTS = {"km": "kilomètres", "chalants": "chalands", "chalant": "chalands", "chalons": "chalands"}


def score(bench: dict[str, Any], r: dict[str, Any]) -> None:
    """WER, CER et liste des écarts d'après ce que Whisper a entendu (recalculables sans relancer Whisper)."""
    ref_words = normalize(bench["text"])
    ref_norm = " ".join(ref_words)
    hyp_words = [ASR_EQUIVALENTS.get(w, w) for w in normalize(r["transcript"], ref_norm)]
    ops = align(ref_words, hyp_words)
    r["wer"] = round(sum(1 for o in ops if o[0] != "=") / max(1, len(ref_words)), 4)
    r["cer"] = round(edit_distance(ref_norm, " ".join(hyp_words)) / max(1, len(ref_norm)), 4)
    r["errors"] = [[op, a, b] for op, a, b in ops if op != "="]


def normalize(text: str, reference: str = "") -> list[str]:
    """Mots comparables : minuscules, sans ponctuation ni tirets, nombres en toutes lettres (Whisper écrit « 1992 »
    ce que la narration écrit « dix-neuf cent quatre-vingt-douze » : on garde la forme présente dans le texte)."""
    t = unicodedata.normalize("NFC", text).lower().replace("’", "'")
    t = re.sub(r"\d{1,3}(?:[\u00a0\u202f ]\d{3})+|\d+", lambda m: number_words(int(re.sub(r"\D", "", m.group(0))), reference), t)
    t = re.sub(r"[^\w]+|_", " ", t)
    return t.split()


def number_words(n: int, reference: str) -> str:
    from num2words import num2words

    options = [num2words(n, lang="fr")]
    hundreds, rest = divmod(n, 100)
    if 1100 <= n < 2000 and hundreds % 10:  # 1350 → « treize cent cinquante », 1992 → « dix-neuf cent quatre-vingt-douze »
        options.append(f"{num2words(hundreds, lang='fr')} cent {num2words(rest, lang='fr') if rest else ''}")
    for o in options:
        if " ".join(normalize(o)) in reference:
            return o
    return options[0]


def edit_distance(a: Any, b: Any) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def align(ref: list[str], hyp: list[str]) -> list[tuple[str, str, str]]:
    """Alignement mot à mot : « = » identique, « ~ » remplacé, « - » sauté, « + » ajouté."""
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]))
    ops, i, j = [], n, m
    while i or j:
        if i and j and d[i][j] == d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            ops.append(("=" if ref[i - 1] == hyp[j - 1] else "~", ref[i - 1], hyp[j - 1]))
            i, j = i - 1, j - 1
        elif i and d[i][j] == d[i - 1][j] + 1:
            ops.append(("-", ref[i - 1], ""))
            i -= 1
        else:
            ops.append(("+", "", hyp[j - 1]))
            j -= 1
    return ops[::-1]


def pitch_stats(path: Path) -> tuple[float | None, float | None]:
    """Hauteur médiane (Hz) et variation de la hauteur (écart-type en demi-tons) sur les passages voisés : méthode YIN
    (de Cheveigné et Kawahara, 2002). Une voix monotone reste sous ≈ 2 demi-tons, une lecture vivante dépasse 3."""
    import wave

    import numpy as np

    with wave.open(str(path), "rb") as w:
        sr, ch = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    frame, hop = int(0.04 * sr), int(0.01 * sr)
    tau_min, tau_max = int(sr / 450), int(sr / 60)
    gate = 0.1 * np.sqrt(np.mean(x**2))
    nfft = 1 << int(np.ceil(np.log2(2 * frame + tau_max)))
    taus = np.arange(tau_max + 1)
    f0 = []
    for start in range(0, len(x) - frame - tau_max, hop):
        seg = x[start : start + frame + tau_max]
        if np.sqrt(np.mean(seg[:frame] ** 2)) < gate:
            continue
        cs = np.concatenate([[0.0], np.cumsum(seg**2)])
        r = np.fft.irfft(np.conj(np.fft.rfft(seg[:frame], nfft)) * np.fft.rfft(seg, nfft), nfft)[: tau_max + 1]
        diff = cs[frame] + (cs[taus + frame] - cs[taus]) - 2 * r
        cmnd = diff[1:] * np.arange(1, tau_max + 1) / np.maximum(np.cumsum(diff[1:]), 1e-12)
        below = np.nonzero(cmnd[tau_min - 1 :] < 0.15)[0]
        if not len(below):
            continue
        t = below[0] + tau_min - 1
        while t + 1 < len(cmnd) and cmnd[t + 1] < cmnd[t]:
            t += 1
        f0.append(sr / (t + 1))
    if len(f0) < 20:
        return None, None
    f = np.asarray(f0)
    semis = 12 * np.log2(f / np.median(f))
    semis = semis[np.abs(semis) < 12]  # erreurs d'octave écartées
    return round(float(np.median(f))), round(float(np.std(semis)), 1)


# ---------------------------------------------------------------------------------------------------------------------
# 3. report : README.md, index.html, results.csv
# ---------------------------------------------------------------------------------------------------------------------

COLUMNS = [  # (clé, titre, format)
    ("voice", "Voix", "{}"),
    ("engine_label", "Moteur", "{}"),
    ("where", "Calcul", "{}"),
    ("load_s", "Chargement (s)", "{:.1f}"),
    ("synth_s", "Narration : calcul (s)", "{:.1f}"),
    ("audio_s", "Voix obtenue (s)", "{:.1f}"),
    ("chars_per_s", "Caractères / s (calcul)", "{:.0f}"),
    ("chars_per_s_total", "Caractères / s (chargement compris)", "{:.0f}"),
    ("x_realtime", "× temps réel", "{:.1f}"),
    ("per_1000_s", "1 000 caractères (s)", "{:.0f}"),
    ("short_s", "Un Short (s)", "{:.0f}"),
    ("week_min", "Semaine, 21 Shorts (min)", "{:.0f}"),
    ("speech_cps", "Débit (car. / s de voix)", "{:.1f}"),
    ("vram_mb", "VRAM (Mo)", "{:.0f}"),
    ("ram_mb", "RAM (Mo)", "{:.0f}"),
    ("wer", "Mots mal compris (WER)", "{:.1%}"),
    ("cer", "CER", "{:.1%}"),
    ("f0_std_st", "Variation de hauteur (demi-tons)", "{:.1f}"),
    ("f0_median_hz", "Hauteur (Hz)", "{:.0f}"),
]


def fmt(value: Any, spec: str) -> str:
    if value is None or value == "":
        return "—"
    try:
        return spec.format(value).replace(".", ",") if spec != "{}" else str(value)
    except (ValueError, TypeError):
        return str(value)


def cmd_report(args: argparse.Namespace) -> None:
    folder = Path(args.dir)
    bench = load_bench(folder)
    rows = derive(bench)
    engines = bench.get("engines", {})
    for d in rows:
        d["engine_label"] = engines.get(d["engine"], {}).get("label", d["engine"])
        d["where"] = "carte graphique" if d.get("gpu") else "processeur"
    rows.sort(key=lambda d: (d["engine"], d.get("wer") if d.get("wer") is not None else 9, d["voice"]))

    with (folder / "results.csv").open("w", newline="", encoding="utf-8-sig") as f:  # Excel en français : « ; » et « , »
        keys = [k for k, _, _ in COLUMNS] + ["label", "file", "transcript", "mode", "elapsed_s", "wait_s", "error"]
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore", delimiter=";")
        w.writeheader()
        w.writerows({k: str(v).replace(".", ",") if isinstance(v, float) else v for k, v in d.items()} for d in rows)

    m = bench.get("machine", {})
    speed = str(bench.get("speed")).replace(".", ",")
    head = [
        f"# Banc d'essai des voix · {folder.name}",
        "",
        f"Machine : {m.get('gpu', '?')} · {m.get('cpu', '?')} · RAM {m.get('ram', '?')} (libre au départ : "
        f"{m.get('ram_free_start', '?')}). Vitesse de parole {speed} (celle de la chaîne). "
        f"Texte : {len(bench['text'])} caractères, narration réelle d'un Short.",
        "",
        f"> {bench['text']}",
        "",
        "Un Short = chargement du modèle (moteurs rechargés à chaque vidéo) + calcul de la narration ; semaine = 21 Shorts. "
        "WER / CER : part des mots / caractères que Whisper large-v3-turbo n'entend pas comme écrits (mots sautés, mal "
        "prononcés) ; Whisper se trompe aussi un peu, seul l'écart entre voix compte. Variation de hauteur : écart-type "
        "de la hauteur en demi-tons (< 2 = monotone).",
        "",
        "| " + " | ".join(t for _, t, _ in COLUMNS) + " |",
        "|" + "---|" * len(COLUMNS),
    ]
    lines = head + ["| " + " | ".join(fmt(d.get(k), s) for k, _, s in COLUMNS) + " |" for d in rows]
    errors = [f"- **{d['voice']}** : {d['error']}" for d in rows if d.get("error")]
    if errors:
        lines += ["", "## Échecs", "", *errors]
    (folder / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (folder / "index.html").write_text(render_html(bench, rows, folder), encoding="utf-8")
    print(f"{folder / 'README.md'}\n{folder / 'index.html'}")


def render_html(bench: dict[str, Any], rows: list[dict[str, Any]], folder: Path) -> str:
    m = bench.get("machine", {})
    head_cells = "".join(f'<th data-k="{k}">{html.escape(t)}</th>' for k, t, _ in COLUMNS[1:])
    body = []
    for d in rows:
        cells = "".join(
            f'<td data-v="{html.escape(str(d.get(k, "")))}">{html.escape(fmt(d.get(k), s))}</td>' for k, _, s in COLUMNS[1:]
        )
        audio = f'<audio controls preload="none" src="{html.escape(d["file"])}"></audio>' if d.get("file") else "échec"
        errs = " · ".join(f"{a or '∅'} → {b or '∅'}" for _, a, b in d.get("errors") or [])
        detail = (
            (
                f"<details><summary>Ce que Whisper entend</summary><p>{html.escape(d.get('transcript', ''))}</p>"
                f'<p class="err">{html.escape(errs) or "aucun écart"}</p></details>'
            )
            if d.get("transcript")
            else ""
        )
        body.append(
            f'<tr><td data-v="{html.escape(d["voice"])}"><b>{html.escape(d.get("label") or d["voice"])}</b>'
            f"<br><code>{html.escape(d['voice'])}</code>{audio}{detail}</td>{cells}</tr>"
        )
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Banc des voix</title>
<style>
:root {{ --bg:#fbfaf8; --fg:#1d1c1a; --mute:#6b6862; --line:#e4e1db; --head:#f1eee8; --accent:#9a3412; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#161514; --fg:#ecebe8; --mute:#a19d96; --line:#2d2b28; --head:#201f1d; --accent:#fb923c; }} }}
body {{ margin:0; padding:24px 16px; background:var(--bg); color:var(--fg); font:14px/1.45 system-ui, sans-serif; }}
h1 {{ font-size:20px; margin:0 0 6px; }} p {{ color:var(--mute); max-width:980px; }}
blockquote {{ margin:12px 0; padding:8px 12px; border-left:3px solid var(--accent); color:var(--fg); max-width:980px; }}
.wrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:8px; }}
table {{ border-collapse:collapse; min-width:1400px; width:100%; }}
th, td {{ padding:8px 10px; border-bottom:1px solid var(--line); text-align:right; vertical-align:top; white-space:nowrap; }}
th {{ position:sticky; top:0; background:var(--head); cursor:pointer; font-weight:600; white-space:normal; min-width:70px; }}
th:first-child, td:first-child {{ text-align:left; white-space:normal; min-width:280px; }}
td audio {{ display:block; width:260px; height:32px; margin-top:6px; }}
code {{ color:var(--mute); font-size:12px; }} details {{ margin-top:4px; color:var(--mute); }} .err {{ color:var(--accent); }}
</style></head><body>
<h1>Banc d'essai des voix · {html.escape(folder.name)}</h1>
<p>{html.escape(m.get("gpu", ""))} · {html.escape(m.get("cpu", ""))} · RAM {html.escape(m.get("ram", ""))}.
Même texte ({len(bench["text"])} caractères) pour toutes les voix, vitesse {str(bench.get("speed")).replace(".", ",")}. Un Short = chargement + calcul ;
semaine = 21 Shorts. WER : part des mots que Whisper n'entend pas comme écrits. Cliquer un titre pour trier.</p>
<blockquote>{html.escape(bench["text"])}</blockquote>
<div class="wrap"><table><thead><tr><th data-k="voice">Voix</th>{head_cells}</tr></thead>
<tbody>{"".join(body)}</tbody></table></div>
<script>
document.querySelectorAll('th').forEach((th, i) => th.addEventListener('click', () => {{
  const tb = th.closest('table').tBodies[0], asc = th.dataset.asc !== '1';
  const val = r => {{ const v = r.cells[i].dataset.v; const n = parseFloat(v); return isNaN(n) ? (v || '') : n; }};
  [...tb.rows].sort((a, b) => {{ const x = val(a), y = val(b); return (x > y ? 1 : x < y ? -1 : 0) * (asc ? 1 : -1); }})
    .forEach(r => tb.appendChild(r));
  document.querySelectorAll('th').forEach(t => delete t.dataset.asc); th.dataset.asc = asc ? '1' : '0';
}}));
</script></body></html>
"""


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "_kokoro":
        kokoro_runner(sys.argv[2])
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="faire parler les voix (Python du worker)")
    r.add_argument("--voices", help="moteurs ou voix, séparés par des virgules (défaut : toutes les voix installées)")
    r.add_argument("--lang", default="fr", choices=sorted(TEXTS))
    r.add_argument("--speed", type=float, help="vitesse de parole (défaut : celle de la chaîne)")
    r.add_argument("--direct", action="store_true", help="sans le worker (machine au repos)")
    r.add_argument("--out", default=r"C:\YouTube2\bench", help="dossier parent des bancs")
    r.add_argument("--dir", help="banc existant à compléter")
    r.set_defaults(fn=cmd_run)
    e = sub.add_parser("eval", help="intelligibilité (Whisper) et hauteur (environnement tts/eval)")
    e.add_argument("dir")
    e.add_argument("--whisper", default="large-v3-turbo")
    e.add_argument("--threads", type=int, default=8)
    e.add_argument("--min-free-gb", type=float, default=3.0, help="RAM libre exigée avant de charger Whisper")
    e.add_argument("--force", action="store_true", help="refaire les voix déjà évaluées")
    e.set_defaults(fn=cmd_eval)
    p = sub.add_parser("report", help="README.md, index.html, results.csv")
    p.add_argument("dir")
    p.set_defaults(fn=cmd_report)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
