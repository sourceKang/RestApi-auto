from __future__ import annotations

import copy

import pytest

from cases.case_catalog import (
    catalog_profile_data,
    profile_definition_by_name,
    profile_cases_for_operation,
    profile_definitions_for,
    profile_invalid_cases_for_operation,
)
from utils.assertions import assert_api_failure, assert_api_success
from utils.case_metadata import attach_case_metadata
from utils.diagnostics import format_response_summary
from utils.json_match import content_as_dict


ISOLATED_PROFILE_NAMES = {
    ("GETemplateProfile", "#RestApi_getemp_ge1"): "#RestApi_getemp_ge1_case",
}

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


POST_PROFILE_CASES = None
GET_PROFILE_CASES = None
PATCH_PROFILE_CASES = None
GET_PROFILE_LIST_CASES = None
DELETE_PROFILE_CASES = None
POST_INVALID_PROFILE_CASES = None
PATCH_INVALID_PROFILE_CASES = None


class ProfileWorkspace:
    def __init__(self, profile_service, session_id: str) -> None:
        self.profile_service = profile_service
        self.session_id = session_id
        self._created = {}

    def add(self, definition) -> None:
        self._created[profile_key(definition)] = copy.deepcopy(definition)

    def discard(self, definition) -> None:
        self._created.pop(profile_key(definition), None)

    def cleanup(self) -> None:
        for definition in definitions_delete_order(list(self._created.values())):
            self.profile_service.delete_profile(definition, self.session_id)
        self._created.clear()


class ProfileService:
    def __init__(self, api_client) -> None:
        self.api_client = api_client

    def verify_post_case(self, session_id: str, workspace: ProfileWorkspace, case) -> None:
        attach_case_metadata(case)
        definitions = definitions_create_order(isolated_profile_definitions(profile_definitions_for(case)))
        assert definitions, f"No profile data converted for {case['name']}"

        for definition in definitions_delete_order(definitions):
            self.ensure_profile_deleted(session_id, definition)

        for definition in definitions:
            self.ensure_profile_dependencies(session_id, workspace, definition.get("post_profile_info", {}))
            response = self.post_profile(session_id, definition)
            assert_api_success(response)
            workspace.add(definition)

    def verify_get_case(self, session_id: str, workspace: ProfileWorkspace, case) -> None:
        attach_case_metadata(case)
        definition = first_isolated_profile_definition_for(case)
        self.ensure_profile_exists_or_skip(session_id, workspace, definition)

        response = self.get_profile(session_id, definition)
        assert_api_success(response)
        retval = response.json.get("retval", {})
        assert retval.get("Name") == definition["profilename"]

        if case.get("validation_refs"):
            content = content_as_dict(retval.get("Content", {}))
            for key, value in definition.get("post_profile_info", {}).items():
                if key in content:
                    assert content[key] == value, (
                        f"Profile content mismatch for {definition['profiletype']}/{definition['profilename']} "
                        f"field {key!r}: expected {value!r}, got {content[key]!r}"
                    )

    def verify_get_list_case(self, session_id: str, workspace: ProfileWorkspace, case) -> None:
        attach_case_metadata(case)
        definition = first_isolated_profile_definition_for(case)
        self.ensure_profile_exists_or_skip(session_id, workspace, definition)

        response = self.api_client.request("GET", f"/profile/{definition['profiletype']}", session=session_id)
        assert_api_success(response)
        assert profile_name_is_present(response.json, definition["profilename"])

    def verify_patch_case(self, session_id: str, workspace: ProfileWorkspace, case) -> None:
        attach_case_metadata(case)
        definition = first_isolated_profile_definition_for(case)
        if "patch_profile_info" not in definition:
            pytest.skip(f"{definition['_config_ref']} has no patch_profile_info")
        self.ensure_profile_exists_or_skip(session_id, workspace, definition)

        self.ensure_profile_dependencies(session_id, workspace, definition["patch_profile_info"])
        response = self.patch_profile(session_id, definition, definition["patch_profile_info"])
        assert_api_success(response)

        get_response = self.get_profile(session_id, definition)
        assert_api_success(get_response)

    def verify_delete_case(self, session_id: str, workspace: ProfileWorkspace, case) -> None:
        attach_case_metadata(case)
        definitions = definitions_delete_order(isolated_profile_definitions(profile_definitions_for(case)))
        assert definitions, f"No profile data converted for {case['name']}"

        for definition in definitions:
            self.ensure_profile_exists_or_skip(session_id, workspace, definition)
            self.ensure_profile_deleted(session_id, definition)
            workspace.discard(definition)
            get_response = self.get_profile(session_id, definition)
            assert_api_failure(get_response, accepted_messages=("does not exist", "no data", "not found", "invalid parameter"))

    def verify_post_invalid_param_case(self, session_id: str, workspace: ProfileWorkspace, case) -> None:
        attach_case_metadata(case)
        definition = first_isolated_profile_definition_for(case)
        invalid_params = definition.get("invalid_params_to_test") or []
        if not invalid_params:
            pytest.skip(f"{definition['_config_ref']} has no invalid_params_to_test")

        self.ensure_profile_deleted(session_id, definition)

        for invalid_param in invalid_params:
            payload = copy.deepcopy(definition.get("post_profile_info", {}))
            self.ensure_profile_dependencies(session_id, workspace, payload)
            apply_invalid_values(payload, invalid_param)
            response = self.post_profile(session_id, definition, payload)
            assert_invalid_response(response, invalid_param)

    def verify_patch_invalid_param_case(self, session_id: str, workspace: ProfileWorkspace, case) -> None:
        attach_case_metadata(case)
        definition = first_isolated_profile_definition_for(case)
        invalid_params = definition.get("invalid_params_to_test") or []
        if not invalid_params:
            pytest.skip(f"{definition['_config_ref']} has no invalid_params_to_test")
        if "patch_profile_info" not in definition:
            pytest.skip(f"{definition['_config_ref']} has no patch_profile_info")

        self.ensure_profile_exists_or_skip(session_id, workspace, definition)

        for invalid_param in invalid_params:
            payload = copy.deepcopy(definition["patch_profile_info"])
            self.ensure_profile_dependencies(session_id, workspace, payload)
            apply_invalid_values(payload, invalid_param)
            response = self.patch_profile(session_id, definition, payload)
            assert_invalid_response(response, invalid_param)

    def get_profile(self, session_id: str, definition):
        return self.api_client.request("GET", profile_path(definition), session=session_id)

    def post_profile(self, session_id: str, definition, content=None):
        return self.api_client.request(
            "POST",
            profile_path(definition),
            session=session_id,
            json={"Content": content if content is not None else definition.get("post_profile_info", {})},
        )

    def patch_profile(self, session_id: str, definition, content):
        return self.api_client.request("PATCH", profile_path(definition), session=session_id, json={"Content": content})

    def delete_profile(self, definition, session_id: str):
        return self.api_client.request("DELETE", profile_path(definition), session=session_id)

    def ensure_profile_deleted(self, session_id: str, definition, seen=None) -> None:
        seen = seen or set()
        key = profile_key(definition)
        if key in seen:
            return
        seen.add(key)

        for dependent in profile_dependents(definition):
            self.ensure_profile_deleted(session_id, dependent, seen)

        existing = self.get_profile(session_id, definition)
        if existing.retstatus == "Success":
            delete = self.delete_profile(definition, session_id)
            if delete.retstatus == "Fail" and "used by other Profile" in delete.retresult:
                pytest.skip(
                    f"Profile {definition['profiletype']}/{definition['profilename']} "
                    "is used by another profile and cannot be deleted safely."
                )
            assert_api_success(delete)

    def ensure_profile_exists_or_skip(self, session_id: str, workspace: ProfileWorkspace, definition) -> None:
        existing = self.get_profile(session_id, definition)
        if existing.retstatus == "Success":
            return

        self.ensure_profile_dependencies(session_id, workspace, definition.get("post_profile_info", {}))
        create = self.post_profile(session_id, definition)
        if create.retstatus != "Success":
            pytest.skip(
                f"Cannot create prerequisite profile {definition['_config_ref']} "
                f"({definition['profiletype']}/{definition['profilename']}): {format_response_summary(create)}"
            )
        workspace.add(definition)

    def ensure_profile_dependencies(self, session_id: str, workspace: ProfileWorkspace, payload, seen=None) -> None:
        seen = seen or set()
        dependency_names = sorted(profile_refs(payload), key=profile_name_depth)
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
            self.ensure_profile_dependencies(session_id, workspace, dependency.get("post_profile_info", {}), seen)
            existing = self.get_profile(session_id, dependency)
            if existing.retstatus == "Success":
                continue
            created = self.post_profile(session_id, dependency)
            if created.retstatus != "Success":
                pytest.skip(
                    f"Cannot create dependency profile {dependency['_config_ref']} "
                    f"({dependency['profiletype']}/{dependency['profilename']}): {format_response_summary(created)}"
                )
            workspace.add(dependency)


def profile_refs(value):
    refs = set()
    if isinstance(value, dict):
        for item in value.values():
            refs.update(profile_refs(item))
    elif isinstance(value, list):
        for item in value:
            refs.update(profile_refs(item))
    elif isinstance(value, str) and value.startswith("#RestApi"):
        refs.add(value)
    return refs


def isolated_profile_definitions(definitions):
    return [isolated_profile_definition(definition) for definition in definitions]


def first_isolated_profile_definition_for(case):
    definitions = isolated_profile_definitions(profile_definitions_for(case))
    if not definitions:
        raise KeyError(f"No profile data found for {case['name']}")
    return definitions[0]


def isolated_profile_definition(definition):
    isolated = copy.deepcopy(definition)
    replacement_name = ISOLATED_PROFILE_NAMES.get(profile_key(isolated))
    if not replacement_name:
        return isolated

    original_name = isolated["profilename"]
    isolated = replace_exact_string(isolated, original_name, replacement_name)
    isolated["profilename"] = replacement_name
    isolated["_isolated_from_profilename"] = original_name
    return isolated


def replace_exact_string(value, old: str, new: str):
    if isinstance(value, dict):
        return {key: replace_exact_string(item, old, new) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_exact_string(item, old, new) for item in value]
    if value == old:
        return new
    return value


def sort_profile_cases_for_create(cases):
    return sorted(
        cases,
        key=lambda case: (
            case_dependency_depth(case),
            case_profile_rank(case),
            case.get("source_line") or 0,
        ),
    )


def sort_profile_cases_for_delete(cases):
    return list(reversed(sort_profile_cases_for_create(cases)))


def case_dependency_depth(case):
    definitions = profile_definitions_for(case)
    if not definitions:
        return 0
    return max(profile_definition_depth(definition) for definition in definitions)


def case_profile_rank(case):
    definitions = profile_definitions_for(case)
    if not definitions:
        return 0
    return max(profile_type_rank(definition) for definition in definitions)


def profile_type_rank(definition):
    return PROFILE_TYPE_CREATE_RANK.get(definition["profiletype"], 50)


def profile_definition_depth(definition, seen=None):
    seen = seen or set()
    key = (definition["profiletype"], definition["profilename"])
    if key in seen:
        return 0
    seen.add(key)

    depth = 0
    for dependency_name in profile_refs(definition.get("post_profile_info", {})):
        dependency = profile_definition_by_name(dependency_name)
        if dependency is None:
            continue
        depth = max(depth, 1 + profile_definition_depth(dependency, seen.copy()))
    return depth


def profile_path(definition):
    return f"/profile/{definition['profiletype']}/{definition['profilename']}"


def profile_key(definition):
    return definition["profiletype"], definition["profilename"]


def definitions_create_order(definitions):
    local_by_name = {definition["profilename"]: definition for definition in definitions}
    ordered = []
    seen = set()

    def visit(definition):
        key = profile_key(definition)
        if key in seen:
            return
        seen.add(key)
        for dependency_name in sorted(profile_refs(definition.get("post_profile_info", {}))):
            dependency = local_by_name.get(dependency_name)
            if dependency is not None:
                visit(dependency)
        ordered.append(definition)

    for definition in sorted(
        definitions,
        key=lambda item: (
            profile_definition_depth(item),
            profile_type_rank(item),
            item.get("_config_ref", ""),
        ),
    ):
        visit(definition)
    return ordered


def definitions_delete_order(definitions):
    return list(reversed(definitions_create_order(definitions)))


def profile_name_depth(profilename):
    dependency = profile_definition_by_name(profilename)
    if dependency is None:
        return 0
    return profile_definition_depth(dependency)


def profile_dependents(definition):
    profilename = definition["profilename"]
    dependents = []
    for ref, data in catalog_profile_data().items():
        if data.get("profilename") == profilename:
            continue
        if profilename not in profile_refs(data.get("post_profile_info", {})):
            continue
        if "profiletype" not in data or "profilename" not in data:
            continue
        item = copy.deepcopy(data)
        item["_config_ref"] = ref
        dependents.append(item)
    return definitions_delete_order(dependents)


def profile_name_is_present(payload, profilename):
    if isinstance(payload, dict):
        if payload.get("Name") == profilename:
            return True
        return any(profile_name_is_present(value, profilename) for value in payload.values())
    if isinstance(payload, list):
        return any(profile_name_is_present(item, profilename) for item in payload)
    return False


def apply_invalid_values(payload, invalid_param):
    for key, value in invalid_param.items():
        if key == "expected_error":
            continue
        payload[key] = value


def assert_invalid_response(response, invalid_param):
    assert response.retstatus == "Fail", f"Expected invalid parameter failure, got {format_response_summary(response)}"
    expected_error = invalid_param.get("expected_error")
    if expected_error:
        assert expected_error in response.retresult, (
            f"Expected error {expected_error!r} in response, got {format_response_summary(response)}"
        )


POST_PROFILE_CASES = sort_profile_cases_for_create(profile_cases_for_operation("post"))
GET_PROFILE_CASES = sort_profile_cases_for_create(profile_cases_for_operation("get"))
PATCH_PROFILE_CASES = sort_profile_cases_for_create(profile_cases_for_operation("patch"))
GET_PROFILE_LIST_CASES = sort_profile_cases_for_create(profile_cases_for_operation("get_profiles"))
DELETE_PROFILE_CASES = sort_profile_cases_for_delete(profile_cases_for_operation("delete"))
POST_INVALID_PROFILE_CASES = profile_invalid_cases_for_operation("post")
PATCH_INVALID_PROFILE_CASES = profile_invalid_cases_for_operation("patch")
