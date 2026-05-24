from __future__ import annotations

import json
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schemas import ArtifactRecord


class ArtifactRecorder:
    def __init__(self, root: Path, job_id: str):
        self.root = root
        self.job_id = job_id
        self.job_dir = root / job_id
        self.job_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._records: list[ArtifactRecord] = []

    @property
    def records(self) -> list[ArtifactRecord]:
        return self.snapshot()

    def snapshot(self) -> list[ArtifactRecord]:
        with self._lock:
            return list(self._records)

    def add_text(self, filename: str, text: str, *, kind: str, label: str) -> ArtifactRecord:
        path = self.job_dir / filename
        path.write_text(text, encoding="utf-8")
        return self._record(path, kind=kind, label=label, content_type="text/plain")

    def add_json(self, filename: str, data: Any, *, kind: str, label: str) -> ArtifactRecord:
        path = self.job_dir / filename
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return self._record(path, kind=kind, label=label, content_type="application/json")

    def capture_screenshot(
        self,
        adb_path: str,
        device_id: str | None,
        filename: str,
        *,
        label: str,
    ) -> ArtifactRecord | None:
        cmd = [adb_path]
        if device_id:
            cmd.extend(["-s", device_id])
        cmd.extend(["exec-out", "screencap", "-p"])

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=20, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None

        if result.returncode != 0 or not result.stdout:
            return None

        path = self.job_dir / filename
        path.write_bytes(result.stdout)
        return self._record(path, kind="screenshot", label=label, content_type="image/png")

    def _record(
        self,
        path: Path,
        *,
        kind: str,
        label: str,
        content_type: str,
    ) -> ArtifactRecord:
        record = ArtifactRecord(
            id=uuid.uuid4().hex,
            job_id=self.job_id,
            kind=kind,
            label=label,
            path=str(path),
            url=f"/artifacts/{self.job_id}/{path.name}",
            content_type=content_type,
            created_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._records.append(record)
        return record
