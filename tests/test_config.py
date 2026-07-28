from __future__ import annotations

from types import SimpleNamespace

import pytest

from config_loader import load_environment
from config_loader.hardware import load_hardware_config
from tests.support.fixtures import temporary_ge_template


@pytest.mark.smoke
def test_environment_resolves_active_auth_profile_accounts(env_config):
    role_accounts = {
        "readwrite": (env_config.readwrite, env_config.readwrite_account),
        "readonly": (env_config.readonly, env_config.readonly_account),
        "noaccess": (env_config.noaccess, env_config.noaccess_account),
    }

    for role, (credentials, account) in role_accounts.items():
        assert account.role == role
        assert account.account_name
        assert account.username
        assert credentials.username == account.username
        assert credentials.password == account.password

    assert len({account.username for _, account in role_accounts.values()}) == len(role_accounts)


@pytest.mark.smoke
def test_environment_has_usable_dut_sample(env_config):
    dut = env_config.dut
    assert dut.device_name
    assert dut.device_ip
    assert dut.chassis
    assert dut.slot_id
    assert dut.port_id
    assert dut.ont_sn


@pytest.mark.smoke
def test_default_auth_profile_loads_expected_accounts():
    env = load_environment(node="NODE1", auth_profile="default")
    assert env.auth_profile == "default"
    assert env.source_path.name == "ems.yaml"
    assert_profile_role_mapping(env)


@pytest.mark.smoke
def test_rad_external_auth_profile_loads_expected_accounts():
    env = load_environment(node="NODE1", auth_profile="rad_external")
    assert env.auth_profile == "rad_external"
    assert_profile_role_mapping(env)


def test_ems_local_rw2_auth_profile_loads_second_local_account_set():
    env = load_environment(node="NODE1", auth_profile="ems_local_rw2")
    assert env.auth_profile == "ems_local_rw2"
    assert_profile_role_mapping(env)


def assert_profile_role_mapping(env) -> None:
    accounts = {
        "readwrite": (env.readwrite, env.readwrite_account),
        "readonly": (env.readonly, env.readonly_account),
        "noaccess": (env.noaccess, env.noaccess_account),
    }
    for role, (credentials, account) in accounts.items():
        assert account.role == role
        assert account.account_name
        assert credentials.username == account.username
        assert credentials.password == account.password
    assert len({account.username for _, account in accounts.values()}) == len(accounts)


def test_node2_resolves_configured_ont_without_ge_target():
    env = load_environment(node="NODE2")

    assert env.dut.device_name == "OLT1408AC_168.84"
    assert env.dut.device_ip == "192.168.168.84"
    assert env.dut.ssh_host == "192.168.168.84"
    assert env.dut.ssh_backend == "openssh_legacy"
    assert env.dut.ssh_username == "admin"
    assert env.dut.ssh_password
    assert env.dut.slot_id == "0"
    assert env.dut.port_id == "8"
    assert env.dut.ont_id == "1"
    assert env.dut.ont_sn == "5A594F4F805F5C81"
    assert env.dut.ge_slot_id == ""
    assert env.dut.ge_port_id == ""
    assert env.dut.ge_template == ""


def test_all_nodes_define_independent_ssh_credentials():
    hardware = load_hardware_config()

    for node_key, target in hardware.targets["nodes"].items():
        assert target.get("ssh_username"), f"{node_key} is missing ssh_username"
        assert target.get("ssh_password"), f"{node_key} is missing ssh_password"

def test_temporary_ge_template_skips_before_setup_when_target_is_missing():
    env_config = SimpleNamespace(
        dut=SimpleNamespace(node_key="NODE2", ge_slot_id="", ge_port_id="")
    )
    fixture_generator = temporary_ge_template.__wrapped__(None, None, env_config)

    with pytest.raises(pytest.skip.Exception, match="configured GE target for NODE2"):
        next(fixture_generator)


def test_sensitive_config_fields_are_excluded_from_dataclass_repr():
    from config_loader.auth import AuthConfig, ResolvedAccount
    from config_loader.settings import Credentials, DutSample, EnvironmentConfig

    assert Credentials.__dataclass_fields__["password"].repr is False
    assert DutSample.__dataclass_fields__["ssh_password"].repr is False
    assert DutSample.__dataclass_fields__["ont_password"].repr is False
    assert ResolvedAccount.__dataclass_fields__["password"].repr is False
    assert AuthConfig.__dataclass_fields__["raw"].repr is False
    for field_name in (
        "hardware",
        "readwrite",
        "readonly",
        "noaccess",
        "readwrite_account",
        "readonly_account",
        "noaccess_account",
        "node_target",
    ):
        assert EnvironmentConfig.__dataclass_fields__[field_name].repr is False
