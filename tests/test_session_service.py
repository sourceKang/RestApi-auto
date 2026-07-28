from __future__ import annotations

from types import SimpleNamespace

import pytest

from config_loader.settings import Credentials
from models.api import ApiResponse, SessionRole
from services.session.service import UserSessionService


def api_response(retstatus: str, retresult: str = "", *, session_id: str | None = None) -> ApiResponse:
    body = {"retstatus": retstatus, "retresult": retresult}
    if session_id is not None:
        body["retval"] = {"sessionid": session_id}
    return ApiResponse(200, body, "", 0, "id", "GET", "https://ems/device")


class FakeApiClient:
    def __init__(self, device_responses: list[ApiResponse]) -> None:
        self.device_responses = list(device_responses)
        self.login_roles: list[SessionRole] = []
        self.device_sessions: list[str] = []
        self.logout_sessions: list[str] = []

    def login(self, credentials: Credentials) -> ApiResponse:
        role = SessionRole(credentials.username)
        self.login_roles.append(role)
        return api_response("Success", session_id=f"session-{len(self.login_roles)}")

    def request(self, method: str, path: str, **kwargs) -> ApiResponse:
        assert (method, path) == ("GET", "/device")
        self.device_sessions.append(kwargs["session"])
        assert self.device_responses, "No fake /device response left"
        return self.device_responses.pop(0)

    def logout(self, session_id: str) -> ApiResponse:
        self.logout_sessions.append(session_id)
        return api_response("Success")

    @staticmethod
    def session_id_from(response: ApiResponse) -> str | None:
        return response.json.get("retval", {}).get("sessionid")


def env_config():
    return SimpleNamespace(credentials_for=lambda role: Credentials(role.value, "password"))


def test_readwrite_role_checks_absolute_lifetime_and_recovers_after_relogin(monkeypatch: pytest.MonkeyPatch):
    responses = [api_response("Success") for _ in range(9)]
    responses.extend([api_response("Fail", "Not authorized."), api_response("Success")])
    client = FakeApiClient(responses)
    service = UserSessionService(client, env_config())
    clock = {"now": 0.0}
    sleeps: list[float] = []

    monkeypatch.setattr("services.session.service.time.monotonic", lambda: clock["now"])

    def advance(seconds: float) -> None:
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr("services.session.service.time.sleep", advance)

    service.verify_login_and_logout_by_role(SessionRole.READWRITE)

    assert sleeps == [60] * 10
    assert client.login_roles == [SessionRole.READWRITE, SessionRole.READWRITE]
    assert client.device_sessions == ["session-1"] * 10 + ["session-2"]
    assert client.logout_sessions == ["session-2"]


def test_non_readwrite_roles_keep_login_logout_flow_without_lifetime_checks():
    for role in (SessionRole.READONLY, SessionRole.NOACCESS):
        client = FakeApiClient([])
        service = UserSessionService(client, env_config())

        service.verify_login_and_logout_by_role(role)

        assert client.login_roles == [role]
        assert client.device_sessions == []
        assert client.logout_sessions == ["session-1"]
