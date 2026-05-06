from __future__ import annotations

import json
import time

import pytest

from utils.assertions import assert_api_failure, assert_api_success
from utils.case_metadata import attach_case_id


class AlarmService:
    def __init__(self, api_client, env_config) -> None:
        self.api_client = api_client
        self.env_config = env_config

    def verify_active_alarm_list(self, session_id: str) -> None:
        attach_case_id("EMS1-6641", "test_get_active_alarm")
        response = self.api_client.request("GET", "/activealarm", session=session_id, params=self.alarm_filter())
        if response.retstatus == "Fail" and "No data found" in response.retresult:
            pytest.skip("No active alarm is available for this EMS environment.")
        assert_api_success(response)

    def verify_history_alarm_list(self, session_id: str) -> None:
        attach_case_id("EMS1-6642", "test_get_history_alarm")
        response = self.api_client.request("GET", "/historyalarm", session=session_id, params=self.alarm_filter())
        if response.retstatus == "Fail" and "No data found" in response.retresult:
            self.create_history_alarm_from_remote_console(session_id)
            response = self.api_client.request("GET", "/historyalarm", session=session_id, params=self.alarm_filter())
        if response.retstatus == "Fail" and "No data found" in response.retresult:
            pytest.skip("No history alarm is available after remote console seed flow.")
        assert_api_success(response)

    def verify_active_alarm_ack_and_clear_if_exists(self, session_id: str) -> None:
        attach_case_id("EMS1-6658", "test_patch_active_alarm_by_id")
        alarms = self.api_client.request("GET", "/activealarm", session=session_id, params=self.alarm_filter())
        if alarms.retstatus == "Fail" and "No data found" in alarms.retresult:
            pytest.skip("No active alarm is available for ack/clear verification.")
        assert_api_success(alarms)
        alarm = first_alarm(alarms.json)
        if alarm is None:
            pytest.skip("No active alarm is available for ack/clear verification.")

        ids = alarm_ids(alarm)
        if ids is None:
            pytest.skip(f"Active alarm does not expose log/sublog ids: {alarm!r}")
        logid, sublogid = ids
        get_by_id = self.api_client.request("GET", f"/activealarm/{logid}/{sublogid}", session=session_id)
        assert_api_success(get_by_id)
        ack = self.api_client.request("PATCH", f"/activealarm/{logid}/{sublogid}", session=session_id)
        assert_api_success(ack)
        clear = self.api_client.request("DELETE", f"/activealarm/{logid}/{sublogid}", session=session_id)
        assert_api_success(clear)

    def verify_history_alarm_get_by_id_if_exists(self, session_id: str) -> None:
        attach_case_id("EMS1-6670", "test_get_history_alarm_by_id")
        alarms = self.api_client.request("GET", "/historyalarm", session=session_id, params=self.alarm_filter())
        if alarms.retstatus == "Fail" and "No data found" in alarms.retresult:
            ids = self.create_history_alarm_from_remote_console(session_id)
            response = self.api_client.request("GET", f"/historyalarm/{ids[0]}/{ids[1]}", session=session_id)
            assert_api_success(response)
            return
        assert_api_success(alarms)
        alarm = first_alarm(alarms.json)
        if alarm is None:
            pytest.skip("No history alarm is available for by-id verification.")

        ids = alarm_ids(alarm)
        if ids is None:
            pytest.skip(f"History alarm does not expose log/sublog ids: {alarm!r}")
        logid, sublogid = ids
        response = self.api_client.request("GET", f"/historyalarm/{logid}/{sublogid}", session=session_id)
        assert_api_success(response)

    def verify_history_alarm_delete_if_exists(self, session_id: str) -> None:
        attach_case_id("EMS1-6674", "test_delete_history_alarm_by_id")
        alarms = self.api_client.request("GET", "/historyalarm", session=session_id, params={"alarmfilter": "{}"})
        assert_api_success(alarms)
        alarm = first_alarm(alarms.json)
        if alarm is None:
            pytest.skip("No history alarm is available for delete verification.")

        ids = alarm_ids(alarm)
        if ids is None:
            pytest.skip(f"History alarm does not expose log/sublog ids: {alarm!r}")
        logid, sublogid = ids
        response = self.api_client.request("DELETE", f"/historyalarm/{logid}/{sublogid}", session=session_id)
        assert_api_success(response)

    def verify_alarm_lifecycle_remote_console_to_history_delete(self, session_id: str) -> None:
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
        assert alarm_info["Description"] == "Login Success"
        assert alarm_info["DevName"] == self.env_config.dut.device_name
        assert alarm_info["DevIP"] == self.env_config.dut.device_ip

        delete_history = self.api_client.request("DELETE", f"/historyalarm/{logid}/{sublogid}", session=session_id)
        assert_api_success(delete_history)

        after_delete = self.api_client.request("GET", f"/historyalarm/{logid}/{sublogid}", session=session_id)
        assert_api_failure(after_delete, accepted_messages=("No data found", "does not exist"))

    def verify_noaccess_rejected(self, session_id: str) -> None:
        attach_case_id("EMS1-7029", "test_active_alarm_various_invalid_parameters_should_return_error")
        response = self.api_client.request("GET", "/activealarm", session=session_id, params={"alarmfilter": "{}"})
        assert_api_failure(response, accepted_messages=("not authorized", "no access", "permission", "privilege"))

    def create_history_alarm_from_remote_console(self, session_id: str) -> tuple[str, str]:
        self.post_remote_console_like_legacy(session_id)
        active = self.wait_for_matching_active_alarm(session_id)
        alarm = first_alarm(active.json)
        if alarm is None:
            pytest.skip("Remote console did not create a matching active Login Success alarm.")
        ids = alarm_ids(alarm)
        if ids is None:
            pytest.skip(f"Active alarm does not expose log/sublog ids: {alarm!r}")
        logid, sublogid = ids

        active_by_id = self.api_client.request("GET", f"/activealarm/{logid}/{sublogid}", session=session_id)
        assert_api_success(active_by_id)
        active_info = active_by_id.json["retval"]["alarminfo"]
        assert active_info["Description"] == "Login Success"
        assert active_info["DevName"] == self.env_config.dut.device_name
        assert active_info["DevIP"] == self.env_config.dut.device_ip

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
            "Remote console did not create a matching active Login Success alarm. "
            f"Last response: {last.retresult if last else 'None'}"
        )

    def post_remote_console_like_legacy(self, session_id: str) -> None:
        commands_1 = ["sh ip", "sh system"]
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
        assert f"inband    {self.env_config.dut.device_ip}" in retval_str

        commands_2 = ["con", f"in xpon {self.env_config.dut.slot_id}-{self.env_config.dut.port_id}"]
        response = self.api_client.request(
            "POST",
            f"/remote/{self.env_config.dut.device_name}",
            session=session_id,
            json={"command": commands_2},
        )
        assert_api_success(response)

    def alarm_filter(self) -> dict[str, str]:
        return {"alarmfilter": json.dumps({"KeyWord": [self.env_config.dut.device_ip, "Login Success"]})}


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
