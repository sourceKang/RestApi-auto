from __future__ import annotations

import pytest

from models.api import SessionRole


@pytest.mark.session
@pytest.mark.smoke
@pytest.mark.parametrize("role", list(SessionRole), ids=lambda role: role.value)
def test_login_and_logout_by_role(user_session_service, role):
    user_session_service.verify_login_and_logout_by_role(role)


@pytest.mark.session
def test_login_rejects_invalid_username(user_session_service):
    user_session_service.verify_login_rejects_invalid_username()


@pytest.mark.session
def test_login_rejects_invalid_password(user_session_service):
    user_session_service.verify_login_rejects_invalid_password()


@pytest.mark.session
def test_protected_api_rejects_missing_session(user_session_service):
    user_session_service.verify_protected_api_rejects_missing_session()


@pytest.mark.session
def test_protected_api_rejects_invalid_session(user_session_service):
    user_session_service.verify_protected_api_rejects_invalid_session()


@pytest.mark.session
def test_deleted_session_cannot_be_reused(user_session_service):
    user_session_service.verify_deleted_session_cannot_be_reused()
