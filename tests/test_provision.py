from __future__ import annotations

import time

import pytest

from cases.endpoint_cases import MUTATING_ENDPOINTS, READ_ENDPOINTS
from cases.payloads import ont_service_payload
from cases.neox_legacy import profile_definition_by_name
from utils.assertions import assert_api_failure, assert_api_success
from utils.allure_helpers import allure_step
from utils.case_metadata import attach_case_id
from utils.cleanup import CleanupRegistry
from utils.diagnostics import format_response_summary, format_value_summary
from utils.names import unique_name


PROVISION_READ_CASES = [case for case in READ_ENDPOINTS if case.domain == "provision"]
PROVISION_MUTATING_CASES = [case for case in MUTATING_ENDPOINTS if case.domain == "provision"]


@pytest.fixture(scope="module")
def provision_seed_data(api_client, env_config):
    registry = CleanupRegistry()
    login = api_client.login(env_config.readwrite)
    assert_api_success(login)
    session_id = api_client.session_id_from(login)
    assert session_id, f"Login succeeded but no sessionid was returned: {format_response_summary(login)}"
    try:
        with allure_step("Ensure prerequisite ONT template profile exists"):
            _ensure_profile_by_name(api_client, session_id, registry, env_config.dut.ont_template)
        with allure_step("Ensure prerequisite GE template profile exists"):
            _ensure_profile_by_name(api_client, session_id, registry, env_config.dut.ge_template)
        with allure_step("Create or normalize recorded ONT service data for GET verification"):
            _ensure_recorded_ont_service(api_client, env_config, session_id)
        with allure_step("Create or normalize recorded GE service data for GET verification"):
            _ensure_recorded_ge_service(api_client, env_config, session_id)
        yield
    finally:
        api_client.logout(session_id)


@pytest.mark.provision
@pytest.mark.readwrite
@pytest.mark.parametrize("case", PROVISION_READ_CASES, ids=lambda case: case.name)
def test_provision_read_endpoints_readwrite(api_client, env_config, readwrite_session, provision_seed_data, case):
    attach_case_id(case.case_id, case.name)
    name = unique_name(case.name)
    with allure_step(f"GET {case.name} as readwrite"):
        response = api_client.request(
            case.method,
            case.build_path(env_config),
            session=readwrite_session,
            params=case.build_params(env_config, name),
        )
    if response.retstatus == "Fail" and "No data found" in response.retresult:
        pytest.fail(f"{case.name} expected seeded provision data, but EMS returned no data: {format_response_summary(response)}")
    assert_api_success(response)
    _assert_provision_get_matches_recorded_data(response.json, env_config, case.name)


@pytest.mark.provision
@pytest.mark.readonly
@pytest.mark.parametrize("case", PROVISION_READ_CASES, ids=lambda case: case.name)
def test_provision_read_endpoints_readonly(api_client, env_config, readonly_session, provision_seed_data, case):
    attach_case_id(case.case_id, case.name)
    name = unique_name(case.name)
    with allure_step(f"GET {case.name} as readonly"):
        response = api_client.request(
            case.method,
            case.build_path(env_config),
            session=readonly_session,
            params=case.build_params(env_config, name),
        )
    if response.retstatus == "Fail" and "No data found" in response.retresult:
        pytest.fail(
            f"{case.name} expected seeded provision data for readonly GET, but EMS returned no data: "
            f"{format_response_summary(response)}"
        )
    assert_api_success(response)
    _assert_provision_get_matches_recorded_data(response.json, env_config, case.name)


@pytest.mark.provision
@pytest.mark.noaccess
@pytest.mark.parametrize("case", PROVISION_READ_CASES, ids=lambda case: case.name)
def test_provision_read_endpoints_noaccess(api_client, env_config, noaccess_session, case):
    attach_case_id(case.case_id, case.name)
    name = unique_name(case.name)
    with allure_step(f"Verify noaccess cannot GET {case.name}"):
        response = api_client.request(
            case.method,
            case.build_path(env_config),
            session=noaccess_session,
            params=case.build_params(env_config, name),
        )
    assert_api_failure(response, accepted_messages=("not authorized", "no access", "permission", "privilege"))


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.parametrize("case", PROVISION_MUTATING_CASES, ids=lambda case: case.name)
def test_mutating_endpoints_reject_readonly(api_client, env_config, readonly_session, case):
    attach_case_id(case.case_id, case.name)
    name = unique_name(case.name)
    with allure_step(f"Verify readonly cannot mutate {case.name}"):
        response = api_client.request(
            case.method,
            case.build_path(env_config),
            session=readonly_session,
            json=case.build_payload(env_config, name),
        )
    assert_api_failure(response, accepted_messages=("not authorized", "no access", "permission", "privilege"))


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.parametrize("case", PROVISION_MUTATING_CASES, ids=lambda case: case.name)
def test_mutating_endpoints_reject_noaccess(api_client, env_config, noaccess_session, case):
    attach_case_id(case.case_id, case.name)
    name = unique_name(case.name)
    with allure_step(f"Verify noaccess cannot mutate {case.name}"):
        response = api_client.request(
            case.method,
            case.build_path(env_config),
            session=noaccess_session,
            json=case.build_payload(env_config, name),
        )
    assert_api_failure(response, accepted_messages=("not authorized", "no access", "permission", "privilege"))


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_service_crud_readwrite(api_client, env_config, readwrite_session, cleanup_registry):
    attach_case_id("EMS1-6666", "test_post_ont_service_by_sn")
    attach_case_id("EMS1-6647", "test_get_ont_service")
    attach_case_id("EMS1-6665", "test_get_ont_service_by_sn")
    attach_case_id("EMS1-6667", "test_put_ont_service_by_sn")
    attach_case_id("EMS1-6668", "test_patch_ont_service_by_sn")
    attach_case_id("EMS1-6669", "test_delete_ont_service_by_sn")
    path = f"/ontservice/{env_config.dut.ont_sn}"
    create_payload = _recorded_ont_service_payload(env_config)
    modified_payload = _recorded_ont_service_modified_payload(env_config)
    with allure_step("Ensure ONT template profile exists"):
        _ensure_profile_by_name(api_client, readwrite_session, cleanup_registry, env_config.dut.ont_template)

    with allure_step("Clean existing ONT service before create"):
        _delete_ont_service_if_exists(api_client, env_config, readwrite_session, timeout=180, interval=15)

    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))

    with allure_step("POST ONT service by SN using recorded validation data"):
        create = _post_ont_service_with_retry(api_client, env_config, readwrite_session, create_payload)
        assert_api_success(create)
        _wait_for_ont_service_state(api_client, env_config, readwrite_session, {"Success"}, timeout=180, interval=15, initial_delay=30)

    with allure_step("GET ONT service list and verify created service data"):
        get_list = api_client.request(
            "GET",
            "/ontservice",
            session=readwrite_session,
            params={"ontservicefilter": f'{{"SN":"{env_config.dut.ont_sn}"}}'},
        )
        assert_api_success(get_list)
        _assert_ont_service_fields(_find_ont_service(get_list.json, env_config), env_config, create_payload)

    with allure_step("GET ONT service by SN and verify created service data"):
        get_created = api_client.request("GET", path, session=readwrite_session)
        assert_api_success(get_created)
        _assert_ont_service_fields(_ont_service_info(get_created.json), env_config, create_payload)

    with allure_step("PUT ONT service by SN using recorded modified data"):
        update = api_client.request("PUT", path, session=readwrite_session, json=modified_payload)
        assert_api_success(update)
        _wait_for_ont_service_state(api_client, env_config, readwrite_session, {"Success"})
        get_modified = api_client.request("GET", path, session=readwrite_session)
        assert_api_success(get_modified)
        _assert_ont_service_fields(_ont_service_info(get_modified.json), env_config, modified_payload)

    with allure_step("PATCH ONT service by SN and verify reprovision state when EMS exposes it"):
        patch = api_client.request("PATCH", path, session=readwrite_session)
        assert_api_success(patch)
        _wait_for_ont_service_state(api_client, env_config, readwrite_session, {"Success", "Reprovision"})
        patched = api_client.request("GET", path, session=readwrite_session)
        assert_api_success(patched)
        state = _ont_service_info(patched.json).get("state")
        if state is not None:
            assert state in {"Reprovision", "Success"}, (
                f"Unexpected ONT service state after PATCH: {format_response_summary(patched)}"
            )

    with allure_step("DELETE ONT service by SN and verify it is removed"):
        delete = api_client.request("DELETE", path, session=readwrite_session)
        assert_api_success(delete)
        _wait_for_ont_service_removed(api_client, env_config, readwrite_session)
        removed = api_client.request("GET", path, session=readwrite_session)
        assert_api_failure(removed, accepted_messages=("No data found", "serial number does not exist"))


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.readwrite
def test_ge_service_crud_readwrite(api_client, env_config, readwrite_session, cleanup_registry):
    attach_case_id("EMS1-6661", "test_post_ge_service_by_port")
    attach_case_id("EMS1-6648", "test_get_ge_service")
    attach_case_id("EMS1-6660", "test_get_ge_service_by_port")
    attach_case_id("EMS1-6662", "test_put_ge_service_by_serviceid")
    attach_case_id("EMS1-6663", "test_patch_ge_service_by_serviceid")
    attach_case_id("EMS1-6664", "test_delete_ge_service_by_serviceid")
    dut = env_config.dut
    port_path = f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}"
    create_payload = _recorded_ge_service_payload(env_config)
    modified_payload = _recorded_ge_service_modified_payload(env_config)
    with allure_step("Ensure GE template profile exists"):
        _ensure_profile_by_name(api_client, readwrite_session, cleanup_registry, dut.ge_template)

    with allure_step("Clean existing GE service before create"):
        _delete_ge_service_if_exists(api_client, env_config, readwrite_session)

    with allure_step("POST GE service by port using recorded validation data"):
        create = _post_ge_service_with_retry(api_client, env_config, readwrite_session, create_payload)
        assert_api_success(create)
        _wait_for_ge_service_state(api_client, env_config, readwrite_session, {"Success"})

    with allure_step("GET GE service by port and verify created service data"):
        get_created = api_client.request("GET", port_path, session=readwrite_session)
        assert_api_success(get_created)
        _assert_ge_service_fields(_ge_service_info(get_created.json), env_config, create_payload)
        service_id = _ge_service_id(get_created.json)
        assert service_id, f"GE service was created but no service id was found: {format_response_summary(get_created)}"

    cleanup_registry.add(lambda: api_client.request("DELETE", f"/geservice/{service_id}", session=readwrite_session))

    with allure_step("GET GE service list and verify created service data"):
        get_list = api_client.request("GET", "/geservice", session=readwrite_session, params={"geservicefilter": f'{{"IP":"{dut.device_ip}"}}'})
        assert_api_success(get_list)
        _assert_ge_service_fields(_find_ge_service(get_list.json, env_config), env_config, create_payload)

    with allure_step("PUT GE service by service ID using recorded modified data"):
        update = api_client.request(
            "PUT",
            f"/geservice/{service_id}",
            session=readwrite_session,
            json=modified_payload,
        )
        assert_api_success(update)
        _wait_for_ge_service_state(api_client, env_config, readwrite_session, {"Success"})
        get_modified = api_client.request("GET", port_path, session=readwrite_session)
        assert_api_success(get_modified)
        _assert_ge_service_fields(_ge_service_info(get_modified.json), env_config, modified_payload)

    with allure_step("PATCH GE service by service ID and verify service remains readable"):
        patch = api_client.request("PATCH", f"/geservice/{service_id}", session=readwrite_session)
        assert_api_success(patch)
        _wait_for_ge_service_state(api_client, env_config, readwrite_session, {"Success", "Reprovision"})
        patched = api_client.request("GET", port_path, session=readwrite_session)
        assert_api_success(patched)
        _assert_ge_service_fields(_ge_service_info(patched.json), env_config, modified_payload)

    with allure_step("DELETE GE service by service ID and verify it is removed"):
        delete = api_client.request("DELETE", f"/geservice/{service_id}", session=readwrite_session)
        assert_api_success(delete)
        _wait_for_ge_service_removed(api_client, env_config, readwrite_session)
        removed = api_client.request("GET", port_path, session=readwrite_session)
        assert_api_failure(removed, accepted_messages=("No data found", "does not exist"))


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


def _ensure_recorded_ont_service(api_client, env_config, session_id):
    path = f"/ontservice/{env_config.dut.ont_sn}"
    payload = _recorded_ont_service_payload(env_config)
    existing = api_client.request("GET", path, session=session_id)
    if existing.retstatus == "Success":
        update = api_client.request("PUT", path, session=session_id, json=payload)
        assert_api_success(update)
        _wait_for_ont_service_state(api_client, env_config, session_id, {"Success"}, timeout=180, interval=15, initial_delay=20)
        return
    create = api_client.request("POST", path, session=session_id, json=payload)
    assert_api_success(create)
    _wait_for_ont_service_state(api_client, env_config, session_id, {"Success"}, timeout=180, interval=15, initial_delay=30)


def _ensure_recorded_ge_service(api_client, env_config, session_id):
    dut = env_config.dut
    path = f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}"
    payload = _recorded_ge_service_payload(env_config)
    existing = api_client.request("GET", path, session=session_id)
    if existing.retstatus == "Success":
        service_id = _ge_service_id(existing.json)
        assert service_id, f"Existing GE service does not expose service id: {format_response_summary(existing)}"
        update = api_client.request("PUT", f"/geservice/{service_id}", session=session_id, json=payload)
        if update.retstatus == "Success":
            _wait_for_ge_service_state(api_client, env_config, session_id, {"Success"})
            return
        if "does not exist" not in update.retresult:
            assert_api_success(update)
        _delete_ge_service_if_exists(api_client, env_config, session_id)
    create = _post_ge_service_with_retry(api_client, env_config, session_id, payload)
    assert_api_success(create)
    _wait_for_ge_service_state(api_client, env_config, session_id, {"Success"})


def _recorded_ont_service_payload(env_config):
    payload = ont_service_payload(env_config, env_config.dut.ont_description)
    data = payload["ontservice"]["data"]
    data["description"] = env_config.dut.ont_description
    data["wifi5ssid1"] = "musk_wifi5"
    data["wifi5pass1"] = "musk1234"
    return payload


def _recorded_ont_service_modified_payload(env_config):
    payload = _recorded_ont_service_payload(env_config)
    data = payload["ontservice"]["data"]
    data["description"] = f"{env_config.dut.ont_description}_modify"
    data["wifi5ssid1"] = "musk_wifi5_m"
    data["wifi5pass1"] = "musk1234m"
    return payload


def _recorded_ge_service_payload(env_config):
    return {
        "geservice": {
            "geTemplate": env_config.dut.ge_template,
            "Tel": env_config.dut.ge_telephone,
            "PortName": env_config.dut.ge_port_name,
        }
    }


def _recorded_ge_service_modified_payload(env_config):
    return {
        "geservice": {
            "geTemplate": env_config.dut.ge_template,
            "Tel": f"{env_config.dut.ge_telephone}0123",
            "PortName": f"modify_{env_config.dut.ge_port_name}",
        }
    }


def _post_ont_service_with_retry(api_client, env_config, session_id, payload, timeout=180, interval=5):
    path = f"/ontservice/{env_config.dut.ont_sn}"
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() <= deadline:
        response = api_client.request("POST", path, session=session_id, json=payload)
        last = response
        if response.retstatus == "Success":
            return response
        if "already exists" not in response.retresult:
            return response
        _delete_ont_service_if_exists(api_client, env_config, session_id, timeout=180, interval=15)
        deadline = time.monotonic() + timeout
    return last


def _delete_ont_service_if_exists(api_client, env_config, session_id, timeout=180, interval=15):
    path = f"/ontservice/{env_config.dut.ont_sn}"
    existing = api_client.request("GET", path, session=session_id)
    if existing.retstatus != "Success":
        return
    delete = api_client.request("DELETE", path, session=session_id)
    if delete.retstatus == "Fail" and "serial number does not exist" in delete.retresult:
        return
    assert_api_success(delete)
    _wait_for_ont_service_removed(api_client, env_config, session_id, timeout=timeout, interval=interval)


def _post_ge_service_with_retry(api_client, env_config, session_id, payload, timeout=180, interval=5):
    dut = env_config.dut
    path = f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}"
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() <= deadline:
        response = api_client.request("POST", path, session=session_id, json=payload)
        last = response
        if response.retstatus == "Success":
            return response
        if "exist in service list" not in response.retresult and "already exists" not in response.retresult:
            return response
        _delete_ge_service_if_exists(api_client, env_config, session_id)
        time.sleep(interval)
    return last


def _delete_ge_service_if_exists(api_client, env_config, session_id, wait_after_delete=50):
    dut = env_config.dut
    port_path = f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}"
    existing = api_client.request("GET", port_path, session=session_id)
    if existing.retstatus != "Success":
        return
    service_id = _ge_service_id(existing.json)
    assert service_id, f"Existing GE service does not expose service id: {format_response_summary(existing)}"
    delete = api_client.request("DELETE", f"/geservice/{service_id}", session=session_id)
    if delete.retstatus != "Success" and "does not exist" not in delete.retresult:
        assert_api_success(delete)
    time.sleep(wait_after_delete)


def _assert_provision_get_matches_recorded_data(payload, env_config, case_name):
    if case_name == "ont_service_list":
        _assert_ont_service_fields(_find_ont_service(payload, env_config), env_config, _recorded_ont_service_payload(env_config))
        return
    if case_name == "ont_service_by_sn":
        _assert_ont_service_fields(_ont_service_info(payload), env_config, _recorded_ont_service_payload(env_config))
        return
    if case_name == "ge_service_list":
        _assert_ge_service_fields(_find_ge_service(payload, env_config), env_config, _recorded_ge_service_payload(env_config))
        return
    if case_name == "ge_service_by_port":
        _assert_ge_service_fields(_ge_service_info(payload), env_config, _recorded_ge_service_payload(env_config))
        return


def _ont_service_info(payload):
    retval = payload.get("retval", {}) if isinstance(payload, dict) else {}
    service = retval.get("ontserviceinfo", retval) if isinstance(retval, dict) else None
    assert isinstance(service, dict), f"ONT service response does not contain ontserviceinfo: {format_value_summary(payload)}"
    return service


def _find_ont_service(payload, env_config):
    retval = payload.get("retval", {}) if isinstance(payload, dict) else {}
    services = retval.get("ontserviceinfolist", []) if isinstance(retval, dict) else []
    for service in services:
        if isinstance(service, dict) and service.get("sn") == env_config.dut.ont_sn:
            return service
    raise AssertionError(f"Cannot find ONT service SN={env_config.dut.ont_sn!r}: {format_value_summary(payload)}")


def _assert_ont_service_fields(service, env_config, expected_payload):
    data = expected_payload["ontservice"]["data"]
    expected = {
        "ontTemplate": env_config.dut.ont_template,
        "Desc": data["description"],
        "password": env_config.dut.ont_password,
        "Slot": env_config.dut.slot_id,
        "Port": env_config.dut.port_id,
        "ONT": env_config.dut.ont_id,
        "sn": env_config.dut.ont_sn,
    }
    _assert_fields(service, expected, "ONT service")
    service_data = service.get("data")
    if isinstance(service_data, str) and service_data and service_data != "{}":
        import json

        service_data = json.loads(service_data)
    if isinstance(service_data, dict):
        _assert_fields(
            service_data,
            {
                "description": data["description"],
                "wifi5ssid1": data["wifi5ssid1"],
                "wifi5pass1": data["wifi5pass1"],
            },
            "ONT service data",
        )
    state = service.get("state")
    if state is not None:
        assert state in {"Success", "Reprovision"}, f"Unexpected ONT service state: {service!r}"


def _ge_service_info(payload):
    retval = payload.get("retval", {}) if isinstance(payload, dict) else {}
    service = retval.get("geserviceinfo", retval) if isinstance(retval, dict) else None
    assert isinstance(service, dict), f"GE service response does not contain geserviceinfo: {format_value_summary(payload)}"
    return service


def _find_ge_service(payload, env_config):
    retval = payload.get("retval", {}) if isinstance(payload, dict) else {}
    services = retval.get("geserviceinfolist", []) if isinstance(retval, dict) else []
    dut = env_config.dut
    for service in services:
        if (
            isinstance(service, dict)
            and service.get("DevName") == dut.device_name
            and str(service.get("SlotID")) == dut.ge_slot_id
            and str(service.get("PortID")) == dut.ge_port_id
        ):
            return service
    raise AssertionError(
        f"Cannot find GE service {dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}: {format_value_summary(payload)}"
    )


def _assert_ge_service_fields(service, env_config, expected_payload):
    dut = env_config.dut
    info = expected_payload["geservice"]
    expected = {
        "SlotID": dut.ge_slot_id,
        "PortID": dut.ge_port_id,
        "DevName": dut.device_name,
        "Tel": info["Tel"],
        "PortName": info["PortName"],
        "geTemplate": info["geTemplate"],
    }
    _assert_fields(service, expected, "GE service")
    if "data" in service:
        assert service["data"] == "{}", f"GE service field 'data' mismatch: expected '{{}}', got {service['data']!r}"
    if "result" in service:
        assert service["result"] == "--", f"GE service field 'result' mismatch: expected '--', got {service['result']!r}"
    state = service.get("state")
    if state is not None:
        assert state in {"Success", "Reprovision"}, f"Unexpected GE service state: {service!r}"


def _assert_fields(actual, expected, label):
    assert isinstance(actual, dict), f"{label} is not a dict: {actual!r}"
    for key, expected_value in expected.items():
        assert key in actual, f"{label} missing field {key!r}: {actual!r}"
        assert str(actual[key]) == str(expected_value), (
            f"{label} field {key!r} mismatch: expected {expected_value!r}, got {actual[key]!r}. "
            f"Full data: {actual!r}"
        )


def _wait_for_ont_service_state(api_client, env_config, session_id, expected_states, timeout=180, interval=15, initial_delay=0):
    path = f"/ontservice/{env_config.dut.ont_sn}"
    if initial_delay > 0:
        time.sleep(initial_delay)
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() <= deadline:
        response = api_client.request("GET", path, session=session_id)
        last = response
        if response.retstatus == "Success":
            service = _ont_service_info(response.json)
            if service.get("state") in expected_states:
                return service
        time.sleep(interval)
    raise AssertionError(f"ONT service did not reach states {expected_states!r}. Last response: {_response_summary(last)}")


def _wait_for_ge_service_state(api_client, env_config, session_id, expected_states, timeout=120, interval=5):
    dut = env_config.dut
    path = f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}"
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() <= deadline:
        response = api_client.request("GET", path, session=session_id)
        last = response
        if response.retstatus == "Success":
            service = _ge_service_info(response.json)
            if service.get("state") in expected_states:
                return service
        time.sleep(interval)
    raise AssertionError(f"GE service did not reach states {expected_states!r}. Last response: {_response_summary(last)}")


def _wait_for_ont_service_removed(api_client, env_config, session_id, timeout=60, interval=3):
    path = f"/ontservice/{env_config.dut.ont_sn}"
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() <= deadline:
        response = api_client.request("GET", path, session=session_id)
        last = response
        if response.retstatus == "Fail" and (
            "No data found" in response.retresult or "serial number does not exist" in response.retresult
        ):
            return
        time.sleep(interval)
    raise AssertionError(f"ONT service was not removed. Last response: {_response_summary(last)}")


def _wait_for_ge_service_removed(api_client, env_config, session_id, timeout=60, interval=3):
    dut = env_config.dut
    path = f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}"
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() <= deadline:
        response = api_client.request("GET", path, session=session_id)
        last = response
        if response.retstatus == "Fail" and "No data found" in response.retresult:
            return
        time.sleep(interval)
    raise AssertionError(f"GE service was not removed. Last response: {_response_summary(last)}")


def _ensure_profile_by_name(api_client, session_id, cleanup_registry, profilename, seen=None):
    definition = profile_definition_by_name(profilename)
    if definition is None:
        pytest.skip(f"No converted profile data found for prerequisite profile {profilename}.")
    seen = seen or set()
    key = (definition["profiletype"], definition["profilename"])
    if key in seen:
        return
    seen.add(key)

    for dependency in _profile_refs(definition.get("post_profile_info", {})):
        _ensure_profile_by_name(api_client, session_id, cleanup_registry, dependency, seen)

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
        pytest.skip(f"Cannot create prerequisite profile {profilename}: {format_response_summary(created)}")
    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=session_id))


def _response_summary(response):
    return format_response_summary(response) if response is not None else "None"


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
