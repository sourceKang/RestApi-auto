from __future__ import annotations

import pytest

from models.api import SessionRole


@pytest.mark.session
@pytest.mark.smoke
@pytest.mark.parametrize("role", list(SessionRole), ids=lambda role: role.value)
def test_login_and_logout_by_role(services, role):
    services.user_session.verify_login_and_logout_by_role(role)


@pytest.mark.session
def test_login_rejects_invalid_username(services):
    services.user_session.verify_login_rejects_invalid_username()


@pytest.mark.session
def test_login_rejects_invalid_password(services):
    services.user_session.verify_login_rejects_invalid_password()


@pytest.mark.session
def test_protected_api_rejects_missing_session(services):
    services.user_session.verify_protected_api_rejects_missing_session()


@pytest.mark.session
def test_protected_api_rejects_invalid_session(services):
    services.user_session.verify_protected_api_rejects_invalid_session()


@pytest.mark.session
def test_deleted_session_cannot_be_reused(services):
    services.user_session.verify_deleted_session_cannot_be_reused()
