from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass
from threading import RLock
from typing import TYPE_CHECKING, Callable, Iterator, Protocol, runtime_checkable

from config_loader.settings import EnvironmentConfig
from models.api import SessionRole
from utils.assertions import assert_api_success
from utils.diagnostics import format_response_summary

if TYPE_CHECKING:
    from clients.ems_api_client import EmsApiClient


SESSION_ABSOLUTE_LIFETIME_SECONDS = 600
SESSION_PROACTIVE_REFRESH_SECONDS = 540
SAFE_RETRY_METHODS = frozenset({"GET", "HEAD"})


@runtime_checkable
class RefreshableSession(Protocol):
    def current_session_id(self) -> str: ...

    def should_refresh_on_not_authorized(self, method: str) -> bool: ...

    def refresh_after_not_authorized(self, observed_session_id: str) -> str: ...

    def record_authorization_recovery(self, *, request_retried: bool) -> None: ...


@dataclass(frozen=True)
class _CachedSessionEntry:
    session_id: str
    issued_at: float


@dataclass(frozen=True)
class CachedSessionHandle:
    manager: "SessionManager"
    role: SessionRole

    def current_session_id(self) -> str:
        return self.manager.cached_session_id(self.role)

    def should_refresh_on_not_authorized(self, method: str) -> bool:
        normalized = method.upper()
        if self.role is SessionRole.READWRITE:
            return True
        if self.role is SessionRole.READONLY:
            return normalized in SAFE_RETRY_METHODS
        return False

    def refresh_after_not_authorized(self, observed_session_id: str) -> str:
        return self.manager.refresh_after_not_authorized(self.role, observed_session_id)

    def record_authorization_recovery(self, *, request_retried: bool) -> None:
        self.manager.record_authorization_recovery(request_retried=request_retried)


class SessionManager:
    """Creates EMS sessions and guarantees logout for fixture-owned sessions."""

    def __init__(
        self,
        api_client: EmsApiClient,
        env: EnvironmentConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
        proactive_refresh_seconds: float = SESSION_PROACTIVE_REFRESH_SECONDS,
        cache_enabled: bool = True,
    ) -> None:
        if not 0 < proactive_refresh_seconds < SESSION_ABSOLUTE_LIFETIME_SECONDS:
            raise ValueError(
                "proactive_refresh_seconds must be greater than 0 and less than the 600-second lifetime"
            )
        self.api_client = api_client
        self.env = env
        self.clock = clock
        self.proactive_refresh_seconds = proactive_refresh_seconds
        self.cache_enabled = cache_enabled
        self._cached: dict[SessionRole, _CachedSessionEntry] = {}
        self._lock = RLock()
        self._metrics = {
            "login_requests": 0,
            "logout_requests": 0,
            "fresh_logins": 0,
            "cached_logins": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "proactive_refreshes": 0,
            "authorization_refreshes": 0,
            "safe_retries": 0,
            "mutation_not_retried": 0,
        }
        self._session_generations = {role: 0 for role in SessionRole}

    @contextmanager
    def role_session(self, role: SessionRole) -> Iterator[str]:
        self.discard_cached_role(role)
        self._record_login(cached=False)
        response = self.api_client.login(self.env.credentials_for(role))
        assert_api_success(response)
        session_id = self.api_client.session_id_from(response)
        assert session_id, f"Login succeeded but no sessionid was returned: {format_response_summary(response)}"
        try:
            yield session_id
        finally:
            self._logout(session_id)

    @contextmanager
    def credentials_session(self, credentials) -> Iterator[str]:
        role = self._role_for_credentials(credentials)
        if role is not None:
            self.discard_cached_role(role)
        self._record_login(cached=False)
        response = self.api_client.login(credentials)
        assert_api_success(response)
        session_id = self.api_client.session_id_from(response)
        assert session_id, f"Login succeeded but no sessionid was returned: {format_response_summary(response)}"
        try:
            yield session_id
        finally:
            self._logout(session_id)

    @contextmanager
    def shared_role_session(self, role: SessionRole) -> Iterator[str | CachedSessionHandle]:
        if self.cache_enabled:
            with self.cached_role_session(role) as session:
                yield session
            return
        with self.role_session(role) as session:
            yield session

    @contextmanager
    def cached_role_session(self, role: SessionRole) -> Iterator[CachedSessionHandle]:
        handle = CachedSessionHandle(self, role)
        handle.current_session_id()
        yield handle

    def cached_session_id(self, role: SessionRole) -> str:
        with self._lock:
            entry = self._cached.get(role)
            if entry is not None and self.clock() - entry.issued_at < self.proactive_refresh_seconds:
                self._metrics["cache_hits"] += 1
                return entry.session_id
            self._metrics["cache_misses"] += 1
            if entry is not None:
                self._metrics["proactive_refreshes"] += 1
                self._logout(entry.session_id)
                self._cached.pop(role, None)
            return self._login_cached(role)

    def refresh_after_not_authorized(self, role: SessionRole, observed_session_id: str) -> str:
        with self._lock:
            self._metrics["authorization_refreshes"] += 1
            entry = self._cached.get(role)
            if entry is not None and entry.session_id != observed_session_id:
                return entry.session_id
            self._cached.pop(role, None)
            return self._login_cached(role)

    def record_authorization_recovery(self, *, request_retried: bool) -> None:
        with self._lock:
            key = "safe_retries" if request_retried else "mutation_not_retried"
            self._metrics[key] += 1

    def discard_cached_role(self, role: SessionRole) -> None:
        with self._lock:
            entry = self._cached.pop(role, None)
            if entry is not None:
                self._logout(entry.session_id)

    def close(self) -> None:
        with self._lock:
            entries = list(self._cached.values())
            self._cached.clear()
            for entry in entries:
                self._logout(entry.session_id)

    def metrics_snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "mode": "on" if self.cache_enabled else "off",
                **self._metrics,
                "session_generations": {
                    role.value: generation
                    for role, generation in self._session_generations.items()
                    if generation > 0
                },
            }

    def _login_cached(self, role: SessionRole) -> str:
        self._record_login(cached=True)
        response = self.api_client.login(self.env.credentials_for(role))
        assert_api_success(response)
        session_id = self.api_client.session_id_from(response)
        assert session_id, f"Login succeeded but no sessionid was returned: {format_response_summary(response)}"
        self._session_generations[role] += 1
        self._cached[role] = _CachedSessionEntry(session_id=session_id, issued_at=self.clock())
        return session_id

    def _record_login(self, *, cached: bool) -> None:
        with self._lock:
            self._metrics["login_requests"] += 1
            self._metrics["cached_logins" if cached else "fresh_logins"] += 1

    def _logout(self, session_id: str) -> None:
        with self._lock:
            self._metrics["logout_requests"] += 1
        self.api_client.logout(session_id)

    def _role_for_credentials(self, credentials) -> SessionRole | None:
        for role in SessionRole:
            if credentials == self.env.credentials_for(role):
                return role
        return None
