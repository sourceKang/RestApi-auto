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
from cases.neox_legacy import case_id
from models.api import SessionRole


@pytest.fixture(scope="module")
def profile_workspace(profile_service, session_manager, env_config):
    with session_manager.role_session(SessionRole.READWRITE) as session_id:
        workspace = ProfileWorkspace(profile_service, session_id)
        try:
            yield workspace
        finally:
            workspace.cleanup()


@pytest.mark.profile
@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("case", POST_PROFILE_CASES, ids=case_id)
def test_legacy_profile_post_cases(profile_service, readwrite_session, profile_workspace, case):
    profile_service.verify_post_case(readwrite_session, profile_workspace, case)


@pytest.mark.profile
@pytest.mark.readwrite
@pytest.mark.parametrize("case", GET_PROFILE_CASES, ids=case_id)
def test_legacy_profile_get_cases(profile_service, readwrite_session, profile_workspace, case):
    profile_service.verify_get_case(readwrite_session, profile_workspace, case)


@pytest.mark.profile
@pytest.mark.readwrite
@pytest.mark.parametrize("case", GET_PROFILE_LIST_CASES, ids=case_id)
def test_legacy_profile_get_list_cases(profile_service, readwrite_session, profile_workspace, case):
    profile_service.verify_get_list_case(readwrite_session, profile_workspace, case)


@pytest.mark.profile
@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("case", PATCH_PROFILE_CASES, ids=case_id)
def test_legacy_profile_patch_cases(profile_service, readwrite_session, profile_workspace, case):
    profile_service.verify_patch_case(readwrite_session, profile_workspace, case)


@pytest.mark.profile
@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("case", DELETE_PROFILE_CASES, ids=case_id)
def test_legacy_profile_delete_cases(profile_service, readwrite_session, profile_workspace, case):
    profile_service.verify_delete_case(readwrite_session, profile_workspace, case)


@pytest.mark.profile
@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("case", POST_INVALID_PROFILE_CASES, ids=case_id)
def test_legacy_profile_post_invalid_param_cases(profile_service, readwrite_session, profile_workspace, case):
    profile_service.verify_post_invalid_param_case(readwrite_session, profile_workspace, case)


@pytest.mark.profile
@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("case", PATCH_INVALID_PROFILE_CASES, ids=case_id)
def test_legacy_profile_patch_invalid_param_cases(profile_service, readwrite_session, profile_workspace, case):
    profile_service.verify_patch_invalid_param_case(readwrite_session, profile_workspace, case)
