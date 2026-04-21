from __future__ import annotations

import copy

import pytest

from cases.neox_legacy import (
    case_id,
    first_profile_definition_for,
    profile_definition_by_name,
    profile_cases_for_operation,
    profile_definitions_for,
    profile_invalid_cases_for_operation,
)
from utils.assertions import assert_api_failure, assert_api_success
from utils.case_metadata import attach_legacy_case
from utils.json_match import content_as_dict


POST_PROFILE_CASES = profile_cases_for_operation("post")
GET_PROFILE_CASES = profile_cases_for_operation("get")
PATCH_PROFILE_CASES = profile_cases_for_operation("patch")
GET_PROFILE_LIST_CASES = profile_cases_for_operation("get_profiles")
DELETE_PROFILE_CASES = profile_cases_for_operation("delete")
POST_INVALID_PROFILE_CASES = profile_invalid_cases_for_operation("post")
PATCH_INVALID_PROFILE_CASES = profile_invalid_cases_for_operation("patch")


@pytest.mark.profile
@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("case", POST_PROFILE_CASES, ids=case_id)
def test_legacy_profile_post_cases(api_client, readwrite_session, cleanup_registry, case):
    attach_legacy_case(case)
    definitions = profile_definitions_for(case)
    assert definitions, f"No profile data converted for {case['legacy_name']}"

    for definition in definitions:
        _ensure_profile_deleted(api_client, readwrite_session, definition)
        cleanup_registry.add(lambda d=definition: _delete_profile(api_client, readwrite_session, d))
        _ensure_profile_dependencies(api_client, readwrite_session, cleanup_registry, definition.get("post_profile_info", {}))
        response = _post_profile(api_client, readwrite_session, definition)
        assert_api_success(response)


@pytest.mark.profile
@pytest.mark.readwrite
@pytest.mark.parametrize("case", GET_PROFILE_CASES, ids=case_id)
def test_legacy_profile_get_cases(api_client, readwrite_session, cleanup_registry, case):
    attach_legacy_case(case)
    definition = first_profile_definition_for(case)
    _ensure_profile_exists_or_skip(api_client, readwrite_session, cleanup_registry, definition)

    response = _get_profile(api_client, readwrite_session, definition)
    assert_api_success(response)
    retval = response.json.get("retval", {})
    assert retval.get("Name") == definition["profilename"]

    content = content_as_dict(retval.get("Content", {}))
    for key, value in definition.get("post_profile_info", {}).items():
        if key in content:
            assert content[key] == value


@pytest.mark.profile
@pytest.mark.readwrite
@pytest.mark.parametrize("case", GET_PROFILE_LIST_CASES, ids=case_id)
def test_legacy_profile_get_list_cases(api_client, readwrite_session, cleanup_registry, case):
    attach_legacy_case(case)
    definition = first_profile_definition_for(case)
    _ensure_profile_exists_or_skip(api_client, readwrite_session, cleanup_registry, definition)

    response = api_client.request("GET", f"/profile/{definition['profiletype']}", session=readwrite_session)
    assert_api_success(response)
    assert _profile_name_is_present(response.json, definition["profilename"])


@pytest.mark.profile
@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("case", PATCH_PROFILE_CASES, ids=case_id)
def test_legacy_profile_patch_cases(api_client, readwrite_session, cleanup_registry, case):
    attach_legacy_case(case)
    definition = first_profile_definition_for(case)
    if "patch_profile_info" not in definition:
        pytest.skip(f"{definition['_config_ref']} has no patch_profile_info")
    _ensure_profile_exists_or_skip(api_client, readwrite_session, cleanup_registry, definition)

    _ensure_profile_dependencies(api_client, readwrite_session, cleanup_registry, definition["patch_profile_info"])
    response = _patch_profile(api_client, readwrite_session, definition, definition["patch_profile_info"])
    assert_api_success(response)

    get_response = _get_profile(api_client, readwrite_session, definition)
    assert_api_success(get_response)


@pytest.mark.profile
@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("case", DELETE_PROFILE_CASES, ids=case_id)
def test_legacy_profile_delete_cases(api_client, readwrite_session, cleanup_registry, case):
    attach_legacy_case(case)
    definitions = profile_definitions_for(case)
    assert definitions, f"No profile data converted for {case['legacy_name']}"

    for definition in definitions:
        _ensure_profile_exists_or_skip(api_client, readwrite_session, cleanup_registry, definition)
        response = _delete_profile(api_client, readwrite_session, definition)
        assert_api_success(response)
        get_response = _get_profile(api_client, readwrite_session, definition)
        assert_api_failure(get_response, accepted_messages=("does not exist", "no data", "not found", "invalid parameter"))


@pytest.mark.profile
@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("case", POST_INVALID_PROFILE_CASES, ids=case_id)
def test_legacy_profile_post_invalid_param_cases(api_client, readwrite_session, cleanup_registry, case):
    attach_legacy_case(case)
    definition = first_profile_definition_for(case)
    invalid_params = definition.get("invalid_params_to_test") or []
    if not invalid_params:
        pytest.skip(f"{definition['_config_ref']} has no invalid_params_to_test")

    _ensure_profile_deleted(api_client, readwrite_session, definition)
    cleanup_registry.add(lambda: _delete_profile(api_client, readwrite_session, definition))

    for invalid_param in invalid_params:
        payload = copy.deepcopy(definition.get("post_profile_info", {}))
        _ensure_profile_dependencies(api_client, readwrite_session, cleanup_registry, payload)
        _apply_invalid_values(payload, invalid_param)
        response = _post_profile(api_client, readwrite_session, definition, payload)
        _assert_invalid_response(response, invalid_param)


@pytest.mark.profile
@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("case", PATCH_INVALID_PROFILE_CASES, ids=case_id)
def test_legacy_profile_patch_invalid_param_cases(api_client, readwrite_session, cleanup_registry, case):
    attach_legacy_case(case)
    definition = first_profile_definition_for(case)
    invalid_params = definition.get("invalid_params_to_test") or []
    if not invalid_params:
        pytest.skip(f"{definition['_config_ref']} has no invalid_params_to_test")
    if "patch_profile_info" not in definition:
        pytest.skip(f"{definition['_config_ref']} has no patch_profile_info")

    _ensure_profile_exists_or_skip(api_client, readwrite_session, cleanup_registry, definition)

    for invalid_param in invalid_params:
        payload = copy.deepcopy(definition["patch_profile_info"])
        _ensure_profile_dependencies(api_client, readwrite_session, cleanup_registry, payload)
        _apply_invalid_values(payload, invalid_param)
        response = _patch_profile(api_client, readwrite_session, definition, payload)
        _assert_invalid_response(response, invalid_param)


def _profile_path(definition):
    return f"/profile/{definition['profiletype']}/{definition['profilename']}"


def _get_profile(api_client, session_id, definition):
    return api_client.request("GET", _profile_path(definition), session=session_id)


def _post_profile(api_client, session_id, definition, content=None):
    return api_client.request(
        "POST",
        _profile_path(definition),
        session=session_id,
        json={"Content": content if content is not None else definition.get("post_profile_info", {})},
    )


def _patch_profile(api_client, session_id, definition, content):
    return api_client.request("PATCH", _profile_path(definition), session=session_id, json={"Content": content})


def _delete_profile(api_client, session_id, definition):
    return api_client.request("DELETE", _profile_path(definition), session=session_id)


def _ensure_profile_deleted(api_client, session_id, definition):
    existing = _get_profile(api_client, session_id, definition)
    if existing.retstatus == "Success":
        delete = _delete_profile(api_client, session_id, definition)
        if delete.retstatus == "Fail" and "used by other Profile" in delete.retresult:
            pytest.skip(
                f"Profile {definition['profiletype']}/{definition['profilename']} "
                "is used by another profile and cannot be deleted safely."
            )
        assert_api_success(delete)


def _ensure_profile_exists_or_skip(api_client, session_id, cleanup_registry, definition):
    existing = _get_profile(api_client, session_id, definition)
    if existing.retstatus == "Success":
        return

    _ensure_profile_dependencies(api_client, session_id, cleanup_registry, definition.get("post_profile_info", {}))
    create = _post_profile(api_client, session_id, definition)
    if create.retstatus != "Success":
        pytest.skip(
            f"Cannot create prerequisite profile {definition['_config_ref']} "
            f"({definition['profiletype']}/{definition['profilename']}): {create.json!r}"
        )
    cleanup_registry.add(lambda: _delete_profile(api_client, session_id, definition))


def _ensure_profile_dependencies(api_client, session_id, cleanup_registry, payload, seen=None):
    seen = seen or set()
    for dependency_name in sorted(_profile_refs(payload)):
        if dependency_name in seen:
            continue
        dependency = profile_definition_by_name(dependency_name)
        if dependency is None:
            continue
        key = (dependency["profiletype"], dependency["profilename"])
        if key in seen:
            continue
        seen.add(key)
        _ensure_profile_dependencies(
            api_client,
            session_id,
            cleanup_registry,
            dependency.get("post_profile_info", {}),
            seen,
        )
        existing = _get_profile(api_client, session_id, dependency)
        if existing.retstatus == "Success":
            continue
        created = _post_profile(api_client, session_id, dependency)
        if created.retstatus != "Success":
            pytest.skip(
                f"Cannot create dependency profile {dependency['_config_ref']} "
                f"({dependency['profiletype']}/{dependency['profilename']}): {created.json!r}"
            )
        cleanup_registry.add(lambda d=dependency: _delete_profile(api_client, session_id, d))


def _profile_refs(value):
    refs = set()
    if isinstance(value, dict):
        for item in value.values():
            refs.update(_profile_refs(item))
    elif isinstance(value, list):
        for item in value:
            refs.update(_profile_refs(item))
    elif isinstance(value, str) and value.startswith("#RestApi"):
        refs.add(value)
    return refs


def _profile_name_is_present(payload, profilename):
    if isinstance(payload, dict):
        if payload.get("Name") == profilename:
            return True
        return any(_profile_name_is_present(value, profilename) for value in payload.values())
    if isinstance(payload, list):
        return any(_profile_name_is_present(item, profilename) for item in payload)
    return False


def _apply_invalid_values(payload, invalid_param):
    for key, value in invalid_param.items():
        if key == "expected_error":
            continue
        payload[key] = value


def _assert_invalid_response(response, invalid_param):
    assert response.retstatus == "Fail", f"Expected invalid parameter failure, got {response.json!r}"
    expected_error = invalid_param.get("expected_error")
    if expected_error:
        assert expected_error in response.retresult, (
            f"Expected error {expected_error!r} in response, got {response.json!r}"
        )
