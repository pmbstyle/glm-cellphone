from __future__ import annotations

import builtins
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone


class TaskLog:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._parts: list[str] = []

    def write(self, text: str) -> None:
        if not text:
            return
        with self._lock:
            self._parts.append(text)

    def line(self, text: str) -> None:
        self.write(f"[{_timestamp()}] {text}\n")

    def flush(self) -> None:
        pass

    def text(self) -> str:
        with self._lock:
            return "".join(self._parts)

    def tail(self, limit: int) -> str:
        value = self.text()
        if limit <= 0 or len(value) <= limit:
            return value
        return value[-limit:]


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def capture_prints(task_log: TaskLog) -> Iterator[None]:
    original_print = builtins.print

    def captured_print(*args, **kwargs) -> None:
        file = kwargs.get("file")
        if file is not None:
            original_print(*args, **kwargs)
            return
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        task_log.write(sep.join(str(arg) for arg in args) + end)

    builtins.print = captured_print
    try:
        yield
    finally:
        builtins.print = original_print
