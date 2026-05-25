from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


DEFAULT_OPENAPI_ROOT = Path(r"D:\FW\NetAtlasEMS")
DEFAULT_OPENAPI_VERSION_DIR = "03.00.11 (AAVV.221)"
LEGACY_OPENAPI_VERSION_DIR = "V3011"
OPENAPI_YAML_ENV = "EMS_OPENAPI_YAML_FILE"
BASELINE_CONTRACT_FILE = Path(__file__).with_name("openapi_contract_baseline.json")
OPENAPI_FILE_PATTERN = "NetAtlasEMS_OpenAPI_*.yaml"
HTTP_METHODS = ("delete", "get", "head", "options", "patch", "post", "put", "trace")
SCHEMA_KEYS = (
    "$ref",
    "type",
    "format",
    "nullable",
    "enum",
    "required",
    "properties",
    "items",
    "additionalProperties",
    "allOf",
    "anyOf",
    "oneOf",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "pattern",
    "default",
)


class OpenApiContractError(RuntimeError):
    pass


def configured_openapi_yaml_file(ems_version: Any | None = None) -> Path:
    override = os.environ.get(OPENAPI_YAML_ENV)
    if override:
        return Path(override)

    directory = _openapi_version_directory(ems_version)
    return latest_openapi_yaml_file(directory)


def latest_openapi_yaml_file(directory: Path) -> Path:
    if not directory.exists():
        raise OpenApiContractError(f"OpenAPI version directory does not exist: {directory}")
    candidates = [path for path in directory.glob(OPENAPI_FILE_PATTERN) if path.is_file()]
    if not candidates:
        raise OpenApiContractError(f"No {OPENAPI_FILE_PATTERN} files found in {directory}")
    return max(candidates, key=_openapi_file_sort_key)


def load_openapi_document(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as error:
        raise OpenApiContractError("PyYAML is required to parse OpenAPI YAML files.") from error

    if not path.exists():
        raise OpenApiContractError(
            f"OpenAPI YAML file does not exist: {path}. "
            f"Set {OPENAPI_YAML_ENV} to override the default path."
        )
    with path.open("r", encoding="utf-8-sig") as handle:
        document = yaml.safe_load(handle)
    if not isinstance(document, dict):
        raise OpenApiContractError(f"{path} must contain a YAML mapping at the document root.")
    return document


def load_baseline_contract(path: Path = BASELINE_CONTRACT_FILE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_openapi_contract(document: dict[str, Any]) -> dict[str, Any]:
    components = document.get("components", {})
    schemas = components.get("schemas", {}) if isinstance(components, dict) else {}
    return {
        "openapi": str(document.get("openapi", "")),
        "info": {
            "title": _string_at(document, "info", "title"),
        },
        "paths": _paths_contract(document.get("paths", {})),
        "schemas": _schemas_contract(schemas),
    }


def diff_contracts(expected: Any, actual: Any, *, path: str = "$") -> list[str]:
    differences: list[str] = []
    _diff_values(expected, actual, path, differences)
    return differences


def normalize_ems_version(value: Any) -> str:
    text = str(value)
    match = re.search(r"\d+(?:\.\d+){2}", text)
    return match.group(0) if match else text.strip()


def openapi_version_dir_name(ems_version: Any) -> str:
    text = str(ems_version).strip()
    return re.sub(r"\s+b\d+\s*$", "", text, flags=re.IGNORECASE) or DEFAULT_OPENAPI_VERSION_DIR


def format_contract_differences(differences: list[str], *, limit: int = 80) -> str:
    if not differences:
        return ""
    shown = differences[:limit]
    message = "\n".join(f"- {difference}" for difference in shown)
    remaining = len(differences) - len(shown)
    if remaining > 0:
        message += f"\n- ... {remaining} more differences"
    return message


def _paths_contract(paths: Any) -> dict[str, Any]:
    if not isinstance(paths, dict):
        raise OpenApiContractError("OpenAPI document must contain paths: mapping.")
    contract: dict[str, Any] = {}
    for path_name in sorted(paths):
        path_item = paths[path_name]
        if not isinstance(path_item, dict):
            continue
        path_parameters = path_item.get("parameters", [])
        operations: dict[str, Any] = {}
        for method in HTTP_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            parameters = [*_list_items(path_parameters), *_list_items(operation.get("parameters", []))]
            operations[method] = {
                "tags": sorted(str(tag) for tag in _list_items(operation.get("tags", []))),
                "operationId": str(operation.get("operationId", "")),
                "parameters": sorted(
                    (_parameter_contract(parameter) for parameter in parameters),
                    key=lambda item: (item.get("in", ""), item.get("name", "")),
                ),
                "requestBody": _request_body_contract(operation.get("requestBody")),
                "responses": _responses_contract(operation.get("responses", {})),
            }
        contract[str(path_name)] = operations
    return contract


def _schemas_contract(schemas: Any) -> dict[str, Any]:
    if not isinstance(schemas, dict):
        raise OpenApiContractError("OpenAPI document must contain components.schemas: mapping.")
    return {str(name): _schema_contract(schema) for name, schema in sorted(schemas.items())}


def _parameter_contract(parameter: Any) -> dict[str, Any]:
    if not isinstance(parameter, dict):
        return {"invalid": repr(parameter)}
    if "$ref" in parameter:
        return {"$ref": str(parameter["$ref"])}
    return {
        "name": str(parameter.get("name", "")),
        "in": str(parameter.get("in", "")),
        "required": bool(parameter.get("required", False)),
        "schema": _schema_contract(parameter.get("schema", {})),
    }


def _request_body_contract(request_body: Any) -> dict[str, Any]:
    if not isinstance(request_body, dict):
        return {}
    if "$ref" in request_body:
        return {"$ref": str(request_body["$ref"])}
    return {
        "required": bool(request_body.get("required", False)),
        "content": _content_contract(request_body.get("content", {})),
    }


def _responses_contract(responses: Any) -> dict[str, Any]:
    if not isinstance(responses, dict):
        return {}
    contract: dict[str, Any] = {}
    for status, response in sorted(responses.items(), key=lambda item: str(item[0])):
        if isinstance(response, dict) and "$ref" in response:
            contract[str(status)] = {"$ref": str(response["$ref"])}
            continue
        contract[str(status)] = {
            "content": _content_contract(response.get("content", {}) if isinstance(response, dict) else {}),
        }
    return contract


def _content_contract(content: Any) -> dict[str, Any]:
    if not isinstance(content, dict):
        return {}
    return {
        str(media_type): {"schema": _schema_contract(media.get("schema", {}) if isinstance(media, dict) else {})}
        for media_type, media in sorted(content.items())
    }


def _schema_contract(schema: Any) -> Any:
    if isinstance(schema, list):
        return [_schema_contract(item) for item in schema]
    if not isinstance(schema, dict):
        return schema

    contract: dict[str, Any] = {}
    for key in SCHEMA_KEYS:
        if key not in schema:
            continue
        value = schema[key]
        if key == "properties" and isinstance(value, dict):
            contract[key] = {str(name): _schema_contract(prop) for name, prop in sorted(value.items())}
        elif key in {"items", "additionalProperties"}:
            contract[key] = _schema_contract(value)
        elif key in {"allOf", "anyOf", "oneOf"} and isinstance(value, list):
            contract[key] = [_schema_contract(item) for item in value]
        elif key == "required" and isinstance(value, list):
            contract[key] = sorted(str(item) for item in value)
        elif key == "enum" and isinstance(value, list):
            contract[key] = sorted(value, key=repr)
        else:
            contract[key] = value
    return contract


def _diff_values(expected: Any, actual: Any, path: str, differences: list[str]) -> None:
    if isinstance(expected, dict) and isinstance(actual, dict):
        expected_keys = set(expected)
        actual_keys = set(actual)
        for key in sorted(expected_keys - actual_keys):
            differences.append(f"{path}.{key} was removed")
        for key in sorted(actual_keys - expected_keys):
            differences.append(f"{path}.{key} was added")
        for key in sorted(expected_keys & actual_keys):
            _diff_values(expected[key], actual[key], f"{path}.{key}", differences)
        return
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            differences.append(f"{path} length changed from {len(expected)} to {len(actual)}")
            return
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual)):
            _diff_values(expected_item, actual_item, f"{path}[{index}]", differences)
        return
    if expected != actual:
        differences.append(f"{path} changed from {expected!r} to {actual!r}")


def _string_at(mapping: dict[str, Any], *keys: str) -> str:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return str(current or "")


def _list_items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _openapi_version_directory(ems_version: Any | None) -> Path:
    preferred = openapi_version_dir_name(ems_version) if ems_version else DEFAULT_OPENAPI_VERSION_DIR
    candidates = [DEFAULT_OPENAPI_ROOT / preferred]
    candidates.extend(_matching_version_directories(ems_version))
    for fallback in (DEFAULT_OPENAPI_VERSION_DIR, LEGACY_OPENAPI_VERSION_DIR):
        fallback_path = DEFAULT_OPENAPI_ROOT / fallback
        if fallback_path not in candidates:
            candidates.append(fallback_path)
    for directory in candidates:
        if directory.exists():
            return directory
    return candidates[0]


def _openapi_file_sort_key(path: Path) -> tuple[int, float, str]:
    match = re.search(r"(\d{8})(?=\.ya?ml$)", path.name, re.IGNORECASE)
    file_date = int(match.group(1)) if match else 0
    try:
        modified = path.stat().st_mtime
    except OSError:
        modified = 0.0
    return (file_date, modified, path.name)


def _matching_version_directories(ems_version: Any | None) -> list[Path]:
    if not ems_version or not DEFAULT_OPENAPI_ROOT.exists():
        return []
    prefix = normalize_ems_version(ems_version)
    if not prefix:
        return []
    try:
        directories = [path for path in DEFAULT_OPENAPI_ROOT.iterdir() if path.is_dir()]
    except OSError:
        return []
    return sorted(
        (path for path in directories if path.name.startswith(prefix)),
        key=lambda path: path.name,
    )
