"""Boucle principale : deux voies (gpu = 1 job à la fois, io = N jobs), heartbeat, planificateur."""

from __future__ import annotations

import argparse
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import structlog

from .config import Settings
from .db import Db
from .models import Job
from .scheduler import start_scheduler
from .steps import REGISTRY, Context

log = structlog.get_logger(__name__)


def run_job(job: Job, db: Db, settings: Settings) -> None:
    step = REGISTRY[job.type]
    ctx = Context(job=job, db=db, settings=settings)
    stop = threading.Event()

    def beat() -> None:
        while not stop.wait(30):
            db.heartbeat(job.id)

    threading.Thread(target=beat, daemon=True).start()
    log.info("job.start", type=job.type, id=str(job.id), attempt=job.attempts)
    try:
        result = step.run(ctx)
        db.complete(job.id, result)
        log.info("job.done", type=job.type, id=str(job.id))
    except Exception as exc:  # noqa: BLE001
        log.exception("job.failed", type=job.type, id=str(job.id))
        db.log(job.id, "error", str(exc)[:4000])
        db.fail(job.id, f"{type(exc).__name__}: {exc}")
    finally:
        stop.set()


def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube 2.0 worker")
    parser.add_argument("--once", action="store_true", help="traite au plus un job par voie puis quitte")
    args = parser.parse_args()

    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db = Db(settings.database_url)
    scheduler = start_scheduler(db, settings)

    gpu_types = [t for t in settings.job_types if REGISTRY[t].lane == "gpu"]
    io_types = [t for t in settings.job_types if REGISTRY[t].lane == "io"]
    pool = ThreadPoolExecutor(max_workers=settings.io_concurrency, thread_name_prefix="io")
    io_inflight: set = set()
    log.info("worker.start", id=settings.worker_id, gpu=gpu_types, io=io_types, dry_run=settings.dry_run)

    try:
        while True:
            did_work = False
            # voie io : remplir jusqu'à la concurrence
            io_inflight = {f for f in io_inflight if not f.done()}
            free = settings.io_concurrency - len(io_inflight)
            if io_types and free > 0:
                for job in db.claim_jobs(f"{settings.worker_id}/io", io_types, free):
                    io_inflight.add(pool.submit(run_job, job, db, settings))
                    did_work = True
            # voie gpu : un seul job, bloquant
            if gpu_types:
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
        scheduler.shutdown(wait=False)
        pool.shutdown(wait=True)


if __name__ == "__main__":
    main()
