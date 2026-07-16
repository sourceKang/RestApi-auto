from __future__ import annotations

import copy
import json
import time

import pytest

from services.profile import ProfileService
from cases.payloads import ge_service_payload, ont_service_payload
from utils.allure_helpers import allure_step
from utils.case_metadata import attach_case_id
from utils.diagnostics import format_response_summary, format_value_summary


class InvalidParamsService:
    def __init__(self, api_client, env_config, profile_service=None) -> None:
        self.api_client = api_client
        self.env_config = env_config
        self.profile_service = profile_service or ProfileService(api_client)

    def verify_ont_service_post_invalid_parameters(self, session_id: str, ont_template: str | None = None) -> None:
        attach_case_id("EMS1-7023", "test_ont_service_post_various_invalid_parameters_should_return_error")
        if ont_template is None:
            with allure_step("Ensure ONT template profile exists before invalid ONT service POST checks"):
                self.ensure_profile_exists(session_id, self.env_config.dut.ont_template)

        invalid_cases = [
            ("invalid_ont_template", {"ontservice": {"data": {"templateprof": "#invalid_profile"}}}, "ONT Template not found."),
            ("dspir_below_minimum", {"ontservice": {"data": {"dspir": "127"}}}, "dspir: Range 128~10000000"),
            ("wifi5inactive1_invalid_value", {"ontservice": {"data": {"wifi5inactive1": "123invalid"}}}, "inactive value is error"),
            (
                "wifi5ssid1_too_long",
                {"ontservice": {"data": {"wifi5ssid1": "012345678901234567890123456789AB"}}},
                "maximum length is 31",
            ),
        ]

        path = f"/ontservice/{self.env_config.dut.ont_sn}"
        for name, patch, expected in invalid_cases:
            with allure_step(f"Verify ONT service POST rejects {name}"):
                self.delete_ont_service_if_exists(session_id)
                payload = copy.deepcopy(ont_service_payload(self.env_config, "legacy_invalid_ont", ont_template=ont_template))
                deep_merge(payload, patch)
                response = self.post_ont_invalid_after_sn_release(session_id, path, payload)
                assert_failure_contains(response, expected)

    def post_ont_invalid_after_sn_release(
        self,
        session_id: str,
        path: str,
        payload: dict,
        *,
        timeout: int = 180,
        initial_interval: int = 5,
        max_interval: int = 15,
    ):
        deadline = time.monotonic() + timeout
        interval = initial_interval
        response = self.api_client.request("POST", path, session=session_id, json=payload)
        if not _ont_sn_already_exists(response):
            return response

        self.delete_ont_service_if_exists(session_id)
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            time.sleep(min(interval, max(remaining, 0)))
            response = self.api_client.request("POST", path, session=session_id, json=payload)
            if not _ont_sn_already_exists(response):
                return response
            interval = min(interval * 2, max_interval)

        raise AssertionError(
            "ONT SN remained reserved after the prior service was removed; "
            f"invalid payload validation could not start. Last response: {format_response_summary(response)}"
        )

    def verify_ge_service_post_invalid_parameters(self, session_id: str, ge_template: str | None = None) -> None:
        attach_case_id("EMS1-7024", "test_ge_service_post_various_invalid_parameters_should_return_error")
        if ge_template is None:
            with allure_step("Ensure GE template profile exists before invalid GE service POST checks"):
                self.ensure_profile_exists(session_id, self.env_config.dut.ge_template)

        dut = self.env_config.dut
        invalid_cases = [
            ("device_name_not_found", f"/geservice/NotExistDevice/{dut.ge_slot_id}/{dut.ge_port_id}", {}, "Device name not found."),
            ("slot_not_found", f"/geservice/{dut.device_name}/999/{dut.ge_port_id}", {}, "Slot or Port not found."),
            ("port_not_found", f"/geservice/{dut.device_name}/{dut.ge_slot_id}/999", {}, "Slot or Port not found."),
            (
                "ge_template_not_found",
                f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}",
                {"geservice": {"geTemplate": "#NotExistTemplate"}},
                "GE Template not found.",
            ),
            (
                "tel_too_long",
                f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}",
                {"geservice": {"Tel": "012345678901234567890123456789012"}},
                "Telephone: Maximum length is 31",
            ),
            (
                "port_name_too_long",
                f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}",
                {"geservice": {"PortName": "012345678901234567890123456789012"}},
                "Port Name: Maximum length is 31",
            ),
        ]

        for name, path, patch, expected in invalid_cases:
            with allure_step(f"Verify GE service POST rejects {name}"):
                self.delete_ge_service_if_exists(session_id)
                payload = copy.deepcopy(ge_service_payload(self.env_config, "legacy_invalid_ge", ge_template=ge_template))
                deep_merge(payload, patch)
                response = self.api_client.request("POST", path, session=session_id, json=payload)
                assert_failure_contains(response, expected)

    def verify_history_alarm_invalid_parameters(self, session_id: str) -> None:
        attach_case_id("EMS1-7030", "test_history_alarm_various_invalid_parameters_should_return_error")
        invalid_cases = [
            (
                "history_alarm_filter_no_match",
                "GET",
                "/historyalarm",
                {"alarmfilter": json.dumps({"KeyWord": ["not_exist_ip", "no_such_event"]})},
                "No data found in the database.",
            ),
            ("history_alarm_by_id_missing", "GET", "/historyalarm/123123546/456789764", None, "No data found in the database."),
            ("history_alarm_delete_missing", "DELETE", "/historyalarm/45642578/78976548", None, "The alarm does not exist."),
        ]
        for name, method, path, params, expected in invalid_cases:
            with allure_step(f"Verify history alarm API rejects {name}"):
                response = self.api_client.request(method, path, session=session_id, params=params)
                assert_failure_contains(response, expected)

    def verify_device_name_invalid_parameters(self, session_id: str) -> None:
        attach_case_id("EMS1-7031", "test_get_device_name_with_invalid_parameters_should_return_error")
        with allure_step("Verify GET /device/{devicename} rejects a non-existent device name"):
            response = self.api_client.request("GET", "/device/not_exist_device_123", session=session_id)
            assert_failure_contains(response, "No data found in the database.")

    def verify_slot_invalid_parameters(self, session_id: str) -> None:
        attach_case_id("EMS1-7032", "test_slot_api_with_invalid_parameters_should_return_error")
        invalid_cases = [
            ("slot_by_devicename_missing_device", "/slot/no_such_device", "No data found in the database."),
            ("slot_by_id_missing_device_and_slot", "/slot/no_such_device/999", "No data found in the database."),
        ]
        for name, path, expected in invalid_cases:
            with allure_step(f"Verify slot API rejects {name}"):
                response = self.api_client.request("GET", path, session=session_id)
                assert_failure_contains(response, expected)

    def verify_port_invalid_parameters(self, session_id: str) -> None:
        attach_case_id("EMS1-7033", "test_port_api_with_invalid_parameters_should_return_error")
        invalid_cases = [
            ("port_by_devicename_missing_device", "/port/no_such_device", "No data found in the database."),
            ("port_by_slot_missing_device_and_slot", "/port/no_such_device/999", "No data found in the database."),
            ("port_by_id_missing_device_slot_port", "/port/no_such_device/999/1000", "No data found in the database."),
        ]
        for name, path, expected in invalid_cases:
            with allure_step(f"Verify port API rejects {name}"):
                response = self.api_client.request("GET", path, session=session_id)
                assert_failure_contains(response, expected)

    def verify_ont_invalid_parameters(self, session_id: str) -> None:
        attach_case_id("EMS1-7034", "test_ont_api_with_invalid_parameters_should_return_error")
        invalid_cases = [
            ("ont_by_sn_missing", "/ont/sn/not_exist_sn_999", "No data found in the database."),
            ("ont_by_description_missing", "/ont/description/no_such_desc", "No data found in the database."),
            ("ont_by_devicename_missing_device", "/ont/no_such_device", "No data found in the database."),
            ("ont_by_slot_missing_device_slot", "/ont/no_such_device/999", "No data found in the database."),
            ("ont_by_port_missing_device_slot_port", "/ont/no_such_device/999/888", "No data found in the database."),
            ("ont_by_id_missing_device_slot_port_ont", "/ont/no_such_device/999/888/123", "No data found in the database."),
        ]
        for name, path, expected in invalid_cases:
            with allure_step(f"Verify ONT API rejects {name}"):
                response = self.api_client.request("GET", path, session=session_id)
                assert_failure_contains(response, expected)

    def ensure_profile_exists(self, session_id: str, profilename: str, seen=None) -> None:
        self.profile_service.ensure_prerequisite_profile(session_id, profilename, seen=seen)

    def delete_ont_service_if_exists(self, session_id: str) -> None:
        path = f"/ontservice/{self.env_config.dut.ont_sn}"
        existing = self.api_client.request("GET", path, session=session_id)
        if existing.retstatus == "Success":
            self.api_client.request("DELETE", path, session=session_id)
            self.wait_for_ont_service_removed(session_id)

    def wait_for_ont_service_removed(self, session_id: str, timeout: int = 180, interval: int = 15) -> None:
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
        raise AssertionError(f"ONT service was not removed before invalid-param check. Last response: {format_response_summary(last)}")

    def delete_ge_service_if_exists(self, session_id: str, timeout: int = 120, interval: int = 5) -> None:
        dut = self.env_config.dut
        port_path = f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}"
        existing = self.api_client.request("GET", port_path, session=session_id)
        if existing.retstatus != "Success":
            return
        service_id = ge_service_id(existing.json)
        if not service_id:
            return
        self.api_client.request("DELETE", f"/geservice/{service_id}", session=session_id)
        deadline = time.monotonic() + timeout
        while time.monotonic() <= deadline:
            response = self.api_client.request("GET", port_path, session=session_id)
            if response.retstatus == "Fail" and "No data found" in response.retresult:
                return
            time.sleep(interval)
        raise AssertionError(
            "GE service was not removed before invalid-param check. "
            f"Last response: {format_response_summary(response)}"
        )


def assert_failure_contains(response, expected_text: str) -> None:
    body = response.json if isinstance(response.json, dict) else {"raw": response.text}
    result = json.dumps(body, ensure_ascii=False, default=str)
    assert response.retstatus == "Fail" or response.status_code >= 400, (
        f"Expected failure but got success. {format_response_summary(response)}"
    )
    assert expected_text.lower() in result.lower(), (
        f"Expected error containing {expected_text!r}, got {format_value_summary(body)}"
    )


def _ont_sn_already_exists(response) -> bool:
    return response.retstatus == "Fail" and "already exists" in response.retresult.lower()


def deep_merge(target: dict, patch: dict) -> dict:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            deep_merge(target[key], value)
        else:
            target[key] = value
    return target



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
