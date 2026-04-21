from __future__ import annotations

import pytest

from cases import READ_ENDPOINTS
from utils.assertions import assert_api_failure, assert_api_success
from utils.case_metadata import attach_case_id
from utils.names import unique_name


INVENTORY_READ_CASES = [case for case in READ_ENDPOINTS if case.domain in {"inventory", "ont"}]


@pytest.mark.inventory
@pytest.mark.ont
@pytest.mark.readwrite
@pytest.mark.smoke
@pytest.mark.parametrize("case", INVENTORY_READ_CASES, ids=lambda case: case.name)
def test_inventory_read_endpoints_readwrite(api_client, env_config, readwrite_session, case):
    attach_case_id(case.case_id, case.name)
    name = unique_name(case.name)
    response = api_client.request(
        case.method,
        case.build_path(env_config),
        session=readwrite_session,
        params=case.build_params(env_config, name),
    )
    if case.name == "port_list" and response.status_code == 404:
        pytest.skip("/port list endpoint is not supported by this EMS build.")
    if case.domain == "ont" and response.retstatus == "Fail" and "No data found" in response.retresult:
        if case.name == "ont_by_sn":
            _prepare_ont_for_get(api_client, env_config, readwrite_session)
            response = api_client.request(
                case.method,
                case.build_path(env_config),
                session=readwrite_session,
                params=case.build_params(env_config, name),
            )
        if response.retstatus == "Fail" and "No data found" in response.retresult:
            pytest.skip(f"{case.name} has no ONT data in this EMS environment after prepare.")
    assert_api_success(response)


@pytest.mark.inventory
@pytest.mark.ont
@pytest.mark.readonly
@pytest.mark.parametrize("case", INVENTORY_READ_CASES, ids=lambda case: case.name)
def test_inventory_read_endpoints_readonly(api_client, env_config, readonly_session, case):
    attach_case_id(case.case_id, case.name)
    name = unique_name(case.name)
    response = api_client.request(
        case.method,
        case.build_path(env_config),
        session=readonly_session,
        params=case.build_params(env_config, name),
    )
    if case.name == "port_list" and response.status_code == 404:
        pytest.skip("/port list endpoint is not supported by this EMS build.")
    if case.domain == "ont" and response.retstatus == "Fail" and "No data found" in response.retresult:
        pytest.skip(f"{case.name} has no ONT data in this EMS environment.")
    assert_api_success(response)


@pytest.mark.inventory
@pytest.mark.ont
@pytest.mark.noaccess
@pytest.mark.parametrize("case", INVENTORY_READ_CASES, ids=lambda case: case.name)
def test_inventory_read_endpoints_noaccess(api_client, env_config, noaccess_session, case):
    attach_case_id(case.case_id, case.name)
    name = unique_name(case.name)
    response = api_client.request(
        case.method,
        case.build_path(env_config),
        session=noaccess_session,
        params=case.build_params(env_config, name),
    )
    assert_api_failure(response, accepted_messages=("not authorized", "no access", "permission", "privilege"))


def _prepare_ont_for_get(api_client, env_config, session_id):
    dut = env_config.dut
    commands = [
        f"no in remote xont {dut.slot_id}-{dut.port_id}-{dut.ont_id}",
        "con",
        f"in xpon {dut.slot_id}-{dut.port_id}",
        "inactive",
        "register-method A",
        "no inactive",
        "exit",
    ]
    response = api_client.request(
        "POST",
        f"/remote/{dut.device_name}",
        session=session_id,
        json={"command": commands},
    )
    if response.retstatus != "Success":
        pytest.skip(f"ONT prepare remote console command failed: {response.json!r}")
