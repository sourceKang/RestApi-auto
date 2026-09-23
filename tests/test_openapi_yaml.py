from __future__ import annotations

import json
import os
import ssl
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from cases.openapi_contract import (
    build_openapi_contract,
    build_openapi_yaml_document,
    configured_openapi_yaml_file,
    diff_contracts,
    diff_openapi_key_documents,
    diff_semantic_openapi_documents,
    format_contract_differences,
    load_baseline_contract,
    load_baseline_yaml_document,
    load_openapi_document,
    latest_openapi_yaml_file,
    normalize_ems_version,
    openapi_file_date,
    openapi_root,
    openapi_root_available,
    openapi_version_dir_name,
    swagger_api_docs_url,
)
from config_loader.settings import DEFAULT_EMS_FILE
from config_loader.simple_yaml import load_simple_yaml
from services.neox_config.service import NEOX_SWAGGER_DATA_FILE
from tests.support.options import option_or_full_testcases
from utils.allure_helpers import attach_json, attach_text, allure_step
from utils.case_metadata import attach_case_id


@pytest.mark.openapi
@pytest.mark.smoke
@pytest.mark.live_swagger
def test_latest_openapi_yaml_keys_match_live_swagger(request):
    attach_case_id("EMS1-7116", "YAML File")
    guard_failures: list[str] = []

    if not option_or_full_testcases(request.config, "--run-live-swagger-check"):
        pytest.skip("Latest YAML versus live Swagger key check requires --run-live-swagger-check.")

    if not openapi_root_available():
        pytest.skip(
            f"OpenAPI YAML source is not available on this machine: {openapi_root()}. "
            "The per-version OpenAPI YAML files ship with the EMS firmware and are not "
            "part of this repository. Set ems.openapi_root in the EMS YAML file, "
            "EMS_OPENAPI_ROOT, or EMS_OPENAPI_YAML_FILE."
        )

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

    with allure_step("2. Locate latest OpenAPI YAML file for configured EMS version"):
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
                "file_date": openapi_file_date(openapi_file),
            },
        )
        assert exists, (
            f"OpenAPI YAML file does not exist: {openapi_file}. "
            "Set EMS_OPENAPI_YAML_FILE to override the default path."
        )

    with allure_step("3. Parse latest OpenAPI YAML document"):
        try:
            yaml_document = load_openapi_document(openapi_file)
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
                "root_type": type(yaml_document).__name__,
                "path_count": len(yaml_document.get("paths", {})) if isinstance(yaml_document.get("paths"), dict) else None,
                "schema_count": len(yaml_document.get("components", {}).get("schemas", {}))
                if isinstance(yaml_document.get("components"), dict)
                and isinstance(yaml_document.get("components", {}).get("schemas"), dict)
                else None,
            },
        )

    with allure_step("4. Fetch latest live Swagger OpenAPI document"):
        url = request.config.getoption("--neox-swagger-api-docs-url")
        live_url = swagger_api_docs_url(url)
        try:
            live_document = fetch_openapi_document(url)
        except Exception as error:
            _attach_failed_check(
                "Live Swagger fetch result",
                error,
                openapi_json=live_url,
                openapi_file=str(openapi_file),
            )
            pytest.fail(f"Cannot fetch live Swagger OpenAPI JSON from {live_url}: {error}", pytrace=False)
        _attach_check_result(
            "Live Swagger fetch result",
            {
                "status": "passed",
                "openapi_json": live_url,
                "path_count": len(live_document.get("paths", {})) if isinstance(live_document.get("paths"), dict) else None,
                "schema_count": len(live_document.get("components", {}).get("schemas", {}))
                if isinstance(live_document.get("components"), dict)
                and isinstance(live_document.get("components", {}).get("schemas"), dict)
                else None,
            },
        )

    with allure_step("5. Verify OpenAPI version matches EMS config"):
        info = yaml_document.get("info", {})
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
        if actual_version != expected_version:
            guard_failures.append(
                f"{openapi_file} info.version {actual_version!r} does not match "
                f"configured EMS version {expected_version!r}"
            )

    with allure_step("6. Compare latest YAML keys with latest live Swagger keys"):
        differences = diff_openapi_key_documents(live_document, yaml_document)
        _attach_check_result(
            "Latest YAML versus live Swagger key contract result",
            {
                "status": "passed" if not differences else "failed",
                "openapi_file": str(openapi_file),
                "openapi_json": live_url,
                "difference_count": len(differences),
                "differences": differences,
            },
        )
        guard_failures.extend(f"swagger_key: {difference}" for difference in differences)

    with allure_step("7. Summarize latest YAML versus live Swagger result"):
        _attach_check_result(
            "OpenAPI YAML versus live Swagger summary",
            {
                "status": "passed" if not guard_failures else "failed",
                "openapi_file": str(openapi_file),
                "openapi_json": live_url,
                "failure_count": len(guard_failures),
                "failures": guard_failures,
            },
        )
        assert not guard_failures, (
            f"{openapi_file} differs from live Swagger {live_url} with {len(guard_failures)} issue(s):\n"
            f"{format_contract_differences(guard_failures, limit=120)}"
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
        if key in {"status", "differences", "failures"}:
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

    failures = result.get("failures")
    if isinstance(failures, list):
        lines.append("")
        lines.append(f"Failures shown: {min(len(failures), 20)} of {len(failures)}")
        if failures:
            for failure in failures[:20]:
                lines.append(f"  - {failure}")
            if len(failures) > 20:
                lines.append(f"  - ... {len(failures) - 20} more failures in JSON attachment")
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


def test_openapi_file_date_accepts_suffix_after_date():
    assert openapi_file_date(Path("NetAtlasEMS_OpenAPI_20260605 - test.yaml")) == 20260605


def test_openapi_root_prefers_environment_override(tmp_path, monkeypatch):
    monkeypatch.setenv("EMS_OPENAPI_ROOT", str(tmp_path))
    assert openapi_root() == tmp_path


def test_openapi_root_reads_ems_yaml_when_environment_is_unset(tmp_path, monkeypatch):
    configured_root = tmp_path / "NetAtlasEMS"
    configured_root.mkdir()
    ems_file = tmp_path / "ems.yaml"
    ems_file.write_text(
        "version: 1\n"
        "\n"
        "ems:\n"
        '  rest_api_url: "https://example.invalid/netatlasemsapi"\n'
        '  version: "03.00.11 (AAVV.221) b12"\n'
        f'  openapi_root: "{configured_root.as_posix()}"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("EMS_OPENAPI_ROOT", raising=False)
    monkeypatch.setenv("EMS_YAML_FILE", str(ems_file))
    assert openapi_root() == Path(configured_root.as_posix())
    assert openapi_root_available() is True


def test_openapi_root_available_is_false_for_missing_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("EMS_OPENAPI_YAML_FILE", raising=False)
    monkeypatch.setenv("EMS_OPENAPI_ROOT", str(tmp_path / "missing"))
    assert openapi_root_available() is False


def test_latest_openapi_yaml_file_prefers_official_name_for_same_date(tmp_path):
    official = tmp_path / "NetAtlasEMS_OpenAPI_20260605.yaml"
    test_copy = tmp_path / "NetAtlasEMS_OpenAPI_20260605 - test.yaml"
    official.write_text("openapi: 3.0.1\n", encoding="utf-8")
    test_copy.write_text("openapi: 3.0.1\n", encoding="utf-8")

    assert latest_openapi_yaml_file(tmp_path) == official


def test_semantic_openapi_diff_treats_ref_and_inline_schema_as_equivalent():
    expected = _semantic_doc_with_schema(
        {
            "Example": {"properties": {"Content": {"$ref": "#/components/schemas/ExampleContent"}}},
            "ExampleContent": {"properties": {"name": {"type": "string"}}},
        }
    )
    actual = _semantic_doc_with_schema(
        {
            "Example": {"properties": {"Content": {"properties": {"name": {"type": "string"}}, "type": "object"}}},
        }
    )

    assert diff_semantic_openapi_documents(expected, actual) == []


def test_semantic_openapi_diff_detects_field_schema_changes():
    expected = _semantic_doc_with_schema(
        {
            "Example": {
                "properties": {
                    "Content": {
                        "properties": {"mode": {"enum": ["enable", "disable"], "type": "string"}},
                        "required": ["mode"],
                        "type": "object",
                    }
                }
            }
        }
    )
    actual = _semantic_doc_with_schema(
        {
            "Example": {
                "properties": {
                    "Content": {
                        "properties": {"mode": {"enum": ["enable"], "type": "string"}},
                        "type": "object",
                    }
                }
            }
        }
    )

    differences = diff_semantic_openapi_documents(expected, actual)

    assert any("Content.mode" in difference for difference in differences)
    assert any("required" in difference for difference in differences)
    assert any("enum" in difference for difference in differences)


def test_semantic_openapi_diff_detects_path_changes():
    expected = _semantic_doc_with_schema({"Example": {"properties": {"Content": {"type": "object"}}}})
    actual = _semantic_doc_with_schema(
        {"Example": {"properties": {"Content": {"type": "object"}}}},
        path="/example/{ide}",
    )

    differences = diff_semantic_openapi_documents(expected, actual)

    assert "$.paths./example/{id}" in "\n".join(differences)
    assert "$.paths./example/{ide}" in "\n".join(differences)


def test_openapi_key_diff_ignores_schema_value_changes():
    expected = _semantic_doc_with_schema(
        {
            "Example": {
                "properties": {
                    "Content": {
                        "properties": {"mode": {"enum": ["enable", "disable"], "type": "string"}},
                        "required": ["mode"],
                        "type": "object",
                    }
                }
            }
        }
    )
    actual = _semantic_doc_with_schema(
        {
            "Example": {
                "properties": {
                    "Content": {
                        "properties": {"mode": {"enum": ["enable"], "type": "integer"}},
                        "type": "object",
                    }
                }
            }
        }
    )

    assert diff_openapi_key_documents(expected, actual) == []


def test_openapi_key_diff_detects_field_key_changes():
    expected = _semantic_doc_with_schema(
        {
            "Example": {
                "properties": {
                    "Content": {
                        "properties": {"mode": {"type": "string"}},
                        "type": "object",
                    }
                }
            }
        }
    )
    actual = _semantic_doc_with_schema(
        {
            "Example": {
                "properties": {
                    "Content": {
                        "properties": {"mode_name": {"type": "string"}},
                        "type": "object",
                    }
                }
            }
        }
    )

    differences = diff_openapi_key_documents(expected, actual)

    assert "$.schemas.Example.leaf_keys.Content.mode was removed" in differences
    assert "$.schemas.Example.leaf_keys.Content.mode_name was added" in differences


def _semantic_doc_with_schema(schemas: dict[str, Any], path: str = "/example/{id}") -> dict[str, Any]:
    return {
        "components": {"schemas": schemas},
        "paths": {
            path: {
                "post": {
                    "parameters": [
                        {"in": "path", "name": "id", "required": True, "schema": {"type": "string"}},
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Example"}},
                        },
                        "required": True,
                    },
                    "responses": {},
                },
            },
        },
    }


@pytest.mark.openapi
def test_neox_swagger_nni_summary_matches_openapi_baseline():
    reference = load_openapi_document(NEOX_SWAGGER_DATA_FILE)
    baseline_schema = openapi_content_schema(load_baseline_yaml_document(), "NniPortInfo")
    summary = reference["schemas"]["NniPortInfoContent"]

    assert summary["field_count"] == len(baseline_schema)
    assert set(summary["fields"]).issubset(baseline_schema)


@pytest.mark.openapi
@pytest.mark.live_swagger
def test_live_neox_swagger_nni_schema_matches_baseline(request):
    if not option_or_full_testcases(request.config, "--run-live-swagger-check"):
        pytest.skip("Live Swagger checks require --run-live-swagger-check.")

    url = request.config.getoption("--neox-swagger-api-docs-url")
    live_schema = openapi_content_schema(fetch_openapi_document(url), "NniPortInfo")
    baseline_schema = openapi_content_schema(load_baseline_yaml_document(), "NniPortInfo")

    assert live_schema == baseline_schema


@pytest.mark.openapi
@pytest.mark.live_swagger
def test_live_swagger_openapi_document_is_available(request):
    attach_case_id("EMS1-7210", "Live Swagger OpenAPI document availability")
    if not option_or_full_testcases(request.config, "--run-live-swagger-check"):
        pytest.skip("Live Swagger checks require --run-live-swagger-check.")

    url = request.config.getoption("--neox-swagger-api-docs-url")
    live_url = swagger_api_docs_url(url)
    try:
        live_document = fetch_openapi_document(url)
    except Exception as error:
        _attach_failed_check(
            "Live Swagger fetch result",
            error,
            openapi_json=live_url,
        )
        pytest.fail(f"Cannot fetch live Swagger OpenAPI JSON from {live_url}: {error}", pytrace=False)

    paths = live_document.get("paths")
    components = live_document.get("components")
    schemas = components.get("schemas") if isinstance(components, dict) else None
    failures: list[str] = []
    if not isinstance(live_document.get("openapi"), str) and not isinstance(live_document.get("swagger"), str):
        failures.append("Live Swagger document does not declare an openapi/swagger version.")
    if not isinstance(paths, dict) or not paths:
        failures.append("Live Swagger document does not contain non-empty paths.")
    if not isinstance(schemas, dict) or not schemas:
        failures.append("Live Swagger document does not contain non-empty components.schemas.")

    path_count = len(paths) if isinstance(paths, dict) else 0
    schema_count = len(schemas) if isinstance(schemas, dict) else 0
    _attach_check_result(
        "Live Swagger OpenAPI availability result",
        {
            "status": "passed" if not failures else "failed",
            "openapi_json": live_url,
            "openapi_version": live_document.get("openapi") or live_document.get("swagger"),
            "path_count": path_count,
            "schema_count": schema_count,
            "failures": failures,
        },
    )

    assert not failures, f"Live Swagger OpenAPI document is not usable from {live_url}:\n" + "\n".join(failures)


def fetch_openapi_document(url: str) -> dict[str, Any]:
    url = swagger_api_docs_url(url)
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(url, timeout=30, context=context) as response:
        return json.loads(response.read().decode("utf-8"))


def openapi_content_schema(document: dict[str, Any], schema_name: str) -> dict[str, list[str]]:
    schemas = document["components"]["schemas"]
    schema = schemas[schema_name]
    content = schema["properties"]["Content"]
    properties = resolved_properties(schemas, content)
    return {
        name: resolved_array_item_fields(schemas, field_schema)
        for name, field_schema in sorted(properties.items())
    }


def resolved_properties(schemas: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if ref:
        return schemas[ref.rsplit("/", 1)[-1]].get("properties", {})
    return schema.get("properties", {})


def resolved_array_item_fields(schemas: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    if schema.get("type") != "array":
        return []
    item_schema = schema.get("items", {})
    return sorted(resolved_properties(schemas, item_schema))
