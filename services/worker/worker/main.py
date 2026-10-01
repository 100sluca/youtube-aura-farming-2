"""Boucle principale : deux voies (gpu = 1 job à la fois, dans son propre fil ; io = N jobs), heartbeat, planificateur ;
plus un fil pour les aperçus demandés depuis le dashboard (voie preview : rendu exact de l'onglet Montage), pris même
pendant un job GPU.

La voie gpu a son fil (docs/43) : avant le 30/09 elle bloquait la boucle, et les scripts, idées ou SEO (voie io, clés
Gemini libres) attendaient la fin de chaque job GPU (images du storyboard, clip de 10 min) pour partir.

Relance automatique : `worker` lance un superviseur qui fait tourner le vrai worker dans un processus enfant. Quand un
fichier .py du worker change (plusieurs sessions le modifient en parallèle), l'enfant finit ses jobs en cours, n'en
prend plus, puis sort avec RESTART_CODE ; le superviseur le relance aussitôt avec le nouveau code. Plus besoin de
fermer la fenêtre du worker à chaque modification (constaté le 25/09 : des clips Gemini refusés par un code périmé).
WORKER_AUTO_RESTART=0 désactive le superviseur.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import structlog

from . import cancel
from .config import Settings, utf8_console
from .db import Db
from .models import Job
from .postpone import Postpone
from .prompts import sync_code_prompts
from .scheduler import start_scheduler
from .steps import REGISTRY, Context
from .system import StatusBeat, restart_requested

log = structlog.get_logger(__name__)


def run_job(job: Job, db: Db, settings: Settings) -> None:
    step = REGISTRY[job.type]
    ctx = Context(job=job, db=db, settings=settings)
    stop = threading.Event()
    stopped_by_user = threading.Event()  # arrêt demandé depuis le dashboard (worker/cancel.py)

    def beat() -> None:
        ticks = 0
        while not stop.wait(5):
            ticks += 1
            try:
                if db.job_status(job.id) == "cancelled":
                    stopped_by_user.set()
                    return
                if ticks % 6 == 0:  # battement toutes les 30 s (requeue_stale_jobs : 15 min sans battement)
                    db.heartbeat(job.id)
            except Exception:  # noqa: BLE001 — une coupure réseau passagère ne doit pas tuer le battement
                log.warning("job.heartbeat_failed", id=str(job.id))

    threading.Thread(target=beat, daemon=True).start()
    cancel.bind(stopped_by_user)
    log.info("job.start", type=job.type, id=str(job.id), attempt=job.attempts)
    try:
        result = step.run(ctx)
        if db.complete(job.id, result):
            log.info("job.done", type=job.type, id=str(job.id))
        else:
            log.info("job.cancelled", type=job.type, id=str(job.id), moment="à la fin du step")
    except Postpone as later:  # attente d'un service extérieur (vidéo Gemini en cours, quota) : pas un échec
        if db.postpone(job.id, later.delay_s, label=later.label, error=later.error):
            log.info("job.postponed", type=job.type, id=str(job.id), delay_s=round(later.delay_s), reason=later.reason)
            db.log(job.id, "info", later.reason)
        else:
            log.info("job.cancelled", type=job.type, id=str(job.id), moment="pendant l'attente")
    except Exception as exc:  # noqa: BLE001
        if _stopped_by_user(db, job, exc, stopped_by_user):
            log.info("job.cancelled", type=job.type, id=str(job.id))
            db.log(job.id, "info", "Arrêtée depuis le dashboard")
        else:
            log.exception("job.failed", type=job.type, id=str(job.id))
            db.log(job.id, "error", str(exc)[:4000])
            db.fail(job.id, f"{type(exc).__name__}: {exc}")
    finally:
        stop.set()
        cancel.bind(None)


def _stopped_by_user(db: Db, job: Job, exc: Exception, flag: threading.Event) -> bool:
    """L'exception vient-elle d'un arrêt demandé depuis le dashboard (et non d'une vraie panne) ?"""
    if isinstance(exc, cancel.JobCancelled) or flag.is_set():
        return True
    try:
        return db.job_status(job.id) == "cancelled"
    except Exception:  # noqa: BLE001
        return False


def preview_lane(
    db: Db, settings: Settings, types: list[str], busy: threading.Event, stop: threading.Event, label: str = "preview"
) -> None:
    """Voie des aperçus (rendu exact de l'onglet Montage) : quelques secondes de CPU, à prendre tout de suite. La voie io
    peut être pleine (trois scripts de plusieurs minutes) : ces jobs ont donc leur fil.
    Même fil, `label` « stats », pour les synchros YouTube et l'agent analyste (STATS_TYPES), et `label` « gpu » pour la
    voie GPU (un job à la fois, pendant que la voie io continue de se remplir)."""
    while not stop.wait(1.0):
        busy.set()  # avant de réclamer : une relance attend la fin d'un job à peine pris
        try:
            for job in db.claim_jobs(f"{settings.worker_id}/{label}", types, 1):
                run_job(job, db, settings)
        except Exception:  # noqa: BLE001 — base injoignable un instant : on réessaie à la seconde suivante
            log.warning("preview.claim_failed")
        finally:
            busy.clear()


# « Actualiser » et « Analyser maintenant » du Dashboard (docs/25), « Actualiser » de l'onglet TikTok (docs/39) : pris dans
# la seconde par leur propre fil (la voie io les prend aussi ; claim_jobs ne donne un job qu'une fois)
STATS_TYPES = ("sync_metrics", "analyze", "sync_tiktok")

RESTART_CODE = 3  # sortie de l'enfant quand son code a changé : le superviseur le relance
CODE_CHECK_S = 30.0  # intervalle de vérification du code source
CODE_SETTLE_S = 20.0  # un fichier modifié depuis moins longtemps est peut-être en cours d'écriture : on attend


def code_stamp(root: Path | None = None) -> float:
    """Date de la dernière modification d'un fichier .py du worker."""
    base = root or Path(__file__).resolve().parent
    return max((p.stat().st_mtime for p in base.rglob("*.py")), default=0.0)


def code_changed(started: float, current: float, now: float, settle_s: float = CODE_SETTLE_S) -> bool:
    """Code modifié depuis le lancement et plus touché depuis `settle_s` secondes (édition terminée)."""
    return current > started and now - current >= settle_s


def supervise(argv: list[str], call: object = subprocess.call, pause_s: float = 30.0) -> int:
    """Fait tourner le worker dans un processus enfant ; le relance quand il sort avec RESTART_CODE (code modifié) ou
    après un plantage (30 s d'attente : souvent un fichier en cours d'édition). Sortie normale ou Ctrl+C : on s'arrête."""
    cmd = [sys.executable, "-m", "worker.main", "--child", *argv]
    while True:
        try:
            code = call(cmd)  # type: ignore[operator]
        except KeyboardInterrupt:
            return 0
        if code == RESTART_CODE:
            log.info("worker.relance", raison="code du worker modifié ou bouton « Redémarrer » du dashboard")
            continue
        if code == 0:
            return 0
        log.warning("worker.plantage", code=code, nouvel_essai_dans_s=pause_s)
        try:
            time.sleep(pause_s)
        except KeyboardInterrupt:
            return int(code)


def recover_after_crash(db: Db, settings: Settings, clear_comfy: object = None) -> list[dict]:
    """Reprise après un plantage (docs/42) : les jobs que le processus précédent tenait repartent tout de suite (au lieu
    des 15 min de requeue_stale_jobs), sans consommer de tentative. Si l'un d'eux était sur la voie GPU, le rendu qu'il
    avait confié à ComfyUI tourne encore pour rien : on vide la file de ComfyUI avant que la reprise en soumette un autre."""
    try:
        jobs = db.recover_after_crash(settings.worker_id)
    except Exception as exc:  # noqa: BLE001 — base injoignable : requeue_stale_jobs prendra le relais
        log.warning("reprise.impossible", error=str(exc)[:300])
        return []
    if not jobs:
        return []
    for j in jobs:
        db.log(j["id"], "warn", "Worker arrêté pendant cette tâche : reprise automatique, le travail déjà enregistré est gardé")
    if any(str(j["locked_by"]).endswith("/gpu") for j in jobs):
        (clear_comfy or _clear_comfy)(settings.comfy_base_url)  # type: ignore[operator]
    names = ", ".join(sorted({j["type"] for j in jobs}))
    log.warning("reprise.apres_plantage", jobs=len(jobs), types=names)
    try:
        db.alert("info", f"Reprise après un arrêt du worker : {len(jobs)} tâche(s) relancée(s)", names)
    except Exception:  # noqa: BLE001
        pass
    return jobs


def _clear_comfy(base_url: str) -> None:
    """Vide la file de ComfyUI et interrompt le calcul orphelin (seul le worker s'en sert)."""
    import httpx

    base = base_url.rstrip("/")
    try:
        httpx.post(f"{base}/queue", json={"clear": True}, timeout=10)
        httpx.post(f"{base}/interrupt", timeout=10)
    except httpx.HTTPError:
        pass  # ComfyUI arrêté aussi : rien à vider, ensure_comfy le relancera


def main() -> None:
    utf8_console()
    parser = argparse.ArgumentParser(description="YouTube 2.0 worker")
    parser.add_argument("--once", action="store_true", help="traite au plus un job par voie puis quitte")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)  # lancé par le superviseur
    args = parser.parse_args()
    if not args.child and not args.once and os.environ.get("WORKER_AUTO_RESTART", "1") != "0":
        sys.exit(supervise(sys.argv[1:]))

    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db = Db(settings.database_url)
    # Texte du code de chaque prompt → prompt_templates (onglet Agents du dashboard, worker/prompts.py) : un prompt modifié
    # dans le code sert dès cette relance, sauf si une version écrite dans le dashboard est active
    try:
        synced = {k: r for k, r in sync_code_prompts(db).items() if r != "unchanged"}
        if synced:
            log.info("prompts.code", **synced)
    except Exception as exc:  # noqa: BLE001 — migration 0012 absente : les agents gardent le texte du code
        log.warning("prompts.sync_impossible", error=str(exc)[:300])
    if not args.once:
        recover_after_crash(db, settings)
    scheduler = start_scheduler(db, settings)

    gpu_types = [t for t in settings.job_types if REGISTRY[t].lane == "gpu"]
    io_types = [t for t in settings.job_types if REGISTRY[t].lane == "io"]
    preview_types = [t for t in settings.job_types if REGISTRY[t].lane == "preview"]
    pool = ThreadPoolExecutor(max_workers=settings.io_concurrency, thread_name_prefix="io")
    io_inflight: set = set()
    preview_busy, preview_stop = threading.Event(), threading.Event()
    if preview_types and not args.once:
        threading.Thread(
            target=preview_lane, args=(db, settings, preview_types, preview_busy, preview_stop), name="preview", daemon=True
        ).start()
    stats_types = [t for t in STATS_TYPES if t in io_types]
    stats_busy, stats_stop = threading.Event(), threading.Event()
    if stats_types and not args.once:
        threading.Thread(
            target=preview_lane, args=(db, settings, stats_types, stats_busy, stats_stop, "stats"), name="stats", daemon=True
        ).start()
    gpu_busy, gpu_stop = threading.Event(), threading.Event()
    if gpu_types and not args.once:
        threading.Thread(
            target=preview_lane, args=(db, settings, gpu_types, gpu_busy, gpu_stop, "gpu"), name="gpu", daemon=True
        ).start()
    log.info(
        "worker.start",
        id=settings.worker_id,
        gpu=gpu_types,
        io=io_types,
        preview=preview_types,
        stats=stats_types,
        dry_run=settings.dry_run,
    )
    started_stamp, last_check, draining, restart = code_stamp(), time.monotonic(), False, False
    # signe de vie pour la barre latérale du dashboard (« Machine », docs/28) : toutes les 30 s, même pendant un clip
    beat = StatusBeat(db, settings.worker_id, settings.comfy_base_url)
    if not args.once:
        beat.start()

    try:
        while True:
            did_work = False
            io_inflight = {f for f in io_inflight if not f.done()}
            # code modifié ou bouton « Redémarrer » du dashboard (superviseur) : on ne prend plus de job, on finit ceux en
            # cours, puis on se fait relancer
            if args.child and not draining and time.monotonic() - last_check >= CODE_CHECK_S:
                last_check = time.monotonic()
                reason = "code modifié" if code_changed(started_stamp, code_stamp(), time.time()) else None
                try:
                    if not reason and restart_requested(db, beat.started_at):
                        reason = "demandée depuis le dashboard"
                except Exception:  # noqa: BLE001 — base injoignable un instant : on revérifie dans 30 s
                    log.warning("worker.relance_illisible")
                if reason:
                    draining = beat.draining = True
                    gpu_stop.set()
                    preview_stop.set()
                    stats_stop.set()
                    log.info("worker.relance_prevue", raison=reason, action="fin des jobs en cours puis relance")
            if draining:
                if not io_inflight and not gpu_busy.is_set() and not preview_busy.is_set() and not stats_busy.is_set():
                    restart = True
                    break
                time.sleep(1)
                continue
            # voie io : remplir jusqu'à la concurrence
            free = settings.io_concurrency - len(io_inflight)
            if io_types and free > 0:
                for job in db.claim_jobs(f"{settings.worker_id}/io", io_types, free):
                    io_inflight.add(pool.submit(run_job, job, db, settings))
                    did_work = True
            # voie gpu : son fil (plus haut) ; en --once, un job ici, bloquant
            if gpu_types and args.once:
                for job in db.claim_jobs(f"{settings.worker_id}/gpu", gpu_types, 1):
                    run_job(job, db, settings)
                    did_work = True
            if args.once:
                break
            if not did_work:
                time.sleep(settings.poll_interval_s)
    except KeyboardInterrupt:
        pass
    finally:
        beat.stop()
        gpu_stop.set()
        preview_stop.set()
        stats_stop.set()
        scheduler.shutdown(wait=False)
        pool.shutdown(wait=True)
    if restart:
        sys.exit(RESTART_CODE)


if __name__ == "__main__":
    main()
