from __future__ import annotations

import copy
import re
import secrets
import time
from dataclasses import dataclass

import pytest

from cases.case_catalog import (
    catalog_profile_data,
    profile_definition_by_name,
    profile_cases_for_operation,
    profile_definitions_for,
    profile_invalid_cases_for_operation,
)
from utils.assertions import assert_api_failure, assert_api_success
from utils.allure_helpers import attach_json
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

TEMPORARY_PROFILE_NAME_MAX_LENGTH = 31


@dataclass(frozen=True)
class TemporaryProfileGraph:
    root_name: str
    definitions: tuple[dict, ...]
    names_by_source: dict[str, str]

    def name_for(self, source_name: str) -> str:
        return self.names_by_source[source_name]


class TemporaryOntTemplate(str):
    def __new__(cls, graph: TemporaryProfileGraph):
        instance = super().__new__(cls, graph.root_name)
        instance.graph = graph
        return instance

    @property
    def bandwidth_name(self) -> str:
        return self.graph.name_for("#RestApi_1G")


class TemporaryGeTemplate(str):
    def __new__(cls, graph: TemporaryProfileGraph):
        instance = super().__new__(cls, graph.root_name)
        instance.graph = graph
        return instance

    @property
    def definition(self) -> dict:
        return self.graph.definitions[-1]


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
        self._planned = {}
        self._borrowed = {}

    def plan(self, definition) -> None:
        key = profile_key(definition)
        if key not in self._created and key not in self._borrowed:
            self._planned[key] = copy.deepcopy(definition)

    def add(self, definition) -> None:
        key = profile_key(definition)
        self._created[key] = copy.deepcopy(definition)
        self._planned.pop(key, None)
        self._borrowed.pop(key, None)

    def borrow(self, definition) -> None:
        key = profile_key(definition)
        if key not in self._created:
            self._borrowed[key] = copy.deepcopy(definition)
        self._planned.pop(key, None)

    def owns(self, definition) -> bool:
        return profile_key(definition) in self._created

    def discard(self, definition) -> None:
        key = profile_key(definition)
        self._created.pop(key, None)
        self._planned.pop(key, None)
        self._borrowed.pop(key, None)

    def cleanup(self) -> None:
        owned = {**self._planned, **self._created}
        results = []
        errors = []
        for definition in definitions_delete_order(list(owned.values())):
            key = profile_key(definition)
            try:
                self.profile_service.delete_temporary_profile(
                    self.session_id,
                    definition,
                    timeout=90,
                    interval=2,
                )
            except Exception as error:
                errors.append(f"{definition['profiletype']}/{definition['profilename']}: {error}")
                results.append({"profile": key, "status": "failed", "error": str(error)})
            else:
                self._created.pop(key, None)
                self._planned.pop(key, None)
                results.append({"profile": key, "status": "removed"})
        self._borrowed.clear()
        attach_json("Profile workspace cleanup", {"results": results, "errors": errors})
        if errors:
            raise AssertionError("Profile workspace cleanup failed: " + "; ".join(errors))


class ProfileService:
    def __init__(self, api_client) -> None:
        self.api_client = api_client

    def verify_post_case(self, session_id: str, workspace: ProfileWorkspace, case) -> None:
        attach_case_metadata(case)
        definitions = definitions_create_order(isolated_profile_definitions(profile_definitions_for(case)))
        assert definitions, f"No profile data converted for {case['name']}"

        for attempt in range(2):
            for definition in definitions_delete_order(definitions):
                self.ensure_profile_deleted(session_id, definition)

            retry_after_cleanup = False
            for definition in definitions:
                self.ensure_profile_dependencies(session_id, workspace, definition.get("post_profile_info", {}))
                workspace.plan(definition)
                response = self.post_profile(session_id, definition)
                if attempt == 0 and profile_capacity_reached(response):
                    workspace.cleanup()
                    retry_after_cleanup = True
                    break
                assert_api_success(response)
                workspace.add(definition)

            if not retry_after_cleanup:
                return

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

        baseline_response = self.get_profile(session_id, definition)
        assert_api_success(baseline_response)
        baseline_content = writable_profile_content(baseline_response)
        self.ensure_profile_dependencies(session_id, workspace, definition["patch_profile_info"])
        try:
            response = self.patch_profile(session_id, definition, definition["patch_profile_info"])
            assert_api_success(response)
            self.wait_for_profile_content(session_id, definition, definition["patch_profile_info"])
        finally:
            self.restore_profile_content(session_id, definition, baseline_content)

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
            delete_missing = self.delete_profile(definition, session_id)
            assert_api_failure(
                delete_missing,
                accepted_messages=("does not exist", "no data", "not found", "invalid parameter"),
            )

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
            workspace.plan(definition)
            response = self.post_profile(session_id, definition, payload)
            validation_error = None
            try:
                assert_invalid_response(response, invalid_param)
            except AssertionError as error:
                validation_error = error

            residual = self.get_profile(session_id, definition)
            if residual.retstatus == "Success":
                workspace.add(definition)
                self.delete_temporary_profile(session_id, definition)
                workspace.discard(definition)
                raise AssertionError(
                    f"Invalid POST created residual profile "
                    f"{definition['profiletype']}/{definition['profilename']}."
                ) from validation_error
            if not profile_response_is_missing(residual):
                raise AssertionError(
                    f"Cannot verify invalid POST cleanup for "
                    f"{definition['profiletype']}/{definition['profilename']}: "
                    f"{format_response_summary(residual)}"
                ) from validation_error
            workspace.discard(definition)
            if validation_error is not None:
                raise validation_error

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
            baseline_response = self.get_profile(session_id, definition)
            assert_api_success(baseline_response)
            baseline_content = writable_profile_content(baseline_response)
            payload = copy.deepcopy(definition["patch_profile_info"])
            self.ensure_profile_dependencies(session_id, workspace, payload)
            apply_invalid_values(payload, invalid_param)
            response = self.patch_profile(session_id, definition, payload)
            validation_error = None
            try:
                assert_invalid_response(response, invalid_param)
            except AssertionError as error:
                validation_error = error

            after_response = self.get_profile(session_id, definition)
            assert_api_success(after_response)
            if writable_profile_content(after_response) != baseline_content:
                self.restore_profile_content(session_id, definition, baseline_content)
                raise AssertionError(
                    f"Invalid PATCH changed profile "
                    f"{definition['profiletype']}/{definition['profilename']}; baseline was restored."
                ) from validation_error
            if validation_error is not None:
                raise validation_error

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
            workspace.borrow(definition)
            return

        self.ensure_profile_dependencies(session_id, workspace, definition.get("post_profile_info", {}))
        workspace.plan(definition)
        create = self.post_profile(session_id, definition)
        if create.retstatus != "Success":
            pytest.skip(
                f"Cannot create prerequisite profile {definition['_config_ref']} "
                f"({definition['profiletype']}/{definition['profilename']}): {format_response_summary(create)}"
            )
        workspace.add(definition)

    def ensure_prerequisite_profile(
        self,
        session_id: str,
        profilename: str,
        workspace: ProfileWorkspace | None = None,
        seen=None,
        timeout: float = 30,
        interval: float = 1,
    ) -> None:
        definition = profile_definition_by_name(profilename)
        if definition is None:
            raise AssertionError(f"No profile definition found for prerequisite {profilename!r}.")

        seen = seen or set()
        key = profile_key(definition)
        if key in seen:
            return
        seen.add(key)

        for dependency_name in sorted(profile_refs(definition.get("post_profile_info", {})), key=profile_name_depth):
            self.ensure_prerequisite_profile(
                session_id,
                dependency_name,
                workspace=workspace,
                seen=seen,
                timeout=timeout,
                interval=interval,
            )

        existing = self.get_profile(session_id, definition)
        if existing.retstatus == "Success":
            try:
                assert_profile_matches_definition(existing, definition)
            except AssertionError as mismatch:
                if workspace is None or not is_catalog_test_profile(definition):
                    raise
                self.reconcile_test_prerequisite(
                    session_id,
                    workspace,
                    definition,
                    mismatch,
                    timeout=timeout,
                    interval=interval,
                )
            else:
                if workspace is not None:
                    workspace.borrow(definition)
            return

        if workspace is not None:
            workspace.plan(definition)
        created = self.post_profile(session_id, definition)
        if created.retstatus != "Success":
            raise AssertionError(
                f"Cannot create prerequisite profile {definition['_config_ref']} "
                f"({definition['profiletype']}/{definition['profilename']}): {format_response_summary(created)}"
            )
        if workspace is not None:
            workspace.add(definition)
        self.wait_for_prerequisite_profile(session_id, definition, timeout=timeout, interval=interval)

    def reconcile_test_prerequisite(
        self,
        session_id: str,
        workspace: ProfileWorkspace,
        definition,
        mismatch: AssertionError,
        timeout: float = 30,
        interval: float = 1,
    ) -> None:
        if workspace.owns(definition):
            expected_content = definition.get("post_profile_info", {})
            restored = self.patch_profile(session_id, definition, expected_content)
            assert_api_success(restored)
            self.wait_for_profile_content(session_id, definition, expected_content)
            return

        deleted = self.delete_profile(definition, session_id)
        if deleted.retstatus != "Success" and not profile_response_is_missing(deleted):
            raise AssertionError(
                f"Cannot safely reconcile test prerequisite "
                f"{definition['profiletype']}/{definition['profilename']}. "
                "The existing content differs from YAML and exact DELETE failed; "
                f"no dependent profiles were deleted. {format_response_summary(deleted)}"
            ) from mismatch
        self.wait_for_profile_removed(session_id, definition, timeout=timeout, interval=interval)

        workspace.plan(definition)
        created = self.post_profile(session_id, definition)
        if created.retstatus != "Success":
            raise AssertionError(
                f"Cannot recreate test prerequisite "
                f"{definition['profiletype']}/{definition['profilename']}: "
                f"{format_response_summary(created)}"
            ) from mismatch
        workspace.add(definition)
        self.wait_for_prerequisite_profile(session_id, definition, timeout=timeout, interval=interval)

    def wait_for_prerequisite_profile(
        self,
        session_id: str,
        definition,
        timeout: float = 30,
        interval: float = 1,
    ) -> None:
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() <= deadline:
            last = self.get_profile(session_id, definition)
            if last.retstatus == "Success":
                assert_profile_matches_definition(last, definition)
                return
            if interval > 0:
                time.sleep(interval)
        raise AssertionError(
            f"Prerequisite profile {definition['profiletype']}/{definition['profilename']} "
            f"did not become readable: {format_response_summary(last)}"
        )

    def wait_for_profile_content(
        self,
        session_id: str,
        definition,
        expected_content,
        timeout: float = 30,
        interval: float = 1,
        exact: bool = False,
    ):
        deadline = time.monotonic() + timeout
        last = None
        last_error = None
        while time.monotonic() <= deadline:
            last = self.get_profile(session_id, definition)
            if last.retstatus == "Success":
                actual_content = writable_profile_content(last)
                try:
                    if exact:
                        assert actual_content == expected_content, (
                            f"actual={actual_content!r}, expected={expected_content!r}"
                        )
                    else:
                        assert_expected_profile_subset(actual_content, expected_content)
                except AssertionError as error:
                    last_error = error
                else:
                    return last
            if interval > 0:
                time.sleep(interval)
        raise AssertionError(
            f"Profile {definition['profiletype']}/{definition['profilename']} content did not converge: "
            f"{last_error or format_response_summary(last)}"
        )

    def restore_profile_content(
        self,
        session_id: str,
        definition,
        baseline_content,
        timeout: float = 30,
        interval: float = 1,
    ) -> None:
        response = self.patch_profile(session_id, definition, baseline_content)
        assert_api_success(response)
        self.wait_for_profile_content(
            session_id,
            definition,
            baseline_content,
            timeout=timeout,
            interval=interval,
            exact=True,
        )

    def wait_for_profile_removed(
        self,
        session_id: str,
        definition,
        timeout: float = 30,
        interval: float = 1,
    ) -> None:
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() <= deadline:
            last = self.get_profile(session_id, definition)
            if profile_response_is_missing(last):
                return
            if interval > 0:
                time.sleep(interval)
        raise AssertionError(
            f"Profile {definition['profiletype']}/{definition['profilename']} was not removed: "
            f"{format_response_summary(last)}"
        )

    def create_temporary_profile(
        self,
        session_id: str,
        source_profilename: str,
        temporary_profilename: str,
        reference_names: dict[str, str] | None = None,
        ensure_dependencies: bool = True,
        timeout: float = 30,
        interval: float = 1,
    ):
        source = profile_definition_by_name(source_profilename)
        if source is None:
            raise AssertionError(f"No profile definition found for temporary profile source {source_profilename!r}.")

        definition = copy.deepcopy(source)
        definition["profilename"] = temporary_profilename
        definition["_config_ref"] = f"{source['_config_ref']}:temporary"
        definition["post_profile_info"] = replace_profile_refs(
            definition.get("post_profile_info", {}),
            reference_names or {},
        )
        if ensure_dependencies:
            for dependency_name in sorted(
                profile_refs(definition.get("post_profile_info", {})),
                key=profile_name_depth,
            ):
                self.ensure_prerequisite_profile(
                    session_id,
                    dependency_name,
                    timeout=timeout,
                    interval=interval,
                )

        existing = self.get_profile(session_id, definition)
        if existing.retstatus == "Success":
            raise AssertionError(
                f"Temporary profile collision: {definition['profiletype']}/{temporary_profilename} already exists."
            )
        created = self.post_profile(session_id, definition)
        if created.retstatus != "Success":
            raise AssertionError(
                f"Cannot create temporary profile {definition['profiletype']}/{temporary_profilename}: "
                f"{format_response_summary(created)}"
            )
        self.wait_for_prerequisite_profile(session_id, definition, timeout=timeout, interval=interval)
        return definition

    def create_temporary_profile_graph(
        self,
        session_id: str,
        source_profilename: str,
        ems_version: str,
        node_key: str,
        run_token: str | None = None,
        timeout: float = 30,
        interval: float = 1,
    ) -> TemporaryProfileGraph:
        source_names = profile_dependency_order(source_profilename)
        token = normalized_run_token(run_token)
        temporary_names = {
            source_name: temporary_profile_name(
                profile_definition_by_name(source_name),
                ems_version,
                node_key,
                token,
            )
            for source_name in source_names
        }
        temporary_name_set = set(temporary_names.values())
        if len(temporary_name_set) != len(temporary_names):
            raise AssertionError("Temporary profile names must be unique within one run.")
        formal_profile_names = {
            data["profilename"]
            for data in catalog_profile_data().values()
            if isinstance(data, dict) and data.get("profilename")
        }
        formal_profile_names.update(ISOLATED_PROFILE_NAMES.values())
        collisions = sorted(temporary_name_set & formal_profile_names)
        if collisions:
            raise AssertionError(f"Temporary profile names overlap formal profile cases: {collisions!r}")

        definitions = []
        try:
            for source_name in source_names:
                definitions.append(
                    self.create_temporary_profile(
                        session_id,
                        source_name,
                        temporary_names[source_name],
                        reference_names=temporary_names,
                        ensure_dependencies=False,
                        timeout=timeout,
                        interval=interval,
                    )
                )
        except Exception:
            for definition in reversed(definitions):
                self.delete_temporary_profile(
                    session_id,
                    definition,
                    timeout=timeout,
                    interval=interval,
                )
            raise
        return TemporaryProfileGraph(
            root_name=temporary_names[source_profilename],
            definitions=tuple(definitions),
            names_by_source=dict(temporary_names),
        )

    def delete_temporary_profile(
        self,
        session_id: str,
        definition,
        timeout: float = 30,
        interval: float = 1,
    ) -> None:
        existing = self.get_profile(session_id, definition)
        if profile_response_is_missing(existing):
            return
        if existing.retstatus != "Success":
            raise AssertionError(
                f"Cannot inspect temporary profile before cleanup: {format_response_summary(existing)}"
            )

        deadline = time.monotonic() + timeout
        deleted = None
        while time.monotonic() <= deadline:
            deleted = self.delete_profile(definition, session_id)
            if deleted.retstatus == "Success":
                break
            if not profile_response_is_still_referenced(deleted):
                raise AssertionError(
                    f"Cannot delete temporary profile {definition['profiletype']}/{definition['profilename']}: "
                    f"{format_response_summary(deleted)}"
                )
            if interval > 0:
                time.sleep(interval)
        else:
            raise AssertionError(
                f"Temporary profile {definition['profiletype']}/{definition['profilename']} remained referenced: "
                f"{format_response_summary(deleted)}"
            )

        last = None
        while time.monotonic() <= deadline:
            last = self.get_profile(session_id, definition)
            if profile_response_is_missing(last):
                return
            if interval > 0:
                time.sleep(interval)
        raise AssertionError(
            f"Temporary profile {definition['profiletype']}/{definition['profilename']} was not removed: "
            f"{format_response_summary(last)}"
        )
    def ensure_profile_dependencies(self, session_id: str, workspace: ProfileWorkspace, payload, seen=None) -> None:
        seen = seen or set()
        dependency_names = sorted(profile_refs(payload), key=profile_name_depth)
        for dependency_name in dependency_names:
            self.ensure_prerequisite_profile(session_id, dependency_name, workspace=workspace, seen=seen)


def writable_profile_content(response):
    retval = response.json.get("retval", {}) if isinstance(response.json, dict) else {}
    content = content_as_dict(retval.get("Content", {}))
    return {
        key: copy.deepcopy(value)
        for key, value in content.items()
        if str(key).lower() != "name"
    }


def is_catalog_test_profile(definition) -> bool:
    return bool(definition.get("_config_ref")) and str(definition.get("profilename", "")).startswith("#RestApi")


def assert_profile_matches_definition(response, definition) -> None:
    retval = response.json.get("retval", {}) if isinstance(response.json, dict) else {}
    actual_name = retval.get("Name")
    expected_name = definition["profilename"]
    if actual_name != expected_name:
        raise AssertionError(
            f"Prerequisite profile name mismatch for {definition['profiletype']}/{expected_name}: "
            f"EMS returned {actual_name!r}."
        )

    actual_content = content_as_dict(retval.get("Content", {}))
    expected_content = definition.get("post_profile_info", {})
    try:
        assert_expected_profile_subset(actual_content, expected_content)
    except AssertionError as error:
        raise AssertionError(
            f"Prerequisite profile content mismatch for {definition['profiletype']}/{expected_name}: {error}"
        ) from error


def assert_expected_profile_subset(actual, expected, path: str = "") -> None:
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path or '<root>'}: expected dict, got {type(actual).__name__}"
        for key, expected_value in expected.items():
            assert key in actual, f"{path or '<root>'}: missing key {key!r}"
            next_path = f"{path}.{key}" if path else key
            assert_expected_profile_subset(actual[key], expected_value, next_path)
        return
    if isinstance(expected, list):
        assert isinstance(actual, list), f"{path or '<root>'}: expected list, got {type(actual).__name__}"
        assert len(actual) >= len(expected), f"{path or '<root>'}: expected at least {len(expected)} item(s)"
        for index, expected_item in enumerate(expected):
            assert_expected_profile_subset(actual[index], expected_item, f"{path}[{index}]")
        return

    actual_value = str(actual).strip().lower() if isinstance(actual, bool) else str(actual).strip()
    expected_value = str(expected).strip().lower() if isinstance(expected, bool) else str(expected).strip()
    assert actual_value == expected_value, f"{path or '<root>'}: actual={actual!r}, expected={expected!r}"


def temporary_ont_template_name(ems_version: str, node_key: str, run_token: str | None = None) -> str:
    definition = {
        "profiletype": "ONTTemplateProfile",
        "profilename": "#RestApi_provision_temp_SFU",
    }
    return temporary_profile_name(definition, ems_version, node_key, normalized_run_token(run_token))


def temporary_profile_name(definition, ems_version: str, node_key: str, run_token: str) -> str:
    version_match = re.search(r"(\d+)\.(\d+)\.(\d+)", ems_version)
    build_match = re.search(r"\bb\s*(\d+)\b", ems_version, flags=re.IGNORECASE)
    if version_match is None or build_match is None:
        raise ValueError(f"Cannot derive temporary profile version tag from {ems_version!r}.")
    release_tag = "".join(str(int(part)) for part in version_match.groups())
    build_tag = f"b{int(build_match.group(1))}"
    node_digits = "".join(character for character in node_key if character.isdigit())
    if not node_digits:
        raise ValueError(f"Cannot derive temporary profile node tag from {node_key!r}.")
    component = temporary_profile_component(definition)
    name = f"#RestApi_{component}_{release_tag}{build_tag}_N{node_digits}_R{run_token}"
    if len(name) > TEMPORARY_PROFILE_NAME_MAX_LENGTH:
        raise ValueError(
            f"Temporary profile name exceeds {TEMPORARY_PROFILE_NAME_MAX_LENGTH} characters: {name!r}."
        )
    return name


def normalized_run_token(run_token: str | None = None) -> str:
    token = re.sub(r"[^A-Za-z0-9]", "", run_token or secrets.token_hex(1)).upper()[:3]
    if not token:
        raise ValueError("Temporary profile run token must contain an alphanumeric character.")
    return token


def temporary_profile_component(definition) -> str:
    profile_type = definition["profiletype"]
    source_name = definition["profilename"]
    if profile_type == "ONTTemplateProfile":
        return "ONT_SFU"
    if profile_type == "ONTBandwidthProfile":
        return "BW"
    if profile_type == "ONTSecurityProfile":
        return "SEC"
    if profile_type == "ONTUNIProfile":
        return "UNI"
    if profile_type == "ONTServiceProfile":
        suffix = re.search(r"s(\d+)$", source_name, flags=re.IGNORECASE)
        return f"SVC{suffix.group(1)}" if suffix else "SVC"
    if profile_type == "GETemplateProfile":
        return "GE"
    raise ValueError(f"No temporary profile component for {profile_type}/{source_name}.")


def profile_dependency_order(root_name: str) -> list[str]:
    ordered = []
    visiting = set()
    visited = set()

    def visit(profile_name: str) -> None:
        if profile_name in visited:
            return
        if profile_name in visiting:
            raise AssertionError(f"Profile dependency cycle found at {profile_name!r}.")
        definition = profile_definition_by_name(profile_name)
        if definition is None:
            raise AssertionError(f"No profile definition found for temporary profile source {profile_name!r}.")
        visiting.add(profile_name)
        for dependency_name in sorted(
            profile_refs(definition.get("post_profile_info", {})),
            key=profile_name_depth,
        ):
            visit(dependency_name)
        visiting.remove(profile_name)
        visited.add(profile_name)
        ordered.append(profile_name)

    visit(root_name)
    return ordered


def replace_profile_refs(value, replacements: dict[str, str]):
    if isinstance(value, dict):
        return {key: replace_profile_refs(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_profile_refs(item, replacements) for item in value]
    if isinstance(value, str):
        return replacements.get(value, value)
    return value


def profile_response_is_missing(response) -> bool:
    if response.retstatus != "Fail":
        return False
    result = response.retresult.lower()
    return any(text in result for text in ("no data", "not found", "does not exist", "is not exists"))


def profile_response_is_still_referenced(response) -> bool:
    return response.retstatus == "Fail" and "used by other profile" in response.retresult.lower()


def profile_capacity_reached(response) -> bool:
    return response.retstatus == "Fail" and "maximum number of profiles" in response.retresult.lower()


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
