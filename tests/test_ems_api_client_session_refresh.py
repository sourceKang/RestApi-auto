from __future__ import annotations

from types import SimpleNamespace

from clients.ems_api_client import EmsApiClient
from models.api import ApiResponse


def response(retstatus: str, retresult: str = "") -> ApiResponse:
    return ApiResponse(200, {"retstatus": retstatus, "retresult": retresult}, "", 0, "id", "GET", "url")


class FakeRefreshableSession:
    def __init__(self, *, should_refresh: bool = True) -> None:
        self.session_id = "session-1"
        self.should_refresh = should_refresh
        self.refresh_calls: list[str] = []
        self.recovery_records: list[bool] = []

    def current_session_id(self) -> str:
        return self.session_id

    def should_refresh_on_not_authorized(self, method: str) -> bool:
        return self.should_refresh

    def refresh_after_not_authorized(self, observed_session_id: str) -> str:
        self.refresh_calls.append(observed_session_id)
        self.session_id = "session-2"
        return self.session_id

    def record_authorization_recovery(self, *, request_retried: bool) -> None:
        self.recovery_records.append(request_retried)


def api_client(monkeypatch, responses: list[ApiResponse]):
    env = SimpleNamespace(base_url="https://ems", timeout=1, verify_tls=True)
    client = EmsApiClient(env)
    calls = []

    def send(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return responses.pop(0)

    monkeypatch.setattr(client, "_send_request", send)
    return client, calls


def test_get_retries_once_with_refreshed_session_after_not_authorized(monkeypatch):
    client, calls = api_client(monkeypatch, [response("Fail", "Not authorized."), response("Success")])
    session = FakeRefreshableSession()

    result = client.request("GET", "/device", session=session, expected="device")

    assert result.retstatus == "Success"
    assert session.refresh_calls == ["session-1"]
    assert session.recovery_records == [True]
    assert [call[2]["session"] for call in calls] == ["session-1", "session-2"]
    assert calls[1][2]["expected"] == "device after session refresh"


def test_mutation_refreshes_cache_but_does_not_replay_request(monkeypatch):
    original = response("Fail", "Not authorized.")
    client, calls = api_client(monkeypatch, [original])
    session = FakeRefreshableSession()

    result = client.request("PATCH", "/activealarm/1/1", session=session)

    assert result is original
    assert session.refresh_calls == ["session-1"]
    assert session.recovery_records == [False]
    assert len(calls) == 1


def test_expected_permission_denial_does_not_refresh_or_retry(monkeypatch):
    denied = response("Fail", "Not authorized.")
    client, calls = api_client(monkeypatch, [denied])
    session = FakeRefreshableSession(should_refresh=False)

    result = client.request("GET", "/device", session=session)

    assert result is denied
    assert session.refresh_calls == []
    assert session.recovery_records == []
    assert len(calls) == 1


def test_non_exact_authorization_message_does_not_trigger_refresh(monkeypatch):
    denied = response("Fail", "User is not authorized for this operation.")
    client, calls = api_client(monkeypatch, [denied])
    session = FakeRefreshableSession()

    result = client.request("GET", "/device", session=session)

    assert result is denied
    assert session.refresh_calls == []
    assert session.recovery_records == []
    assert len(calls) == 1
