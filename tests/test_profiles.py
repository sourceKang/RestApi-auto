from __future__ import annotations

import copy

import pytest

from cases.neox_legacy import (
    case_id,
    first_profile_definition_for,
    legacy_profile_data,
    profile_definition_by_name,
    profile_cases_for_operation,
    profile_definitions_for,
    profile_invalid_cases_for_operation,
)
from models.api import SessionRole
from utils.assertions import assert_api_failure, assert_api_success
from utils.case_metadata import attach_legacy_case
from utils.diagnostics import format_response_summary
from utils.json_match import content_as_dict


PROFILE_TYPE_CREATE_RANK = {
    "IGMPGroupPrivilegeProfile": 10,
    "RateLimitProfile": 10,
    "ShapingProfile": 10,
    "WeightProfile": 10,
    "ONTAlarmProfile": 20,
    "ONTAclProfile": 20,
    "ONTVoipDialPlanProfile": 20,
    "ONTVoipCommonProfile": 20,
    "ONTVoipSipProfile": 20,
    "ONTSecurityProfile": 20,
    "ONTUNIProfile": 20,
    "ONTBandwidthProfile": 20,
    "ONTServiceProfile": 20,
    "ONTONTProfile": 20,
    "ONTMulticastProfile": 30,
    "GETemplateProfile": 80,
    "ONTTemplateProfile": 90,
}


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


def _sort_profile_cases_for_create(cases):
    return sorted(
        cases,
        key=lambda case: (
            _case_dependency_depth(case),
            _case_profile_rank(case),
            case.get("source_line") or 0,
        ),
    )


def _sort_profile_cases_for_delete(cases):
    return list(reversed(_sort_profile_cases_for_create(cases)))


def _case_dependency_depth(case):
    definitions = profile_definitions_for(case)
    if not definitions:
        return 0
    return max(_profile_definition_depth(definition) for definition in definitions)


def _case_profile_rank(case):
    definitions = profile_definitions_for(case)
    if not definitions:
        return 0
    return max(_profile_type_rank(definition) for definition in definitions)


def _profile_type_rank(definition):
    return PROFILE_TYPE_CREATE_RANK.get(definition["profiletype"], 50)


def _profile_definition_depth(definition, seen=None):
    seen = seen or set()
    key = (definition["profiletype"], definition["profilename"])
    if key in seen:
        return 0
    seen.add(key)

    depth = 0
    for dependency_name in _profile_refs(definition.get("post_profile_info", {})):
        dependency = profile_definition_by_name(dependency_name)
        if dependency is None:
            continue
        depth = max(depth, 1 + _profile_definition_depth(dependency, seen.copy()))
    return depth


POST_PROFILE_CASES = _sort_profile_cases_for_create(profile_cases_for_operation("post"))
GET_PROFILE_CASES = _sort_profile_cases_for_create(profile_cases_for_operation("get"))
PATCH_PROFILE_CASES = _sort_profile_cases_for_create(profile_cases_for_operation("patch"))
GET_PROFILE_LIST_CASES = _sort_profile_cases_for_create(profile_cases_for_operation("get_profiles"))
DELETE_PROFILE_CASES = _sort_profile_cases_for_delete(profile_cases_for_operation("delete"))
POST_INVALID_PROFILE_CASES = profile_invalid_cases_for_operation("post")
PATCH_INVALID_PROFILE_CASES = profile_invalid_cases_for_operation("patch")


class ProfileWorkspace:
    def __init__(self, api_client, session_id):
        self.api_client = api_client
        self.session_id = session_id
        self._created = {}

    def add(self, definition):
        self._created[_profile_key(definition)] = copy.deepcopy(definition)

    def discard(self, definition):
        self._created.pop(_profile_key(definition), None)

    def cleanup(self):
        for definition in _definitions_delete_order(list(self._created.values())):
            _delete_profile(self.api_client, self.session_id, definition)
        self._created.clear()


@pytest.fixture(scope="module")
def profile_workspace(api_client, env_config):
    response = api_client.login(env_config.credentials_for(SessionRole.READWRITE))
    assert_api_success(response)
    session_id = api_client.session_id_from(response)
    assert session_id, f"Login succeeded but no sessionid was returned: {format_response_summary(response)}"
    workspace = ProfileWorkspace(api_client, session_id)
    try:
        yield workspace
    finally:
        workspace.cleanup()
        api_client.logout(session_id)


@pytest.mark.profile
@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("case", POST_PROFILE_CASES, ids=case_id)
def test_legacy_profile_post_cases(api_client, readwrite_session, profile_workspace, case):
    attach_legacy_case(case)
    definitions = _definitions_create_order(profile_definitions_for(case))
    assert definitions, f"No profile data converted for {case['legacy_name']}"

    for definition in _definitions_delete_order(definitions):
        _ensure_profile_deleted(api_client, readwrite_session, definition)

    for definition in definitions:
        _ensure_profile_dependencies(
            api_client,
            readwrite_session,
            profile_workspace,
            definition.get("post_profile_info", {}),
        )
        response = _post_profile(api_client, readwrite_session, definition)
        assert_api_success(response)
        profile_workspace.add(definition)


@pytest.mark.profile
@pytest.mark.readwrite
@pytest.mark.parametrize("case", GET_PROFILE_CASES, ids=case_id)
def test_legacy_profile_get_cases(api_client, readwrite_session, profile_workspace, case):
    attach_legacy_case(case)
    definition = first_profile_definition_for(case)
    _ensure_profile_exists_or_skip(api_client, readwrite_session, profile_workspace, definition)

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
def test_legacy_profile_get_list_cases(api_client, readwrite_session, profile_workspace, case):
    attach_legacy_case(case)
    definition = first_profile_definition_for(case)
    _ensure_profile_exists_or_skip(api_client, readwrite_session, profile_workspace, definition)

    response = api_client.request("GET", f"/profile/{definition['profiletype']}", session=readwrite_session)
    assert_api_success(response)
    assert _profile_name_is_present(response.json, definition["profilename"])


@pytest.mark.profile
@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("case", PATCH_PROFILE_CASES, ids=case_id)
def test_legacy_profile_patch_cases(api_client, readwrite_session, profile_workspace, case):
    attach_legacy_case(case)
    definition = first_profile_definition_for(case)
    if "patch_profile_info" not in definition:
        pytest.skip(f"{definition['_config_ref']} has no patch_profile_info")
    _ensure_profile_exists_or_skip(api_client, readwrite_session, profile_workspace, definition)

    _ensure_profile_dependencies(api_client, readwrite_session, profile_workspace, definition["patch_profile_info"])
    response = _patch_profile(api_client, readwrite_session, definition, definition["patch_profile_info"])
    assert_api_success(response)

    get_response = _get_profile(api_client, readwrite_session, definition)
    assert_api_success(get_response)


@pytest.mark.profile
@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("case", DELETE_PROFILE_CASES, ids=case_id)
def test_legacy_profile_delete_cases(api_client, readwrite_session, profile_workspace, case):
    attach_legacy_case(case)
    definitions = _definitions_delete_order(profile_definitions_for(case))
    assert definitions, f"No profile data converted for {case['legacy_name']}"

    for definition in definitions:
        _ensure_profile_exists_or_skip(api_client, readwrite_session, profile_workspace, definition)
        _ensure_profile_deleted(api_client, readwrite_session, definition)
        profile_workspace.discard(definition)
        get_response = _get_profile(api_client, readwrite_session, definition)
        assert_api_failure(get_response, accepted_messages=("does not exist", "no data", "not found", "invalid parameter"))


@pytest.mark.profile
@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("case", POST_INVALID_PROFILE_CASES, ids=case_id)
def test_legacy_profile_post_invalid_param_cases(api_client, readwrite_session, profile_workspace, case):
    attach_legacy_case(case)
    definition = first_profile_definition_for(case)
    invalid_params = definition.get("invalid_params_to_test") or []
    if not invalid_params:
        pytest.skip(f"{definition['_config_ref']} has no invalid_params_to_test")

    _ensure_profile_deleted(api_client, readwrite_session, definition)

    for invalid_param in invalid_params:
        payload = copy.deepcopy(definition.get("post_profile_info", {}))
        _ensure_profile_dependencies(api_client, readwrite_session, profile_workspace, payload)
        _apply_invalid_values(payload, invalid_param)
        response = _post_profile(api_client, readwrite_session, definition, payload)
        _assert_invalid_response(response, invalid_param)


@pytest.mark.profile
@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("case", PATCH_INVALID_PROFILE_CASES, ids=case_id)
def test_legacy_profile_patch_invalid_param_cases(api_client, readwrite_session, profile_workspace, case):
    attach_legacy_case(case)
    definition = first_profile_definition_for(case)
    invalid_params = definition.get("invalid_params_to_test") or []
    if not invalid_params:
        pytest.skip(f"{definition['_config_ref']} has no invalid_params_to_test")
    if "patch_profile_info" not in definition:
        pytest.skip(f"{definition['_config_ref']} has no patch_profile_info")

    _ensure_profile_exists_or_skip(api_client, readwrite_session, profile_workspace, definition)

    for invalid_param in invalid_params:
        payload = copy.deepcopy(definition["patch_profile_info"])
        _ensure_profile_dependencies(api_client, readwrite_session, profile_workspace, payload)
        _apply_invalid_values(payload, invalid_param)
        response = _patch_profile(api_client, readwrite_session, definition, payload)
        _assert_invalid_response(response, invalid_param)


def _profile_path(definition):
    return f"/profile/{definition['profiletype']}/{definition['profilename']}"


def _profile_key(definition):
    return definition["profiletype"], definition["profilename"]


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


def _definitions_create_order(definitions):
    local_by_name = {definition["profilename"]: definition for definition in definitions}
    ordered = []
    seen = set()

    def visit(definition):
        key = _profile_key(definition)
        if key in seen:
            return
        seen.add(key)
        for dependency_name in sorted(_profile_refs(definition.get("post_profile_info", {}))):
            dependency = local_by_name.get(dependency_name)
            if dependency is not None:
                visit(dependency)
        ordered.append(definition)

    for definition in sorted(
        definitions,
        key=lambda item: (
            _profile_definition_depth(item),
            _profile_type_rank(item),
            item.get("_config_ref", ""),
        ),
    ):
        visit(definition)
    return ordered


def _definitions_delete_order(definitions):
    return list(reversed(_definitions_create_order(definitions)))


def _ensure_profile_deleted(api_client, session_id, definition, seen=None):
    seen = seen or set()
    key = _profile_key(definition)
    if key in seen:
        return
    seen.add(key)

    for dependent in _profile_dependents(definition):
        _ensure_profile_deleted(api_client, session_id, dependent, seen)

    existing = _get_profile(api_client, session_id, definition)
    if existing.retstatus == "Success":
        delete = _delete_profile(api_client, session_id, definition)
        if delete.retstatus == "Fail" and "used by other Profile" in delete.retresult:
            pytest.skip(
                f"Profile {definition['profiletype']}/{definition['profilename']} "
                "is used by another profile and cannot be deleted safely."
            )
        assert_api_success(delete)


def _ensure_profile_exists_or_skip(api_client, session_id, profile_workspace, definition):
    existing = _get_profile(api_client, session_id, definition)
    if existing.retstatus == "Success":
        return

    _ensure_profile_dependencies(api_client, session_id, profile_workspace, definition.get("post_profile_info", {}))
    create = _post_profile(api_client, session_id, definition)
    if create.retstatus != "Success":
        pytest.skip(
            f"Cannot create prerequisite profile {definition['_config_ref']} "
            f"({definition['profiletype']}/{definition['profilename']}): {format_response_summary(create)}"
        )
    profile_workspace.add(definition)


def _ensure_profile_dependencies(api_client, session_id, profile_workspace, payload, seen=None):
    seen = seen or set()
    dependency_names = sorted(_profile_refs(payload), key=_profile_name_depth)
    for dependency_name in dependency_names:
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
            profile_workspace,
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
                f"({dependency['profiletype']}/{dependency['profilename']}): {format_response_summary(created)}"
            )
        profile_workspace.add(dependency)


def _profile_name_depth(profilename):
    dependency = profile_definition_by_name(profilename)
    if dependency is None:
        return 0
    return _profile_definition_depth(dependency)


def _profile_dependents(definition):
    profilename = definition["profilename"]
    dependents = []
    for ref, data in legacy_profile_data().items():
        if data.get("profilename") == profilename:
            continue
        if profilename not in _profile_refs(data.get("post_profile_info", {})):
            continue
        if "profiletype" not in data or "profilename" not in data:
            continue
        item = copy.deepcopy(data)
        item["_config_ref"] = ref
        dependents.append(item)
    return _definitions_delete_order(dependents)


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
    assert response.retstatus == "Fail", f"Expected invalid parameter failure, got {format_response_summary(response)}"
    expected_error = invalid_param.get("expected_error")
    if expected_error:
        assert expected_error in response.retresult, (
            f"Expected error {expected_error!r} in response, got {format_response_summary(response)}"
        )
