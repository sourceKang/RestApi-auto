from __future__ import annotations

import pytest

from cases.payloads import remote_console_payload
from utils.assertions import assert_api_failure, assert_api_success
from utils.case_metadata import attach_case_id
from utils.names import unique_name


@pytest.mark.remoteconsole
@pytest.mark.destructive
@pytest.mark.readwrite
def test_remote_console_read_command(api_client, env_config, readwrite_session):
    attach_case_id("EMS1-6652", "test_post_remote_console")
    name = unique_name("remote_console")
    response = api_client.request(
        "POST",
        f"/remote/{env_config.dut.device_name}",
        session=readwrite_session,
        json=remote_console_payload(env_config, name),
    )
    assert_api_success(response)


@pytest.mark.remoteconsole
@pytest.mark.destructive
@pytest.mark.noaccess
def test_remote_console_noaccess_rejected(api_client, env_config, noaccess_session):
    attach_case_id("EMS1-7022", "test_post_remote_console_invalid_param_should_return_error")
    name = unique_name("remote_console_noaccess")
    response = api_client.request(
        "POST",
        f"/remote/{env_config.dut.device_name}",
        session=noaccess_session,
        json=remote_console_payload(env_config, name),
    )
    assert_api_failure(response, accepted_messages=("not authorized", "no access", "permission", "privilege"))
