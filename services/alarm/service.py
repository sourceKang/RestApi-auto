from __future__ import annotations

import json
import time

import pytest

from utils.assertions import assert_api_failure, assert_api_success
from utils.case_metadata import attach_case_id


OLT140X_CHASSIS = {"OLT1404", "OLT1408", "OLT1408A-C", "OLT1408B", "OLT1408B-IA"}


def remote_alarm_seed_commands(env_config) -> tuple[list[str], list[str]]:
    dut = env_config.dut
    if dut.chassis in OLT140X_CHASSIS:
        return (
            ["show version", "show system-information"],
            [f"show interface pon-{dut.port_id}"],
        )
    return (
        ["sh ip", "sh system"],
        ["con", f"in xpon {dut.slot_id}-{dut.port_id}"],
    )


def alarm_keywords(env_config) -> list[str]:
    dut = env_config.dut
    if dut.chassis in OLT140X_CHASSIS:
        return [dut.device_ip, dut.ont_sn, "Unregister ONT"]
    return [dut.device_ip, "Login Success"]


def expected_alarm_description(env_config) -> str:
    dut = env_config.dut
    if dut.chassis in OLT140X_CHASSIS:
        return f"Discover Unregister ONT - [pon-{dut.port_id}] Unregister ONT, SN: {dut.ont_sn}"
    return "Login Success"


def assert_matching_alarm_info(alarm_info, env_config) -> None:
    expected_description = expected_alarm_description(env_config)
    actual_description = str(alarm_info.get("Description") or alarm_info.get("description") or "")
    if env_config.dut.chassis in OLT140X_CHASSIS:
        assert actual_description.startswith(expected_description), (
            f"OLT140X alarm description mismatch: expected prefix {expected_description!r}, "
            f"got {actual_description!r}"
        )
    else:
        assert actual_description == expected_description, (
            f"Alarm description mismatch: expected {expected_description!r}, got {actual_description!r}"
        )
    assert str(alarm_info.get("DevName") or alarm_info.get("devname") or "") == env_config.dut.device_name
    assert str(alarm_info.get("DevIP") or alarm_info.get("devip") or "") == env_config.dut.device_ip


class AlarmService:
    def __init__(self, api_client, env_config) -> None:
        self.api_client = api_client
        self.env_config = env_config

    def verify_active_alarm_list(self, session_id: str) -> tuple[str, str]:
        attach_case_id("EMS1-6641", "test_get_active_alarm")
        response = self.api_client.request("GET", "/activealarm", session=session_id, params=self.alarm_filter())
        if response.retstatus == "Fail" and "No data found" in response.retresult:
            pytest.skip("No active alarm is available for this EMS environment.")
        assert_api_success(response)
        alarm = first_alarm(response.json)
        if alarm is None:
            pytest.skip("No matching active alarm is available for this EMS environment.")
        assert_matching_alarm_info(alarm, self.env_config)
        ids = alarm_ids(alarm)
        if ids is None:
            pytest.skip(f"Active alarm does not expose log/sublog ids: {alarm!r}")
        return ids

    def verify_active_alarm_ack_and_clear_if_exists(
        self,
        session_id: str,
        expected_ids: tuple[str, str] | None = None,
    ) -> tuple[str, str]:
        attach_case_id("EMS1-6658", "test_patch_active_alarm_by_id")
        if expected_ids is None:
            expected_ids = self.verify_active_alarm_list(session_id)
        logid, sublogid = expected_ids

        get_by_id = self.api_client.request("GET", f"/activealarm/{logid}/{sublogid}", session=session_id)
        assert_api_success(get_by_id)
        assert_matching_alarm_info(get_by_id.json["retval"]["alarminfo"], self.env_config)

        ack = self.api_client.request("PATCH", f"/activealarm/{logid}/{sublogid}", session=session_id)
        assert_api_success(ack)
        acked = self.api_client.request("GET", f"/activealarm/{logid}/{sublogid}", session=session_id)
        assert_api_success(acked)
        assert acked.json["retval"]["alarminfo"]["Ack"] == "1"

        clear = self.api_client.request("DELETE", f"/activealarm/{logid}/{sublogid}", session=session_id)
        assert_api_success(clear)
        cleared = self.api_client.request("GET", f"/activealarm/{logid}/{sublogid}", session=session_id)
        assert_api_failure(cleared, accepted_messages=("No data found", "does not exist"))
        self.wait_for_history_alarm_by_id(session_id, expected_ids)
        return expected_ids

    def verify_history_alarm_list(
        self,
        session_id: str,
        expected_ids: tuple[str, str] | None = None,
    ) -> tuple[str, str]:
        attach_case_id("EMS1-6642", "test_get_history_alarm")
        response = self.api_client.request("GET", "/historyalarm", session=session_id, params=self.alarm_filter())
        if response.retstatus == "Fail" and "No data found" in response.retresult:
            pytest.skip("No history alarm is available for this EMS environment.")
        assert_api_success(response)

        alarm = find_alarm_by_ids(response.json, expected_ids) if expected_ids else first_alarm(response.json)
        if alarm is None:
            if expected_ids is not None:
                pytest.fail(f"Expected history alarm {expected_ids!r} is missing from filtered history list.")
            pytest.skip("No matching history alarm is available for this EMS environment.")
        assert_matching_alarm_info(alarm, self.env_config)
        ids = alarm_ids(alarm)
        if ids is None:
            pytest.skip(f"History alarm does not expose log/sublog ids: {alarm!r}")
        return ids

    def verify_history_alarm_get_by_id_if_exists(
        self,
        session_id: str,
        expected_ids: tuple[str, str] | None = None,
    ) -> tuple[str, str]:
        attach_case_id("EMS1-6670", "test_get_history_alarm_by_id")
        if expected_ids is None:
            expected_ids = self.verify_history_alarm_list(session_id)
        logid, sublogid = expected_ids

        response = self.api_client.request("GET", f"/historyalarm/{logid}/{sublogid}", session=session_id)
        assert_api_success(response)
        assert_matching_alarm_info(response.json["retval"]["alarminfo"], self.env_config)
        return expected_ids

    def verify_history_alarm_delete_if_exists(
        self,
        session_id: str,
        expected_ids: tuple[str, str] | None = None,
    ) -> None:
        attach_case_id("EMS1-6674", "test_delete_history_alarm_by_id")
        if expected_ids is None:
            expected_ids = self.verify_history_alarm_list(session_id)
        logid, sublogid = expected_ids

        history_by_id = self.api_client.request("GET", f"/historyalarm/{logid}/{sublogid}", session=session_id)
        assert_api_success(history_by_id)
        assert_matching_alarm_info(history_by_id.json["retval"]["alarminfo"], self.env_config)

        response = self.api_client.request("DELETE", f"/historyalarm/{logid}/{sublogid}", session=session_id)
        assert_api_success(response)
        removed = self.api_client.request("GET", f"/historyalarm/{logid}/{sublogid}", session=session_id)
        assert_api_failure(removed, accepted_messages=("No data found", "does not exist"))

    def wait_for_history_alarm_by_id(
        self,
        session_id: str,
        expected_ids: tuple[str, str],
        timeout: int = 60,
        interval: int = 5,
    ):
        logid, sublogid = expected_ids
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() <= deadline:
            response = self.api_client.request("GET", f"/historyalarm/{logid}/{sublogid}", session=session_id)
            last = response
            if response.retstatus == "Success":
                assert_matching_alarm_info(response.json["retval"]["alarminfo"], self.env_config)
                return response
            if response.retstatus == "Fail" and "No data found" in response.retresult:
                time.sleep(interval)
                continue
            assert_api_success(response)
        raise AssertionError(
            f"Cleared active alarm {expected_ids!r} did not appear in history. "
            f"Last response: {last.retresult if last else 'None'}"
        )

    def verify_alarm_lifecycle_remote_console_to_history_delete(self, session_id: str) -> None:
        if self.env_config.dut.chassis not in OLT140X_CHASSIS:
            attach_case_id("EMS1-6652", "test_post_remote_console")
        attach_case_id("EMS1-6641", "test_get_active_alarm")
        attach_case_id("EMS1-6654", "test_get_active_alarm_by_id")
        attach_case_id("EMS1-6658", "test_patch_active_alarm_by_id")
        attach_case_id("EMS1-6659", "test_delete_active_alarm_by_id")
        attach_case_id("EMS1-6642", "test_get_history_alarm")
        attach_case_id("EMS1-6670", "test_get_history_alarm_by_id")
        attach_case_id("EMS1-6674", "test_delete_history_alarm_by_id")

        logid, sublogid = self.create_history_alarm_from_remote_console(session_id)

        history_by_id = self.api_client.request("GET", f"/historyalarm/{logid}/{sublogid}", session=session_id)
        assert_api_success(history_by_id)
        alarm_info = history_by_id.json["retval"]["alarminfo"]
        assert alarm_info["LogID"] == logid
        assert alarm_info["LogSubID"] == sublogid
        assert_matching_alarm_info(alarm_info, self.env_config)

        delete_history = self.api_client.request("DELETE", f"/historyalarm/{logid}/{sublogid}", session=session_id)
        assert_api_success(delete_history)

        after_delete = self.api_client.request("GET", f"/historyalarm/{logid}/{sublogid}", session=session_id)
        assert_api_failure(after_delete, accepted_messages=("No data found", "does not exist"))

    def verify_noaccess_rejected(self, session_id: str) -> None:
        attach_case_id("EMS1-7029", "test_active_alarm_various_invalid_parameters_should_return_error")
        response = self.api_client.request("GET", "/activealarm", session=session_id, params={"alarmfilter": "{}"})
        assert_api_failure(response, accepted_messages=("not authorized", "no access", "permission", "privilege"))

    def create_history_alarm_from_remote_console(self, session_id: str) -> tuple[str, str]:
        if self.env_config.dut.chassis not in OLT140X_CHASSIS:
            self.post_remote_console_like_legacy(session_id)
        active = self.wait_for_matching_active_alarm(session_id)
        alarm = first_alarm(active.json)
        if alarm is None:
            pytest.skip("No matching active alarm is available for lifecycle verification.")
        ids = alarm_ids(alarm)
        if ids is None:
            pytest.skip(f"Active alarm does not expose log/sublog ids: {alarm!r}")
        logid, sublogid = ids

        active_by_id = self.api_client.request("GET", f"/activealarm/{logid}/{sublogid}", session=session_id)
        assert_api_success(active_by_id)
        active_info = active_by_id.json["retval"]["alarminfo"]
        assert_matching_alarm_info(active_info, self.env_config)

        ack = self.api_client.request("PATCH", f"/activealarm/{logid}/{sublogid}", session=session_id)
        assert_api_success(ack)
        acked = self.api_client.request("GET", f"/activealarm/{logid}/{sublogid}", session=session_id)
        assert_api_success(acked)
        assert acked.json["retval"]["alarminfo"]["Ack"] == "1"

        clear = self.api_client.request("DELETE", f"/activealarm/{logid}/{sublogid}", session=session_id)
        assert_api_success(clear)

        cleared = self.api_client.request("GET", f"/activealarm/{logid}/{sublogid}", session=session_id)
        assert_api_failure(cleared, accepted_messages=("No data found", "does not exist"))

        history = self.api_client.request("GET", "/historyalarm", session=session_id, params=self.alarm_filter())
        assert_api_success(history)
        return logid, sublogid

    def wait_for_matching_active_alarm(self, session_id: str, timeout: int = 60, interval: int = 5):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() <= deadline:
            response = self.api_client.request("GET", "/activealarm", session=session_id, params=self.alarm_filter())
            last = response
            if response.retstatus == "Success" and first_alarm(response.json) is not None:
                return response
            if response.retstatus == "Fail" and "No data found" in response.retresult:
                time.sleep(interval)
                continue
            assert_api_success(response)
        pytest.skip(
            "No matching active alarm became available for lifecycle verification. "
            f"Last response: {last.retresult if last else 'None'}"
        )

    def post_remote_console_like_legacy(self, session_id: str) -> None:
        commands_1, commands_2 = remote_alarm_seed_commands(self.env_config)
        response = self.api_client.request(
            "POST",
            f"/remote/{self.env_config.dut.device_name}",
            session=session_id,
            json={"command": commands_1},
        )
        assert_api_success(response)
        returns = response.json["retval"]["return"]
        assert isinstance(returns, list)
        retval_str = "\n".join(returns)
        for command in commands_1:
            assert command in retval_str
        if self.env_config.dut.chassis not in OLT140X_CHASSIS:
            assert f"inband    {self.env_config.dut.device_ip}" in retval_str
        response = self.api_client.request(
            "POST",
            f"/remote/{self.env_config.dut.device_name}",
            session=session_id,
            json={"command": commands_2},
        )
        assert_api_success(response)

    def alarm_filter(self) -> dict[str, str]:
        return {"alarmfilter": json.dumps({"KeyWord": alarm_keywords(self.env_config)})}


def first_alarm(payload):
    if not isinstance(payload, dict):
        return None
    retval = payload.get("retval", {})
    if isinstance(retval, dict):
        for key in ("alarminfolist", "alarmloglist", "activealarmlist", "historyalarmlist", "alarmlist", "Content"):
            value = retval.get(key)
            if isinstance(value, list) and value:
                return value[0]
    return None


def find_alarm_by_ids(payload, expected_ids: tuple[str, str] | None):
    if expected_ids is None or not isinstance(payload, dict):
        return None
    retval = payload.get("retval", {})
    if not isinstance(retval, dict):
        return None
    for key in ("alarminfolist", "alarmloglist", "activealarmlist", "historyalarmlist", "alarmlist", "Content"):
        value = retval.get(key)
        if not isinstance(value, list):
            continue
        for alarm in value:
            if isinstance(alarm, dict) and alarm_ids(alarm) == expected_ids:
                return alarm
    return None


def alarm_ids(alarm):
    logid = alarm.get("logid") or alarm.get("LogID") or alarm.get("LogId")
    sublogid = (
        alarm.get("logsubid")
        or alarm.get("sublogid")
        or alarm.get("SubLogID")
        or alarm.get("LogSubID")
        or alarm.get("SubLogId")
    )
    if logid is None or sublogid is None:
        return None
    return str(logid), str(sublogid)
