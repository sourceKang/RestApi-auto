from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import TextIO

from clients.ssh_cli import CliCommandResult, normalize_cli_output


LEGACY_KEX = "diffie-hellman-group14-sha1"
LEGACY_HOST_KEY = "ssh-rsa"
LEGACY_MAC = "hmac-sha1"
PROMPT_PATTERN = re.compile(r"(?:^|\n)[^\n]*[>#]\s*$")
ASKPASS_ENV = "RESTAPI_SSH_ASKPASS_PASSWORD"


class _ProcessOutputBuffer:
    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._text = ""
        self._condition = threading.Condition()
        self._closed = False
        self._thread = threading.Thread(target=self._pump, name="legacy-ssh-output", daemon=True)
        self._thread.start()

    def position(self) -> int:
        with self._condition:
            return len(self._text)

    def wait_for_prompt(self, start: int, process: subprocess.Popen[str], timeout: float, label: str) -> str:
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                output = self._text[start:]
                normalized = _prompt_text(output)
                if PROMPT_PATTERN.search(normalized):
                    return normalize_cli_output(output)
                if self._closed or process.poll() is not None:
                    detail = normalize_cli_output(output)[-1000:]
                    raise RuntimeError(f"Legacy SSH closed before {label} prompt. Output: {detail}")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    detail = normalize_cli_output(output)[-1000:]
                    raise TimeoutError(f"Legacy SSH timed out waiting for {label} prompt. Output: {detail}")
                self._condition.wait(min(remaining, 0.2))

    def _pump(self) -> None:
        try:
            while True:
                chunk = self._stream.read(1)
                if not chunk:
                    break
                with self._condition:
                    self._text += chunk
                    self._condition.notify_all()
        finally:
            with self._condition:
                self._closed = True
                self._condition.notify_all()


class LegacyOpenSshCliClient:
    """Windows OpenSSH backend for explicitly configured legacy lab OLTs."""

    def __init__(self, host: str, username: str, password: str, *, timeout: float = 15) -> None:
        self.host = host
        self.username = username
        self.password = password
        self.timeout = timeout

    def run_commands(self, commands: list[str]) -> list[CliCommandResult]:
        ssh_executable = shutil.which("ssh.exe") or shutil.which("ssh")
        if not ssh_executable:
            raise RuntimeError("Windows OpenSSH client is required for legacy OLT CLI verification")

        process: subprocess.Popen[str] | None = None
        with tempfile.TemporaryDirectory(prefix="restapi-ssh-askpass-") as temp_dir:
            askpass_path = Path(temp_dir) / "askpass.cmd"
            askpass_path.write_text(_askpass_script(), encoding="ascii")
            environment = os.environ.copy()
            environment.update(
                {
                    ASKPASS_ENV: self.password,
                    "SSH_ASKPASS": str(askpass_path),
                    "SSH_ASKPASS_REQUIRE": "force",
                    "DISPLAY": "restapi-auto",
                }
            )
            try:
                process = subprocess.Popen(
                    self.ssh_args(ssh_executable),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=environment,
                    shell=False,
                )
                if process.stdout is None:
                    raise RuntimeError("Legacy SSH stdout pipe is unavailable")
                output_buffer = _ProcessOutputBuffer(process.stdout)
                output_buffer.wait_for_prompt(0, process, self.timeout, "login")
                results: list[CliCommandResult] = []
                for command in commands:
                    start = output_buffer.position()
                    self._write_command(process, command)
                    output = output_buffer.wait_for_prompt(start, process, self.timeout, command)
                    results.append(CliCommandResult(command=command, output=output))
                return results
            finally:
                environment[ASKPASS_ENV] = ""
                self._close_process(process)

    def ssh_args(self, ssh_executable: str = "ssh.exe") -> list[str]:
        return [
            ssh_executable,
            "-tt",
            "-o",
            f"KexAlgorithms=+{LEGACY_KEX}",
            "-o",
            f"HostKeyAlgorithms=+{LEGACY_HOST_KEY}",
            "-o",
            f"PubkeyAcceptedAlgorithms=+{LEGACY_HOST_KEY}",
            "-o",
            f"MACs=+{LEGACY_MAC}",
            "-o",
            "PubkeyAuthentication=no",
            "-o",
            "PreferredAuthentications=password,keyboard-interactive",
            "-o",
            "NumberOfPasswordPrompts=1",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=NUL",
            "-o",
            f"ConnectTimeout={max(1, int(self.timeout))}",
            f"{self.username}@{self.host}",
        ]

    @staticmethod
    def _write_command(process: subprocess.Popen[str], command: str) -> None:
        if process.stdin is None:
            raise RuntimeError("Legacy SSH stdin pipe is unavailable")
        process.stdin.write(command + "\n")
        process.stdin.flush()

    @classmethod
    def _close_process(cls, process: subprocess.Popen[str] | None) -> None:
        if process is None or process.poll() is not None:
            return
        try:
            cls._write_command(process, "exit")
            process.wait(timeout=3)
        except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


def _askpass_script() -> str:
    return (
        "@echo off\r\n"
        "powershell.exe -NoProfile -NonInteractive -Command "
        '"[Console]::Out.Write([Environment]::GetEnvironmentVariable('
        f"'{ASKPASS_ENV}'"
        '))"\r\n'
    )


def _prompt_text(output: str) -> str:
    return output.replace("\r", "\n")