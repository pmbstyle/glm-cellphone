from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .schemas import TaskStatus

TAKEOVER_ACTIONS = {"Take_over", "Interact"}

FAILURE_MARKERS = (
    "unable",
    "can't",
    "cannot",
    "could not",
    "failed",
    "failure",
    "not found",
    "no suitable",
    "not available",
    "not possible",
    "cancelled",
    "canceled",
    "incomplete",
    "unsuccessful",
    "error",
    "не удалось",
    "не могу",
    "не смог",
    "не найд",
    "невозможно",
    "ошиб",
    "отмен",
    "нет подход",
    "无法",
    "不能",
    "未找到",
    "没有合适",
    "失败",
    "错误",
)

RETRYABLE_MARKERS = (
    "model error",
    "api",
    "timeout",
    "timed out",
    "connection",
    "network",
    "rate limit",
    "temporary",
    "temporarily",
    "unknown action",
    "failed to parse",
    "action failed",
    "app not found",
    "max steps reached",
)


@dataclass(frozen=True)
class StepOutcome:
    status: TaskStatus | None
    message: str | None = None
    retryable: bool = False


def classify_step_outcome(
    *,
    action: dict[str, Any] | None,
    success: bool,
    finished: bool,
    message: str | None,
    takeover_requested: bool,
    stop_on_takeover: bool,
) -> StepOutcome:
    action_name = action.get("action") if action else None
    action_type = action.get("_metadata") if action else None
    resolved_message = message or _action_message(action)

    if takeover_requested or (action_name in TAKEOVER_ACTIONS and stop_on_takeover):
        return StepOutcome(
            status="needs_takeover",
            message=resolved_message or "Manual takeover is required.",
        )

    if finished:
        if not success:
            return StepOutcome(
                status="failed",
                message=resolved_message or "Task failed.",
                retryable=is_retryable_message(resolved_message),
            )
        if action_type == "finish" and is_failure_message(resolved_message):
            return StepOutcome(
                status="failed",
                message=resolved_message or "Task failed.",
                retryable=is_retryable_message(resolved_message),
            )
        return StepOutcome(status="completed", message=resolved_message or "Task completed.")

    if not success and resolved_message:
        return StepOutcome(
            status=None,
            message=resolved_message,
            retryable=is_retryable_message(resolved_message),
        )

    return StepOutcome(status=None)


def is_failure_message(message: str | None) -> bool:
    if not message:
        return False
    lowered = message.lower()
    return any(marker in lowered for marker in FAILURE_MARKERS)


def is_retryable_message(message: str | None) -> bool:
    if not message:
        return False
    lowered = message.lower()
    return any(marker in lowered for marker in RETRYABLE_MARKERS)


def _action_message(action: dict[str, Any] | None) -> str | None:
    if not action:
        return None
    value = action.get("message")
    return value if isinstance(value, str) else None

