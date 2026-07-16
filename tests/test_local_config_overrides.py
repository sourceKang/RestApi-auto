from __future__ import annotations

from config_loader import auth as auth_module
from config_loader import hardware as hardware_module


AUTH_YAML = """version: 1
profiles:
  default:
    readwrite_account: "default"
    readonly_account: "default"
    noaccess_account: "default"
accounts:
  readwrite:
    default:
      source: "test"
      username: "rw"
      password: "pw"
  readonly:
    default:
      source: "test"
      username: "ro"
      password: "pw"
  noaccess:
    default:
      source: "test"
      username: "na"
      password: "pw"
"""

TARGETS_YAML = """version: 2
nodes:
  NODEX:
    device_name: "example"
    device_ip: "192.0.2.1"
    chassis: "IES4204"
    slots:
      1:
        card: "MSC1240QA"
        role: "controller"
        ports:
          1:
            type: "Network"
            speed: "1G"
    test_targets:
      report_slots: ["1"]
"""


def test_auth_loader_prefers_local_override(monkeypatch, tmp_path):
    local_file = tmp_path / "auth_accounts.local.yaml"
    local_file.write_text(AUTH_YAML, encoding="utf-8")
    monkeypatch.delenv("EMS_AUTH_ACCOUNTS_FILE", raising=False)
    monkeypatch.setattr(auth_module, "LOCAL_AUTH_ACCOUNTS_FILE", local_file)

    auth = auth_module.load_auth_config()

    assert auth.path == local_file
    assert auth.resolve_profile("default")["readwrite"].username == "rw"


def test_auth_loader_environment_override_wins_over_local(monkeypatch, tmp_path):
    local_file = tmp_path / "auth_accounts.local.yaml"
    env_file = tmp_path / "auth_accounts.env.yaml"
    local_file.write_text(AUTH_YAML.replace('username: "rw"', 'username: "local_rw"'), encoding="utf-8")
    env_file.write_text(AUTH_YAML.replace('username: "rw"', 'username: "env_rw"'), encoding="utf-8")
    monkeypatch.setattr(auth_module, "LOCAL_AUTH_ACCOUNTS_FILE", local_file)
    monkeypatch.setenv("EMS_AUTH_ACCOUNTS_FILE", str(env_file))

    auth = auth_module.load_auth_config()

    assert auth.path == env_file
    assert auth.resolve_profile("default")["readwrite"].username == "env_rw"


def test_hardware_loader_prefers_local_target_override(monkeypatch, tmp_path):
    local_file = tmp_path / "test_targets.local.yaml"
    local_file.write_text(TARGETS_YAML, encoding="utf-8")
    monkeypatch.delenv("EMS_TEST_TARGETS_FILE", raising=False)
    monkeypatch.setattr(hardware_module, "LOCAL_TEST_TARGETS_FILE", local_file)

    hardware = hardware_module.load_hardware_config()

    assert hardware.targets_path == local_file
    assert "NODEX" in hardware.targets["nodes"]


def test_hardware_loader_environment_override_wins_over_local(monkeypatch, tmp_path):
    local_file = tmp_path / "test_targets.local.yaml"
    env_file = tmp_path / "test_targets.env.yaml"
    local_file.write_text(TARGETS_YAML, encoding="utf-8")
    env_file.write_text(TARGETS_YAML.replace("NODEX", "NODEENV"), encoding="utf-8")
    monkeypatch.setattr(hardware_module, "LOCAL_TEST_TARGETS_FILE", local_file)
    monkeypatch.setenv("EMS_TEST_TARGETS_FILE", str(env_file))

    hardware = hardware_module.load_hardware_config()

    assert hardware.targets_path == env_file
    assert "NODEENV" in hardware.targets["nodes"]
