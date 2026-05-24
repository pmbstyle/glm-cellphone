from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .adb import find_adb, inspect_adb, list_devices
from .artifacts import ArtifactRecorder
from .config import get_settings
from .control import JobControl
from .logs import TaskLog
from .mcp_server import mcp
from .runner import PhoneTaskRunner
from .schemas import (
    ClearHistoryResponse,
    DeviceRecord,
    DevicesResponse,
    HealthResponse,
    JobActionResponse,
    JobArtifactsResponse,
    JobListResponse,
    JobLogsResponse,
    JobRecord,
    StatsResponse,
    TaskRequest,
    TaskResult,
)
from .store import JobStore

settings = get_settings()
runner = PhoneTaskRunner(settings)
phone_lock = asyncio.Lock()
jobs: dict[str, JobRecord] = {}
job_logs: dict[str, TaskLog] = {}
job_controls: dict[str, JobControl] = {}
job_artifacts: dict[str, ArtifactRecorder] = {}
state_dir = Path(settings.state_dir)
artifact_root = state_dir / "artifacts"
store = JobStore(state_dir / "glm-cellphone.sqlite3")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="GLM Cellphone", version="0.1.0", lifespan=lifespan)
app.mount("/mcp", mcp.streamable_http_app(), name="mcp")
app.mount("/artifacts", StaticFiles(directory=artifact_root, check_dir=False), name="artifacts")
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "web", check_dir=False),
    name="static",
)


def _adb_status():
    adb_path = find_adb(settings.adb_path, settings.extra_adb_paths)
    return inspect_adb(adb_path)


async def _run_task(
    request: TaskRequest,
    task_id: str | None = None,
    task_log: TaskLog | None = None,
    artifacts: ArtifactRecorder | None = None,
    control: JobControl | None = None,
) -> TaskResult:
    async with phone_lock:
        return await asyncio.to_thread(
            runner.run,
            request,
            task_id,
            task_log,
            artifacts,
            control,
        )


@app.get("/", include_in_schema=False)
async def dashboard() -> FileResponse:
    return FileResponse(Path(__file__).parent / "web" / "index.html")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    adb_status = _adb_status()
    return HealthResponse(
        ok=bool(settings.resolved_api_key) and adb_status.available,
        api_configured=bool(settings.resolved_api_key),
        base_url=settings.base_url,
        model=settings.model_name,
        adb_available=adb_status.available,
        adb_path=adb_status.path,
        busy=phone_lock.locked(),
    )


@app.get("/devices", response_model=DevicesResponse)
async def devices() -> DevicesResponse:
    adb_status = _adb_status()
    if not adb_status.available:
        return DevicesResponse(
            adb_available=False,
            adb_path=adb_status.path,
            adb_version=adb_status.version,
            error=adb_status.error,
            devices=[],
        )
    try:
        connected = list_devices(adb_status.path)
    except RuntimeError as exc:
        return DevicesResponse(
            adb_available=True,
            adb_path=adb_status.path,
            adb_version=adb_status.version,
            error=str(exc),
            devices=[],
        )
    return DevicesResponse(
        adb_available=True,
        adb_path=adb_status.path,
        adb_version=adb_status.version,
        devices=[
            DeviceRecord(serial=d.serial, state=d.state, details=d.details)
            for d in connected
        ],
    )


@app.post("/tasks", response_model=TaskResult)
async def run_task(request: TaskRequest) -> TaskResult:
    try:
        return await _run_task(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def _run_job(job_id: str, request: TaskRequest) -> None:
    now = datetime.now(timezone.utc)
    log = job_logs[job_id]
    control = job_controls[job_id]
    initial_status = "stopping" if control.stop_requested.is_set() else "running"
    if control.pause_requested.is_set():
        initial_status = "paused"
    jobs[job_id] = jobs[job_id].model_copy(update={"status": initial_status, "updated_at": now})
    store.upsert_job(jobs[job_id])
    artifacts = ArtifactRecorder(artifact_root, job_id)
    job_artifacts[job_id] = artifacts
    artifacts.add_json(
        "request.json",
        request.model_dump(mode="json"),
        kind="request",
        label="Request",
    )
    try:
        result: TaskResult | None = None
        for attempt in range(1, request.max_retries + 2):
            if attempt > 1:
                log.line(f"retry attempt {attempt}/{request.max_retries + 1}: restarting task")
                jobs[job_id] = jobs[job_id].model_copy(
                    update={"status": "retrying", "updated_at": datetime.now(timezone.utc)}
                )
                store.upsert_job(jobs[job_id])
            result = await _run_task(
                request,
                task_id=job_id,
                task_log=log,
                artifacts=artifacts,
                control=control,
            )
            result = result.model_copy(update={"attempts": attempt})
            if not (result.status == "failed" and result.retryable):
                break
            if attempt > request.max_retries:
                break
        if result is None:
            raise RuntimeError("Job produced no result")
        artifacts.add_text("run.log", log.text(), kind="log", label="Run log")
        artifacts.add_json(
            "result.json",
            result.model_dump(mode="json"),
            kind="result",
            label="Result",
        )
        artifact_snapshot = artifacts.snapshot()
        result = result.model_copy(update={"artifacts": artifact_snapshot, "logs": log.text()})
        jobs[job_id] = jobs[job_id].model_copy(
            update={
                "status": result.status,
                "result": result,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        store.add_artifacts(artifact_snapshot)
        store.upsert_job(jobs[job_id])
    except Exception as exc:
        log.line(f"task failed: {exc}")
        artifacts.add_text("run.log", log.text(), kind="log", label="Run log")
        store.add_artifacts(artifacts.snapshot())
        jobs[job_id] = jobs[job_id].model_copy(
            update={
                "status": "failed",
                "error": str(exc),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        store.upsert_job(jobs[job_id])
    finally:
        job_controls.pop(job_id, None)
        job_artifacts.pop(job_id, None)


@app.post("/jobs", response_model=JobRecord, status_code=202)
async def create_job(request: TaskRequest) -> JobRecord:
    job_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    job = JobRecord(
        id=job_id,
        status="queued",
        task=request.task,
        created_at=now,
        updated_at=now,
    )
    jobs[job_id] = job
    job_logs[job_id] = TaskLog()
    job_controls[job_id] = JobControl()
    store.upsert_job(job, request=request.model_dump(mode="json"))
    asyncio.create_task(_run_job(job_id, request))
    return job


@app.get("/jobs", response_model=JobListResponse)
async def list_jobs(limit: int = Query(default=100, ge=1, le=500)) -> JobListResponse:
    active_ids = set(jobs)
    stored = store.list_jobs(limit=limit)
    merged = {job.id: job for job in stored}
    for job_id in active_ids:
        merged[job_id] = jobs[job_id]
    ordered = sorted(merged.values(), key=lambda item: item.updated_at, reverse=True)
    return JobListResponse(jobs=ordered[:limit])


@app.delete("/jobs", response_model=ClearHistoryResponse)
async def clear_jobs() -> ClearHistoryResponse:
    active_ids = set(job_controls)
    deleted = store.clear_history(exclude_ids=active_ids, artifact_root=artifact_root)
    for job_id in list(jobs):
        if job_id not in active_ids:
            jobs.pop(job_id, None)
            job_logs.pop(job_id, None)
            job_artifacts.pop(job_id, None)
    return ClearHistoryResponse(deleted=deleted, kept_active=len(active_ids))


@app.post("/jobs/{job_id}/pause", response_model=JobActionResponse)
async def pause_job(job_id: str) -> JobActionResponse:
    control = job_controls.get(job_id)
    job = jobs.get(job_id)
    if control is None or job is None:
        raise HTTPException(status_code=404, detail="Active job not found")
    if job.status not in {"queued", "running", "retrying"}:
        raise HTTPException(status_code=409, detail=f"Job is {job.status}")
    control.pause()
    job_logs[job_id].line("pause requested")
    jobs[job_id] = job.model_copy(
        update={"status": "paused", "updated_at": datetime.now(timezone.utc)}
    )
    store.upsert_job(jobs[job_id])
    return JobActionResponse(id=job_id, status="paused", message="Pause requested")


@app.post("/jobs/{job_id}/resume", response_model=JobActionResponse)
async def resume_job(job_id: str) -> JobActionResponse:
    control = job_controls.get(job_id)
    job = jobs.get(job_id)
    if control is None or job is None:
        raise HTTPException(status_code=404, detail="Active job not found")
    if job.status != "paused":
        raise HTTPException(status_code=409, detail=f"Job is {job.status}")
    control.resume()
    job_logs[job_id].line("resume requested")
    jobs[job_id] = job.model_copy(
        update={"status": "running", "updated_at": datetime.now(timezone.utc)}
    )
    store.upsert_job(jobs[job_id])
    return JobActionResponse(id=job_id, status="running", message="Resume requested")


@app.post("/jobs/{job_id}/stop", response_model=JobActionResponse)
async def stop_job(job_id: str) -> JobActionResponse:
    control = job_controls.get(job_id)
    job = jobs.get(job_id)
    if control is None or job is None:
        raise HTTPException(status_code=404, detail="Active job not found")
    if job.status in {"completed", "failed", "needs_takeover", "stopped"}:
        raise HTTPException(status_code=409, detail=f"Job is {job.status}")
    control.stop()
    job_logs[job_id].line("stop requested")
    jobs[job_id] = job.model_copy(
        update={"status": "stopping", "updated_at": datetime.now(timezone.utc)}
    )
    store.upsert_job(jobs[job_id])
    return JobActionResponse(id=job_id, status="stopping", message="Stop requested")


@app.get("/stats", response_model=StatsResponse)
async def stats() -> StatsResponse:
    return store.stats()


@app.get("/jobs/{job_id}", response_model=JobRecord)
async def get_job(job_id: str) -> JobRecord:
    job = jobs.get(job_id) or store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/jobs/{job_id}/artifacts", response_model=JobArtifactsResponse)
async def get_job_artifacts(job_id: str) -> JobArtifactsResponse:
    job = jobs.get(job_id) or store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    recorder = job_artifacts.get(job_id)
    if recorder is not None:
        artifacts = recorder.snapshot()
    else:
        artifacts = store.get_artifacts(job_id)

    return JobArtifactsResponse(id=job_id, status=job.status, artifacts=artifacts)


@app.get("/jobs/{job_id}/logs", response_model=JobLogsResponse)
async def get_job_logs(
    job_id: str,
    tail: int = Query(default=20000, ge=0, le=200000),
) -> JobLogsResponse:
    job = jobs.get(job_id) or store.get_job(job_id)
    log = job_logs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if log is not None:
        logs = log.tail(tail)
    elif job.result:
        logs = job.result.logs
        if tail > 0 and len(logs) > tail:
            logs = logs[-tail:]
    else:
        logs = ""
    return JobLogsResponse(id=job_id, status=job.status, logs=logs)
