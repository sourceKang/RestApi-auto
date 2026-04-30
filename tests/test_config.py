from __future__ import annotations

import pytest

from configs import load_environment


@pytest.mark.smoke
def test_environment_has_expected_rest_api_users(env_config):
    users = env_config.raw["EMS"]["USER"]
    assert users["USER4"]["name"] == "RestApiNA"
    assert users["USER5"]["name"] == "RestApiRO"


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
    assert env.readwrite_account.account_name == "default"
    assert env.readonly_account.account_name == "default"
    assert env.noaccess_account.account_name == "default"


@pytest.mark.smoke
def test_rad_external_auth_profile_loads_expected_accounts():
    env = load_environment(node="NODE1", auth_profile="rad_external")
    assert env.auth_profile == "rad_external"
    assert env.readwrite_account.account_name == "readwrite1"
    assert env.readwrite.username == "readwrite1"
    assert env.readonly_account.account_name == "readonly1"
    assert env.readonly.username == "readonly1"
    assert env.noaccess_account.account_name == "noaccess1"
    assert env.noaccess.username == "noaccess1"
