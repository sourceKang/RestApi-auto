from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from typing import Any


DEFAULT_OPENAPI_ROOT = Path(r"D:\FW\NetAtlasEMS")
DEFAULT_OPENAPI_VERSION_DIR = "03.00.11 (AAVV.221)"
LEGACY_OPENAPI_VERSION_DIR = "V3011"
OPENAPI_YAML_ENV = "EMS_OPENAPI_YAML_FILE"
BASELINE_CONTRACT_FILE = Path(__file__).with_name("openapi_contract_baseline.json")
BASELINE_YAML_FILE = Path(__file__).with_name("openapi_yaml_baseline.json")
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
    baseline = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(baseline.get("contract"), dict):
        return baseline["contract"]
    return baseline


def load_baseline_yaml_document(path: Path = BASELINE_YAML_FILE) -> dict[str, Any]:
    baseline = json.loads(path.read_text(encoding="utf-8"))
    document = baseline.get("document")
    if not isinstance(document, dict):
        raise OpenApiContractError(f"{path} must contain document: mapping.")
    return document


def build_openapi_yaml_document(document: dict[str, Any]) -> dict[str, Any]:
    return _canonical_value(document)


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


def diff_semantic_openapi_documents(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    differences = diff_contracts(
        _semantic_paths_contract(expected.get("paths", {})),
        _semantic_paths_contract(actual.get("paths", {})),
        path="$.paths",
    )
    expected_schemas = _document_schemas(expected)
    actual_schemas = _document_schemas(actual)
    schema_names = sorted(_direct_path_schema_refs(expected) | _direct_path_schema_refs(actual))
    for schema_name in schema_names:
        expected_schema = expected_schemas.get(schema_name)
        actual_schema = actual_schemas.get(schema_name)
        if not isinstance(expected_schema, dict):
            differences.append(f"$.schemas.{schema_name} was added")
            continue
        if not isinstance(actual_schema, dict):
            differences.append(f"$.schemas.{schema_name} was removed")
            continue
        expected_fields = _schema_leaf_contracts(expected_schemas, expected_schema)
        actual_fields = _schema_leaf_contracts(actual_schemas, actual_schema)
        differences.extend(diff_contracts(expected_fields, actual_fields, path=f"$.schemas.{schema_name}.leaf_fields"))
    return differences


def diff_openapi_key_documents(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    differences = diff_contracts(
        _openapi_key_paths_contract(expected.get("paths", {})),
        _openapi_key_paths_contract(actual.get("paths", {})),
        path="$.paths",
    )
    expected_schemas = _document_schemas(expected)
    actual_schemas = _document_schemas(actual)
    schema_names = sorted(_direct_path_schema_refs(expected) | _direct_path_schema_refs(actual))
    for schema_name in schema_names:
        expected_schema = expected_schemas.get(schema_name)
        actual_schema = actual_schemas.get(schema_name)
        if not isinstance(expected_schema, dict):
            differences.append(f"$.schemas.{schema_name} was added")
            continue
        if not isinstance(actual_schema, dict):
            differences.append(f"$.schemas.{schema_name} was removed")
            continue
        expected_keys = {name: True for name in sorted(_schema_leaf_paths(expected_schemas, expected_schema))}
        actual_keys = {name: True for name in sorted(_schema_leaf_paths(actual_schemas, actual_schema))}
        differences.extend(diff_contracts(expected_keys, actual_keys, path=f"$.schemas.{schema_name}.leaf_keys"))
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


def openapi_file_date(path: Path) -> int:
    match = re.search(r"(\d{8})", path.name)
    return int(match.group(1)) if match else 0


def swagger_api_docs_url(url: str) -> str:
    text = str(url).strip()
    if not text or "/swagger-ui/" not in text:
        return text

    parts = urlsplit(text)
    base_path = parts.path.split("/swagger-ui/", 1)[0].rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, f"{base_path}/v3/api-docs", "", ""))


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


def _canonical_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _canonical_value(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    return value


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
    try:
        modified = path.stat().st_mtime
    except OSError:
        modified = 0.0
    official_name = 1 if re.fullmatch(r"NetAtlasEMS_OpenAPI_\d{8}\.yaml", path.name) else 0
    return (openapi_file_date(path), official_name, modified, path.name)


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


def _semantic_paths_contract(paths: Any) -> dict[str, Any]:
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
                "parameters": sorted(
                    (_semantic_parameter_contract(parameter) for parameter in parameters),
                    key=lambda item: (item.get("in", ""), item.get("name", "")),
                ),
                "requestBody": _semantic_request_body_contract(operation.get("requestBody")),
                "responses": _semantic_responses_contract(operation.get("responses", {})),
            }
        contract[str(path_name)] = operations
    return contract


def _openapi_key_paths_contract(paths: Any) -> dict[str, Any]:
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
                "parameters": sorted(_parameter_key(parameter) for parameter in parameters),
                "requestBody": _openapi_key_request_body_contract(operation.get("requestBody")),
                "responses": _openapi_key_responses_contract(operation.get("responses", {})),
            }
        contract[str(path_name)] = operations
    return contract


def _parameter_key(parameter: Any) -> str:
    if not isinstance(parameter, dict):
        return repr(parameter)
    if "$ref" in parameter:
        return str(parameter["$ref"])
    return f"{parameter.get('in', '')}:{parameter.get('name', '')}"


def _openapi_key_request_body_contract(request_body: Any) -> dict[str, Any]:
    if not isinstance(request_body, dict):
        return {}
    if "$ref" in request_body:
        return {"$ref": str(request_body["$ref"])}
    return {
        "content": _openapi_key_content_contract(request_body.get("content", {})),
    }


def _openapi_key_responses_contract(responses: Any) -> dict[str, Any]:
    if not isinstance(responses, dict):
        return {}
    contract: dict[str, Any] = {}
    for status, response in sorted(responses.items(), key=lambda item: str(item[0])):
        if isinstance(response, dict) and "$ref" in response:
            contract[str(status)] = {"$ref": str(response["$ref"])}
            continue
        contract[str(status)] = {
            "content": _openapi_key_content_contract(response.get("content", {}) if isinstance(response, dict) else {}),
        }
    return contract


def _openapi_key_content_contract(content: Any) -> dict[str, Any]:
    if not isinstance(content, dict):
        return {}
    return {
        str(media_type): {"schema": _schema_ref_or_type(media.get("schema", {}) if isinstance(media, dict) else {})}
        for media_type, media in sorted(content.items())
    }


def _semantic_parameter_contract(parameter: Any) -> dict[str, Any]:
    if not isinstance(parameter, dict):
        return {"invalid": repr(parameter)}
    if "$ref" in parameter:
        return {"$ref": str(parameter["$ref"])}
    return {
        "name": str(parameter.get("name", "")),
        "in": str(parameter.get("in", "")),
        "required": bool(parameter.get("required", False)),
        "schema": _schema_ref_or_type(parameter.get("schema", {})),
    }


def _semantic_request_body_contract(request_body: Any) -> dict[str, Any]:
    if not isinstance(request_body, dict):
        return {}
    if "$ref" in request_body:
        return {"$ref": str(request_body["$ref"])}
    return {
        "required": bool(request_body.get("required", False)),
        "content": _semantic_content_contract(request_body.get("content", {})),
    }


def _semantic_responses_contract(responses: Any) -> dict[str, Any]:
    if not isinstance(responses, dict):
        return {}
    contract: dict[str, Any] = {}
    for status, response in sorted(responses.items(), key=lambda item: str(item[0])):
        if isinstance(response, dict) and "$ref" in response:
            contract[str(status)] = {"$ref": str(response["$ref"])}
            continue
        contract[str(status)] = {
            "content": _semantic_content_contract(response.get("content", {}) if isinstance(response, dict) else {}),
        }
    return contract


def _semantic_content_contract(content: Any) -> dict[str, Any]:
    if not isinstance(content, dict):
        return {}
    return {
        str(media_type): {"schema": _schema_ref_or_type(media.get("schema", {}) if isinstance(media, dict) else {})}
        for media_type, media in sorted(content.items())
    }


def _schema_ref_or_type(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {}
    if "$ref" in schema:
        return {"$ref": str(schema["$ref"])}
    return {key: schema[key] for key in ("type", "format", "nullable") if key in schema}


def _schema_leaf_paths(schemas: dict[str, Any], schema: Any, prefix: str = "", seen: set[str] | None = None) -> set[str]:
    seen = set() if seen is None else set(seen)
    schema = _resolve_schema_ref(schemas, schema, seen)
    if not isinstance(schema, dict):
        return {prefix} if prefix else set()
    properties = schema.get("properties")
    if isinstance(properties, dict):
        paths: set[str] = set()
        for name, child_schema in properties.items():
            child_prefix = f"{prefix}.{name}" if prefix else str(name)
            child_paths = _schema_leaf_paths(schemas, child_schema, child_prefix, seen)
            paths.update(child_paths or {child_prefix})
        return paths
    if schema.get("type") == "array":
        return _schema_leaf_paths(schemas, schema.get("items", {}), prefix, seen)
    return {prefix} if prefix else set()


def _schema_leaf_contracts(
    schemas: dict[str, Any],
    schema: Any,
    prefix: str = "",
    seen: set[str] | None = None,
    *,
    required: bool = False,
) -> dict[str, Any]:
    seen = set() if seen is None else set(seen)
    schema = _resolve_schema_ref(schemas, schema, seen)
    if not isinstance(schema, dict):
        return {prefix: {"required": required}} if prefix else {}

    properties = schema.get("properties")
    if isinstance(properties, dict):
        required_fields = set(schema.get("required", []) if isinstance(schema.get("required"), list) else [])
        contracts: dict[str, Any] = {}
        for name, child_schema in properties.items():
            child_prefix = f"{prefix}.{name}" if prefix else str(name)
            child_contracts = _schema_leaf_contracts(
                schemas,
                child_schema,
                child_prefix,
                seen,
                required=str(name) in required_fields,
            )
            contracts.update(child_contracts or {child_prefix: {"required": str(name) in required_fields}})
        return contracts

    if schema.get("type") == "array":
        item_contracts = _schema_leaf_contracts(schemas, schema.get("items", {}), prefix, seen, required=required)
        if item_contracts:
            return {
                name: _with_array_marker(contract)
                for name, contract in item_contracts.items()
            }

    if not prefix:
        return {}
    return {prefix: _schema_leaf_signature(schema, required=required)}


def _schema_leaf_signature(schema: dict[str, Any], *, required: bool) -> dict[str, Any]:
    signature = {"required": required}
    for key in (
        "type",
        "nullable",
        "enum",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "pattern",
    ):
        if key in schema:
            value = schema[key]
            signature[key] = sorted(value, key=repr) if key == "enum" and isinstance(value, list) else value
    return signature


def _with_array_marker(contract: Any) -> Any:
    if not isinstance(contract, dict):
        return contract
    marked = dict(contract)
    marked["array_item"] = True
    return marked


def _direct_path_schema_refs(document: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    paths = document.get("paths", {})
    if not isinstance(paths, dict):
        return refs
    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        for method in HTTP_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            _collect_schema_refs(operation.get("requestBody"), refs)
            _collect_schema_refs(operation.get("responses"), refs)
    return refs


def _collect_schema_refs(value: Any, refs: set[str]) -> None:
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            refs.add(ref.rsplit("/", 1)[-1])
        for item in value.values():
            _collect_schema_refs(item, refs)
        return
    if isinstance(value, list):
        for item in value:
            _collect_schema_refs(item, refs)


def _document_schemas(document: dict[str, Any]) -> dict[str, Any]:
    components = document.get("components", {})
    schemas = components.get("schemas", {}) if isinstance(components, dict) else {}
    return schemas if isinstance(schemas, dict) else {}


def _resolve_schema_ref(schemas: dict[str, Any], schema: Any, seen: set[str]) -> Any:
    if not isinstance(schema, dict):
        return schema
    ref = schema.get("$ref")
    if not isinstance(ref, str):
        return schema
    name = ref.rsplit("/", 1)[-1]
    if name in seen:
        return {}
    seen.add(name)
    return _resolve_schema_ref(schemas, schemas.get(name, {}), seen)
