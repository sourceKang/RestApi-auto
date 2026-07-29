from __future__ import annotations

import os

import pytest

from config_loader import auth as auth_module
from config_loader import hardware as hardware_module
from config_loader.simple_yaml import SimpleYamlError, load_local_env, load_simple_yaml


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


def test_local_env_populates_missing_values_without_overriding_process_env(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        'RESTAPI_TEST_FROM_FILE="file value # with equals="\n'
        'RESTAPI_TEST_PROCESS_WINS="file value"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("RESTAPI_TEST_FROM_FILE", raising=False)
    monkeypatch.setenv("RESTAPI_TEST_PROCESS_WINS", "process value")

    try:
        load_local_env(env_file)

        assert os.environ["RESTAPI_TEST_FROM_FILE"] == "file value # with equals="
        assert os.environ["RESTAPI_TEST_PROCESS_WINS"] == "process value"
    finally:
        os.environ.pop("RESTAPI_TEST_FROM_FILE", None)


def test_simple_yaml_expands_environment_reference_and_fallback(monkeypatch, tmp_path):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text(
        'from_env: "${RESTAPI_TEST_USERNAME:-example}"\n'
        'from_fallback: "${RESTAPI_TEST_FALLBACK:-CHANGE_ME}"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("RESTAPI_TEST_USERNAME", "local-user")
    monkeypatch.delenv("RESTAPI_TEST_FALLBACK", raising=False)

    config = load_simple_yaml(yaml_file)

    assert config == {"from_env": "local-user", "from_fallback": "CHANGE_ME"}


def test_simple_yaml_rejects_missing_required_environment_reference(monkeypatch, tmp_path):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text('password: "${RESTAPI_TEST_REQUIRED_SECRET}"\n', encoding="utf-8")
    monkeypatch.delenv("RESTAPI_TEST_REQUIRED_SECRET", raising=False)

    with pytest.raises(
        SimpleYamlError,
        match="required environment variable RESTAPI_TEST_REQUIRED_SECRET is not set",
    ):
        load_simple_yaml(yaml_file)


def test_auth_loader_environment_file_override_still_selects_explicit_yaml(monkeypatch, tmp_path):
    env_file = tmp_path / "auth_accounts.env.yaml"
    env_file.write_text(AUTH_YAML, encoding="utf-8")
    monkeypatch.setenv("EMS_AUTH_ACCOUNTS_FILE", str(env_file))

    auth = auth_module.load_auth_config()

    assert auth.path == env_file
    assert auth.resolve_profile("default")["readwrite"].username == "rw"


def test_auth_loader_prefers_ignored_local_yaml_without_environment_override(monkeypatch, tmp_path):
    local_file = tmp_path / "auth_accounts.local.yaml"
    local_file.write_text(AUTH_YAML, encoding="utf-8")
    monkeypatch.delenv("EMS_AUTH_ACCOUNTS_FILE", raising=False)
    monkeypatch.setattr(auth_module, "LOCAL_AUTH_ACCOUNTS_FILE", local_file)

    auth = auth_module.load_auth_config()

    assert auth.path == local_file
    assert auth.resolve_profile("default")["readwrite"].username == "rw"


def test_hardware_loader_environment_file_override_still_selects_explicit_yaml(monkeypatch, tmp_path):
    targets_file = tmp_path / "test_targets.env.yaml"
    targets_file.write_text(TARGETS_YAML, encoding="utf-8")
    monkeypatch.setenv("EMS_TEST_TARGETS_FILE", str(targets_file))

    hardware = hardware_module.load_hardware_config()

    assert hardware.targets_path == targets_file
    assert "NODEX" in hardware.targets["nodes"]


def test_hardware_loader_prefers_ignored_local_yaml_without_environment_override(monkeypatch, tmp_path):
    local_file = tmp_path / "test_targets.local.yaml"
    local_file.write_text(TARGETS_YAML, encoding="utf-8")
    monkeypatch.delenv("EMS_TEST_TARGETS_FILE", raising=False)
    monkeypatch.setattr(hardware_module, "LOCAL_TEST_TARGETS_FILE", local_file)

    hardware = hardware_module.load_hardware_config()

    assert hardware.targets_path == local_file
    assert "NODEX" in hardware.targets["nodes"]
