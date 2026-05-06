from __future__ import annotations

import pytest


@pytest.mark.alarm
@pytest.mark.readwrite
def test_active_alarm_list(alarm_service, readwrite_session):
    alarm_service.verify_active_alarm_list(readwrite_session)


@pytest.mark.alarm
@pytest.mark.readwrite
def test_history_alarm_list(alarm_service, readwrite_session):
    alarm_service.verify_history_alarm_list(readwrite_session)


@pytest.mark.alarm
@pytest.mark.mutating
def test_active_alarm_ack_and_clear_if_alarm_exists(alarm_service, readwrite_session):
    alarm_service.verify_active_alarm_ack_and_clear_if_exists(readwrite_session)


@pytest.mark.alarm
@pytest.mark.readwrite
def test_history_alarm_get_by_id_if_alarm_exists(alarm_service, readwrite_session):
    alarm_service.verify_history_alarm_get_by_id_if_exists(readwrite_session)


@pytest.mark.alarm
@pytest.mark.alarm_delete
@pytest.mark.destructive
@pytest.mark.mutating
def test_history_alarm_delete_if_alarm_exists(alarm_service, readwrite_session):
    alarm_service.verify_history_alarm_delete_if_exists(readwrite_session)


@pytest.mark.alarm
@pytest.mark.alarm_delete
@pytest.mark.destructive
@pytest.mark.mutating
def test_alarm_lifecycle_remote_console_to_history_delete(alarm_service, readwrite_session):
    alarm_service.verify_alarm_lifecycle_remote_console_to_history_delete(readwrite_session)


@pytest.mark.alarm
@pytest.mark.noaccess
def test_alarm_noaccess_is_rejected(alarm_service, noaccess_session):
    alarm_service.verify_noaccess_rejected(noaccess_session)
