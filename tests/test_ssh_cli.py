from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from clients.ssh_cli import CliCommandResult, SshCliClient


class FakeTransport:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeChannel:
    def __init__(self, fail_on_send: str | None = None) -> None:
        self.closed = False
        self.sent: list[str] = []
        self.fail_on_send = fail_on_send

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def send(self, command: str) -> None:
        if self.fail_on_send and self.fail_on_send in command:
            raise RuntimeError("send failed")
        self.sent.append(command)

    def close(self) -> None:
        self.closed = True


class FakeSshClient:
    def __init__(self, channel: FakeChannel) -> None:
        self.channel = channel
        self.transport = FakeTransport()
        self.closed = False

    def set_missing_host_key_policy(self, policy) -> None:
        self.policy = policy

    def connect(self, **kwargs) -> None:
        self.connect_kwargs = kwargs

    def invoke_shell(self, **kwargs) -> FakeChannel:
        self.invoke_kwargs = kwargs
        return self.channel

    def get_transport(self) -> FakeTransport:
        return self.transport

    def close(self) -> None:
        self.closed = True


def install_fake_paramiko(monkeypatch: pytest.MonkeyPatch, fake_client: FakeSshClient) -> None:
    fake_paramiko = SimpleNamespace(
        SSHClient=lambda: fake_client,
        AutoAddPolicy=lambda: object(),
    )
    monkeypatch.setitem(sys.modules, "paramiko", fake_paramiko)


def test_ssh_cli_closes_channel_transport_and_client(monkeypatch: pytest.MonkeyPatch):
    channel = FakeChannel()
    fake_client = FakeSshClient(channel)
    install_fake_paramiko(monkeypatch, fake_client)
    monkeypatch.setattr(SshCliClient, "_read_available", staticmethod(lambda *args, **kwargs: "ok"))

    results = SshCliClient("host", "user", "password").run_commands(["show version"])

    assert results == [CliCommandResult(command="show version", output="ok")]
    assert channel.sent == ["show version\n", "exit\n"]
    assert channel.closed
    assert fake_client.transport.closed
    assert fake_client.closed


def test_ssh_cli_closes_session_when_command_send_fails(monkeypatch: pytest.MonkeyPatch):
    channel = FakeChannel(fail_on_send="show")
    fake_client = FakeSshClient(channel)
    install_fake_paramiko(monkeypatch, fake_client)
    monkeypatch.setattr(SshCliClient, "_read_available", staticmethod(lambda *args, **kwargs: "ok"))

    with pytest.raises(RuntimeError, match="send failed"):
        SshCliClient("host", "user", "password").run_commands(["show version"])

    assert channel.closed
    assert fake_client.transport.closed
    assert fake_client.closed
