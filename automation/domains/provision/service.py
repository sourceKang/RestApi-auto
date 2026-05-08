from __future__ import annotations

import json
import time

import pytest

from automation.domains.endpoint_case import assert_permission_rejected, request_endpoint_case
from cases.case_catalog import profile_definition_by_name
from cases.payloads import ge_service_payload, ont_service_payload
from models.api import EndpointCase
from utils.allure_helpers import allure_step
from utils.assertions import assert_api_failure, assert_api_success
from utils.case_metadata import attach_case_id
from utils.diagnostics import format_response_summary, format_value_summary


class ProvisionService:
    def __init__(self, api_client, env_config) -> None:
        self.api_client = api_client
        self.env_config = env_config

    def ensure_seed_data(self, session_id: str, cleanup_registry) -> None:
        with allure_step("Ensure prerequisite ONT template profile exists"):
            self.ensure_profile_by_name(session_id, cleanup_registry, self.env_config.dut.ont_template)
        with allure_step("Ensure prerequisite GE template profile exists"):
            self.ensure_profile_by_name(session_id, cleanup_registry, self.env_config.dut.ge_template)
        with allure_step("Create or normalize recorded ONT service data for GET verification"):
            self.ensure_recorded_ont_service(session_id)
        with allure_step("Create or normalize recorded GE service data for GET verification"):
            self.ensure_recorded_ge_service(session_id)

    def verify_read_success(self, session_id: str, case: EndpointCase, role_name: str) -> None:
        response = request_endpoint_case(
            self.api_client,
            self.env_config,
            session_id,
            case,
            step=f"GET {case.name} as {role_name}",
        )
        if response.retstatus == "Fail" and "No data found" in response.retresult:
            pytest.fail(
                f"{case.name} expected seeded provision data for {role_name} GET, but EMS returned no data: "
                f"{format_response_summary(response)}"
            )
        assert_api_success(response)
        assert_provision_get_matches_recorded_data(response.json, self.env_config, case.name)

    def verify_read_rejected(self, session_id: str, case: EndpointCase) -> None:
        response = request_endpoint_case(
            self.api_client,
            self.env_config,
            session_id,
            case,
            step=f"Verify noaccess cannot GET {case.name}",
        )
        assert_permission_rejected(response)

    def verify_mutation_rejected(self, session_id: str, case: EndpointCase, role_name: str) -> None:
        response = request_endpoint_case(
            self.api_client,
            self.env_config,
            session_id,
            case,
            step=f"Verify {role_name} cannot mutate {case.name}",
            payload=True,
        )
        assert_permission_rejected(response)

    def verify_ont_service_crud(self, session_id: str, cleanup_registry) -> None:
        attach_case_id("EMS1-6666", "test_post_ont_service_by_sn")
        attach_case_id("EMS1-6647", "test_get_ont_service")
        attach_case_id("EMS1-6665", "test_get_ont_service_by_sn")
        attach_case_id("EMS1-6667", "test_put_ont_service_by_sn")
        attach_case_id("EMS1-6668", "test_patch_ont_service_by_sn")
        attach_case_id("EMS1-6669", "test_delete_ont_service_by_sn")
        path = f"/ontservice/{self.env_config.dut.ont_sn}"
        create_payload = recorded_ont_service_payload(self.env_config)
        modified_payload = recorded_ont_service_modified_payload(self.env_config)
        with allure_step("Ensure ONT template profile exists"):
            self.ensure_profile_by_name(session_id, cleanup_registry, self.env_config.dut.ont_template)

        with allure_step("Clean existing ONT service before create"):
            self.delete_ont_service_if_exists(session_id, timeout=180, interval=15)

        cleanup_registry.add(lambda: self.delete_ont_service_if_exists(session_id, timeout=180, interval=15))

        with allure_step("POST ONT service by SN using recorded validation data"):
            create = self.post_ont_service_with_retry(session_id, create_payload)
            assert_api_success(create)
            self.wait_for_ont_service_state(session_id, {"Success"}, timeout=180, interval=15, initial_delay=30)

        with allure_step("GET ONT service list and verify created service data"):
            get_list = self.api_client.request(
                "GET",
                "/ontservice",
                session=session_id,
                params={"ontservicefilter": f'{{"SN":"{self.env_config.dut.ont_sn}"}}'},
            )
            assert_api_success(get_list)
            assert_ont_service_fields(find_ont_service(get_list.json, self.env_config), self.env_config, create_payload)

        with allure_step("GET ONT service by SN and verify created service data"):
            get_created = self.api_client.request("GET", path, session=session_id)
            assert_api_success(get_created)
            assert_ont_service_fields(ont_service_info(get_created.json), self.env_config, create_payload)

        with allure_step("PUT ONT service by SN using recorded modified data"):
            update = self.api_client.request("PUT", path, session=session_id, json=modified_payload)
            assert_api_success(update)
            self.wait_for_ont_service_state(session_id, {"Success"})
            get_modified = self.api_client.request("GET", path, session=session_id)
            assert_api_success(get_modified)
            assert_ont_service_fields(ont_service_info(get_modified.json), self.env_config, modified_payload)

        with allure_step("PATCH ONT service by SN and verify reprovision state when EMS exposes it"):
            patch = self.api_client.request("PATCH", path, session=session_id)
            assert_api_success(patch)
            self.wait_for_ont_service_state(session_id, {"Success", "Reprovision"})
            patched = self.api_client.request("GET", path, session=session_id)
            assert_api_success(patched)
            state = ont_service_info(patched.json).get("state")
            if state is not None:
                assert state in {"Reprovision", "Success"}, (
                    f"Unexpected ONT service state after PATCH: {format_response_summary(patched)}"
                )

        with allure_step("DELETE ONT service by SN and verify it is removed"):
            delete = self.api_client.request("DELETE", path, session=session_id)
            assert_api_success(delete)
            self.wait_for_ont_service_removed(session_id)
            removed = self.api_client.request("GET", path, session=session_id)
            assert_api_failure(removed, accepted_messages=("No data found", "serial number does not exist"))

    def verify_ge_service_crud(self, session_id: str, cleanup_registry) -> None:
        attach_case_id("EMS1-6661", "test_post_ge_service_by_port")
        attach_case_id("EMS1-6648", "test_get_ge_service")
        attach_case_id("EMS1-6660", "test_get_ge_service_by_port")
        attach_case_id("EMS1-6662", "test_put_ge_service_by_serviceid")
        attach_case_id("EMS1-6663", "test_patch_ge_service_by_serviceid")
        attach_case_id("EMS1-6664", "test_delete_ge_service_by_serviceid")
        dut = self.env_config.dut
        port_path = f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}"
        create_payload = recorded_ge_service_payload(self.env_config)
        modified_payload = recorded_ge_service_modified_payload(self.env_config)
        with allure_step("Ensure GE template profile exists"):
            self.ensure_profile_by_name(session_id, cleanup_registry, dut.ge_template)

        with allure_step("Clean existing GE service before create"):
            self.delete_ge_service_if_exists(session_id)

        with allure_step("POST GE service by port using recorded validation data"):
            create = self.post_ge_service_with_retry(session_id, create_payload)
            assert_api_success(create)
            self.wait_for_ge_service_state(session_id, {"Success"})

        with allure_step("GET GE service by port and verify created service data"):
            get_created = self.api_client.request("GET", port_path, session=session_id)
            assert_api_success(get_created)
            assert_ge_service_fields(ge_service_info(get_created.json), self.env_config, create_payload)
            service_id = ge_service_id(get_created.json)
            assert service_id, f"GE service was created but no service id was found: {format_response_summary(get_created)}"

        cleanup_registry.add(lambda: self.api_client.request("DELETE", f"/geservice/{service_id}", session=session_id))

        with allure_step("GET GE service list and verify created service data"):
            get_list = self.api_client.request("GET", "/geservice", session=session_id, params={"geservicefilter": f'{{"IP":"{dut.device_ip}"}}'})
            assert_api_success(get_list)
            assert_ge_service_fields(find_ge_service(get_list.json, self.env_config), self.env_config, create_payload)

        with allure_step("PUT GE service by service ID using recorded modified data"):
            update = self.api_client.request("PUT", f"/geservice/{service_id}", session=session_id, json=modified_payload)
            assert_api_success(update)
            self.wait_for_ge_service_state(session_id, {"Success"})
            get_modified = self.api_client.request("GET", port_path, session=session_id)
            assert_api_success(get_modified)
            assert_ge_service_fields(ge_service_info(get_modified.json), self.env_config, modified_payload)

        with allure_step("PATCH GE service by service ID and verify service remains readable"):
            patch = self.api_client.request("PATCH", f"/geservice/{service_id}", session=session_id)
            assert_api_success(patch)
            self.wait_for_ge_service_state(session_id, {"Success", "Reprovision"})
            patched = self.api_client.request("GET", port_path, session=session_id)
            assert_api_success(patched)
            assert_ge_service_fields(ge_service_info(patched.json), self.env_config, modified_payload)

        with allure_step("DELETE GE service by service ID and verify it is removed"):
            delete = self.api_client.request("DELETE", f"/geservice/{service_id}", session=session_id)
            assert_api_success(delete)
            self.wait_for_ge_service_removed(session_id)
            removed = self.api_client.request("GET", port_path, session=session_id)
            assert_api_failure(removed, accepted_messages=("No data found", "does not exist"))

    def ensure_recorded_ont_service(self, session_id: str) -> None:
        path = f"/ontservice/{self.env_config.dut.ont_sn}"
        payload = recorded_ont_service_payload(self.env_config)
        existing = self.api_client.request("GET", path, session=session_id)
        if existing.retstatus == "Success":
            update = self.api_client.request("PUT", path, session=session_id, json=payload)
            assert_api_success(update)
            self.wait_for_ont_service_state(session_id, {"Success"}, timeout=180, interval=15, initial_delay=20)
            return
        create = self.api_client.request("POST", path, session=session_id, json=payload)
        assert_api_success(create)
        self.wait_for_ont_service_state(session_id, {"Success"}, timeout=180, interval=15, initial_delay=30)

    def ensure_recorded_ge_service(self, session_id: str) -> None:
        dut = self.env_config.dut
        path = f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}"
        payload = recorded_ge_service_payload(self.env_config)
        existing = self.api_client.request("GET", path, session=session_id)
        if existing.retstatus == "Success":
            service_id = ge_service_id(existing.json)
            assert service_id, f"Existing GE service does not expose service id: {format_response_summary(existing)}"
            update = self.api_client.request("PUT", f"/geservice/{service_id}", session=session_id, json=payload)
            if update.retstatus == "Success":
                self.wait_for_ge_service_state(session_id, {"Success"})
                return
            if "does not exist" not in update.retresult:
                assert_api_success(update)
            self.delete_ge_service_if_exists(session_id)
        create = self.post_ge_service_with_retry(session_id, payload)
        assert_api_success(create)
        self.wait_for_ge_service_state(session_id, {"Success"})

    def post_ont_service_with_retry(self, session_id: str, payload, timeout: int = 180):
        path = f"/ontservice/{self.env_config.dut.ont_sn}"
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() <= deadline:
            response = self.api_client.request("POST", path, session=session_id, json=payload)
            last = response
            if response.retstatus == "Success":
                return response
            if "already exists" not in response.retresult:
                return response
            self.delete_ont_service_if_exists(session_id, timeout=180, interval=15)
            deadline = time.monotonic() + timeout
        return last

    def delete_ont_service_if_exists(self, session_id: str, timeout: int = 180, interval: int = 15) -> None:
        path = f"/ontservice/{self.env_config.dut.ont_sn}"
        existing = self.api_client.request("GET", path, session=session_id)
        if existing.retstatus != "Success":
            return
        delete = self.api_client.request("DELETE", path, session=session_id)
        if delete.retstatus == "Fail" and "serial number does not exist" in delete.retresult:
            return
        assert_api_success(delete)
        self.wait_for_ont_service_removed(session_id, timeout=timeout, interval=interval)

    def post_ge_service_with_retry(self, session_id: str, payload, timeout: int = 180, interval: int = 5):
        dut = self.env_config.dut
        path = f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}"
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() <= deadline:
            response = self.api_client.request("POST", path, session=session_id, json=payload)
            last = response
            if response.retstatus == "Success":
                return response
            if "exist in service list" not in response.retresult and "already exists" not in response.retresult:
                return response
            self.delete_ge_service_if_exists(session_id)
            time.sleep(interval)
        return last

    def delete_ge_service_if_exists(self, session_id: str, wait_after_delete: int = 50) -> None:
        dut = self.env_config.dut
        port_path = f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}"
        existing = self.api_client.request("GET", port_path, session=session_id)
        if existing.retstatus != "Success":
            return
        service_id = ge_service_id(existing.json)
        assert service_id, f"Existing GE service does not expose service id: {format_response_summary(existing)}"
        delete = self.api_client.request("DELETE", f"/geservice/{service_id}", session=session_id)
        if delete.retstatus != "Success" and "does not exist" not in delete.retresult:
            assert_api_success(delete)
        time.sleep(wait_after_delete)

    def wait_for_ont_service_state(
        self,
        session_id: str,
        expected_states: set[str],
        timeout: int = 180,
        interval: int = 15,
        initial_delay: int = 0,
    ):
        path = f"/ontservice/{self.env_config.dut.ont_sn}"
        if initial_delay > 0:
            time.sleep(initial_delay)
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() <= deadline:
            response = self.api_client.request("GET", path, session=session_id)
            last = response
            if response.retstatus == "Success":
                service = ont_service_info(response.json)
                if service.get("state") in expected_states:
                    return service
            time.sleep(interval)
        raise AssertionError(f"ONT service did not reach states {expected_states!r}. Last response: {_response_summary(last)}")

    def wait_for_ge_service_state(self, session_id: str, expected_states: set[str], timeout: int = 120, interval: int = 5):
        dut = self.env_config.dut
        path = f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}"
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() <= deadline:
            response = self.api_client.request("GET", path, session=session_id)
            last = response
            if response.retstatus == "Success":
                service = ge_service_info(response.json)
                if service.get("state") in expected_states:
                    return service
            time.sleep(interval)
        raise AssertionError(f"GE service did not reach states {expected_states!r}. Last response: {_response_summary(last)}")

    def wait_for_ont_service_removed(self, session_id: str, timeout: int = 60, interval: int = 3) -> None:
        path = f"/ontservice/{self.env_config.dut.ont_sn}"
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() <= deadline:
            response = self.api_client.request("GET", path, session=session_id)
            last = response
            if response.retstatus == "Fail" and (
                "No data found" in response.retresult or "serial number does not exist" in response.retresult
            ):
                return
            time.sleep(interval)
        raise AssertionError(f"ONT service was not removed. Last response: {_response_summary(last)}")

    def wait_for_ge_service_removed(self, session_id: str, timeout: int = 60, interval: int = 3) -> None:
        dut = self.env_config.dut
        path = f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}"
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() <= deadline:
            response = self.api_client.request("GET", path, session=session_id)
            last = response
            if response.retstatus == "Fail" and "No data found" in response.retresult:
                return
            time.sleep(interval)
        raise AssertionError(f"GE service was not removed. Last response: {_response_summary(last)}")

    def ensure_profile_by_name(self, session_id: str, cleanup_registry, profilename: str, seen=None) -> None:
        definition = profile_definition_by_name(profilename)
        if definition is None:
            pytest.skip(f"No converted profile data found for prerequisite profile {profilename}.")
        seen = seen or set()
        key = (definition["profiletype"], definition["profilename"])
        if key in seen:
            return
        seen.add(key)

        for dependency in _profile_refs(definition.get("post_profile_info", {})):
            self.ensure_profile_by_name(session_id, cleanup_registry, dependency, seen)

        path = f"/profile/{definition['profiletype']}/{definition['profilename']}"
        existing = self.api_client.request("GET", path, session=session_id)
        if existing.retstatus == "Success":
            return

        created = self.api_client.request(
            "POST",
            path,
            session=session_id,
            json={"Content": definition.get("post_profile_info", {})},
        )
        if created.retstatus != "Success":
            pytest.skip(f"Cannot create prerequisite profile {profilename}: {format_response_summary(created)}")
        cleanup_registry.add(lambda: self.api_client.request("DELETE", path, session=session_id))


def ge_service_id(payload):
    if not isinstance(payload, dict):
        return None
    retval = payload.get("retval", {})
    if not isinstance(retval, dict):
        return None
    service = retval.get("geserviceinfo", retval)
    if isinstance(service, dict):
        return service.get("GeServiceID") or service.get("geserviceid") or service.get("serviceid")
    return None


def recorded_ont_service_payload(env_config):
    payload = ont_service_payload(env_config, env_config.dut.ont_description)
    data = payload["ontservice"]["data"]
    data["description"] = env_config.dut.ont_description
    data["wifi5ssid1"] = "musk_wifi5"
    data["wifi5pass1"] = "musk1234"
    return payload


def recorded_ont_service_modified_payload(env_config):
    payload = recorded_ont_service_payload(env_config)
    data = payload["ontservice"]["data"]
    data["description"] = f"{env_config.dut.ont_description}_modify"
    data["wifi5ssid1"] = "musk_wifi5_m"
    data["wifi5pass1"] = "musk1234m"
    return payload


def recorded_ge_service_payload(env_config):
    return {
        "geservice": {
            "geTemplate": env_config.dut.ge_template,
            "Tel": env_config.dut.ge_telephone,
            "PortName": env_config.dut.ge_port_name,
        }
    }


def recorded_ge_service_modified_payload(env_config):
    return {
        "geservice": {
            "geTemplate": env_config.dut.ge_template,
            "Tel": f"{env_config.dut.ge_telephone}0123",
            "PortName": f"modify_{env_config.dut.ge_port_name}",
        }
    }


def assert_provision_get_matches_recorded_data(payload, env_config, case_name: str) -> None:
    if case_name == "ont_service_list":
        assert_ont_service_fields(find_ont_service(payload, env_config), env_config, recorded_ont_service_payload(env_config))
        return
    if case_name == "ont_service_by_sn":
        assert_ont_service_fields(ont_service_info(payload), env_config, recorded_ont_service_payload(env_config))
        return
    if case_name == "ge_service_list":
        assert_ge_service_fields(find_ge_service(payload, env_config), env_config, recorded_ge_service_payload(env_config))
        return
    if case_name == "ge_service_by_port":
        assert_ge_service_fields(ge_service_info(payload), env_config, recorded_ge_service_payload(env_config))


def ont_service_info(payload):
    retval = payload.get("retval", {}) if isinstance(payload, dict) else {}
    service = retval.get("ontserviceinfo", retval) if isinstance(retval, dict) else None
    assert isinstance(service, dict), f"ONT service response does not contain ontserviceinfo: {format_value_summary(payload)}"
    return service


def find_ont_service(payload, env_config):
    retval = payload.get("retval", {}) if isinstance(payload, dict) else {}
    services = retval.get("ontserviceinfolist", []) if isinstance(retval, dict) else []
    for service in services:
        if isinstance(service, dict) and service.get("sn") == env_config.dut.ont_sn:
            return service
    raise AssertionError(f"Cannot find ONT service SN={env_config.dut.ont_sn!r}: {format_value_summary(payload)}")


def assert_ont_service_fields(service, env_config, expected_payload):
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


def ge_service_info(payload):
    retval = payload.get("retval", {}) if isinstance(payload, dict) else {}
    service = retval.get("geserviceinfo", retval) if isinstance(retval, dict) else None
    assert isinstance(service, dict), f"GE service response does not contain geserviceinfo: {format_value_summary(payload)}"
    return service


def find_ge_service(payload, env_config):
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


def assert_ge_service_fields(service, env_config, expected_payload):
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
