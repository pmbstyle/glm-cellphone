from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AdbDevice:
    serial: str
    state: str
    details: str = ""


@dataclass(frozen=True)
class AdbStatus:
    available: bool
    path: str | None
    version: str | None = None
    error: str | None = None


def _candidate_paths(extra_paths: list[str] | None = None) -> list[Path]:
    home = Path.home()
    candidates = [
        Path("/opt/homebrew/bin/adb"),
        Path("/usr/local/bin/adb"),
        home / "Library" / "Android" / "sdk" / "platform-tools" / "adb",
        home / "Downloads" / "platform-tools" / "adb",
    ]
    for item in extra_paths or []:
        if not item:
            continue
        path = Path(item).expanduser()
        candidates.append(path if path.name == "adb" else path / "adb")
    return candidates


def find_adb(
    configured_path: str | None = None,
    extra_paths: list[str] | None = None,
) -> str | None:
    if configured_path:
        path = Path(configured_path).expanduser()
        if path.exists() and os.access(path, os.X_OK):
            return str(path)

    path_from_env = shutil.which("adb")
    if path_from_env:
        return path_from_env

    for candidate in _candidate_paths(extra_paths):
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def ensure_adb_on_path(adb_path: str | None) -> None:
    if not adb_path:
        return
    adb_dir = str(Path(adb_path).parent)
    current = os.environ.get("PATH", "")
    if adb_dir not in current.split(os.pathsep):
        os.environ["PATH"] = os.pathsep.join([adb_dir, current]) if current else adb_dir


def inspect_adb(adb_path: str | None) -> AdbStatus:
    if not adb_path:
        return AdbStatus(
            available=False,
            path=None,
            error="adb was not found. Set ADB_PATH or add platform-tools to PATH.",
        )

    try:
        result = subprocess.run(
            [adb_path, "version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except OSError as exc:
        return AdbStatus(available=False, path=adb_path, error=str(exc))
    except subprocess.TimeoutExpired:
        return AdbStatus(available=False, path=adb_path, error="adb version timed out")

    if result.returncode != 0:
        return AdbStatus(
            available=False,
            path=adb_path,
            error=(result.stderr or result.stdout).strip() or "adb version failed",
        )

    version = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
    return AdbStatus(available=True, path=adb_path, version=version)


def list_devices(adb_path: str | None) -> list[AdbDevice]:
    if not adb_path:
        return []

    result = subprocess.run(
        [adb_path, "devices", "-l"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or "adb devices failed")

    devices: list[AdbDevice] = []
    for line in result.stdout.splitlines()[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(maxsplit=2)
        serial = parts[0]
        state = parts[1] if len(parts) > 1 else "unknown"
        details = parts[2] if len(parts) > 2 else ""
        devices.append(AdbDevice(serial=serial, state=state, details=details))
    return devices
