from __future__ import annotations

import os
from pathlib import Path

import pytest

from cases.openapi_contract import (
    build_openapi_contract,
    build_openapi_yaml_document,
    configured_openapi_yaml_file,
    diff_contracts,
    format_contract_differences,
    load_baseline_contract,
    load_baseline_yaml_document,
    load_openapi_document,
    normalize_ems_version,
    openapi_version_dir_name,
)
from config_loader.settings import DEFAULT_EMS_FILE
from config_loader.simple_yaml import load_simple_yaml
from utils.allure_helpers import attach_json, attach_text, allure_step
from utils.case_metadata import attach_case_id


@pytest.mark.openapi
@pytest.mark.smoke
def test_openapi_yaml_contract_matches_baseline():
    attach_case_id("EMS1-7116", "YAML File")

    with allure_step("1. Read configured EMS version from YAML"):
        ems_file = Path(os.environ.get("EMS_YAML_FILE", DEFAULT_EMS_FILE))
        try:
            configured_version = _configured_ems_version()
        except Exception as error:
            _attach_failed_check(
                "OpenAPI configured EMS version result",
                error,
                ems_file=str(ems_file),
            )
            raise
        _attach_check_result(
            "OpenAPI configured EMS version result",
            {
                "status": "passed",
                "ems_file": str(ems_file),
                "configured_version": configured_version,
                "normalized_version": normalize_ems_version(configured_version),
            },
        )

    with allure_step("2. Locate OpenAPI YAML file"):
        try:
            openapi_file = configured_openapi_yaml_file(configured_version)
        except Exception as error:
            _attach_failed_check(
                "OpenAPI YAML location result",
                error,
                configured_version=configured_version,
                normalized_version=normalize_ems_version(configured_version),
            )
            raise
        exists = openapi_file.exists()
        _attach_check_result(
            "OpenAPI YAML location result",
            {
                "status": "passed" if exists else "failed",
                "openapi_file": str(openapi_file),
                "exists": exists,
            },
        )
        assert exists, (
            f"OpenAPI YAML file does not exist: {openapi_file}. "
            "Set EMS_OPENAPI_YAML_FILE to override the default path."
        )

    with allure_step("3. Parse OpenAPI YAML document"):
        try:
            document = load_openapi_document(openapi_file)
        except Exception as error:
            _attach_failed_check(
                "OpenAPI YAML parse result",
                error,
                openapi_file=str(openapi_file),
                exists=openapi_file.exists(),
            )
            raise
        _attach_check_result(
            "OpenAPI YAML parse result",
            {
                "status": "passed",
                "openapi_file": str(openapi_file),
                "root_type": type(document).__name__,
                "path_count": len(document.get("paths", {})) if isinstance(document.get("paths"), dict) else None,
                "schema_count": len(document.get("components", {}).get("schemas", {}))
                if isinstance(document.get("components"), dict)
                and isinstance(document.get("components", {}).get("schemas"), dict)
                else None,
            },
        )

    with allure_step("4. Verify OpenAPI version matches EMS config"):
        info = document.get("info", {})
        actual_info_version = info.get("version", "") if isinstance(info, dict) else ""
        expected_version = normalize_ems_version(configured_version)
        actual_version = normalize_ems_version(actual_info_version)
        _attach_check_result(
            "OpenAPI version check result",
            {
                "status": "passed" if actual_version == expected_version else "failed",
                "openapi_file": str(openapi_file),
                "raw_openapi_info_version": actual_info_version,
                "actual_version": actual_version,
                "expected_version": expected_version,
            },
        )
        assert actual_version == expected_version, (
            f"{openapi_file} info.version {actual_version!r} does not match "
            f"configured EMS version {expected_version!r}"
        )

    with allure_step("5. Compare OpenAPI contract with baseline"):
        try:
            expected_contract = load_baseline_contract()
            actual_contract = build_openapi_contract(document)
        except Exception as error:
            _attach_failed_check(
                "OpenAPI contract comparison result",
                error,
                openapi_file=str(openapi_file),
            )
            raise
        differences = diff_contracts(expected_contract, actual_contract)
        _attach_check_result(
            "OpenAPI contract comparison result",
            {
                "status": "passed" if not differences else "failed",
                "openapi_file": str(openapi_file),
                "difference_count": len(differences),
                "differences": differences,
            },
        )
        assert not differences, (
            f"{openapi_file} OpenAPI contract differs from baseline:\n"
            f"{format_contract_differences(differences)}"
        )

    with allure_step("6. Compare full OpenAPI YAML document with baseline"):
        try:
            expected_document = load_baseline_yaml_document()
            actual_document = build_openapi_yaml_document(document)
        except Exception as error:
            _attach_failed_check(
                "Full OpenAPI YAML comparison result",
                error,
                openapi_file=str(openapi_file),
            )
            raise
        yaml_differences = diff_contracts(expected_document, actual_document)
        _attach_check_result(
            "Full OpenAPI YAML comparison result",
            {
                "status": "passed" if not yaml_differences else "failed",
                "openapi_file": str(openapi_file),
                "document_summary": _document_summary(actual_document),
                "difference_count": len(yaml_differences),
                "differences": yaml_differences,
            },
        )
        assert not yaml_differences, (
            f"{openapi_file} full OpenAPI YAML document differs from baseline:\n"
            f"{format_contract_differences(yaml_differences)}"
        )


def _configured_ems_version() -> str:
    ems_file = Path(os.environ.get("EMS_YAML_FILE", DEFAULT_EMS_FILE))
    raw = load_simple_yaml(ems_file)
    ems = raw.get("ems", {}) if isinstance(raw, dict) else {}
    return str(ems.get("version", ""))


def _attach_failed_check(name: str, error: Exception, **context: object) -> None:
    _attach_check_result(
        name,
        _check_result(
            status="failed",
            error_type=type(error).__name__,
            error=str(error),
            **context,
        ),
    )


def _check_result(**values: object) -> dict[str, object]:
    return values


def _attach_check_result(name: str, result: dict[str, object]) -> None:
    attach_text(f"{name} summary", _format_check_result(result))
    attach_json(name, result)


def _format_check_result(result: dict[str, object]) -> str:
    lines: list[str] = []
    status = str(result.get("status", "unknown")).upper()
    lines.append(f"Status: {status}")
    lines.append("")

    for key, value in result.items():
        if key in {"status", "differences"}:
            continue
        if isinstance(value, dict):
            lines.append(f"{key}:")
            for nested_key, nested_value in value.items():
                lines.append(f"  - {nested_key}: {nested_value}")
            continue
        lines.append(f"{key}: {value}")

    differences = result.get("differences")
    if isinstance(differences, list):
        lines.append("")
        lines.append(f"Differences shown: {min(len(differences), 20)} of {len(differences)}")
        if differences:
            for difference in differences[:20]:
                lines.append(f"  - {difference}")
            if len(differences) > 20:
                lines.append(f"  - ... {len(differences) - 20} more differences in JSON attachment")
        else:
            lines.append("  - none")

    return "\n".join(lines)


def _document_summary(value: object) -> dict[str, int]:
    summary = {"dict_count": 0, "list_count": 0, "key_count": 0, "scalar_count": 0}
    _count_document_nodes(value, summary)
    return summary


def _count_document_nodes(value: object, summary: dict[str, int]) -> None:
    if isinstance(value, dict):
        summary["dict_count"] += 1
        summary["key_count"] += len(value)
        for item in value.values():
            _count_document_nodes(item, summary)
        return
    if isinstance(value, list):
        summary["list_count"] += 1
        for item in value:
            _count_document_nodes(item, summary)
        return
    summary["scalar_count"] += 1


def test_openapi_version_dir_name_uses_ems_release_folder():
    assert openapi_version_dir_name("03.00.11 (AAVV.221) b2") == "03.00.11 (AAVV.221)"
