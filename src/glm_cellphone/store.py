from __future__ import annotations

import json
import shutil
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from .schemas import ArtifactRecord, JobRecord, StatsResponse, TaskResult


class JobStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                create table if not exists jobs (
                    id text primary key,
                    status text not null,
                    task text not null,
                    request_json text not null,
                    result_json text,
                    error text,
                    created_at text not null,
                    updated_at text not null
                );

                create table if not exists artifacts (
                    id text primary key,
                    job_id text not null,
                    kind text not null,
                    label text not null,
                    path text not null,
                    url text not null,
                    content_type text not null,
                    created_at text not null
                );

                create index if not exists idx_jobs_updated_at on jobs(updated_at desc);
                create index if not exists idx_artifacts_job_id on artifacts(job_id);
                """
            )

    def upsert_job(self, job: JobRecord, request: Any | None = None) -> None:
        request_json = _json_dump(request if request is not None else {})
        result_json = _json_dump(job.result.model_dump(mode="json")) if job.result else None
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "select request_json from jobs where id = ?",
                (job.id,),
            ).fetchone()
            if existing and request is None:
                request_json = existing["request_json"]
            conn.execute(
                """
                insert into jobs (
                    id, status, task, request_json, result_json, error, created_at, updated_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(id) do update set
                    status = excluded.status,
                    task = excluded.task,
                    request_json = excluded.request_json,
                    result_json = excluded.result_json,
                    error = excluded.error,
                    updated_at = excluded.updated_at
                """,
                (
                    job.id,
                    job.status,
                    job.task,
                    request_json,
                    result_json,
                    job.error,
                    _dt(job.created_at),
                    _dt(job.updated_at),
                ),
            )

    def add_artifacts(self, artifacts: list[ArtifactRecord]) -> None:
        if not artifacts:
            return
        with self._lock, self._connect() as conn:
            conn.executemany(
                """
                insert or replace into artifacts (
                    id, job_id, kind, label, path, url, content_type, created_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.id,
                        item.job_id,
                        item.kind,
                        item.label,
                        item.path,
                        item.url,
                        item.content_type,
                        _dt(item.created_at),
                    )
                    for item in artifacts
                ],
            )

    def list_jobs(self, limit: int = 100) -> list[JobRecord]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "select * from jobs order by updated_at desc limit ?",
                (limit,),
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("select * from jobs where id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def get_artifacts(self, job_id: str) -> list[ArtifactRecord]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "select * from artifacts where job_id = ? order by created_at, label",
                (job_id,),
            ).fetchall()
        return [ArtifactRecord(**dict(row)) for row in rows]

    def stats(self) -> StatsResponse:
        jobs = self.list_jobs(limit=10000)
        values: dict[str, Any] = {"total": len(jobs)}
        durations: list[float] = []
        for job in jobs:
            values[job.status] = values.get(job.status, 0) + 1
            if job.result:
                durations.append(job.result.duration_seconds)
        if durations:
            values["average_duration_seconds"] = round(sum(durations) / len(durations), 3)
        return StatsResponse(**values)

    def clear_history(self, *, exclude_ids: set[str], artifact_root: Path) -> int:
        with self._lock, self._connect() as conn:
            rows = conn.execute("select id from jobs").fetchall()
            delete_ids = [row["id"] for row in rows if row["id"] not in exclude_ids]
            if delete_ids:
                placeholders = ",".join("?" for _ in delete_ids)
                conn.execute(f"delete from artifacts where job_id in ({placeholders})", delete_ids)
                conn.execute(f"delete from jobs where id in ({placeholders})", delete_ids)

        for job_id in delete_ids:
            shutil.rmtree(artifact_root / job_id, ignore_errors=True)
        return len(delete_ids)

    def _row_to_job(self, row: sqlite3.Row) -> JobRecord:
        result = None
        if row["result_json"]:
            result = TaskResult(**json.loads(row["result_json"]))
        job = JobRecord(
            id=row["id"],
            status=row["status"],
            task=row["task"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            result=result,
            error=row["error"],
        )
        if job.result:
            job.result.artifacts = self.get_artifacts(job.id)
        return job


def _json_dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _dt(value: datetime | str) -> str:
    return value.isoformat() if isinstance(value, datetime) else value
