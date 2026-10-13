from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
import requests

import clients.ems_api_client as client_module
from clients.ems_api_client import EmsApiClient
from utils import reporting


class FakeRaw:
    status_code = 200
    text = '{"retstatus": "Success", "retresult": ""}'
    url = "https://ems/netatlasemsapi/ontservice/SN1"

    def json(self):
        return {"retstatus": "Success", "retresult": ""}


@pytest.fixture
def fresh_report_state(monkeypatch):
    state = reporting.ReportState()
    monkeypatch.setattr(reporting, "REPORT_STATE", state)
    return state


def current_nodeid() -> str:
    return os.environ["PYTEST_CURRENT_TEST"].split(" ", 1)[0]


def transport_client(monkeypatch, outcomes: list):
    sleeps: list[float] = []
    calls: list[str] = []

    def fake_request(method, url, **kwargs):
        calls.append(method)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(client_module.requests, "request", fake_request)
    monkeypatch.setattr(client_module.time, "sleep", sleeps.append)
    env = SimpleNamespace(base_url="https://ems/netatlasemsapi", timeout=1, verify_tls=True)
    return EmsApiClient(env), calls, sleeps


def test_get_is_resent_after_dropped_connection_and_recorded_as_recovered(monkeypatch, fresh_report_state):
    dropped = requests.ConnectionError("Remote end closed connection without response")
    client, calls, sleeps = transport_client(monkeypatch, [dropped, FakeRaw()])

    result = client.request("GET", "/ontservice/SN1")

    assert result.retstatus == "Success"
    assert calls == ["GET", "GET"]
    assert sleeps == [client_module.TRANSPORT_RETRY_DELAYS[0]]
    [event] = fresh_report_state.connection_events
    assert event.nodeid == current_nodeid()
    assert (event.method, event.path, event.attempt, event.action, event.recovered) == (
        "GET",
        "/ontservice/SN1",
        1,
        "retried",
        True,
    )


def test_get_raises_after_all_attempts_fail_and_every_attempt_is_recorded(monkeypatch, fresh_report_state):
    attempts = len(client_module.TRANSPORT_RETRY_DELAYS) + 1
    client, calls, _ = transport_client(
        monkeypatch, [requests.ConnectTimeout("Connection timed out") for _ in range(attempts)]
    )

    with pytest.raises(requests.ConnectTimeout):
        client.request("GET", "/ontservice/SN1")

    assert len(calls) == attempts
    events = fresh_report_state.connection_events
    assert [event.action for event in events] == ["retried"] * (attempts - 1) + ["raised"]
    assert not any(event.recovered for event in events)


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_mutating_request_is_not_resent_after_transport_error(monkeypatch, fresh_report_state, method):
    client, calls, sleeps = transport_client(monkeypatch, [requests.ConnectionError("reset")])

    with pytest.raises(requests.ConnectionError):
        client.request(method, "/ontservice/SN1", json={"a": 1})

    assert calls == [method]
    assert sleeps == []
    [event] = fresh_report_state.connection_events
    assert (event.attempt, event.max_attempts, event.action) == (1, 1, "raised")


def test_report_header_lists_connection_errors_with_case_id(monkeypatch, fresh_report_state):
    nodeid = current_nodeid()
    reporting.register_node_case(nodeid, "EMS1-6666", "test_post_ont_service_by_sn")
    event = reporting.record_connection_event(
        "GET", "/ontservice/SN1", "ConnectionError: reset", attempt=1, max_attempts=3, action="retried"
    )
    event.recovered = True
    reporting.record_connection_event(
        "POST", "/usersession", "ConnectTimeout: timed out", attempt=1, max_attempts=1, action="raised"
    )

    lines = reporting._report_note_lines()

    assert lines[0] == "EMS Connection Errors: 2 (recovered by retry 1, not recovered 1)"
    assert lines[1] == (
        f"EMS Connection Error #1: EMS1-6666 {nodeid} | GET /ontservice/SN1 | attempt 1/3 | "
        "ConnectionError: reset | recovered by retry"
    )
    assert lines[2].endswith("POST /usersession | attempt 1/1 | ConnectTimeout: timed out | raised")
    assert all(not line.startswith("[") for line in lines)


def test_report_header_has_no_connection_lines_without_errors(fresh_report_state):
    assert reporting._report_note_lines() == []
