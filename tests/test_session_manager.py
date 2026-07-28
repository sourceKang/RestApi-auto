from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from config_loader.settings import Credentials
from models.api import ApiResponse, SessionRole
from clients.session import CachedSessionHandle, SessionManager


def response(retstatus: str, *, session_id: str | None = None) -> ApiResponse:
    body = {"retstatus": retstatus, "retresult": ""}
    if session_id is not None:
        body["retval"] = {"sessionid": session_id}
    return ApiResponse(200, body, "", 0, "id", "POST", "https://ems/usersession")


class FakeApiClient:
    def __init__(self, *, login_delay: float = 0.0, fail_logins: int = 0) -> None:
        self.login_roles: list[SessionRole] = []
        self.logout_sessions: list[str] = []
        self.login_delay = login_delay
        self.fail_logins = fail_logins

    def login(self, credentials: Credentials) -> ApiResponse:
        role = SessionRole(credentials.username)
        self.login_roles.append(role)
        if self.login_delay:
            time.sleep(self.login_delay)
        if self.fail_logins > 0:
            self.fail_logins -= 1
            return response("Fail")
        return response("Success", session_id=f"{role.value}-{len(self.login_roles)}")

    def logout(self, session_id: str) -> ApiResponse:
        self.logout_sessions.append(session_id)
        return response("Success")

    @staticmethod
    def session_id_from(login: ApiResponse) -> str | None:
        return login.json.get("retval", {}).get("sessionid")


def env_config():
    return SimpleNamespace(credentials_for=lambda role: Credentials(role.value, "password"))


def test_cached_role_session_reuses_then_refreshes_at_540_seconds():
    clock = {"now": 0.0}
    client = FakeApiClient()
    manager = SessionManager(client, env_config(), clock=lambda: clock["now"])

    with manager.cached_role_session(SessionRole.READWRITE) as first:
        assert isinstance(first, CachedSessionHandle)
        assert first.current_session_id() == "readwrite-1"

    clock["now"] = 539.9
    with manager.cached_role_session(SessionRole.READWRITE) as reused:
        assert reused.current_session_id() == "readwrite-1"

    clock["now"] = 540.0
    with manager.cached_role_session(SessionRole.READWRITE) as refreshed:
        assert refreshed.current_session_id() == "readwrite-2"

    manager.close()

    assert client.login_roles == [SessionRole.READWRITE, SessionRole.READWRITE]
    assert client.logout_sessions == ["readwrite-1", "readwrite-2"]


def test_not_authorized_refresh_reuses_newer_session_when_another_request_already_refreshed():
    client = FakeApiClient()
    manager = SessionManager(client, env_config())
    handle = CachedSessionHandle(manager, SessionRole.READWRITE)
    original = handle.current_session_id()

    renewed = handle.refresh_after_not_authorized(original)
    reused = handle.refresh_after_not_authorized(original)

    assert renewed == "readwrite-2"
    assert reused == "readwrite-2"
    assert client.login_roles == [SessionRole.READWRITE, SessionRole.READWRITE]


def test_fresh_role_session_discards_matching_cached_session_and_logs_out_fresh_session():
    client = FakeApiClient()
    manager = SessionManager(client, env_config())
    cached = CachedSessionHandle(manager, SessionRole.READONLY)
    assert cached.current_session_id() == "readonly-1"

    with manager.role_session(SessionRole.READONLY) as fresh:
        assert fresh == "readonly-2"

    assert client.logout_sessions == ["readonly-1", "readonly-2"]
    assert cached.current_session_id() == "readonly-3"


def test_role_policy_distinguishes_expiry_from_expected_permission_denials():
    manager = SessionManager(FakeApiClient(), env_config())

    assert CachedSessionHandle(manager, SessionRole.READWRITE).should_refresh_on_not_authorized("PATCH")
    assert CachedSessionHandle(manager, SessionRole.READONLY).should_refresh_on_not_authorized("GET")
    assert not CachedSessionHandle(manager, SessionRole.READONLY).should_refresh_on_not_authorized("PATCH")
    assert not CachedSessionHandle(manager, SessionRole.NOACCESS).should_refresh_on_not_authorized("GET")


def test_concurrent_cache_misses_create_only_one_session():
    client = FakeApiClient(login_delay=0.01)
    manager = SessionManager(client, env_config())

    with ThreadPoolExecutor(max_workers=8) as executor:
        session_ids = list(executor.map(lambda _index: manager.cached_session_id(SessionRole.READWRITE), range(8)))

    assert session_ids == ["readwrite-1"] * 8
    assert client.login_roles == [SessionRole.READWRITE]
    assert manager.metrics_snapshot()["cache_misses"] == 1
    assert manager.metrics_snapshot()["cache_hits"] == 7


def test_failed_login_does_not_leave_stale_cache_entry():
    client = FakeApiClient(fail_logins=1)
    manager = SessionManager(client, env_config())

    with pytest.raises(AssertionError):
        manager.cached_session_id(SessionRole.READWRITE)

    assert manager.cached_session_id(SessionRole.READWRITE) == "readwrite-2"
    assert manager.metrics_snapshot()["cached_logins"] == 2


def test_close_is_idempotent_and_metrics_do_not_expose_session_ids():
    client = FakeApiClient()
    manager = SessionManager(client, env_config(), cache_enabled=True)
    session_id = manager.cached_session_id(SessionRole.READWRITE)

    manager.close()
    manager.close()
    metrics = manager.metrics_snapshot()

    assert client.logout_sessions == [session_id]
    assert metrics["logout_requests"] == 1
    assert session_id not in repr(metrics)


def test_shared_role_session_respects_cache_feature_flag():
    cached_client = FakeApiClient()
    cached_manager = SessionManager(cached_client, env_config(), cache_enabled=True)
    with cached_manager.shared_role_session(SessionRole.READWRITE):
        pass
    with cached_manager.shared_role_session(SessionRole.READWRITE):
        pass

    fresh_client = FakeApiClient()
    fresh_manager = SessionManager(fresh_client, env_config(), cache_enabled=False)
    with fresh_manager.shared_role_session(SessionRole.READWRITE):
        pass
    with fresh_manager.shared_role_session(SessionRole.READWRITE):
        pass

    assert cached_client.login_roles == [SessionRole.READWRITE]
    assert fresh_client.login_roles == [SessionRole.READWRITE, SessionRole.READWRITE]
    assert cached_manager.metrics_snapshot()["mode"] == "on"
    assert fresh_manager.metrics_snapshot()["mode"] == "off"
