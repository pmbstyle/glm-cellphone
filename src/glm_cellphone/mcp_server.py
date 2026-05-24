from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from .config import get_settings
from .schemas import ArtifactRecord, JobRecord, TaskRequest, TaskStatus

TERMINAL_STATUSES: set[TaskStatus] = {
    "completed",
    "failed",
    "needs_takeover",
    "stopped",
}

mcp = FastMCP(
    "GLM Cellphone",
    instructions=(
        "Run Android phone tasks through the local GLM Cellphone service. "
        "Start a task, poll status until it reaches a terminal status, then fetch the result."
    ),
    json_response=True,
    streamable_http_path="/",
)


@mcp.tool()
async def start_phone_task(
    task: str,
    device_id: str | None = None,
    max_steps: int | None = None,
    max_retries: int = 0,
    lang: Literal["en", "cn"] | None = None,
    allow_sensitive_actions: bool = False,
    stop_on_takeover: bool = True,
) -> dict[str, Any]:
    """Start an Android phone task and return a job id for polling."""
    request = TaskRequest(
        task=task,
        device_id=device_id or None,
        max_steps=max_steps,
        max_retries=max_retries,
        lang=lang,
        allow_sensitive_actions=allow_sensitive_actions,
        stop_on_takeover=stop_on_takeover,
    )
    job = await _call_api("start job", lambda api: api.create_job(request))
    return {
        "job_id": job.id,
        "status": job.status,
        "task": job.task,
        "created_at": job.created_at.isoformat(),
        "message": "Task accepted. Poll get_phone_task_status until the status is terminal.",
        "terminal_statuses": sorted(TERMINAL_STATUSES),
    }


@mcp.tool()
async def get_phone_task_status(job_id: str, log_tail: int = 4000) -> dict[str, Any]:
    """Get concise live status for a phone task."""
    job, logs, artifacts = await _job_bundle(job_id, log_tail=log_tail)
    log_summary = _summarize_logs(logs.logs)
    return {
        "job_id": job.id,
        "status": job.status,
        "terminal": job.status in TERMINAL_STATUSES,
        "task": job.task,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "error": job.error,
        "current_step": log_summary["current_step"],
        "last_action": log_summary["last_action"],
        "last_log_lines": log_summary["last_log_lines"],
        "artifacts_count": len(artifacts.artifacts),
        "result_available": job.result is not None,
        "message": _status_message(job),
    }


@mcp.tool()
async def get_phone_task_result(job_id: str, log_tail: int = 8000) -> dict[str, Any]:
    """Get the final result for a phone task, or current status if it is not done."""
    job, logs, artifacts = await _job_bundle(job_id, log_tail=log_tail)
    if job.status not in TERMINAL_STATUSES:
        return {
            "job_id": job.id,
            "status": job.status,
            "terminal": False,
            "message": (
                "Task is still running. Poll get_phone_task_status before requesting result."
            ),
            "last_log_lines": _summarize_logs(logs.logs)["last_log_lines"],
            "artifacts_count": len(artifacts.artifacts),
        }

    result = job.result
    return {
        "job_id": job.id,
        "status": job.status,
        "terminal": True,
        "task": job.task,
        "message": result.message if result else job.error,
        "duration_seconds": result.duration_seconds if result else None,
        "retryable": result.retryable if result else False,
        "attempts": result.attempts if result else None,
        "steps_count": len(result.steps) if result else 0,
        "steps": _summarize_steps(job),
        "artifacts": [_artifact_payload(item) for item in artifacts.artifacts],
        "logs_tail": logs.logs,
    }


@mcp.tool()
async def stop_phone_task(job_id: str) -> dict[str, Any]:
    """Request cooperative stop for a queued or running phone task."""
    action = await _call_api("stop job", lambda api: api.stop_job(job_id))
    return {
        "job_id": action.id,
        "status": action.status,
        "message": action.message,
    }


async def _job_bundle(job_id: str, *, log_tail: int):
    log_tail = max(0, min(log_tail, 200000))
    job = await _call_api("get job", lambda api: api.get_job(job_id))
    logs = await _call_api("get job logs", lambda api: api.get_job_logs(job_id, tail=log_tail))
    artifacts = await _call_api("get job artifacts", lambda api: api.get_job_artifacts(job_id))
    return job, logs, artifacts


async def _call_api(operation: str, callback):
    try:
        from . import api

        return await callback(api)
    except HTTPException as exc:
        raise ToolError(f"{operation} failed: {exc.detail}") from exc
    except ValueError as exc:
        raise ToolError(f"{operation} failed: {exc}") from exc


def _status_message(job: JobRecord) -> str:
    if job.result:
        return job.result.message
    if job.error:
        return job.error
    if job.status in TERMINAL_STATUSES:
        return f"Task finished with status {job.status}."
    return f"Task is {job.status}."


def _summarize_logs(logs: str) -> dict[str, Any]:
    lines = [line for line in logs.splitlines() if line.strip()]
    current_step = None
    last_action = None

    for line in lines:
        step_match = re.search(r"step\s+(\d+)/(\d+):", line)
        if step_match:
            current_step = {
                "index": int(step_match.group(1)),
                "max": int(step_match.group(2)),
            }
        if ": action=" in line:
            last_action = line.split(": action=", 1)[1]

    return {
        "current_step": current_step,
        "last_action": last_action,
        "last_log_lines": lines[-12:],
    }


def _summarize_steps(job: JobRecord) -> list[dict[str, Any]]:
    if not job.result:
        return []
    summary = []
    for step in job.result.steps:
        action = step.action or {}
        summary.append(
            {
                "index": step.index,
                "success": step.success,
                "finished": step.finished,
                "action": action.get("action"),
                "metadata": action.get("_metadata"),
                "message": step.message or action.get("message"),
            }
        )
    return summary


def _artifact_payload(artifact: ArtifactRecord) -> dict[str, Any]:
    url = artifact.url
    base_url = (get_settings().public_base_url or "").rstrip("/")
    if base_url and url.startswith("/"):
        url = f"{base_url}{url}"
    return {
        "id": artifact.id,
        "kind": artifact.kind,
        "label": artifact.label,
        "content_type": artifact.content_type,
        "created_at": artifact.created_at.isoformat(),
        "url": url,
    }
