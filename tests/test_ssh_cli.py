from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from clients.ssh_cli import CliCommandResult, FileTokenSemaphore, SshCliClient, SshSessionPool


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
        self.connect_count = 0

    def set_missing_host_key_policy(self, policy) -> None:
        self.policy = policy

    def connect(self, **kwargs) -> None:
        self.connect_count += 1
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


def test_ssh_cli_confirms_logout_prompt(monkeypatch: pytest.MonkeyPatch):
    channel = FakeChannel()
    fake_client = FakeSshClient(channel)
    install_fake_paramiko(monkeypatch, fake_client)
    outputs = iter(
        [
            "banner",
            "show output",
            "Warning!! The system configuration MAY be modified\nlogout system now(y/n)? >",
            "logout",
        ]
    )
    monkeypatch.setattr(SshCliClient, "_read_available", staticmethod(lambda *args, **kwargs: next(outputs)))

    results = SshCliClient("host", "user", "password").run_commands(["show version"])

    assert results == [CliCommandResult(command="show version", output="show output")]
    assert channel.sent == ["show version\n", "exit\n", "y\n"]
    assert channel.closed
    assert fake_client.transport.closed
    assert fake_client.closed


def test_ssh_cli_confirms_command_prompt(monkeypatch: pytest.MonkeyPatch):
    channel = FakeChannel()
    fake_client = FakeSshClient(channel)
    install_fake_paramiko(monkeypatch, fake_client)
    outputs = iter(
        [
            "banner",
            "Warning: This is per-card setting, rules will be applied to all ports, please confirm [y/N]",
            "command accepted",
            "logout",
        ]
    )
    monkeypatch.setattr(SshCliClient, "_read_available", staticmethod(lambda *args, **kwargs: next(outputs)))

    results = SshCliClient("host", "user", "password").run_commands(["vlan trunk uni-untag subnet 192.0.2.1/24 svlan 1314 spbit 0"])

    assert results == [
        CliCommandResult(
            command="vlan trunk uni-untag subnet 192.0.2.1/24 svlan 1314 spbit 0",
            output="Warning: This is per-card setting, rules will be applied to all ports, please confirm [y/N]\ncommand accepted",
        )
    ]
    assert channel.sent == ["vlan trunk uni-untag subnet 192.0.2.1/24 svlan 1314 spbit 0\n", "y\n", "exit\n"]
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



def test_ssh_session_pool_reuses_healthy_session(monkeypatch: pytest.MonkeyPatch, tmp_path):
    channel = FakeChannel()
    fake_client = FakeSshClient(channel)
    install_fake_paramiko(monkeypatch, fake_client)
    monkeypatch.setattr(SshCliClient, "_read_available", staticmethod(lambda *args, **kwargs: "ok"))
    pool = SshSessionPool(
        "NODE3",
        "host",
        "user",
        "password",
        max_sessions=1,
        acquire_timeout_seconds=1,
        token_directory=tmp_path,
    )

    first_results, first_timing = pool.run_commands(["show one"], owner="first")
    second_results, second_timing = pool.run_commands(["show two"], owner="second")
    pool.close_all()

    assert first_results == [CliCommandResult(command="show one", output="ok")]
    assert second_results == [CliCommandResult(command="show two", output="ok")]
    assert not first_timing.reused_session
    assert second_timing.reused_session
    assert fake_client.connect_count == 1
    assert channel.sent == ["show one\n", "show two\n", "exit\n"]
    assert not list(tmp_path.glob("*.token"))


def test_file_token_semaphore_times_out_when_tokens_are_exhausted(tmp_path):
    semaphore = FileTokenSemaphore("node3", 1, tmp_path, timeout_seconds=0.01)
    token_path, _wait_seconds = semaphore.acquire("first")
    try:
        with pytest.raises(TimeoutError, match="SSH token timed out"):
            semaphore.acquire("second")
    finally:
        semaphore.release(token_path)

    assert not list(tmp_path.glob("*.token"))



def test_ssh_session_pool_can_release_token_after_each_batch(monkeypatch: pytest.MonkeyPatch, tmp_path):
    channel = FakeChannel()
    fake_client = FakeSshClient(channel)
    install_fake_paramiko(monkeypatch, fake_client)
    monkeypatch.setattr(SshCliClient, "_read_available", staticmethod(lambda *args, **kwargs: "ok"))
    pool = SshSessionPool(
        "NODE3",
        "host",
        "user",
        "password",
        max_sessions=1,
        acquire_timeout_seconds=1,
        token_directory=tmp_path,
        reuse_sessions=False,
    )

    _results, timing = pool.run_commands(["show one"], owner="first")

    assert timing.closed
    assert channel.sent == ["show one\n", "exit\n"]
    assert not list(tmp_path.glob("*.token"))