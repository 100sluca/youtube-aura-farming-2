"""Accès Postgres (psycopg 3) : file de jobs, journal, requêtes utilitaires."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .models import Job


class Db:
    def __init__(self, url: str, max_size: int = 6) -> None:
        self.pool = ConnectionPool(url, min_size=1, max_size=max_size, kwargs={"row_factory": dict_row})

    # ---- helpers ------------------------------------------------------------
    def fetch_all(self, sql: str, params: Sequence[Any] | dict[str, Any] | None = None) -> list[dict]:
        with self.pool.connection() as conn:
            return list(conn.execute(sql, params).fetchall())

    def fetch_one(self, sql: str, params: Sequence[Any] | dict[str, Any] | None = None) -> dict | None:
        with self.pool.connection() as conn:
            return conn.execute(sql, params).fetchone()

    def execute(self, sql: str, params: Sequence[Any] | dict[str, Any] | None = None) -> int:
        with self.pool.connection() as conn:
            return conn.execute(sql, params).rowcount

    # ---- file de jobs -------------------------------------------------------
    def claim_jobs(self, worker: str, types: list[str], max_jobs: int = 1) -> list[Job]:
        rows = self.fetch_all("select * from claim_jobs(%s, %s::job_type[], %s)", (worker, types, max_jobs))
        return [Job.model_validate(r) for r in rows]

    def heartbeat(self, job_id: UUID, progress: int | None = None, label: str | None = None) -> bool:
        """Renvoie False si le job ne tourne plus (arrêté depuis le dashboard : status = 'cancelled')."""
        return (
            self.execute(
                """update jobs set locked_at = now(),
                     progress = coalesce(%s, progress), progress_label = coalesce(%s, progress_label)
                   where id = %s and status = 'running'""",
                (progress, label, job_id),
            )
            > 0
        )

    def job_status(self, job_id: UUID) -> str | None:
        row = self.fetch_one("select status::text as status from jobs where id = %s", (job_id,))
        return row["status"] if row else None

    def complete(self, job_id: UUID, result: dict[str, Any] | None = None) -> bool:
        """Un job arrêté pendant qu'il tournait reste « cancelled » (renvoie False)."""
        return (
            self.execute(
                """update jobs set status = 'done', progress = 100, result = %s, finished_at = now(),
                     locked_by = null, locked_at = null, error = null
                   where id = %s and status = 'running'""",
                (Jsonb(result or {}), job_id),
            )
            > 0
        )

    def fail(self, job_id: UUID, error: str) -> None:
        self.execute("select fail_job(%s, %s)", (job_id, error[:4000]))

    def postpone(self, job_id: UUID, delay_s: float, *, label: str | None = None, error: str | None = None) -> bool:
        """Remet en file, dans `delay_s` secondes, un job qui attend un service extérieur (vidéo Gemini en cours,
        quota atteint) sans consommer de tentative (worker/postpone.py). False si le job ne tourne plus (arrêté
        depuis le dashboard entre-temps)."""
        return (
            self.execute(
                """update jobs set status = 'queued', run_after = now() + make_interval(secs => %s),
                     attempts = greatest(attempts - 1, 0), locked_by = null, locked_at = null,
                     progress_label = coalesce(%s, progress_label), error = %s
                   where id = %s and status = 'running'""",
                (float(delay_s), label, error[:4000] if error else None, job_id),
            )
            > 0
        )

    def log(self, job_id: UUID, level: str, message: str, data: dict[str, Any] | None = None) -> None:
        self.execute(
            "insert into job_logs (job_id, level, message, data) values (%s, %s, %s, %s)",
            (job_id, level, message, Jsonb(data) if data else None),
        )

    def enqueue(
        self,
        type_: str,
        *,
        production_id: UUID | None = None,
        video_id: UUID | None = None,
        channel_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
        depends_on: Sequence[UUID] = (),
        priority: int = 100,
        run_after: datetime | None = None,
        max_attempts: int = 3,
    ) -> UUID:
        row = self.fetch_one(
            """insert into jobs (type, production_id, video_id, channel_id, payload, depends_on,
                                 priority, run_after, max_attempts)
               values (%s, %s, %s, %s, %s, %s, %s, coalesce(%s, now()), %s) returning id""",
            (
                type_,
                production_id,
                video_id,
                channel_id,
                Jsonb(payload or {}),
                list(depends_on),
                priority,
                run_after,
                max_attempts,
            ),
        )
        assert row is not None
        return row["id"]

    def recover_after_crash(self, worker_id: str) -> list[dict]:
        """Au démarrage du worker : les jobs encore « running » à son nom sont ceux du processus précédent, mort en
        route (plantage, coupure de courant). Remis en file tout de suite, sans consommer de tentative ; le travail déjà
        enregistré (clips, images, voix) est gardé par l'idempotence des steps (docs/42)."""
        return self.fetch_all(
            """update jobs set status = 'queued', run_after = now(), attempts = greatest(attempts - 1, 0),
                 locked_by = null, locked_at = null, progress_label = 'Reprise après un arrêt du worker'
               where status = 'running' and locked_by like %s
               returning id, type::text as type, locked_by, production_id""",
            (f"{worker_id}/%",),
        )

    def requeue_stale_jobs(self) -> int:
        row = self.fetch_one("select requeue_stale_jobs() as n")
        return int(row["n"]) if row else 0

    # ---- raccourcis métier --------------------------------------------------
    def set_status(self, table: str, id_: UUID, status: str, error: str | None = None) -> None:
        assert table in {"productions", "videos", "concepts"}
        self.execute(
            f"update {table} set status = %s, error = coalesce(%s, error) where id = %s",  # noqa: S608
            (status, error, id_),
        )

    def add_asset(self, **cols: Any) -> UUID:
        keys = list(cols)
        vals = [Jsonb(v) if isinstance(v, dict) else v for v in cols.values()]
        row = self.fetch_one(
            f"insert into assets ({', '.join(keys)}) values ({', '.join(['%s'] * len(keys))}) returning id",  # noqa: S608
            vals,
        )
        assert row is not None
        return row["id"]

    def alert(self, severity: str, title: str, body: str | None = None, **refs: UUID | None) -> UUID:
        row = self.fetch_one(
            """insert into alerts (severity, title, body, job_id, production_id, video_id)
               values (%s, %s, %s, %s, %s, %s) returning id""",
            (severity, title, body, refs.get("job_id"), refs.get("production_id"), refs.get("video_id")),
        )
        assert row is not None
        return row["id"]

    def record_quota(self, channel_id: UUID | None, endpoint: str, units: int) -> None:
        self.execute(
            "insert into api_quota_usage (channel_id, endpoint, units) values (%s, %s, %s)",
            (channel_id, endpoint, units),
        )


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


__all__ = ["Db", "dumps", "psycopg"]
