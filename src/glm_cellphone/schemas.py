from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

TaskStatus = Literal[
    "queued",
    "running",
    "paused",
    "stopping",
    "stopped",
    "completed",
    "failed",
    "needs_takeover",
    "retrying",
]


class TaskRequest(BaseModel):
    task: str = Field(min_length=1)
    device_id: str | None = None
    max_steps: int | None = Field(default=None, ge=1, le=100)
    max_retries: int = Field(default=0, ge=0, le=3)
    lang: Literal["cn", "en"] | None = None
    allow_sensitive_actions: bool = False
    stop_on_takeover: bool = True


class StepRecord(BaseModel):
    index: int
    success: bool
    finished: bool
    action: dict[str, Any] | None
    thinking: str
    message: str | None = None


class ArtifactRecord(BaseModel):
    id: str
    job_id: str
    kind: str
    label: str
    path: str
    url: str
    content_type: str
    created_at: datetime


class TaskResult(BaseModel):
    id: str | None = None
    status: TaskStatus
    task: str
    message: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    device_id: str | None = None
    steps: list[StepRecord] = Field(default_factory=list)
    logs: str = ""
    retryable: bool = False
    attempts: int = 1
    artifacts: list[ArtifactRecord] = Field(default_factory=list)


class JobRecord(BaseModel):
    id: str
    status: TaskStatus
    task: str
    created_at: datetime
    updated_at: datetime
    result: TaskResult | None = None
    error: str | None = None


class JobLogsResponse(BaseModel):
    id: str
    status: TaskStatus
    logs: str


class JobArtifactsResponse(BaseModel):
    id: str
    status: TaskStatus
    artifacts: list[ArtifactRecord] = Field(default_factory=list)


class JobListResponse(BaseModel):
    jobs: list[JobRecord]


class JobActionResponse(BaseModel):
    id: str
    status: TaskStatus
    message: str


class ClearHistoryResponse(BaseModel):
    deleted: int
    kept_active: int


class StatsResponse(BaseModel):
    total: int
    queued: int = 0
    running: int = 0
    paused: int = 0
    stopping: int = 0
    stopped: int = 0
    retrying: int = 0
    completed: int = 0
    failed: int = 0
    needs_takeover: int = 0
    average_duration_seconds: float | None = None


class DeviceRecord(BaseModel):
    serial: str
    state: str
    details: str = ""


class DevicesResponse(BaseModel):
    adb_available: bool
    adb_path: str | None
    adb_version: str | None = None
    error: str | None = None
    devices: list[DeviceRecord] = Field(default_factory=list)


class HealthResponse(BaseModel):
    ok: bool
    api_configured: bool
    base_url: str
    model: str
    adb_available: bool
    adb_path: str | None
    busy: bool
