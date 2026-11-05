from __future__ import annotations

from types import SimpleNamespace

import pytest

from services import target_sync
from tests.support import neox_cli_verification

pytestmark = pytest.mark.offline

SSH_ENV_VARS = (
    "DUT_SSH_USERNAME",
    "DUT_SSH_PASSWORD",
    "NEOX_SSH_USERNAME",
    "NEOX_SSH_PASSWORD",
    "NEOX_SSH_AUTH_PROFILE",
)


@pytest.fixture(autouse=True)
def clear_ssh_env(monkeypatch):
    for name in SSH_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _env_config(**dut_fields):
    return SimpleNamespace(
        auth_profile="default",
        readwrite=SimpleNamespace(username="ems-admin", password="ems-secret"),
        dut=SimpleNamespace(node_key="NODE3", ssh_host="192.0.2.3", ssh_backend="paramiko", **dut_fields),
    )


def test_neox_cli_credentials_prefer_node_target_over_ems_account():
    env_config = _env_config(ssh_username="kang", ssh_password="device-secret")

    assert neox_cli_verification.neox_cli_credentials(env_config, "GE") == ("kang", "device-secret")


def test_neox_cli_credentials_fall_back_to_ems_readwrite_without_node_login():
    env_config = _env_config(ssh_username="", ssh_password="")

    assert neox_cli_verification.neox_cli_credentials(env_config, "GE") == ("ems-admin", "ems-secret")


def test_neox_cli_credentials_keep_explicit_environment_override(monkeypatch):
    monkeypatch.setenv("NEOX_SSH_USERNAME", "cli-user")
    monkeypatch.setenv("NEOX_SSH_PASSWORD", "cli-password")
    env_config = _env_config(ssh_username="kang", ssh_password="device-secret")

    assert neox_cli_verification.neox_cli_credentials(env_config, "GE") == ("cli-user", "cli-password")


def test_neox_cli_credentials_keep_explicit_auth_profile_override(monkeypatch):
    monkeypatch.setenv("NEOX_SSH_AUTH_PROFILE", "rad_external")
    loaded = SimpleNamespace(readwrite=SimpleNamespace(username="readwrite1", password="rad-secret"))
    calls = []

    def fake_load_environment(**kwargs):
        calls.append(kwargs)
        return loaded

    monkeypatch.setattr(neox_cli_verification, "load_environment", fake_load_environment)
    env_config = _env_config(ssh_username="kang", ssh_password="device-secret")

    assert neox_cli_verification.neox_cli_credentials(env_config, "GE") == ("readwrite1", "rad-secret")
    assert calls == [{"node": "NODE3", "auth_profile": "rad_external"}]


def test_target_sync_logs_in_with_node_target_credentials(monkeypatch):
    env_config = _env_config(ssh_username="kang", ssh_password="device-secret")
    hardware = SimpleNamespace(node_target=lambda node: {"slots": {"4": {"card": "NXC400"}}})
    logins = []

    class FakeSshCliClient:
        def __init__(self, host, username, password):
            logins.append((host, username, password))

        def run_commands(self, commands):
            return [SimpleNamespace(output="")]

    monkeypatch.setattr(target_sync, "load_hardware_config", lambda **kwargs: hardware)
    monkeypatch.setattr(target_sync, "load_environment", lambda **kwargs: env_config)
    monkeypatch.setattr(target_sync, "SshCliClient", FakeSshCliClient)

    result = target_sync.sync_target_data_from_cli("NODE3", None)

    assert logins == [("192.0.2.3", "kang", "device-secret")]
    assert not result.ok
