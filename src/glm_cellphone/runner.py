from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import cast

from .adb import ensure_adb_on_path, find_adb, inspect_adb, list_devices
from .artifacts import ArtifactRecorder
from .config import Settings
from .control import JobControl
from .logs import TaskLog, capture_prints
from .outcome import classify_step_outcome
from .schemas import StepRecord, TaskRequest, TaskResult, TaskStatus


class PhoneTaskRunner:
    def __init__(self, settings: Settings):
        self.settings = settings

    def run(
        self,
        request: TaskRequest,
        task_id: str | None = None,
        task_log: TaskLog | None = None,
        artifacts: ArtifactRecorder | None = None,
        control: JobControl | None = None,
    ) -> TaskResult:
        started = datetime.now(timezone.utc)
        t0 = time.monotonic()
        logs = task_log or TaskLog()
        steps: list[StepRecord] = []
        status = "failed"
        message = ""
        retryable = False

        logs.line(f"task started: {request.task}")
        adb_path = find_adb(self.settings.adb_path, self.settings.extra_adb_paths)
        ensure_adb_on_path(adb_path)
        adb_status = inspect_adb(adb_path)
        if not adb_status.available:
            raise RuntimeError(adb_status.error or "adb is not available")
        devices = list_devices(adb_path)
        ready_devices = [device for device in devices if device.state == "device"]
        if request.device_id:
            matching = [device for device in devices if device.serial == request.device_id]
            if not matching:
                raise RuntimeError(f"ADB device {request.device_id!r} was not found.")
            if matching[0].state != "device":
                raise RuntimeError(
                    f"ADB device {request.device_id!r} is {matching[0].state}, not ready."
                )
        elif not ready_devices:
            states = ", ".join(f"{device.serial}:{device.state}" for device in devices)
            hint = f" Seen devices: {states}." if states else ""
            raise RuntimeError(
                "No authorized Android device found. Enable USB debugging and accept the "
                f"computer authorization prompt on the phone.{hint}"
            )
        logs.line(
            "adb ready: "
            + (request.device_id or ready_devices[0].serial if ready_devices else "unknown")
        )
        active_device_id = request.device_id or (ready_devices[0].serial if ready_devices else None)
        if artifacts and active_device_id:
            artifacts.capture_screenshot(adb_path, active_device_id, "start.png", label="Start")

        api_key = self.settings.resolved_api_key
        if not api_key:
            raise RuntimeError("Z.AI API key is not configured. Set ZAI_KEY in .env.")
        logs.line(f"model: {self.settings.model_name} via {self.settings.base_url}")

        # Import lazily so health/device endpoints work even before dependencies are installed.
        from phone_agent import PhoneAgent
        from phone_agent.agent import AgentConfig
        from phone_agent.model import ModelConfig

        lang = request.lang or self.settings.default_lang
        max_steps = request.max_steps or self.settings.default_max_steps
        takeover_messages: list[str] = []

        def confirm_sensitive_action(prompt: str) -> bool:
            if request.allow_sensitive_actions:
                return True
            takeover_messages.append(prompt)
            return False

        def record_takeover(prompt: str) -> None:
            takeover_messages.append(prompt)

        model_config = ModelConfig(
            base_url=self.settings.base_url,
            api_key=api_key,
            model_name=self.settings.model_name,
            lang=lang,
        )
        agent_config = AgentConfig(
            max_steps=max_steps,
            device_id=request.device_id,
            lang=lang,
            verbose=True,
        )
        agent = PhoneAgent(
            model_config=model_config,
            agent_config=agent_config,
            confirmation_callback=confirm_sensitive_action,
            takeover_callback=record_takeover,
        )

        with capture_prints(logs):
            for index in range(1, max_steps + 1):
                if control and control.stop_requested.is_set():
                    status = "stopped"
                    message = "Run stopped by user."
                    break
                if control and control.wait_if_paused(logs):
                    status = "stopped"
                    message = "Run stopped by user."
                    break
                logs.line(f"step {index}/{max_steps}: begin")
                if artifacts and active_device_id:
                    artifacts.capture_screenshot(
                        adb_path,
                        active_device_id,
                        f"step-{index:03d}-before.png",
                        label=f"Step {index} before",
                    )
                step_result = agent.step(request.task if index == 1 else None)
                if artifacts and active_device_id:
                    artifacts.capture_screenshot(
                        adb_path,
                        active_device_id,
                        f"step-{index:03d}-after.png",
                        label=f"Step {index} after",
                    )
                action = step_result.action
                record = StepRecord(
                    index=index,
                    success=step_result.success,
                    finished=step_result.finished,
                    action=action,
                    thinking=step_result.thinking,
                    message=step_result.message,
                )
                steps.append(record)
                logs.line(f"step {index}/{max_steps}: action={action}")
                if step_result.message:
                    logs.line(f"step {index}/{max_steps}: message={step_result.message}")
                logs.line(
                    "step "
                    f"{index}/{max_steps}: success={step_result.success} "
                    f"finished={step_result.finished}"
                )

                outcome = classify_step_outcome(
                    action=action,
                    success=step_result.success,
                    finished=step_result.finished,
                    message=step_result.message,
                    takeover_requested=bool(takeover_messages)
                    and not request.allow_sensitive_actions,
                    stop_on_takeover=request.stop_on_takeover,
                )
                if outcome.message:
                    message = outcome.message
                retryable = retryable or outcome.retryable
                if outcome.status:
                    status = outcome.status
                    break
            else:
                status = "failed"
                message = f"Max steps reached ({max_steps})"
                retryable = True

        finished = datetime.now(timezone.utc)
        final_status = cast(TaskStatus, status)
        logs.line(f"task finished: status={final_status} message={message or status}")
        if artifacts and active_device_id:
            artifacts.capture_screenshot(adb_path, active_device_id, "final.png", label="Final")
        return TaskResult(
            id=task_id,
            status=final_status,
            task=request.task,
            message=message or status,
            started_at=started,
            finished_at=finished,
            duration_seconds=round(time.monotonic() - t0, 3),
            device_id=request.device_id,
            steps=steps,
            logs=logs.text(),
            retryable=retryable,
            artifacts=artifacts.records if artifacts else [],
        )


def describe_runtime_env(settings: Settings) -> dict[str, str | None]:
    adb_path = find_adb(settings.adb_path, settings.extra_adb_paths)
    return {
        "path": os.environ.get("PATH"),
        "adb_path": adb_path,
        "base_url": settings.base_url,
        "model": settings.model_name,
    }
