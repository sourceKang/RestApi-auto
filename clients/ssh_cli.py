from __future__ import annotations

import re
import time
from dataclasses import dataclass


ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
LOGOUT_CONFIRM_PROMPT = re.compile(r"logout\s+system\s+now\s*\(y/n\)\?", re.IGNORECASE)
YES_NO_CONFIRM_PROMPT = re.compile(r"(?:please\s+)?confirm\s*\[y/n\]|confirm\s*\(y/n\)", re.IGNORECASE)


@dataclass(frozen=True)
class CliCommandResult:
    command: str
    output: str


class SshCliClient:
    def __init__(self, host: str, username: str, password: str, *, timeout: float = 15) -> None:
        self.host = host
        self.username = username
        self.password = password
        self.timeout = timeout

    def run_commands(self, commands: list[str]) -> list[CliCommandResult]:
        try:
            import paramiko
        except ImportError as error:
            raise RuntimeError("paramiko is required for SSH CLI verification") from error

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.host,
            username=self.username,
            password=self.password,
            look_for_keys=False,
            allow_agent=False,
            timeout=self.timeout,
            banner_timeout=self.timeout,
            auth_timeout=self.timeout,
        )
        channel = None
        try:
            channel = client.invoke_shell(width=200, height=120)
            channel.settimeout(3)
            self._read_available(channel)
            results = []
            for command in commands:
                channel.send(command + "\n")
                output = self._read_available(channel)
                if YES_NO_CONFIRM_PROMPT.search(output):
                    channel.send("y\n")
                    output = "\n".join([output, self._read_available(channel, first_wait=0.2, idle_wait=0.4, max_wait=8)])
                results.append(CliCommandResult(command=command, output=output))
            self._logout(channel)
            return results
        finally:
            if channel is not None:
                channel.close()
            transport = client.get_transport()
            if transport is not None:
                transport.close()
            client.close()

    def _logout(self, channel) -> None:
        channel.send("exit\n")
        output = self._read_available(channel, first_wait=0.2, idle_wait=0.2, max_wait=2)
        if LOGOUT_CONFIRM_PROMPT.search(output):
            channel.send("y\n")
            self._read_available(channel, first_wait=0.2, idle_wait=0.2, max_wait=2)

    @staticmethod
    def _read_available(channel, *, first_wait: float = 0.8, idle_wait: float = 0.4, max_wait: float = 8) -> str:
        time.sleep(first_wait)
        chunks: list[str] = []
        deadline = time.time() + max_wait
        idle_deadline = time.time() + idle_wait
        while time.time() < deadline and time.time() < idle_deadline:
            if channel.recv_ready():
                chunks.append(channel.recv(65535).decode("utf-8", errors="replace"))
                idle_deadline = time.time() + idle_wait
            else:
                time.sleep(0.1)
        return normalize_cli_output("".join(chunks))


def normalize_cli_output(output: str) -> str:
    output = ANSI_ESCAPE.sub("", output)
    output = output.replace("\r", "\n")
    lines = []
    for line in output.splitlines():
        cleaned = line.strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)
