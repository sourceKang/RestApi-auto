from __future__ import annotations

import platform
import subprocess
import time
from dataclasses import asdict, dataclass
from typing import Any

import pytest

from utils.allure_helpers import attach_json


@dataclass
class PingResult:
    target: str
    checkpoint: str
    command: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    duration_seconds: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def assert_ping_reachable(
    target: str,
    checkpoint: str,
    context: dict[str, Any] | None = None,
    count: int = 2,
    timeout_ms: int = 2000,
) -> PingResult:
    result = ping_host(target, checkpoint, count=count, timeout_ms=timeout_ms)
    attachment = asdict(result)
    attachment["ok"] = result.ok
    if context:
        attachment["context"] = context
    attach_json(f"Node connectivity ping {checkpoint}", attachment)
    if not result.ok:
        pytest.fail(
            f"Node connectivity ping failed at {checkpoint}: target={target}, "
            f"returncode={result.returncode}, command={' '.join(result.command)}"
        )
    return result


def ping_host(target: str, checkpoint: str, count: int = 2, timeout_ms: int = 2000) -> PingResult:
    command = ping_command(target, count=count, timeout_ms=timeout_ms)
    timeout_seconds = max(5.0, count * (timeout_ms / 1000.0) + 2.0)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return PingResult(
            target=target,
            checkpoint=checkpoint,
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_seconds=round(time.monotonic() - started, 3),
        )
    except FileNotFoundError as exc:
        return PingResult(
            target=target,
            checkpoint=checkpoint,
            command=command,
            returncode=None,
            stdout="",
            stderr=str(exc),
            duration_seconds=round(time.monotonic() - started, 3),
        )
    except subprocess.TimeoutExpired as exc:
        return PingResult(
            target=target,
            checkpoint=checkpoint,
            command=command,
            returncode=None,
            stdout=exc.stdout or "",
            stderr=exc.stderr or f"ping timed out after {timeout_seconds:.1f}s",
            duration_seconds=round(time.monotonic() - started, 3),
        )


def ping_command(target: str, count: int = 2, timeout_ms: int = 2000) -> list[str]:
    if platform.system().casefold() == "windows":
        return ["ping", "-n", str(count), "-w", str(timeout_ms), target]
    timeout_seconds = max(1, int(timeout_ms / 1000))
    return ["ping", "-c", str(count), "-W", str(timeout_seconds), target]
