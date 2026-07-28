from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest


from services.alarm.service import (
    AlarmService,
    alarm_keywords,
    expected_alarm_description,
    find_alarm_by_ids,
    remote_alarm_seed_commands,
)


def test_remote_alarm_seed_commands_use_olt_ug_read_only_commands():
    olt_env = SimpleNamespace(
        dut=SimpleNamespace(chassis="OLT1408A-C", slot_id="0", port_id="8")
    )
    neox_env = SimpleNamespace(
        dut=SimpleNamespace(chassis="NeoX-03", slot_id="3", port_id="16")
    )

    assert remote_alarm_seed_commands(olt_env) == (
        ["show version", "show system-information"],
        ["show interface pon-8"],
    )
    assert remote_alarm_seed_commands(neox_env) == (
        ["sh ip", "sh system"],
        ["con", "in xpon 3-16"],
    )


def test_alarm_ground_truth_uses_unregister_ont_for_olt140x_and_login_for_neox():
    olt_env = SimpleNamespace(
        dut=SimpleNamespace(
            chassis="OLT1408A-C",
            device_ip="192.168.168.84",
            port_id="8",
            ont_sn="5A594F4F805F5C81",
        )
    )
    neox_env = SimpleNamespace(
        dut=SimpleNamespace(
            chassis="NeoX-03",
            device_ip="192.168.169.58",
            port_id="16",
            ont_sn="NEOX_SN",
        )
    )

    assert alarm_keywords(olt_env) == [
        "192.168.168.84",
        "5A594F4F805F5C81",
        "Unregister ONT",
    ]
    assert expected_alarm_description(olt_env) == (
        "Discover Unregister ONT - [pon-8] Unregister ONT, SN: 5A594F4F805F5C81"
    )
    assert alarm_keywords(neox_env) == ["192.168.169.58", "Login Success"]
    assert expected_alarm_description(neox_env) == "Login Success"


@dataclass
class AlarmWorkflowState:
    active_ids: tuple[str, str] | None = None
    history_ids: tuple[str, str] | None = None
    history_list_verified: bool = False
    history_by_id_verified: bool = False
    history_deleted: bool = False


@pytest.fixture(scope="module")
def alarm_workflow_state():
    return AlarmWorkflowState()


def _require_alarm_ids(ids, phase):
    if ids is None:
        pytest.skip(f"Blocked because the shared alarm workflow has not completed phase: {phase}")
    return ids


def test_find_alarm_by_ids_selects_the_shared_workflow_alarm():
    expected = ("20", "2")
    payload = {
        "retval": {
            "alarminfolist": [
                {"LogID": "10", "LogSubID": "1"},
                {"LogID": "20", "LogSubID": "2"},
            ]
        }
    }

    assert find_alarm_by_ids(payload, expected) == {"LogID": "20", "LogSubID": "2"}


class _NoDataAlarmClient:
    def __init__(self):
        self.requests = []

    def request(self, method, path, **kwargs):
        self.requests.append((method, path))
        return SimpleNamespace(retstatus="Fail", retresult="No data found in the database", json={})


@pytest.mark.parametrize(
    ("method_name", "expected_path"),
    [
        ("verify_history_alarm_list", "/historyalarm"),
        ("verify_history_alarm_get_by_id_if_exists", "/historyalarm"),
        ("verify_history_alarm_delete_if_exists", "/historyalarm"),
    ],
)
def test_history_alarm_no_data_skips_without_remote_console(method_name, expected_path):
    client = _NoDataAlarmClient()
    env = SimpleNamespace(dut=SimpleNamespace(chassis="NeoX-03", device_ip="192.0.2.1"))
    service = AlarmService(client, env)

    with pytest.raises(pytest.skip.Exception):
        getattr(service, method_name)("session")

    assert client.requests == [("GET", expected_path)]


@pytest.mark.alarm
@pytest.mark.readwrite
def test_active_alarm_list(services, readwrite_session, alarm_workflow_state):
    alarm_workflow_state.active_ids = services.alarm.verify_active_alarm_list(readwrite_session)


@pytest.mark.alarm
@pytest.mark.mutating
@pytest.mark.destructive
@pytest.mark.ems_scoped
def test_active_alarm_ack_and_clear_if_alarm_exists(services, readwrite_session, alarm_workflow_state):
    active_ids = _require_alarm_ids(alarm_workflow_state.active_ids, "active alarm list")
    alarm_workflow_state.history_ids = services.alarm.verify_active_alarm_ack_and_clear_if_exists(
        readwrite_session,
        active_ids,
    )


@pytest.mark.alarm
@pytest.mark.readwrite
def test_history_alarm_list(services, readwrite_session, alarm_workflow_state):
    history_ids = _require_alarm_ids(alarm_workflow_state.history_ids, "active alarm ack/clear")
    services.alarm.verify_history_alarm_list(readwrite_session, history_ids)
    alarm_workflow_state.history_list_verified = True


@pytest.mark.alarm
@pytest.mark.readwrite
def test_history_alarm_get_by_id_if_alarm_exists(services, readwrite_session, alarm_workflow_state):
    history_ids = _require_alarm_ids(alarm_workflow_state.history_ids, "active alarm ack/clear")
    if not alarm_workflow_state.history_list_verified:
        pytest.skip("Blocked because the shared history alarm list phase has not passed.")
    services.alarm.verify_history_alarm_get_by_id_if_exists(readwrite_session, history_ids)
    alarm_workflow_state.history_by_id_verified = True


@pytest.mark.alarm
@pytest.mark.alarm_delete
@pytest.mark.destructive
@pytest.mark.mutating
def test_history_alarm_delete_if_alarm_exists(services, readwrite_session, alarm_workflow_state):
    history_ids = _require_alarm_ids(alarm_workflow_state.history_ids, "active alarm ack/clear")
    if not alarm_workflow_state.history_by_id_verified:
        pytest.skip("Blocked because the shared history alarm by-ID phase has not passed.")
    services.alarm.verify_history_alarm_delete_if_exists(readwrite_session, history_ids)
    alarm_workflow_state.history_deleted = True

@pytest.mark.alarm
@pytest.mark.alarm_delete
@pytest.mark.remoteconsole
@pytest.mark.destructive
@pytest.mark.mutating
def test_alarm_lifecycle_remote_console_to_history_delete(services, readwrite_session):
    services.alarm.verify_alarm_lifecycle_remote_console_to_history_delete(readwrite_session)


@pytest.mark.alarm
@pytest.mark.noaccess
def test_alarm_noaccess_is_rejected(services, noaccess_session):
    services.alarm.verify_noaccess_rejected(noaccess_session)
