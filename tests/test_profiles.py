from __future__ import annotations

import pytest

from automation.domains.profile import (
    DELETE_PROFILE_CASES,
    GET_PROFILE_CASES,
    GET_PROFILE_LIST_CASES,
    PATCH_INVALID_PROFILE_CASES,
    PATCH_PROFILE_CASES,
    POST_INVALID_PROFILE_CASES,
    POST_PROFILE_CASES,
    ProfileWorkspace,
)
from cases.case_catalog import case_id
from models.api import SessionRole


@pytest.fixture(scope="module")
def profile_workspace(services, session_manager, env_config):
    with session_manager.role_session(SessionRole.READWRITE) as session_id:
        workspace = ProfileWorkspace(services.profile, session_id)
        try:
            yield workspace
        finally:
            workspace.cleanup()


@pytest.mark.profile
@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("case", POST_PROFILE_CASES, ids=case_id)
def test_profile_post_cases(services, readwrite_session, profile_workspace, case):
    services.profile.verify_post_case(readwrite_session, profile_workspace, case)


@pytest.mark.profile
@pytest.mark.readwrite
@pytest.mark.parametrize("case", GET_PROFILE_CASES, ids=case_id)
def test_profile_get_cases(services, readwrite_session, profile_workspace, case):
    services.profile.verify_get_case(readwrite_session, profile_workspace, case)


@pytest.mark.profile
@pytest.mark.readwrite
@pytest.mark.parametrize("case", GET_PROFILE_LIST_CASES, ids=case_id)
def test_profile_get_list_cases(services, readwrite_session, profile_workspace, case):
    services.profile.verify_get_list_case(readwrite_session, profile_workspace, case)


@pytest.mark.profile
@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("case", PATCH_PROFILE_CASES, ids=case_id)
def test_profile_patch_cases(services, readwrite_session, profile_workspace, case):
    services.profile.verify_patch_case(readwrite_session, profile_workspace, case)


@pytest.mark.profile
@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("case", DELETE_PROFILE_CASES, ids=case_id)
def test_profile_delete_cases(services, readwrite_session, profile_workspace, case):
    services.profile.verify_delete_case(readwrite_session, profile_workspace, case)


@pytest.mark.profile
@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("case", POST_INVALID_PROFILE_CASES, ids=case_id)
def test_profile_post_invalid_param_cases(services, readwrite_session, profile_workspace, case):
    services.profile.verify_post_invalid_param_case(readwrite_session, profile_workspace, case)


@pytest.mark.profile
@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("case", PATCH_INVALID_PROFILE_CASES, ids=case_id)
def test_profile_patch_invalid_param_cases(services, readwrite_session, profile_workspace, case):
    services.profile.verify_patch_invalid_param_case(readwrite_session, profile_workspace, case)
