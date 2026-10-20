from __future__ import annotations

from types import SimpleNamespace

import pytest

import tests.test_neox_config as neox_config
from tests.support.ge_acl_profile import acl_profile_names, wait_for_ge_acl_profile_mode, wait_for_ge_acl_profiles


pytestmark = pytest.mark.offline

ENV = SimpleNamespace(wait_scale=1.0)
PROFILE_SHOW = (
    "show acl-profile\n"
    "index:   1, acl profile name:aaa\n=====\n<matching rule>\n<action rule>\ndrop\n"
    "index:   2, acl profile name:RestApiGeAcl\n=====\n<matching rule>\nsource ip: 192.0.2.1\n"
    "NXC400#"
)


class FakeTime:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def reader_from(outputs):
    calls = []

    def read(env_config, command):
        calls.append(command)
        return outputs[min(len(calls), len(outputs)) - 1]

    return read, calls


def test_mode_poll_returns_as_soon_as_the_mode_is_visible():
    fake = FakeTime()
    read, calls = reader_from(["Acl-profile mode : port", "Acl-profile mode : port", "Acl-profile mode : profile"])

    poll = wait_for_ge_acl_profile_mode(ENV, "profile", reader=read, sleeper=fake.sleep, clock=fake.clock)

    assert (poll.polls, calls[0], fake.sleeps) == (3, "show acl-profile mode", [1.0, 1.0])


def test_mode_poll_fails_with_last_output_after_the_deadline():
    fake = FakeTime()
    read, _ = reader_from(["Acl-profile mode : port"])

    with pytest.raises(AssertionError, match=r"GE ACL profile mode 'profile' not visible .*Acl-profile mode : port"):
        wait_for_ge_acl_profile_mode(ENV, "profile", timeout=5, reader=read, sleeper=fake.sleep, clock=fake.clock)

    assert sum(fake.sleeps) == 5


def test_profile_poll_waits_for_every_named_profile():
    fake = FakeTime()
    read, calls = reader_from(["show acl-profile\nindex:   1, acl profile name:aaa\nNXC400#", PROFILE_SHOW])

    poll = wait_for_ge_acl_profiles(ENV, ["RestApiGeAcl"], reader=read, sleeper=fake.sleep, clock=fake.clock)

    assert poll.polls == 2 and calls == ["show acl-profile", "show acl-profile"]
    assert acl_profile_names(PROFILE_SHOW) == ["aaa", "RestApiGeAcl"]


def test_ensure_mode_resends_the_switch_only_after_polling_times_out(monkeypatch):
    attempts = []
    sent = []

    def fake_wait(env_config, mode):
        attempts.append(mode)
        if len(attempts) == 1:
            raise AssertionError("GE ACL profile mode 'profile' not visible after 30 polls")

    monkeypatch.setattr(neox_config, "wait_for_ge_acl_profile_mode", fake_wait)
    monkeypatch.setattr(neox_config, "run_ge_global_config_command_batch_fresh", lambda env, commands: sent.append(commands) or {})
    monkeypatch.setattr(neox_config, "attach_json", lambda *args, **kwargs: None)
    env = SimpleNamespace(dut=SimpleNamespace(node_key="NODE3", device_ip="192.0.2.10"))

    neox_config.ensure_ge_acl_profile_mode(env, "profile")

    assert attempts == ["profile", "profile"]
    assert sent == [["acl-profile mode profile", "y"]]


def test_ensure_mode_does_not_resend_when_the_mode_is_already_visible(monkeypatch):
    sent = []
    monkeypatch.setattr(neox_config, "wait_for_ge_acl_profile_mode", lambda env_config, mode: None)
    monkeypatch.setattr(neox_config, "run_ge_global_config_command_batch_fresh", lambda env, commands: sent.append(commands) or {})

    neox_config.ensure_ge_acl_profile_mode(SimpleNamespace(), "port")

    assert sent == []
