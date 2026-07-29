from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import requests
import urllib3

from clients.session import RefreshableSession
from config_loader.settings import Credentials, EnvironmentConfig
from models.api import ApiResponse
from utils.allure_helpers import allure_step, attach_json
from utils.redaction import redact


class EmsApiClient:
    def __init__(self, env: EnvironmentConfig) -> None:
        self.env = env
        self.base_url = env.base_url.rstrip("/")
        self.timeout = env.timeout
        self.verify_tls = env.verify_tls
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

        raw = requests.request(
            method.upper(),
            url,
            headers=headers,
            params=params,
            json=json,
            verify=self.verify_tls,
            timeout=self.timeout,
        )
        elapsed = time.perf_counter() - started
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
