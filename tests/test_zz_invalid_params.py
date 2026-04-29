from __future__ import annotations

import copy
import json

import pytest

from cases.neox_legacy import profile_definition_by_name
from cases.payloads import ge_service_payload, ont_service_payload
from utils.allure_helpers import allure_step
from utils.case_metadata import attach_case_id


def _assert_failure_contains(response, expected_text: str) -> None:
    body = response.json if isinstance(response.json, dict) else {"raw": response.text}
    result = json.dumps(body, ensure_ascii=False, default=str)
    assert response.retstatus == "Fail" or response.status_code >= 400, (
        f"Expected failure but got success. HTTP={response.status_code}, body={body!r}"
    )
    assert expected_text.lower() in result.lower(), (
        f"Expected error containing {expected_text!r}, got {result!r}"
    )


def _deep_merge(target: dict, patch: dict) -> dict:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value
    return target


def _profile_refs(value):
    refs = set()
    if isinstance(value, dict):
        for item in value.values():
            refs.update(_profile_refs(item))
    elif isinstance(value, list):
        for item in value:
            refs.update(_profile_refs(item))
    elif isinstance(value, str) and value.startswith("#RestApi"):
        refs.add(value)
    return refs


def _ensure_profile_exists(api_client, session_id, profilename, seen=None):
    definition = profile_definition_by_name(profilename)
    if definition is None:
        pytest.skip(f"No converted profile data found for prerequisite profile {profilename}.")
    seen = seen or set()
    key = (definition["profiletype"], definition["profilename"])
    if key in seen:
        return
    seen.add(key)

    for dependency in _profile_refs(definition.get("post_profile_info", {})):
        _ensure_profile_exists(api_client, session_id, dependency, seen)

    path = f"/profile/{definition['profiletype']}/{definition['profilename']}"
    existing = api_client.request("GET", path, session=session_id)
    if existing.retstatus == "Success":
        return
    created = api_client.request(
        "POST",
        path,
        session=session_id,
        json={"Content": definition.get("post_profile_info", {})},
    )
    if created.retstatus != "Success":
        pytest.skip(f"Cannot create prerequisite profile {profilename}: {created.json!r}")


def _delete_ont_service_if_exists(api_client, env_config, session_id):
    path = f"/ontservice/{env_config.dut.ont_sn}"
    existing = api_client.request("GET", path, session=session_id)
    if existing.retstatus == "Success":
        api_client.request("DELETE", path, session=session_id)


def _ge_service_id(payload):
    if not isinstance(payload, dict):
        return None
    retval = payload.get("retval", {})
    if not isinstance(retval, dict):
        return None
    service = retval.get("geserviceinfo", retval)
    if isinstance(service, dict):
        return service.get("GeServiceID") or service.get("geserviceid") or service.get("serviceid")
    return None


def _delete_ge_service_if_exists(api_client, env_config, session_id):
    dut = env_config.dut
    port_path = f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}"
    existing = api_client.request("GET", port_path, session=session_id)
    if existing.retstatus != "Success":
        return
    service_id = _ge_service_id(existing.json)
    if service_id:
        api_client.request("DELETE", f"/geservice/{service_id}", session=session_id)


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_service_post_various_invalid_parameters_should_return_error(api_client, env_config, readwrite_session):
    attach_case_id("EMS1-7023", "test_ont_service_post_various_invalid_parameters_should_return_error")
    with allure_step("Ensure ONT template profile exists before invalid ONT service POST checks"):
        _ensure_profile_exists(api_client, readwrite_session, env_config.dut.ont_template)

    invalid_cases = [
        {
            "name": "invalid_ont_template",
            "patch": {"ontservice": {"data": {"templateprof": "#invalid_profile"}}},
            "expected": "ONT Template not found.",
        },
        {
            "name": "dspir_below_minimum",
            "patch": {"ontservice": {"data": {"dspir": "127"}}},
            "expected": "dspir: Range 128~10000000",
        },
        {
            "name": "wifi5inactive1_invalid_value",
            "patch": {"ontservice": {"data": {"wifi5inactive1": "123invalid"}}},
            "expected": "inactive value is error",
        },
        {
            "name": "wifi5ssid1_too_long",
            "patch": {"ontservice": {"data": {"wifi5ssid1": "012345678901234567890123456789AB"}}},
            "expected": "maximum length is 31",
        },
    ]

    path = f"/ontservice/{env_config.dut.ont_sn}"
    for case in invalid_cases:
        with allure_step(f"Verify ONT service POST rejects {case['name']}"):
            _delete_ont_service_if_exists(api_client, env_config, readwrite_session)
            payload = copy.deepcopy(ont_service_payload(env_config, "legacy_invalid_ont"))
            _deep_merge(payload, case["patch"])
            response = api_client.request("POST", path, session=readwrite_session, json=payload)
            _assert_failure_contains(response, case["expected"])


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.readwrite
def test_ge_service_post_various_invalid_parameters_should_return_error(api_client, env_config, readwrite_session):
    attach_case_id("EMS1-7024", "test_ge_service_post_various_invalid_parameters_should_return_error")
    with allure_step("Ensure GE template profile exists before invalid GE service POST checks"):
        _ensure_profile_exists(api_client, readwrite_session, env_config.dut.ge_template)

    dut = env_config.dut
    invalid_cases = [
        {
            "name": "device_name_not_found",
            "path": f"/geservice/NotExistDevice/{dut.ge_slot_id}/{dut.ge_port_id}",
            "patch": {},
            "expected": "Device name not found.",
        },
        {
            "name": "slot_not_found",
            "path": f"/geservice/{dut.device_name}/999/{dut.ge_port_id}",
            "patch": {},
            "expected": "Slot or Port not found.",
        },
        {
            "name": "port_not_found",
            "path": f"/geservice/{dut.device_name}/{dut.ge_slot_id}/999",
            "patch": {},
            "expected": "Slot or Port not found.",
        },
        {
            "name": "ge_template_not_found",
            "path": f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}",
            "patch": {"geservice": {"geTemplate": "#NotExistTemplate"}},
            "expected": "GE Template not found.",
        },
        {
            "name": "tel_too_long",
            "path": f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}",
            "patch": {"geservice": {"Tel": "012345678901234567890123456789012"}},
            "expected": "Telephone: Maximum length is 31",
        },
        {
            "name": "port_name_too_long",
            "path": f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}",
            "patch": {"geservice": {"PortName": "012345678901234567890123456789012"}},
            "expected": "Port Name: Maximum length is 31",
        },
    ]

    for case in invalid_cases:
        with allure_step(f"Verify GE service POST rejects {case['name']}"):
            _delete_ge_service_if_exists(api_client, env_config, readwrite_session)
            payload = copy.deepcopy(ge_service_payload(env_config, "legacy_invalid_ge"))
            _deep_merge(payload, case["patch"])
            response = api_client.request("POST", case["path"], session=readwrite_session, json=payload)
            _assert_failure_contains(response, case["expected"])


@pytest.mark.alarm
@pytest.mark.mutating
@pytest.mark.readwrite
def test_history_alarm_various_invalid_parameters_should_return_error(api_client, readwrite_session):
    attach_case_id("EMS1-7030", "test_history_alarm_various_invalid_parameters_should_return_error")
    invalid_cases = [
        {
            "name": "history_alarm_filter_no_match",
            "method": "GET",
            "path": "/historyalarm",
            "params": {"alarmfilter": json.dumps({"KeyWord": ["not_exist_ip", "no_such_event"]})},
            "expected": "No data found in the database.",
        },
        {
            "name": "history_alarm_by_id_missing",
            "method": "GET",
            "path": "/historyalarm/123123546/456789764",
            "expected": "No data found in the database.",
        },
        {
            "name": "history_alarm_delete_missing",
            "method": "DELETE",
            "path": "/historyalarm/45642578/78976548",
            "expected": "The alarm does not exist.",
        },
    ]
    for case in invalid_cases:
        with allure_step(f"Verify history alarm API rejects {case['name']}"):
            response = api_client.request(
                case["method"],
                case["path"],
                session=readwrite_session,
                params=case.get("params"),
            )
            _assert_failure_contains(response, case["expected"])


@pytest.mark.inventory
@pytest.mark.readwrite
def test_get_device_name_with_invalid_parameters_should_return_error(api_client, readwrite_session):
    attach_case_id("EMS1-7031", "test_get_device_name_with_invalid_parameters_should_return_error")
    with allure_step("Verify GET /device/{devicename} rejects a non-existent device name"):
        response = api_client.request("GET", "/device/not_exist_device_123", session=readwrite_session)
        _assert_failure_contains(response, "No data found in the database.")


@pytest.mark.inventory
@pytest.mark.readwrite
def test_slot_api_with_invalid_parameters_should_return_error(api_client, readwrite_session):
    attach_case_id("EMS1-7032", "test_slot_api_with_invalid_parameters_should_return_error")
    invalid_cases = [
        {
            "name": "slot_by_devicename_missing_device",
            "path": "/slot/no_such_device",
            "expected": "No data found in the database.",
        },
        {
            "name": "slot_by_id_missing_device_and_slot",
            "path": "/slot/no_such_device/999",
            "expected": "No data found in the database.",
        },
    ]
    for case in invalid_cases:
        with allure_step(f"Verify slot API rejects {case['name']}"):
            response = api_client.request("GET", case["path"], session=readwrite_session)
            _assert_failure_contains(response, case["expected"])


@pytest.mark.inventory
@pytest.mark.readwrite
def test_port_api_with_invalid_parameters_should_return_error(api_client, readwrite_session):
    attach_case_id("EMS1-7033", "test_port_api_with_invalid_parameters_should_return_error")
    invalid_cases = [
        {
            "name": "port_by_devicename_missing_device",
            "path": "/port/no_such_device",
            "expected": "No data found in the database.",
        },
        {
            "name": "port_by_slot_missing_device_and_slot",
            "path": "/port/no_such_device/999",
            "expected": "No data found in the database.",
        },
        {
            "name": "port_by_id_missing_device_slot_port",
            "path": "/port/no_such_device/999/1000",
            "expected": "No data found in the database.",
        },
    ]
    for case in invalid_cases:
        with allure_step(f"Verify port API rejects {case['name']}"):
            response = api_client.request("GET", case["path"], session=readwrite_session)
            _assert_failure_contains(response, case["expected"])


@pytest.mark.ont
@pytest.mark.readwrite
def test_ont_api_with_invalid_parameters_should_return_error(api_client, readwrite_session):
    attach_case_id("EMS1-7034", "test_ont_api_with_invalid_parameters_should_return_error")
    invalid_cases = [
        {
            "name": "ont_by_sn_missing",
            "path": "/ont/sn/not_exist_sn_999",
            "expected": "No data found in the database.",
        },
        {
            "name": "ont_by_description_missing",
            "path": "/ont/description/no_such_desc",
            "expected": "No data found in the database.",
        },
        {
            "name": "ont_by_devicename_missing_device",
            "path": "/ont/no_such_device",
            "expected": "No data found in the database.",
        },
        {
            "name": "ont_by_slot_missing_device_slot",
            "path": "/ont/no_such_device/999",
            "expected": "No data found in the database.",
        },
        {
            "name": "ont_by_port_missing_device_slot_port",
            "path": "/ont/no_such_device/999/888",
            "expected": "No data found in the database.",
        },
        {
            "name": "ont_by_id_missing_device_slot_port_ont",
            "path": "/ont/no_such_device/999/888/123",
            "expected": "No data found in the database.",
        },
    ]
    for case in invalid_cases:
        with allure_step(f"Verify ONT API rejects {case['name']}"):
            response = api_client.request("GET", case["path"], session=readwrite_session)
            _assert_failure_contains(response, case["expected"])
