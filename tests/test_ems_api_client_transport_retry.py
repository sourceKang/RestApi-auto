from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
import requests

import clients.ems_api_client as client_module
from clients.ems_api_client import EmsApiClient
from utils import reporting


pytestmark = pytest.mark.offline


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


HOST = "ems:9116"


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (
            requests.ConnectTimeout("HTTPSConnectionPool(...): Max retries exceeded ... timed out"),
            "ConnectTimeout: could not connect to ems:9116; connect timed out after 21.0 s "
            "(client limit 60 s); connection not established, request not sent",
        ),
        (
            requests.ReadTimeout("Read timed out. (read timeout=60)"),
            "ReadTimeout: ems:9116 accepted the request but sent no response; read timed out after 21.0 s "
            "(client limit 60 s); EMS may have processed the request",
        ),
        (
            requests.ConnectionError(
                "('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))"
            ),
            "Connection dropped: ems:9116 closed the connection without sending a response (after 21.0 s); "
            "EMS may have processed the request",
        ),
        (
            requests.ConnectionError("('Connection aborted.', ConnectionResetError(10054, 'reset'))"),
            "Connection reset: ems:9116 forcibly closed the connection (after 21.0 s); "
            "EMS may have processed the request",
        ),
        (
            requests.ConnectionError("NewConnectionError: Failed to establish a new connection: refused"),
            "Connection refused: ems:9116 rejected the connection (after 21.0 s); request not sent",
        ),
    ],
)
def test_transport_error_summary_describes_error_without_urllib3_retry_wording(exc, expected):
    summary = client_module._transport_error_summary(exc, HOST, 60, 21.0)

    assert summary == expected
    assert "Max retries exceeded" not in summary


def test_recorded_event_uses_host_and_plain_summary(monkeypatch, fresh_report_state):
    client, _, _ = transport_client(monkeypatch, [requests.ConnectTimeout("Max retries exceeded"), FakeRaw()])

    client.request("GET", "/ontservice/SN1")

    [event] = fresh_report_state.connection_events
    assert event.error.startswith("ConnectTimeout: could not connect to ems; connect timed out after ")
    assert "(client limit 1 s)" in event.error


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_mutating_request_is_resent_after_connect_timeout_and_first_attempt_is_marked(
    monkeypatch, fresh_report_state, method
):
    client, calls, sleeps = transport_client(monkeypatch, [requests.ConnectTimeout("timed out"), FakeRaw()])

    result = client.request(method, "/profile/ONTBandwidthProfile/p1", json={"a": 1})

    assert result.retstatus == "Success"
    assert calls == [method, method]
    assert sleeps == [client_module.TRANSPORT_RETRY_DELAYS[0]]
    [event] = fresh_report_state.connection_events
    assert (event.attempt, event.max_attempts, event.action, event.recovered) == (1, 3, "retried", True)
    assert "connection not established, request not sent" in event.error


@pytest.mark.parametrize(
    "exc",
    [
        requests.ReadTimeout("Read timed out"),
        requests.ConnectionError("RemoteDisconnected('Remote end closed connection without response')"),
    ],
)
def test_mutating_request_is_not_resent_when_ems_may_have_received_it(monkeypatch, fresh_report_state, exc):
    client, calls, sleeps = transport_client(monkeypatch, [exc])

    with pytest.raises(type(exc)):
        client.request("PATCH", "/profile/ONTBandwidthProfile/p1", json={"a": 1})

    assert calls == ["PATCH"]
    assert sleeps == []
    [event] = fresh_report_state.connection_events
    assert (event.attempt, event.max_attempts, event.action) == (1, 1, "raised")
    assert "EMS may have processed the request" in event.error


def test_request_over_slow_threshold_is_marked_in_report(monkeypatch, fresh_report_state):
    monkeypatch.setattr(client_module, "SLOW_REQUEST_SECONDS", -1.0)
    client, _, _ = transport_client(monkeypatch, [requests.ConnectTimeout("timed out"), FakeRaw()])
    reporting.register_node_case(current_nodeid(), "EMS1-6834", "test_patch_profile_by_ontbandwidthprofile")

    client.request("PATCH", "/profile/ONTBandwidthProfile/p1", json={"a": 1})

    [slow] = fresh_report_state.slow_requests
    assert (slow.method, slow.path, slow.attempts, slow.status_code) == (
        "PATCH",
        "/profile/ONTBandwidthProfile/p1",
        2,
        200,
    )
    lines = reporting._report_note_lines()
    assert "EMS Slow Requests: 1 (total time over -1 s)" in lines
    [detail] = [line for line in lines if line.startswith("EMS Slow Request #1:")]
    assert detail.startswith(f"EMS Slow Request #1: EMS1-6834 {current_nodeid()} | PATCH /profile/ONTBandwidthProfile/p1 | SLOW ")
    assert detail.endswith("s, 2 attempts | HTTP 200")


def test_fast_request_is_not_marked_slow(monkeypatch, fresh_report_state):
    client, _, _ = transport_client(monkeypatch, [FakeRaw()])

    client.request("GET", "/device")

    assert fresh_report_state.slow_requests == []


def test_retry_waits_come_from_ems_target_profile(monkeypatch, fresh_report_state):
    client, calls, sleeps = transport_client(
        monkeypatch, [requests.ConnectTimeout("t1"), requests.ConnectTimeout("t2"), requests.ConnectTimeout("t3"), FakeRaw()]
    )
    client.retry_delays = (10, 30, 60)

    client.request("GET", "/device")

    assert calls == ["GET"] * 4
    assert sleeps == [10, 30, 60]
    assert [event.max_attempts for event in fresh_report_state.connection_events] == [4, 4, 4]


def test_min_request_interval_spaces_request_starts(monkeypatch, fresh_report_state):
    client, calls, sleeps = transport_client(monkeypatch, [FakeRaw(), FakeRaw()])
    client.min_request_interval = 0.3
    now = iter([100.0, 100.0, 100.1, 100.3])
    monkeypatch.setattr(client_module.time, "monotonic", lambda: next(now))
    monkeypatch.setattr(client_module, "_last_request_started", 0.0)

    client.request("GET", "/device")
    client.request("GET", "/device")

    assert calls == ["GET", "GET"]
    assert sleeps == [pytest.approx(0.2)]


def test_no_pacing_without_min_request_interval(monkeypatch, fresh_report_state):
    client, _, sleeps = transport_client(monkeypatch, [FakeRaw(), FakeRaw()])

    client.request("GET", "/device")
    client.request("GET", "/device")

    assert sleeps == []


def test_report_header_shows_non_default_timing_profile():
    env = SimpleNamespace(
        ems_target="redhat",
        ems_platform="RedHat 9 (HA)",
        wait_scale=1.5,
        transport_retry_delays=(10.0, 30.0, 60.0),
        min_request_interval=0.3,
    )

    assert ("EMS Timing", "wait_scale 1.5, transport retry delays 10/30/60 s, min request interval 0.3 s") in (
        reporting._ems_server_metadata(env)
    )


def test_report_header_omits_default_timing_profile():
    env = SimpleNamespace(ems_target="ubuntu", ems_platform="Ubuntu", wait_scale=1.0,
                          transport_retry_delays=(5.0, 15.0), min_request_interval=0.0)

    assert [label for label, _ in reporting._ems_server_metadata(env)] == ["EMS Target", "EMS Platform"]
