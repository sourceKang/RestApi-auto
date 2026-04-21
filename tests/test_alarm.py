from __future__ import annotations

import json

import pytest

from utils.assertions import assert_api_failure, assert_api_success
from utils.case_metadata import attach_case_id


def _alarm_filter(env_config):
    return {"alarmfilter": json.dumps({"KeyWord": [env_config.dut.device_ip, "Login Success"]})}


@pytest.mark.alarm
@pytest.mark.readwrite
def test_active_alarm_list(api_client, env_config, readwrite_session):
    attach_case_id("EMS1-6641", "test_get_active_alarm")
    response = api_client.request("GET", "/activealarm", session=readwrite_session, params=_alarm_filter(env_config))
    if response.retstatus == "Fail" and "No data found" in response.retresult:
        pytest.skip("No active alarm is available for this EMS environment.")
    assert_api_success(response)


@pytest.mark.alarm
@pytest.mark.readwrite
def test_history_alarm_list(api_client, env_config, readwrite_session):
    attach_case_id("EMS1-6642", "test_get_history_alarm")
    response = api_client.request("GET", "/historyalarm", session=readwrite_session, params=_alarm_filter(env_config))
    if response.retstatus == "Fail" and "No data found" in response.retresult:
        _create_history_alarm_from_remote_console(api_client, env_config, readwrite_session)
        response = api_client.request("GET", "/historyalarm", session=readwrite_session, params=_alarm_filter(env_config))
    if response.retstatus == "Fail" and "No data found" in response.retresult:
        pytest.skip("No history alarm is available after remote console seed flow.")
    assert_api_success(response)


@pytest.mark.alarm
@pytest.mark.mutating
def test_active_alarm_ack_and_clear_if_alarm_exists(api_client, env_config, readwrite_session):
    attach_case_id("EMS1-6658", "test_patch_active_alarm_by_id")
    alarms = api_client.request("GET", "/activealarm", session=readwrite_session, params=_alarm_filter(env_config))
    if alarms.retstatus == "Fail" and "No data found" in alarms.retresult:
        pytest.skip("No active alarm is available for ack/clear verification.")
    assert_api_success(alarms)
    alarm = _first_alarm(alarms.json)
    if alarm is None:
        pytest.skip("No active alarm is available for ack/clear verification.")

    ids = _alarm_ids(alarm)
    if ids is None:
        pytest.skip(f"Active alarm does not expose log/sublog ids: {alarm!r}")
    logid, sublogid = ids
    get_by_id = api_client.request("GET", f"/activealarm/{logid}/{sublogid}", session=readwrite_session)
    assert_api_success(get_by_id)
    ack = api_client.request("PATCH", f"/activealarm/{logid}/{sublogid}", session=readwrite_session)
    assert_api_success(ack)
    clear = api_client.request("DELETE", f"/activealarm/{logid}/{sublogid}", session=readwrite_session)
    assert_api_success(clear)


@pytest.mark.alarm
@pytest.mark.readwrite
def test_history_alarm_get_by_id_if_alarm_exists(api_client, env_config, readwrite_session):
    attach_case_id("EMS1-6670", "test_get_history_alarm_by_id")
    alarms = api_client.request("GET", "/historyalarm", session=readwrite_session, params=_alarm_filter(env_config))
    if alarms.retstatus == "Fail" and "No data found" in alarms.retresult:
        ids = _create_history_alarm_from_remote_console(api_client, env_config, readwrite_session)
        response = api_client.request("GET", f"/historyalarm/{ids[0]}/{ids[1]}", session=readwrite_session)
        assert_api_success(response)
        return
    assert_api_success(alarms)
    alarm = _first_alarm(alarms.json)
    if alarm is None:
        pytest.skip("No history alarm is available for by-id verification.")

    ids = _alarm_ids(alarm)
    if ids is None:
        pytest.skip(f"History alarm does not expose log/sublog ids: {alarm!r}")
    logid, sublogid = ids
    response = api_client.request("GET", f"/historyalarm/{logid}/{sublogid}", session=readwrite_session)
    assert_api_success(response)


@pytest.mark.alarm
@pytest.mark.alarm_delete
@pytest.mark.destructive
@pytest.mark.mutating
def test_history_alarm_delete_if_alarm_exists(api_client, readwrite_session):
    attach_case_id("EMS1-6674", "test_delete_history_alarm_by_id")
    alarms = api_client.request("GET", "/historyalarm", session=readwrite_session, params={"alarmfilter": "{}"})
    assert_api_success(alarms)
    alarm = _first_alarm(alarms.json)
    if alarm is None:
        pytest.skip("No history alarm is available for delete verification.")

    ids = _alarm_ids(alarm)
    if ids is None:
        pytest.skip(f"History alarm does not expose log/sublog ids: {alarm!r}")
    logid, sublogid = ids
    response = api_client.request("DELETE", f"/historyalarm/{logid}/{sublogid}", session=readwrite_session)
    assert_api_success(response)


@pytest.mark.alarm
@pytest.mark.alarm_delete
@pytest.mark.destructive
@pytest.mark.mutating
def test_alarm_lifecycle_remote_console_to_history_delete(api_client, env_config, readwrite_session):
    attach_case_id("EMS1-6652", "test_post_remote_console")
    attach_case_id("EMS1-6641", "test_get_active_alarm")
    attach_case_id("EMS1-6654", "test_get_active_alarm_by_id")
    attach_case_id("EMS1-6658", "test_patch_active_alarm_by_id")
    attach_case_id("EMS1-6659", "test_delete_active_alarm_by_id")
    attach_case_id("EMS1-6642", "test_get_history_alarm")
    attach_case_id("EMS1-6670", "test_get_history_alarm_by_id")
    attach_case_id("EMS1-6674", "test_delete_history_alarm_by_id")

    logid, sublogid = _create_history_alarm_from_remote_console(api_client, env_config, readwrite_session)

    history_by_id = api_client.request("GET", f"/historyalarm/{logid}/{sublogid}", session=readwrite_session)
    assert_api_success(history_by_id)
    alarm_info = history_by_id.json["retval"]["alarminfo"]
    assert alarm_info["LogID"] == logid
    assert alarm_info["LogSubID"] == sublogid
    assert alarm_info["Description"] == "Login Success"
    assert alarm_info["DevName"] == env_config.dut.device_name
    assert alarm_info["DevIP"] == env_config.dut.device_ip

    delete_history = api_client.request("DELETE", f"/historyalarm/{logid}/{sublogid}", session=readwrite_session)
    assert_api_success(delete_history)

    after_delete = api_client.request("GET", f"/historyalarm/{logid}/{sublogid}", session=readwrite_session)
    assert_api_failure(after_delete, accepted_messages=("No data found", "does not exist"))


@pytest.mark.alarm
@pytest.mark.noaccess
def test_alarm_noaccess_is_rejected(api_client, noaccess_session):
    attach_case_id("EMS1-7029", "test_active_alarm_various_invalid_parameters_should_return_error")
    response = api_client.request("GET", "/activealarm", session=noaccess_session, params={"alarmfilter": "{}"})
    assert_api_failure(response, accepted_messages=("not authorized", "no access", "permission", "privilege"))


def _first_alarm(payload):
    if not isinstance(payload, dict):
        return None
    retval = payload.get("retval", {})
    if isinstance(retval, dict):
        for key in ("alarminfolist", "alarmloglist", "activealarmlist", "historyalarmlist", "alarmlist", "Content"):
            value = retval.get(key)
            if isinstance(value, list) and value:
                return value[0]
    return None


def _create_history_alarm_from_remote_console(api_client, env_config, session_id):
    _post_remote_console_like_legacy(api_client, env_config, session_id)
    active = api_client.request("GET", "/activealarm", session=session_id, params=_alarm_filter(env_config))
    assert_api_success(active)
    alarm = _first_alarm(active.json)
    if alarm is None:
        pytest.skip("Remote console did not create a matching active Login Success alarm.")
    ids = _alarm_ids(alarm)
    if ids is None:
        pytest.skip(f"Active alarm does not expose log/sublog ids: {alarm!r}")
    logid, sublogid = ids

    active_by_id = api_client.request("GET", f"/activealarm/{logid}/{sublogid}", session=session_id)
    assert_api_success(active_by_id)
    active_info = active_by_id.json["retval"]["alarminfo"]
    assert active_info["Description"] == "Login Success"
    assert active_info["DevName"] == env_config.dut.device_name
    assert active_info["DevIP"] == env_config.dut.device_ip

    ack = api_client.request("PATCH", f"/activealarm/{logid}/{sublogid}", session=session_id)
    assert_api_success(ack)
    acked = api_client.request("GET", f"/activealarm/{logid}/{sublogid}", session=session_id)
    assert_api_success(acked)
    assert acked.json["retval"]["alarminfo"]["Ack"] == "1"

    clear = api_client.request("DELETE", f"/activealarm/{logid}/{sublogid}", session=session_id)
    assert_api_success(clear)

    cleared = api_client.request("GET", f"/activealarm/{logid}/{sublogid}", session=session_id)
    assert_api_failure(cleared, accepted_messages=("No data found", "does not exist"))

    history = api_client.request("GET", "/historyalarm", session=session_id, params=_alarm_filter(env_config))
    assert_api_success(history)
    return logid, sublogid


def _post_remote_console_like_legacy(api_client, env_config, session_id):
    commands_1 = ["sh ip", "sh system"]
    response = api_client.request(
        "POST",
        f"/remote/{env_config.dut.device_name}",
        session=session_id,
        json={"command": commands_1},
    )
    assert_api_success(response)
    returns = response.json["retval"]["return"]
    assert isinstance(returns, list)
    retval_str = "\n".join(returns)
    for command in commands_1:
        assert command in retval_str
    assert f"inband    {env_config.dut.device_ip}" in retval_str

    commands_2 = ["con", f"in xpon {env_config.dut.slot_id}-{env_config.dut.port_id}"]
    response = api_client.request(
        "POST",
        f"/remote/{env_config.dut.device_name}",
        session=session_id,
        json={"command": commands_2},
    )
    assert_api_success(response)


def _alarm_ids(alarm):
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
