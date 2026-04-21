from __future__ import annotations

import pytest


@pytest.mark.smoke
def test_environment_has_expected_rest_api_users(env_config):
    users = env_config.raw["EMS"]["USER"]
    assert users["USER4"]["name"] == "RestApiNA"
    assert users["USER5"]["name"] == "RestApiRO"


@pytest.mark.smoke
def test_environment_has_usable_dut_sample(env_config):
    dut = env_config.dut
    assert dut.device_name
    assert dut.slot_id
    assert dut.port_id
    assert dut.ont_sn

