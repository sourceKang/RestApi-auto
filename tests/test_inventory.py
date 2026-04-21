from __future__ import annotations

import json

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
    if case.domain == "ont" and _is_no_data(response):
        _prepare_ont_for_get(api_client, env_config, readwrite_session)
        response = api_client.request(
            case.method,
            case.build_path(env_config),
            session=readwrite_session,
            params=case.build_params(env_config, name),
        )
    if case.domain == "ont" and _is_no_data(response):
        pytest.fail(
            f"{case.name} expected an existing ONT from ENV_WEB.JSON, but EMS returned no data. "
            f"path={case.build_path(env_config)}, response={response.json!r}"
        )
    assert_api_success(response)
    if case.domain == "ont":
        _assert_expected_ont_present(response.json, env_config, case.name)


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
    if case.domain == "ont" and _is_no_data(response):
        pytest.fail(
            f"{case.name} expected an existing ONT from ENV_WEB.JSON for readonly GET, "
            f"but EMS returned no data. path={case.build_path(env_config)}, response={response.json!r}"
        )
    assert_api_success(response)
    if case.domain == "ont":
        _assert_expected_ont_present(response.json, env_config, case.name)


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
        pytest.fail(f"ONT prepare remote console command failed: {response.json!r}")


def _is_no_data(response):
    return response.retstatus == "Fail" and "No data found" in response.retresult


def _assert_expected_ont_present(payload, env_config, case_name):
    body = json.dumps(payload, ensure_ascii=False)
    dut = env_config.dut
    expected_values = [dut.ont_sn]
    if case_name == "ont_by_description":
        expected_values.append(dut.ont_description)
    missing = [value for value in expected_values if value and value not in body]
    assert not missing, (
        f"{case_name} returned Success but did not include expected ONT data {missing!r}. "
        f"Expected SN={dut.ont_sn!r}, description={dut.ont_description!r}, payload={payload!r}"
    )
