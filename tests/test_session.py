from __future__ import annotations

import pytest

from models.api import SessionRole
from utils.assertions import assert_api_failure, assert_api_success
from utils.case_metadata import attach_case_id


@pytest.mark.session
@pytest.mark.smoke
@pytest.mark.parametrize("role", list(SessionRole), ids=lambda role: role.value)
def test_login_and_logout_by_role(api_client, env_config, role):
    attach_case_id("EMS1-6640", "test_get_sessionid")
    response = api_client.login(env_config.credentials_for(role))
    assert_api_success(response)
    session_id = api_client.session_id_from(response)
    assert session_id

    logout = api_client.logout(session_id)
    assert logout is not None
    assert_api_success(logout)


@pytest.mark.session
def test_login_rejects_invalid_username(api_client, env_config):
    attach_case_id("EMS1-7020", "test_usersession_post_invalid_param_should_return_error")
    credentials = env_config.readwrite
    response = api_client.request(
        "POST",
        "/usersession",
        json={"username": f"{credentials.username}_invalid", "password": credentials.password},
    )
    assert_api_failure(response, accepted_messages=("invalid username", "invalid password"))


@pytest.mark.session
def test_login_rejects_invalid_password(api_client, env_config):
    attach_case_id("EMS1-7020", "test_usersession_post_invalid_param_should_return_error")
    credentials = env_config.readwrite
    response = api_client.request(
        "POST",
        "/usersession",
        json={"username": credentials.username, "password": "definitely-wrong-password"},
    )
    assert_api_failure(response, accepted_messages=("invalid password", "invalid username"))


@pytest.mark.session
def test_protected_api_rejects_missing_session(api_client):
    attach_case_id("EMS1-7021", "test_usersession_delete_invalid_param_should_return_error")
    response = api_client.request("GET", "/device")
    assert_api_failure(response, accepted_messages=("invalid session", "not authorized"))


@pytest.mark.session
def test_protected_api_rejects_invalid_session(api_client):
    attach_case_id("EMS1-7021", "test_usersession_delete_invalid_param_should_return_error")
    response = api_client.request("GET", "/device", session="invalid-session-id")
    assert_api_failure(response, accepted_messages=("invalid session", "not authorized"))


@pytest.mark.session
def test_deleted_session_cannot_be_reused(api_client, env_config):
    attach_case_id("EMS1-6651", "test_delete_sessionid")
    login = api_client.login(env_config.credentials_for(SessionRole.READWRITE))
    assert_api_success(login)
    session_id = api_client.session_id_from(login)
    assert session_id
    logout = api_client.logout(session_id)
    assert logout is not None
    assert_api_success(logout)

    response = api_client.request("GET", "/device", session=session_id)
    assert_api_failure(response, accepted_messages=("invalid session", "not authorized"))
