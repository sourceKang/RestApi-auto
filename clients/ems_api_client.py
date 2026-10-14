from __future__ import annotations

import threading
import time
from typing import Any
from urllib.parse import quote, urlsplit
from uuid import uuid4

import requests
import urllib3

from clients.session import RefreshableSession
from config_loader.settings import Credentials, EnvironmentConfig
from models.api import ApiResponse
from utils.allure_helpers import allure_step, attach_json
from utils.redaction import redact
from utils.reporting import record_connection_event, record_slow_request

# Default waits before resending a request after a transport error (see ADR 0002);
# an EMS target can override them with ems.transport_retry_delays.
TRANSPORT_RETRY_DELAYS: tuple[float, ...] = (5, 15)
# GET/HEAD are resent after any transport error; other methods only after a connect
# timeout, when the connection was never established and EMS cannot have seen the request.
SAFE_TRANSPORT_RETRY_METHODS = frozenset({"GET", "HEAD"})
# A request whose total time (all attempts and waits) exceeds this is flagged in the report.
SLOW_REQUEST_SECONDS = 30.0

# Process-wide pacing so that every client honours ems.min_request_interval together.
_PACING_LOCK = threading.Lock()
_last_request_started = 0.0


def _transport_error_summary(exc: Exception, host: str, timeout: Any, elapsed: float) -> str:
    """Describe a transport error in plain words, without urllib3's internal retry wording."""
    after = f"after {elapsed:.1f} s"
    if isinstance(exc, requests.ConnectTimeout):
        return (
            f"ConnectTimeout: could not connect to {host}; connect timed out {after} "
            f"(client limit {timeout} s); connection not established, request not sent"
        )
    if isinstance(exc, requests.ReadTimeout):
        return (
            f"ReadTimeout: {host} accepted the request but sent no response; read timed out {after} "
            f"(client limit {timeout} s); EMS may have processed the request"
        )
    detail = str(exc)
    if "RemoteDisconnected" in detail:
        return (
            f"Connection dropped: {host} closed the connection without sending a response ({after}); "
            "EMS may have processed the request"
        )
    if "ConnectionResetError" in detail or "10054" in detail:
        return (
            f"Connection reset: {host} forcibly closed the connection ({after}); "
            "EMS may have processed the request"
        )
    if "NewConnectionError" in detail or "refused" in detail.lower() or "10061" in detail:
        return f"Connection refused: {host} rejected the connection ({after}); request not sent"
    reason = detail.replace("\n", " ")
    return f"{type(exc).__name__}: {host} ({after}): {reason[:160]}"


class EmsApiClient:
    def __init__(self, env: EnvironmentConfig) -> None:
        self.env = env
        self.base_url = env.base_url.rstrip("/")
        self.timeout = env.timeout
        self.verify_tls = env.verify_tls
        self.retry_delays = tuple(getattr(env, "transport_retry_delays", TRANSPORT_RETRY_DELAYS))
        self.min_request_interval = float(getattr(env, "min_request_interval", 0.0) or 0.0)
        if not self.verify_tls:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def request(
        self,
        method: str,
        path: str,
        *,
        session: str | RefreshableSession | None = None,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        expected: str | None = None,
    ) -> ApiResponse:
        with allure_step(f"{method.upper()} {path}"):
            session_id = session.current_session_id() if isinstance(session, RefreshableSession) else session
            response = self._send_request(
                method,
                path,
                session=session_id,
                params=params,
                json=json,
                expected=expected,
            )
            if not isinstance(session, RefreshableSession) or not self._is_not_authorized(response):
                return response
            if not session.should_refresh_on_not_authorized(method):
                return response

            refreshed_session_id = session.refresh_after_not_authorized(session_id)
            safe_to_retry = method.upper() in {"GET", "HEAD"}
            session.record_authorization_recovery(request_retried=safe_to_retry)
            attach_json(
                "session refresh after Not authorized",
                {
                    "method": method.upper(),
                    "path": path,
                    "request_retried": safe_to_retry,
                },
            )
            if not safe_to_retry:
                return response
            retry_expected = f"{expected} after session refresh" if expected else "success after session refresh"
            return self._send_request(
                method,
                path,
                session=refreshed_session_id,
                params=params,
                json=json,
                expected=retry_expected,
            )

    def _send_request(
        self,
        method: str,
        path: str,
        *,
        session: str | None = None,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        expected: str | None = None,
    ) -> ApiResponse:
        request_id = uuid4().hex
        url = f"{self.base_url}{self._encode_path(path)}"
        headers = {"sessionid": session} if session else None
        started = time.perf_counter()

        attach_json(
            f"request {request_id}",
            {
                "method": method.upper(),
                "url": url,
                "headers": headers,
                "params": params,
                "json": json,
                "expected": expected,
            },
        )

        raw, attempts = self._request_with_transport_retry(
            method.upper(),
            path,
            url,
            headers=headers,
            params=params,
            json=json,
        )
        elapsed = time.perf_counter() - started
        if elapsed > SLOW_REQUEST_SECONDS:
            self._record_slow_request(method.upper(), path, elapsed, attempts, raw.status_code)
        parsed = self._parse_response(raw)
        response = ApiResponse(
            status_code=raw.status_code,
            json=parsed,
            text=raw.text,
            elapsed=elapsed,
            request_id=request_id,
            method=method.upper(),
            url=raw.url,
        )

        attach_json(
            f"response {request_id}",
            {
                "status_code": response.status_code,
                "elapsed": response.elapsed,
                "body": redact(response.json),
            },
        )
        return response

    def _request_with_transport_retry(
        self,
        method: str,
        path: str,
        url: str,
        *,
        headers: dict[str, str] | None,
        params: dict[str, Any] | None,
        json: dict[str, Any] | None,
    ) -> tuple[requests.Response, int]:
        """Send one request and resend it after a safe transport error (see ADR 0002).

        Retry waits come from the EMS target (ems.transport_retry_delays).

        GET/HEAD are resent after any connection error or timeout. POST/PUT/PATCH/DELETE
        are resent only after a connect timeout; after a read timeout, reset or dropped
        connection EMS may already have applied them, so they are not resent. Every
        transport error is recorded for the report header and Allure.
        Returns the response and the number of attempts used.
        """
        max_attempts = len(self.retry_delays) + 1
        events = []
        for attempt in range(1, max_attempts + 1):
            self._pace()
            attempt_started = time.perf_counter()
            try:
                raw = requests.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json,
                    verify=self.verify_tls,
                    timeout=self.timeout,
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                retryable = method in SAFE_TRANSPORT_RETRY_METHODS or isinstance(exc, requests.ConnectTimeout)
                will_retry = retryable and attempt < max_attempts
                event = record_connection_event(
                    method,
                    path,
                    _transport_error_summary(
                        exc,
                        self._host_label(),
                        self.timeout,
                        time.perf_counter() - attempt_started,
                    ),
                    attempt=attempt,
                    max_attempts=max_attempts if retryable else attempt,
                    action="retried" if will_retry else "raised",
                )
                events.append(event)
                attach_json(
                    "EMS connection error",
                    {
                        "method": method,
                        "path": path,
                        "attempt": attempt,
                        "max_attempts": event.max_attempts,
                        "error": event.error,
                        "action": event.action,
                        "retry_delay_seconds": self.retry_delays[attempt - 1] if will_retry else None,
                    },
                )
                if not will_retry:
                    raise
                time.sleep(self.retry_delays[attempt - 1])
                continue
            for event in events:
                event.recovered = True
            return raw, attempt
        raise AssertionError("unreachable: transport retry loop exited without a response")

    def _pace(self) -> None:
        """Keep at least min_request_interval seconds between request starts to ease a loaded EMS."""
        global _last_request_started
        if self.min_request_interval <= 0:
            return
        with _PACING_LOCK:
            wait = self.min_request_interval - (time.monotonic() - _last_request_started)
            if wait > 0:
                time.sleep(wait)
            _last_request_started = time.monotonic()

    def _record_slow_request(self, method: str, path: str, elapsed: float, attempts: int, status_code: int) -> None:
        record_slow_request(
            method,
            path,
            elapsed,
            attempts=attempts,
            status_code=status_code,
            threshold=SLOW_REQUEST_SECONDS,
        )
        attach_json(
            "EMS slow request",
            {
                "method": method,
                "path": path,
                "elapsed_seconds": round(elapsed, 1),
                "threshold_seconds": SLOW_REQUEST_SECONDS,
                "attempts": attempts,
                "status_code": status_code,
            },
        )

    def _host_label(self) -> str:
        parsed = urlsplit(self.base_url)
        return parsed.netloc or self.base_url

    def login(self, credentials: Credentials) -> ApiResponse:
        return self.request(
            "POST",
            "/usersession",
            json={"username": credentials.username, "password": credentials.password},
            expected="login",
        )

    def logout(self, session_id: str | None) -> ApiResponse | None:
        if not session_id:
            return None
        return self.request("DELETE", "/usersession", session=session_id, expected="logout")

    @staticmethod
    def session_id_from(response: ApiResponse) -> str | None:
        if isinstance(response.json, dict):
            retval = response.json.get("retval", {})
            if isinstance(retval, dict):
                sessionid = retval.get("sessionid")
                return str(sessionid) if sessionid else None
        return None

    @staticmethod
    def _is_not_authorized(response: ApiResponse) -> bool:
        return response.retstatus == "Fail" and response.retresult.strip().casefold() == "not authorized."

    @staticmethod
    def _parse_response(response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return {"retstatus": "Fail", "retresult": response.text, "raw": response.text}

    @staticmethod
    def _encode_path(path: str) -> str:
        if not path.startswith("/"):
            path = f"/{path}"
        return "/".join(quote(segment, safe="") for segment in path.split("/"))
