from __future__ import annotations

import time

import pytest

from cases import READ_ENDPOINTS
from cases.neox_legacy import profile_definition_by_name
from cases.payloads import ont_service_payload
from utils.assertions import assert_api_failure, assert_api_success
from utils.allure_helpers import allure_step
from utils.case_metadata import attach_case_id
from utils.names import unique_name


INVENTORY_READ_CASES = [case for case in READ_ENDPOINTS if case.domain == "inventory"]
ONT_READ_CASES = [case for case in READ_ENDPOINTS if case.domain == "ont"]
ONTOLOGY_PATH_CASE_NAMES = {"ont_by_device", "ont_by_slot", "ont_by_port", "ont_by_id"}


@pytest.fixture(scope="module")
def ont_inventory_seed_data(api_client, env_config):
    login = api_client.login(env_config.readwrite)
    assert_api_success(login)
    session_id = api_client.session_id_from(login)
    assert session_id, f"Login succeeded but no sessionid was returned: {login.json!r}"
    try:
        with allure_step("Prepare ONT inventory data like legacy test_prepare_for_get_ont_"):
            _prepare_ont_for_get(api_client, env_config, session_id)
        yield
    finally:
        api_client.logout(session_id)


@pytest.mark.inventory
@pytest.mark.readwrite
@pytest.mark.smoke
@pytest.mark.parametrize("case", INVENTORY_READ_CASES, ids=lambda case: case.name)
def test_inventory_read_endpoints_readwrite(api_client, env_config, readwrite_session, case):
    _run_read_success_case(api_client, env_config, readwrite_session, case, "readwrite")


@pytest.mark.inventory
@pytest.mark.readonly
@pytest.mark.parametrize("case", INVENTORY_READ_CASES, ids=lambda case: case.name)
def test_inventory_read_endpoints_readonly(api_client, env_config, readonly_session, case):
    _run_read_success_case(api_client, env_config, readonly_session, case, "readonly")


@pytest.mark.inventory
@pytest.mark.noaccess
@pytest.mark.parametrize("case", INVENTORY_READ_CASES, ids=lambda case: case.name)
def test_inventory_read_endpoints_noaccess(api_client, env_config, noaccess_session, case):
    _run_noaccess_case(api_client, env_config, noaccess_session, case)


@pytest.mark.ont
@pytest.mark.readwrite
@pytest.mark.smoke
@pytest.mark.parametrize("case", ONT_READ_CASES, ids=lambda case: case.name)
def test_ont_read_endpoints_readwrite(api_client, env_config, readwrite_session, ont_inventory_seed_data, case):
    _run_read_success_case(api_client, env_config, readwrite_session, case, "readwrite")


@pytest.mark.ont
@pytest.mark.readonly
@pytest.mark.parametrize("case", ONT_READ_CASES, ids=lambda case: case.name)
def test_ont_read_endpoints_readonly(api_client, env_config, readonly_session, ont_inventory_seed_data, case):
    _run_read_success_case(api_client, env_config, readonly_session, case, "readonly")


@pytest.mark.ont
@pytest.mark.noaccess
@pytest.mark.parametrize("case", ONT_READ_CASES, ids=lambda case: case.name)
def test_ont_read_endpoints_noaccess(api_client, env_config, noaccess_session, case):
    _run_noaccess_case(api_client, env_config, noaccess_session, case)


def _run_read_success_case(api_client, env_config, session_id, case, role_name):
    attach_case_id(case.case_id, case.name)
    name = unique_name(case.name)
    with allure_step(f"GET {case.name} as {role_name}"):
        response = api_client.request(
            case.method,
            case.build_path(env_config),
            session=session_id,
            params=case.build_params(env_config, name),
        )
    if case.name == "port_list" and response.status_code == 404:
        pytest.skip("/port list endpoint is not supported by this EMS build.")
    if case.domain == "ont" and _is_no_data(response):
        if _is_known_chinese_devicename_ont_issue(env_config, case):
            pytest.fail(
                f"{case.name} hit a known EMS issue: topology-based ONT GET returns "
                f"'No data found in the database.' when devicename contains non-ASCII characters. "
                f"device_name={env_config.dut.device_name!r}, path={case.build_path(env_config)}, "
                f"response={response.json!r}"
            )
        pytest.fail(
            f"{case.name} expected an existing ONT from ENV_WEB.JSON for {role_name} GET, "
            f"but EMS returned no data. path={case.build_path(env_config)}, response={response.json!r}"
        )
    assert_api_success(response)
    with allure_step(f"Verify {case.name} response fields match ENV_WEB.JSON"):
        _assert_inventory_response_matches_env(response.json, env_config, case.name)


def _run_noaccess_case(api_client, env_config, noaccess_session, case):
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


def _prepare_ont_for_get(api_client, env_config, session_id):
    dut = env_config.dut
    with allure_step("Run legacy ONT registration remote commands"):
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

    with allure_step("Try to observe Unregistered before provisioning, but continue if EMS inventory is not ready yet"):
        _wait_for_ont_unregistered(api_client, env_config, session_id, timeout=240, raise_on_timeout=False)

    with allure_step("Ensure ONT template profile and dependencies exist"):
        _ensure_profile_by_name(api_client, session_id, dut.ont_template)

    with allure_step("Create or normalize ONT service needed by ONT GET endpoints"):
        path = f"/ontservice/{dut.ont_sn}"
        payload = _recorded_ont_service_payload(env_config)
        existing = api_client.request("GET", path, session=session_id)
        if existing.retstatus == "Success":
            update = api_client.request("PUT", path, session=session_id, json=payload)
            assert_api_success(update)
        else:
            create = api_client.request("POST", path, session=session_id, json=payload)
            assert_api_success(create)
        _wait_for_ont_service_state(api_client, env_config, session_id, {"Success"}, timeout=180, interval=15, initial_delay=30)

    with allure_step("Wait until ONT inventory becomes stable after provisioning instead of sleeping a fixed 180 seconds"):
        _wait_for_ont_inventory(
            api_client,
            env_config,
            session_id,
            timeout=240,
            interval=15,
            initial_delay=30,
            consecutive_successes=2,
            raise_on_timeout=False,
        )


def _is_no_data(response):
    return response.retstatus == "Fail" and "No data found" in response.retresult


def _is_known_chinese_devicename_ont_issue(env_config, case):
    return case.name in ONTOLOGY_PATH_CASE_NAMES and any(ord(char) > 127 for char in env_config.dut.device_name)


def _recorded_ont_service_payload(env_config):
    payload = ont_service_payload(env_config, env_config.dut.ont_description)
    data = payload["ontservice"]["data"]
    data["description"] = env_config.dut.ont_description
    data["wifi5ssid1"] = "musk_wifi5"
    data["wifi5pass1"] = "musk1234"
    return payload


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
            service = response.json["retval"]["ontserviceinfo"]
            if service.get("state") in expected_states:
                return service
            if service.get("state") == "Fail":
                raise AssertionError(f"ONT service provisioning failed: {response.json!r}")
        time.sleep(interval)
    raise AssertionError(f"ONT service did not reach states {expected_states!r}. Last response: {last.json if last else None!r}")


def _wait_for_ont_unregistered(api_client, env_config, session_id, timeout=180, interval=15, raise_on_timeout=True):
    path = f"/ont/sn/{env_config.dut.ont_sn}"
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() <= deadline:
        response = api_client.request("GET", path, session=session_id)
        last = response
        if response.retstatus == "Success":
            item = _find_ont_item(response.json, env_config, "ont_prepare_unregistered")
            ont_state = str(item.get("ONT") or item.get("ONTID") or "")
            if ont_state == "Unregistered":
                return item
        time.sleep(interval)
    if raise_on_timeout:
        raise AssertionError(f"ONT did not become Unregistered before provisioning. Last response: {last.json if last else None!r}")
    return None


def _wait_for_ont_inventory(
    api_client,
    env_config,
    session_id,
    timeout=240,
    interval=15,
    initial_delay=0,
    consecutive_successes=1,
    raise_on_timeout=True,
):
    path = f"/ont/sn/{env_config.dut.ont_sn}"
    if initial_delay > 0:
        time.sleep(initial_delay)
    deadline = time.monotonic() + timeout
    last = None
    stable_hits = 0
    while time.monotonic() <= deadline:
        response = api_client.request("GET", path, session=session_id)
        last = response
        if response.retstatus == "Success":
            try:
                _assert_ont_fields(_find_ont_item(response.json, env_config, "ont_by_sn"), env_config)
            except AssertionError:
                stable_hits = 0
            else:
                stable_hits += 1
                if stable_hits >= consecutive_successes:
                    return True
        else:
            stable_hits = 0
        time.sleep(interval)
    if raise_on_timeout:
        raise AssertionError(f"ONT inventory did not become readable. Last response: {last.json if last else None!r}")
    return False


def _ensure_profile_by_name(api_client, session_id, profilename, seen=None):
    definition = profile_definition_by_name(profilename)
    if definition is None:
        pytest.skip(f"No converted profile data found for prerequisite profile {profilename}.")
    seen = seen or set()
    key = (definition["profiletype"], definition["profilename"])
    if key in seen:
        return
    seen.add(key)

    for dependency in _profile_refs(definition.get("post_profile_info", {})):
        _ensure_profile_by_name(api_client, session_id, dependency, seen)

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


def _assert_inventory_response_matches_env(payload, env_config, case_name):
    if case_name.startswith("device"):
        _assert_device_fields(
            _find_inventory_item(
                payload,
                "deviceinfolist",
                "deviceinfo",
                lambda item: item.get("DevName") == env_config.dut.device_name,
                case_name,
            ),
            env_config,
        )
        return
    if case_name.startswith("slot"):
        _assert_slot_fields(
            _find_inventory_item(
                payload,
                "slotinfolist",
                "slotinfo",
                lambda item: item.get("DevName") == env_config.dut.device_name
                and str(item.get("SlotID")) == env_config.dut.slot_id,
                case_name,
            ),
            env_config,
        )
        return
    if case_name.startswith("port"):
        _assert_port_fields(
            _find_inventory_item(
                payload,
                "portinfolist",
                "portinfo",
                lambda item: item.get("DevName") == env_config.dut.device_name
                and str(item.get("SlotID")) == env_config.dut.slot_id
                and str(item.get("PortID")) == env_config.dut.port_id,
                case_name,
            ),
            env_config,
        )
        return
    if case_name.startswith("ont"):
        _assert_ont_fields(_find_ont_item(payload, env_config, case_name), env_config)


def _find_inventory_item(payload, list_key, info_key, matcher, case_name):
    retval = payload.get("retval", {}) if isinstance(payload, dict) else {}
    if not isinstance(retval, dict):
        raise AssertionError(f"{case_name} response retval is not a dict: {payload!r}")
    if info_key in retval:
        item = retval[info_key]
        assert isinstance(item, dict), f"{case_name} {info_key} is not a dict: {payload!r}"
        assert matcher(item), f"{case_name} {info_key} does not match ENV_WEB.JSON: {item!r}"
        return item
    items = retval.get(list_key)
    assert isinstance(items, list) and items, f"{case_name} response does not contain {list_key}: {payload!r}"
    for item in items:
        if isinstance(item, dict) and matcher(item):
            return item
    raise AssertionError(f"{case_name} cannot find expected item in {list_key}: {payload!r}")


def _find_ont_item(payload, env_config, case_name):
    retval = payload.get("retval", {}) if isinstance(payload, dict) else {}
    if not isinstance(retval, dict):
        raise AssertionError(f"{case_name} response retval is not a dict: {payload!r}")
    for key in ("ontinfo", "ont"):
        item = retval.get(key)
        if isinstance(item, dict):
            return item
    items = retval.get("ontinfolist") or retval.get("ontlist") or []
    assert isinstance(items, list), f"{case_name} ONT list is not a list: {payload!r}"
    dut = env_config.dut
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("SN") or item.get("sn") or item.get("SerialNumber") or "") == dut.ont_sn:
            return item
        if (
            str(item.get("SlotID") or item.get("Slot") or "") == dut.slot_id
            and str(item.get("PortID") or item.get("Port") or "") == dut.port_id
            and str(item.get("ONTID") or item.get("ONT") or "") == dut.ont_id
        ):
            return item
    raise AssertionError(f"{case_name} cannot find expected ONT SN={dut.ont_sn!r}: {payload!r}")


def _assert_device_fields(item, env_config):
    dut = env_config.dut
    _assert_fields(
        item,
        {
            "DevName": dut.device_name,
            "IPAddress": dut.device_ip,
        },
        "Device",
    )


def _assert_slot_fields(item, env_config):
    dut = env_config.dut
    _assert_fields(
        item,
        {
            "DevName": dut.device_name,
            "IPAddress": dut.device_ip,
            "SlotID": dut.slot_id,
        },
        "Slot",
    )


def _assert_port_fields(item, env_config):
    dut = env_config.dut
    _assert_fields(
        item,
        {
            "DevName": dut.device_name,
            "IPAddress": dut.device_ip,
            "SlotID": dut.slot_id,
            "PortID": dut.port_id,
        },
        "Port",
    )


def _assert_ont_fields(item, env_config):
    dut = env_config.dut
    _assert_any_field(item, ("DevName",), dut.device_name, "ONT")
    _assert_any_field(item, ("IPAddress", "IP"), dut.device_ip, "ONT")
    _assert_any_field(item, ("Slot", "SlotID"), dut.slot_id, "ONT")
    _assert_any_field(item, ("Port", "PortID"), dut.port_id, "ONT")
    _assert_any_field(item, ("ONT", "ONTID"), dut.ont_id, "ONT")
    _assert_any_field(item, ("sn", "SN", "SerialNumber"), dut.ont_sn, "ONT")
    _assert_any_field(item, ("password",), dut.ont_password, "ONT")
    _assert_any_field(item, ("templateName", "ontTemplate"), dut.ont_template, "ONT")
    _assert_any_field(item, ("description", "Desc"), dut.ont_description, "ONT")


def _assert_fields(actual, expected, label):
    assert isinstance(actual, dict), f"{label} is not a dict: {actual!r}"
    for key, expected_value in expected.items():
        assert key in actual, f"{label} missing field {key!r}: {actual!r}"
        assert str(actual[key]) == str(expected_value), (
            f"{label} field {key!r} mismatch: expected {expected_value!r}, got {actual[key]!r}. "
            f"Full data: {actual!r}"
        )


def _assert_any_field(actual, keys, expected_value, label):
    assert isinstance(actual, dict), f"{label} is not a dict: {actual!r}"
    for key in keys:
        if key in actual:
            assert str(actual[key]) == str(expected_value), (
                f"{label} field {key!r} mismatch: expected {expected_value!r}, got {actual[key]!r}. "
                f"Full data: {actual!r}"
            )
            return
    raise AssertionError(f"{label} missing one of fields {keys!r}: {actual!r}")
