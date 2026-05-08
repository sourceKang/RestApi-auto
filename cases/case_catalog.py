from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any


CASE_CATALOG_FILE = Path(__file__).with_name("case_catalog.json")


@lru_cache(maxsize=1)
def case_catalog_payload() -> dict[str, Any]:
    return json.loads(CASE_CATALOG_FILE.read_text(encoding="utf-8-sig"))


def catalog_test_cases() -> list[dict[str, Any]]:
    return case_catalog_payload()["test_cases"]


def catalog_profile_data() -> dict[str, dict[str, Any]]:
    return case_catalog_payload()["profile_data"]


def catalog_case_by_name(name: str) -> dict[str, Any]:
    for case in catalog_test_cases():
        if case["name"] == name:
            return case
    raise KeyError(f"Unknown test case: {name}")


def profile_cases_for_operation(operation: str) -> list[dict[str, Any]]:
    if operation == "get_profiles":
        prefixes = ("test_get_profiles_by_",)
    elif operation == "delete":
        prefixes = ("test_delete_profile_by_", "test_delete_profiles_by_")
    else:
        prefixes = (f"test_{operation}_profile_by_",)
    suffix = "_invalid_params"
    cases: list[dict[str, Any]] = []
    for case in catalog_test_cases():
        name = case["name"]
        if not case["markers"] or "profile" not in case["markers"]:
            continue
        if not name.startswith(prefixes):
            continue
        if operation in {"post", "patch"} and name.endswith(suffix):
            continue
        cases.append(case)
    return cases


def profile_invalid_cases_for_operation(operation: str) -> list[dict[str, Any]]:
    prefix = f"test_{operation}_profile_by_"
    cases: list[dict[str, Any]] = []
    for case in catalog_test_cases():
        name = case["name"]
        if "profile" in case["markers"] and name.startswith(prefix) and name.endswith("_invalid_params"):
            cases.append(case)
    return cases


def profile_definitions_for(case: dict[str, Any]) -> list[dict[str, Any]]:
    profile_data = catalog_profile_data()
    definitions: list[dict[str, Any]] = []
    for ref in case["config_data_refs"]:
        data = profile_data.get(ref)
        if data and "profiletype" in data and "profilename" in data:
            item = copy.deepcopy(data)
            item["_config_ref"] = ref
            definitions.append(item)
    return definitions


def profile_definition_by_name(profilename: str) -> dict[str, Any] | None:
    for ref, data in catalog_profile_data().items():
        if data.get("profilename") == profilename:
            item = copy.deepcopy(data)
            item["_config_ref"] = ref
            return item
    return None


def first_profile_definition_for(case: dict[str, Any]) -> dict[str, Any]:
    definitions = profile_definitions_for(case)
    if not definitions:
        raise KeyError(f"No profile data found for {case['name']}")
    return definitions[0]


def case_id(case: dict[str, Any]) -> str:
    ids = case.get("case_ids") or []
    return ids[0] if ids else case["name"]
