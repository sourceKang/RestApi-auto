from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from clients.ems_api_client import EmsApiClient
from config_loader.settings import EnvironmentConfig
from models.api import SessionRole
from utils.assertions import assert_api_success
from utils.diagnostics import format_response_summary


class SessionManager:
    """Creates EMS sessions and guarantees logout for fixture-owned sessions."""

    def __init__(self, api_client: EmsApiClient, env: EnvironmentConfig) -> None:
        self.api_client = api_client
        self.env = env

    @contextmanager
    def role_session(self, role: SessionRole) -> Iterator[str]:
        response = self.api_client.login(self.env.credentials_for(role))
        assert_api_success(response)
        session_id = self.api_client.session_id_from(response)
        assert session_id, f"Login succeeded but no sessionid was returned: {format_response_summary(response)}"
        try:
            yield session_id
        finally:
            self.api_client.logout(session_id)

    @contextmanager
    def credentials_session(self, credentials) -> Iterator[str]:
        response = self.api_client.login(credentials)
        assert_api_success(response)
        session_id = self.api_client.session_id_from(response)
        assert session_id, f"Login succeeded but no sessionid was returned: {format_response_summary(response)}"
        try:
            yield session_id
        finally:
            self.api_client.logout(session_id)
