from __future__ import annotations

import pytest

from config_loader import load_environment
from config_loader.settings import ConfigError


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


def test_explicit_node_without_required_target_data_does_not_fallback():
    with pytest.raises(ConfigError, match="NODE2 has no ONT test target"):
        load_environment(node="NODE2")

def test_sensitive_config_fields_are_excluded_from_dataclass_repr():
    from config_loader.auth import AuthConfig, ResolvedAccount
    from config_loader.settings import Credentials, DutSample, EnvironmentConfig

    assert Credentials.__dataclass_fields__["password"].repr is False
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
