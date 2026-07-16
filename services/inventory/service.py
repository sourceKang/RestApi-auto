from __future__ import annotations

import json
import time

import pytest

from services.endpoint_case import assert_permission_rejected, request_endpoint_case
from services.profile import ProfileService
from cases.payloads import ont_service_payload
from models.api import EndpointCase
from utils.allure_helpers import allure_step
from utils.assertions import assert_api_success
from utils.diagnostics import format_response_summary, format_value_summary


ONTOLOGY_PATH_CASE_NAMES = {"ont_by_device", "ont_by_slot", "ont_by_port", "ont_by_id"}
EXPECTED_ENABLED_STATE = "1"
EXPECTED_UP_OPERATION_STATE = "3"
EXPECTED_PORT_UP_OPERATION_STATE = "1"
PORT_TYPE_ALIASES = {
    "xpon": {"xpon", "gpon", "xgspon", "xgpon", "250"},
    "gpon": {"xpon", "gpon", "xgspon", "xgpon", "250"},
    "network": {"network", "ethernet", "ethernet access"},
    "ethernet access": {"network", "ethernet", "ethernet access", "ge", "6"},
    "ge": {"ge", "6"},
}


class InventoryService:
    def __init__(self, api_client, env_config, profile_service=None) -> None:
        self.api_client = api_client
        self.env_config = env_config
        self.profile_service = profile_service or ProfileService(api_client)

    def verify_read_success(self, session_id: str, case: EndpointCase, role_name: str, ont_template: str | None = None) -> None:
        response = request_endpoint_case(
            self.api_client,
            self.env_config,
            session_id,
            case,
            step=f"GET {case.name} as {role_name}",
        )
        if case.name == "port_list" and response.status_code == 404:
            pytest.skip("/port list endpoint is not supported by this EMS build.")
        if case.domain == "ont" and _is_no_data(response):
            if _is_known_chinese_devicename_ont_issue(self.env_config, case):
                pytest.fail(
                    f"{case.name} hit a known EMS issue: topology-based ONT GET returns "
                    f"'No data found in the database.' when devicename contains non-ASCII characters. "
                    f"device_name={self.env_config.dut.device_name!r}, path={case.build_path(self.env_config)}, "
                    f"response={format_response_summary(response)}"
                )
            pytest.fail(
                f"{case.name} expected an existing ONT from YAML test target for {role_name} GET, "
                f"but EMS returned no data. path={case.build_path(self.env_config)}, response={format_response_summary(response)}"
            )
        assert_api_success(response)
        with allure_step(f"Verify {case.name} response fields match YAML test target"):
            assert_inventory_response_matches_env(response.json, self.env_config, case.name, ont_template=ont_template)

    def verify_noaccess_rejected(self, session_id: str, case: EndpointCase) -> None:
        response = request_endpoint_case(
            self.api_client,
            self.env_config,
            session_id,
            case,
            step=f"Verify noaccess cannot GET {case.name}",
        )
        assert_permission_rejected(response)

    def get_ont_service(self, session_id: str):
        path = f"/ontservice/{self.env_config.dut.ont_sn}"
        return self.api_client.request("GET", path, session=session_id)

    @staticmethod
    def ont_service_is_missing(response) -> bool:
        return _is_no_data(response)

    @staticmethod
    def ont_service_template(response) -> str:
        service = response.json.get("retval", {}).get("ontserviceinfo", {})
        service_data = service.get("data", {})
        if isinstance(service_data, str) and service_data and service_data != "{}":
            service_data = json.loads(service_data)
        actual_template = service.get("ontTemplate")
        if not actual_template and isinstance(service_data, dict):
            actual_template = service_data.get("templateprof")
        if not actual_template:
            raise AssertionError(
                "Existing ONT service does not expose its template: "
                f"{format_response_summary(response)}"
            )
        return str(actual_template)

    def upsert_ont_service(self, session_id: str, ont_template: str | None = None):
        dut = self.env_config.dut
        with allure_step("Create or normalize ONT service needed by ONT GET endpoints"):
            path = f"/ontservice/{dut.ont_sn}"
            payload = recorded_ont_service_payload(self.env_config, ont_template=ont_template)
            existing = self.get_ont_service(session_id)
            if existing.retstatus == "Success":
                return self._update_existing_ont_service(
                    session_id,
                    path,
                    payload,
                    existing,
                    ont_template,
                )
            if not _is_no_data(existing):
                raise AssertionError(
                    "Cannot inspect existing ONT service before create: "
                    f"{format_response_summary(existing)}"
                )

            create = self.api_client.request("POST", path, session=session_id, json=payload)
            if create.retstatus == "Success":
                return create
            if "already exists" not in create.retresult.lower():
                assert_api_success(create)

            deadline = time.monotonic() + 60
            last = create
            while time.monotonic() <= deadline:
                existing = self.api_client.request("GET", path, session=session_id)
                last = existing
                if existing.retstatus == "Success":
                    return self._update_existing_ont_service(
                        session_id,
                        path,
                        payload,
                        existing,
                        ont_template,
                    )
                if not _is_no_data(existing):
                    raise AssertionError(
                        "Cannot safely reconcile ONT service after create conflict: "
                        f"{format_response_summary(existing)}"
                    )
                time.sleep(5)
            raise AssertionError(
                "ONT service create reported already exists, but GET never exposed "
                f"the service for template verification: {format_response_summary(last)}"
            )

    def _update_existing_ont_service(
        self,
        session_id: str,
        path: str,
        payload: dict,
        existing,
        ont_template: str | None,
    ):
        expected_template = str(ont_template or self.env_config.dut.ont_template)
        actual_template = self.ont_service_template(existing)
        if actual_template != expected_template:
            raise AssertionError(
                "Refusing to overwrite ONT service that does not use this run's template: "
                f"{format_response_summary(existing)}"
            )
        update = self.api_client.request("PUT", path, session=session_id, json=payload)
        assert_api_success(update)
        return update

    def wait_for_ont_service_state(
        self,
        session_id: str,
        expected_states: set[str],
        timeout: int = 180,
        interval: int = 15,
        initial_delay: int = 0,
        raise_on_timeout: bool = True,
    ):
        path = f"/ontservice/{self.env_config.dut.ont_sn}"
        if initial_delay > 0:
            time.sleep(initial_delay)
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() <= deadline:
            response = self.api_client.request("GET", path, session=session_id)
            last = response
            if response.retstatus == "Fail" and "not authorized" in response.retresult.lower():
                raise AssertionError(f"ONT service polling lost authorization: {format_response_summary(response)}")
            if response.retstatus == "Success":
                service = response.json["retval"]["ontserviceinfo"]
                if service.get("state") in expected_states:
                    return service
                if service.get("state") == "Fail":
                    raise AssertionError(f"ONT service provisioning failed: {format_response_summary(response)}")
            time.sleep(interval)
        if raise_on_timeout:
            raise AssertionError(
                f"ONT service did not reach states {expected_states!r}. Last response: {_response_summary(last)}"
            )
        return None

    def wait_for_ont_unregistered(
        self,
        session_id: str,
        timeout: int = 180,
        interval: int = 15,
        raise_on_timeout: bool = True,
    ):
        path = f"/ont/sn/{self.env_config.dut.ont_sn}"
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() <= deadline:
            response = self.api_client.request("GET", path, session=session_id)
            last = response
            if response.retstatus == "Success":
                item = find_ont_item(response.json, self.env_config, "ont_prepare_unregistered")
                ont_state = str(item.get("ONT") or item.get("ONTID") or "")
                if ont_state == "Unregistered":
                    return item
            time.sleep(interval)
        if raise_on_timeout:
            raise AssertionError(f"ONT did not become Unregistered before provisioning. Last response: {_response_summary(last)}")
        return None

    def wait_for_ont_inventory(
        self,
        session_id: str,
        ont_template: str | None = None,
        timeout: int = 240,
        interval: int = 15,
        initial_delay: int = 0,
        consecutive_successes: int = 1,
        raise_on_timeout: bool = True,
    ) -> bool:
        path = f"/ont/sn/{self.env_config.dut.ont_sn}"
        if initial_delay > 0:
            time.sleep(initial_delay)
        deadline = time.monotonic() + timeout
        last = None
        stable_hits = 0
        while time.monotonic() <= deadline:
            response = self.api_client.request("GET", path, session=session_id)
            last = response
            if response.retstatus == "Success":
                try:
                    _assert_ont_fields(
                        find_ont_item(response.json, self.env_config, "ont_by_sn"),
                        self.env_config,
                        ont_template=ont_template,
                    )
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
            raise AssertionError(f"ONT inventory did not become readable. Last status: {_ont_inventory_status(last, self.env_config)}")
        return False

    def wait_for_ge_port_inventory(
        self,
        session_id: str,
        timeout: int = 300,
        interval: int = 15,
        raise_on_timeout: bool = True,
    ) -> bool:
        dut = self.env_config.dut
        path = f"/port/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}"
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() <= deadline:
            response = self.api_client.request("GET", path, session=session_id)
            last = response
            if response.retstatus == "Success":
                try:
                    _assert_port_fields(
                        _find_inventory_item(
                            response.json,
                            "portinfolist",
                            "portinfo",
                            lambda item: item.get("DevName") == dut.device_name
                            and str(item.get("SlotID")) == dut.ge_slot_id
                            and str(item.get("PortID")) == dut.ge_port_id,
                            "port_by_id",
                        ),
                        self.env_config,
                    )
                except AssertionError:
                    pass
                else:
                    return True
            time.sleep(interval)
        if raise_on_timeout:
            raise AssertionError(f"GE port inventory did not become readable. Last status: {_ge_port_inventory_status(last)}")
        return False

    def ensure_profile_by_name(self, session_id: str, profilename: str, seen=None) -> None:
        self.profile_service.ensure_prerequisite_profile(session_id, profilename, seen=seen)


def _is_no_data(response) -> bool:
    return response.retstatus == "Fail" and "No data found" in response.retresult


def _is_known_chinese_devicename_ont_issue(env_config, case: EndpointCase) -> bool:
    return case.name in ONTOLOGY_PATH_CASE_NAMES and any(ord(char) > 127 for char in env_config.dut.device_name)


def recorded_ont_service_payload(env_config, ont_template: str | None = None):
    payload = ont_service_payload(
        env_config,
        env_config.dut.ont_description,
        ont_template=ont_template,
    )
    data = payload["ontservice"]["data"]
    data["description"] = env_config.dut.ont_description
    data["wifi5ssid1"] = "musk_wifi5"
    data["wifi5pass1"] = "musk1234"
    return payload


def assert_inventory_response_matches_env(payload, env_config, case_name: str, ont_template: str | None = None) -> None:
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
        item = _find_inventory_item(
            payload,
            "slotinfolist",
            "slotinfo",
            lambda item: item.get("DevName") == env_config.dut.device_name
            and str(item.get("SlotID")) == env_config.dut.slot_id,
            case_name,
        )
        _assert_slot_fields(item, env_config)
        _assert_report_card_inventory(payload, env_config, case_name)
        return
    if case_name.startswith("port"):
        target = _expected_port_target(env_config)
        _assert_port_fields(
            _find_inventory_item(
                payload,
                "portinfolist",
                "portinfo",
                lambda item: item.get("DevName") == env_config.dut.device_name
                and str(item.get("SlotID")) == target["slot_id"]
                and str(item.get("PortID")) == target["port_id"],
                case_name,
            ),
            env_config,
        )
        return
    if case_name.startswith("ont"):
        _assert_ont_fields(find_ont_item(payload, env_config, case_name), env_config, ont_template=ont_template)


def _find_inventory_item(payload, list_key, info_key, matcher, case_name):
    retval = payload.get("retval", {}) if isinstance(payload, dict) else {}
    if not isinstance(retval, dict):
        raise AssertionError(f"{case_name} response retval is not a dict: {format_value_summary(payload)}")
    if info_key in retval:
        item = retval[info_key]
        assert isinstance(item, dict), f"{case_name} {info_key} is not a dict: {format_value_summary(payload)}"
        assert matcher(item), f"{case_name} {info_key} does not match YAML test target: {item!r}"
        return item
    items = retval.get(list_key)
    assert isinstance(items, list) and items, f"{case_name} response does not contain {list_key}: {format_value_summary(payload)}"
    for item in items:
        if isinstance(item, dict) and matcher(item):
            return item
    raise AssertionError(f"{case_name} cannot find expected item in {list_key}: {format_value_summary(payload)}")


def find_ont_item(payload, env_config, case_name):
    retval = payload.get("retval", {}) if isinstance(payload, dict) else {}
    if not isinstance(retval, dict):
        raise AssertionError(f"{case_name} response retval is not a dict: {format_value_summary(payload)}")
    for key in ("ontinfo", "ont"):
        item = retval.get(key)
        if isinstance(item, dict):
            return item
    items = retval.get("ontinfolist") or retval.get("ontlist") or []
    assert isinstance(items, list), f"{case_name} ONT list is not a list: {format_value_summary(payload)}"
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
    raise AssertionError(f"{case_name} cannot find expected ONT SN={dut.ont_sn!r}: {format_value_summary(payload)}")


def _assert_device_fields(item, env_config):
    dut = env_config.dut
    expected = {
        "DevName": dut.device_name,
        "IPAddress": dut.device_ip,
        "DevType": dut.chassis,
    }
    controller_fw = _expected_controller_fw_version(env_config)
    if controller_fw:
        expected["BootFwVersion"] = controller_fw
    _assert_fields(item, expected, "Device")


def _assert_slot_fields(item, env_config):
    dut = env_config.dut
    _assert_fields(item, {"DevName": dut.device_name, "IPAddress": dut.device_ip, "SlotID": dut.slot_id}, "Slot")


def _assert_report_card_inventory(payload, env_config, case_name: str) -> None:
    if case_name == "slot_by_id":
        expected_cards = _expected_cards_by_slot(env_config, only_slot=env_config.dut.slot_id)
    elif case_name in {"slot_list", "slot_by_device"}:
        expected_cards = _expected_cards_by_slot(env_config)
    else:
        return
    if not expected_cards:
        return

    actual_cards = _slot_items_by_slot(payload, env_config, case_name)
    mismatches = []
    for slot_id, expected_card in expected_cards.items():
        actual = actual_cards.get(slot_id)
        if actual is None:
            mismatches.append(f"slot {slot_id}: missing expected {expected_card['type']}")
            continue
        mismatches.extend(_card_field_mismatches(actual, expected_card, slot_id))
    assert not mismatches, f"{case_name} card inventory mismatches: {'; '.join(mismatches)}"


def _expected_cards_by_slot(env_config, only_slot: str | None = None) -> dict[str, dict]:
    cards = env_config.node_target.get("cards", {})
    if not isinstance(cards, dict):
        return {}
    expected = {}
    report_cards = env_config.hardware.report_card_entries(env_config.dut.node_key, env_config.node_target)
    for label, _key, card in report_cards:
        slot_id = str(card.get("slot_id", ""))
        if only_slot is not None and slot_id != str(only_slot):
            continue
        expected[slot_id] = {
            "label": label,
            "type": label,
            "fw_version": str(card.get("fw_version", "")),
            "hw_version": str(card.get("hw_version", "")),
        }
    return expected


def _slot_items_by_slot(payload, env_config, case_name: str) -> dict[str, dict]:
    retval = payload.get("retval", {}) if isinstance(payload, dict) else {}
    if not isinstance(retval, dict):
        raise AssertionError(f"{case_name} response retval is not a dict: {format_value_summary(payload)}")
    items = []
    if isinstance(retval.get("slotinfo"), dict):
        items = [retval["slotinfo"]]
    elif isinstance(retval.get("slotinfolist"), list):
        items = retval["slotinfolist"]
    actual = {}
    for item in items:
        if not isinstance(item, dict) or item.get("DevName") != env_config.dut.device_name:
            continue
        slot_id = str(item.get("SlotID") or item.get("Slot") or "")
        if slot_id:
            actual[slot_id] = item
    return actual


def _card_field_mismatches(actual, expected, slot_id: str) -> list[str]:
    mismatches = []
    for keys, expected_value, label in (
        (("RealType", "CardType", "cardType", "type"), expected["type"], "card type"),
        (("FwVersion", "FW Version", "fwVersion", "fw_version"), expected["fw_version"], "FW version"),
        (("AdminState", "adminState"), EXPECTED_ENABLED_STATE, "admin state"),
        (("OperationStatus", "operationStatus"), EXPECTED_UP_OPERATION_STATE, "operation status"),
    ):
        actual_value = _first_present_value(actual, keys)
        if actual_value is None:
            mismatches.append(f"slot {slot_id} {label}: missing one of {keys}")
        elif str(actual_value) != str(expected_value):
            mismatches.append(f"slot {slot_id} {label}: expected {expected_value!r}, got {actual_value!r}")
    if expected.get("hw_version"):
        actual_hw = _first_present_value(actual, ("HwVersion", "HW Version", "hwVersion", "hw_version"))
        if actual_hw is None:
            mismatches.append(f"slot {slot_id} HW version: missing one of HwVersion/HW Version/hwVersion/hw_version")
        elif str(actual_hw) != str(expected["hw_version"]):
            mismatches.append(f"slot {slot_id} HW version: expected {expected['hw_version']!r}, got {actual_hw!r}")
    return mismatches


def _first_present_value(actual, keys):
    for key in keys:
        if key in actual:
            return actual[key]
    return None


def _assert_port_fields(item, env_config):
    dut = env_config.dut
    target = _expected_port_target(env_config)
    _assert_fields(
        item,
        {
            "DevName": dut.device_name,
            "IPAddress": dut.device_ip,
            "SlotID": target["slot_id"],
            "PortID": target["port_id"],
        },
        "Port",
    )
    checks = [
        lambda: _assert_any_field(item, ("SubmapName", "Submap Name", "submapName"), env_config.node_target.get("submap_name", ""), "Port"),
        lambda: _assert_any_field(item, ("PortName", "Port Name", "portName"), dut.ge_port_name, "Port"),
        lambda: _assert_port_type(item, env_config),
        lambda: _assert_any_field(item, ("portAdminState", "AdminState", "adminState"), EXPECTED_ENABLED_STATE, "Port"),
        lambda: _assert_any_field(
            item,
            ("portOperationStatus", "OperationStatus", "operationStatus"),
            EXPECTED_PORT_UP_OPERATION_STATE,
            "Port",
        ),
        lambda: _assert_optional_port_speed(item, env_config),
        lambda: _assert_any_field_present(item, ("Telephone", "telephone"), "Port"),
        lambda: _assert_any_field_present(item, ("txPower", "TxPower", "Tx Power"), "Port"),
        lambda: _assert_any_field_present(item, ("rxPower", "RxPower", "Rx Power"), "Port"),
    ]
    mismatches = []
    for check in checks:
        try:
            check()
        except AssertionError as error:
            mismatches.append(str(error))
    assert not mismatches, f"Port inventory mismatches: {'; '.join(mismatches)}"


def _assert_ont_fields(item, env_config, ont_template: str | None = None):
    dut = env_config.dut
    _assert_any_field(item, ("DevName",), dut.device_name, "ONT")
    _assert_any_field(item, ("IPAddress", "IP"), dut.device_ip, "ONT")
    _assert_any_field(item, ("Slot", "SlotID"), dut.slot_id, "ONT")
    _assert_any_field(item, ("Port", "PortID"), dut.port_id, "ONT")
    _assert_any_field(item, ("ONT", "ONTID"), dut.ont_id, "ONT")
    _assert_any_field(item, ("sn", "SN", "SerialNumber"), dut.ont_sn, "ONT")
    _assert_any_field(item, ("password",), dut.ont_password, "ONT")
    _assert_any_field(item, ("templateName", "ontTemplate"), ont_template or dut.ont_template, "ONT")
    _assert_any_field(item, ("description", "Desc"), dut.ont_description, "ONT")
    _assert_any_field(item, ("model", "ONTModel", "OntModel"), _expected_ont_model(env_config), "ONT")
    _assert_active_ont_fw_image(item, env_config)


def _expected_controller_fw_version(env_config) -> str:
    controller = env_config.hardware.controller_card_name(env_config.dut.node_key, env_config.node_target)
    if not controller:
        return ""
    resolved = env_config.hardware.resolve_card(env_config.node_target, controller)
    if resolved is None:
        return ""
    return str(resolved[2].get("fw_version", ""))


def _expected_ont_model(env_config) -> str:
    ont = env_config.node_target.get("ont", {})
    return str(ont.get("model") or "")


def _assert_port_type(item, env_config) -> None:
    expected_type = _expected_port_value(env_config, "port_type")
    if not expected_type:
        return
    actual_value = _first_present_value(item, ("PortType", "portType", "type", "PortTypeName"))
    assert actual_value is not None, f"Port missing one of PortType/portType/type/PortTypeName: {item!r}"
    expected_normalized = str(expected_type).strip().lower()
    actual_normalized = str(actual_value).strip().lower()
    allowed = PORT_TYPE_ALIASES.get(expected_normalized, {expected_normalized})
    assert actual_normalized in allowed, (
        f"Port type mismatch: expected {expected_type!r} ({sorted(allowed)}), got {actual_value!r}. Full data: {item!r}"
    )


def _assert_optional_port_speed(item, env_config) -> None:
    expected_speed = _expected_port_value(env_config, "port_speed")
    if not expected_speed:
        return
    actual_speed = _first_present_value(item, ("PortSpeed", "portSpeed", "Speed", "speed"))
    assert actual_speed is not None, f"Port missing one of PortSpeed/portSpeed/Speed/speed: {item!r}"
    assert str(actual_speed).lower() == str(expected_speed).lower(), (
        f"Port speed mismatch: expected {expected_speed!r}, got {actual_speed!r}. Full data: {item!r}"
    )



def _expected_port_value(env_config, field: str) -> str:
    card = env_config.node_target.get("cards", {}).get(env_config.node_target.get("ge_service_card"), {})
    ports = card.get("ports", {}) if isinstance(card, dict) else {}
    for port in ports.values():
        if isinstance(port, dict) and str(port.get("port_id")) == env_config.dut.ge_port_id:
            return str(port.get(field, ""))
    return ""


def _expected_port_target(env_config) -> dict[str, str]:
    dut = env_config.dut
    return {
        "slot_id": dut.ge_slot_id or dut.slot_id,
        "port_id": dut.ge_port_id or dut.port_id,
    }


def _assert_any_field_present(item, keys, label: str) -> None:
    actual_value = _first_present_value(item, keys)
    assert actual_value not in (None, ""), f"{label} missing one of {'/'.join(keys)}: {item!r}"


def _assert_active_ont_fw_image(item, env_config) -> None:
    expected = str(env_config.node_target.get("ont", {}).get("fw_image") or "")
    if not expected:
        return
    actual = _active_ont_fw_image(item)
    assert actual is not None, f"ONT missing active FW image fields versionA/versionB/activeVersion: {item!r}"
    assert str(actual) == expected, f"ONT active FW image mismatch: expected {expected!r}, got {actual!r}. Full data: {item!r}"


def _active_ont_fw_image(item) -> str | None:
    active = str(item.get("activeVersion", "")).strip().lower()
    if active.endswith("1"):
        return item.get("versionA")
    if active.endswith("2"):
        return item.get("versionB")
    return item.get("activeFwVersion") or item.get("fw_image") or item.get("version")


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


def _response_summary(response):
    return format_response_summary(response) if response is not None else "None"


def _ont_inventory_status(response, env_config):
    if response is None:
        return "None"
    summary = format_response_summary(response)
    if response.retstatus != "Success":
        return summary
    try:
        item = find_ont_item(response.json, env_config, "ont_by_sn")
    except Exception:
        item = None
    if not isinstance(item, dict):
        retval = response.json.get("retval", {}) if isinstance(response.json, dict) else {}
        item = retval.get("ontinfo") if isinstance(retval, dict) else None
    if not isinstance(item, dict):
        return summary
    fields = {
        "ONT": item.get("ONT") or item.get("ONTID"),
        "sn": item.get("sn") or item.get("SN") or item.get("SerialNumber"),
        "Slot": item.get("Slot") or item.get("SlotID"),
        "Port": item.get("Port") or item.get("PortID"),
        "OntAdminState": item.get("OntAdminState"),
        "OntOperationStatus": item.get("OntOperationStatus"),
        "templateName": item.get("templateName"),
        "description": item.get("description"),
    }
    compact = {key: value for key, value in fields.items() if value not in {None, ""}}
    return f"{summary}; ONT fields={compact!r}"


def _ge_port_inventory_status(response):
    if response is None:
        return "None"
    summary = format_response_summary(response)
    if response.retstatus != "Success":
        return summary
    retval = response.json.get("retval", {}) if isinstance(response.json, dict) else {}
    item = retval.get("portinfo") if isinstance(retval, dict) else None
    if not isinstance(item, dict):
        return summary
    fields = {
        "PortName": item.get("PortName"),
        "SlotID": item.get("SlotID"),
        "PortID": item.get("PortID"),
        "portAdminState": item.get("portAdminState"),
        "portOperationStatus": item.get("portOperationStatus"),
        "Enable": item.get("Enable"),
        "PortType": item.get("PortType"),
        "txPower": item.get("txPower"),
        "rxPower": item.get("rxPower"),
    }
    compact = {key: value for key, value in fields.items() if value not in {None, ""}}
    return f"{summary}; Port fields={compact!r}"
