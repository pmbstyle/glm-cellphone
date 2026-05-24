from __future__ import annotations

import threading

from .logs import TaskLog


class JobControl:
    def __init__(self) -> None:
        self.pause_requested = threading.Event()
        self.stop_requested = threading.Event()
        self._pause_logged = False

    def pause(self) -> None:
        self.pause_requested.set()

    def resume(self) -> None:
        self.pause_requested.clear()
        self._pause_logged = False

    def stop(self) -> None:
        self.stop_requested.set()
        self.pause_requested.clear()

    def wait_if_paused(self, logs: TaskLog) -> bool:
        if not self.pause_requested.is_set():
            return False
        if not self._pause_logged:
            logs.line("run paused")
            self._pause_logged = True
        while self.pause_requested.is_set() and not self.stop_requested.is_set():
            self.pause_requested.wait(timeout=0.25)
        if not self.stop_requested.is_set() and self._pause_logged:
            logs.line("run resumed")
        self._pause_logged = False
        return self.stop_requested.is_set()

