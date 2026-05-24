from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .schemas import TaskStatus

TAKEOVER_ACTIONS = {"Take_over", "Interact"}

DIAGNOSTIC_PREFIX_CHARS = 320

FAILURE_PATTERNS = (
    r"^(?:i\s+)?(?:am\s+)?unable\b",
    r"^(?:i\s+)?(?:can(?:not|'t)|could not)\b",
    r"^(?:i\s+)?failed\b",
    r"^(?:the\s+)?task\s+(?:failed|is\s+incomplete|was\s+incomplete)\b",
    r"^(?:an?\s+)?error\b",
    r"^(?:no|not)\s+(?:matching|suitable|available)\b",
    r"\b(?:could not find|not found|no suitable|not available|not possible)\b",
    r"\b(?:не удалось|не могу|не смог|не найд|невозможно|ошиб|отмен|нет подход)\b",
    r"(?:无法|不能|未找到|没有合适|失败|错误)",
)

RETRYABLE_PATTERNS = (
    r"\bmodel error\b",
    r"\bapi\b",
    r"\btimeout\b",
    r"\btimed out\b",
    r"\bconnection\b",
    r"\bnetwork\b",
    r"\brate limit\b",
    r"\btemporar(?:y|ily)\b",
    r"\bunknown action\b",
    r"\bfailed to parse\b",
    r"\baction failed\b",
    r"\bapp not found\b",
    r"\bmax steps reached\b",
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
    lead = _diagnostic_lead(message)
    return any(re.search(pattern, lead) for pattern in FAILURE_PATTERNS)


def is_retryable_message(message: str | None) -> bool:
    if not message:
        return False
    lead = _diagnostic_lead(message)
    return any(re.search(pattern, lead) for pattern in RETRYABLE_PATTERNS)


def _action_message(action: dict[str, Any] | None) -> str | None:
    if not action:
        return None
    value = action.get("message")
    return value if isinstance(value, str) else None


def _diagnostic_lead(message: str) -> str:
    normalized = re.sub(r"\s+", " ", message.strip().lower())
    return normalized[:DIAGNOSTIC_PREFIX_CHARS]
