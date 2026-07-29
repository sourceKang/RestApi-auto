from __future__ import annotations

import time

from models.api import SessionRole
from utils.assertions import assert_api_failure, assert_api_failure_exact, assert_api_success
from utils.case_metadata import attach_case_id


SESSION_KEEPALIVE_INTERVAL_SECONDS = 60
SESSION_ABSOLUTE_LIFETIME_SECONDS = 600
SESSION_LAST_AUTHORIZED_MINUTE = 9
SESSION_EXPIRED_MESSAGE = "Not authorized."


class UserSessionService:
    def __init__(self, api_client, env_config) -> None:
        self.api_client = api_client
        self.env_config = env_config

    def verify_login_and_logout_by_role(self, role: SessionRole) -> None:
        attach_case_id("EMS1-6640", "test_get_sessionid")
        response = self.api_client.login(self.env_config.credentials_for(role))
        assert_api_success(response)
        session_id = self.api_client.session_id_from(response)
        assert session_id

        if role is SessionRole.READWRITE:
            session_id = self._verify_readwrite_absolute_lifetime(session_id)

        logout = self.api_client.logout(session_id)
        assert logout is not None
        assert_api_success(logout)

    def _verify_readwrite_absolute_lifetime(self, session_id: str) -> str:
        started_at = time.monotonic()
        observation_count = SESSION_ABSOLUTE_LIFETIME_SECONDS // SESSION_KEEPALIVE_INTERVAL_SECONDS

        for minute in range(1, observation_count + 1):
            target = started_at + minute * SESSION_KEEPALIVE_INTERVAL_SECONDS
            remaining = target - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)

            response = self.api_client.request(
                "GET",
                "/device",
                session=session_id,
                expected=f"readwrite session lifetime minute {minute}",
            )
            if minute <= SESSION_LAST_AUTHORIZED_MINUTE:
                assert_api_success(response)
            else:
                assert_api_failure_exact(response, expected_retresult=SESSION_EXPIRED_MESSAGE)

        renewed = self.api_client.login(self.env_config.credentials_for(SessionRole.READWRITE))
        assert_api_success(renewed)
        renewed_session_id = self.api_client.session_id_from(renewed)
        assert renewed_session_id

        device = self.api_client.request(
            "GET",
            "/device",
            session=renewed_session_id,
            expected="device access after readwrite re-login",
        )
        assert_api_success(device)
        return renewed_session_id

    def verify_login_rejects_invalid_username(self) -> None:
        attach_case_id("EMS1-7020", "test_usersession_post_invalid_param_should_return_error")
        credentials = self.env_config.readwrite
        response = self.api_client.request(
            "POST",
            "/usersession",
            json={"username": f"{credentials.username}_invalid", "password": credentials.password},
        )
        assert_api_failure(response, accepted_messages=("invalid username", "invalid password"))

    def verify_login_rejects_invalid_password(self) -> None:
        attach_case_id("EMS1-7020", "test_usersession_post_invalid_param_should_return_error")
        credentials = self.env_config.readwrite
        response = self.api_client.request(
            "POST",
            "/usersession",
            json={"username": credentials.username, "password": "definitely-wrong-password"},
        )
        assert_api_failure(response, accepted_messages=("invalid password", "invalid username"))

    def verify_protected_api_rejects_missing_session(self) -> None:
        attach_case_id("EMS1-7021", "test_usersession_delete_invalid_param_should_return_error")
        response = self.api_client.request("GET", "/device")
        assert_api_failure(response, accepted_messages=("invalid session", "not authorized"))

    def verify_protected_api_rejects_invalid_session(self) -> None:
        attach_case_id("EMS1-7021", "test_usersession_delete_invalid_param_should_return_error")
        response = self.api_client.request("GET", "/device", session="invalid-session-id")
        assert_api_failure(response, accepted_messages=("invalid session", "not authorized"))

    def verify_deleted_session_cannot_be_reused(self) -> None:
        attach_case_id("EMS1-6651", "test_delete_sessionid")
        login = self.api_client.login(self.env_config.credentials_for(SessionRole.READWRITE))
        assert_api_success(login)
        session_id = self.api_client.session_id_from(login)
        assert session_id
        logout = self.api_client.logout(session_id)
        assert logout is not None
        assert_api_success(logout)

        response = self.api_client.request("GET", "/device", session=session_id)
        assert_api_failure(response, accepted_messages=("invalid session", "not authorized"))
