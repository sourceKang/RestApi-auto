from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cases.openapi_contract import load_baseline_contract


CATALOG_FILE = Path("configs/neox_config/ge/neox_ge_field_catalog.json")
COMPLETION_STATUS_FILE = Path("configs/neox_config/ge/neox_ge_completion_status.json")


def test_neox_ge_field_catalog_matches_swagger_schema():
    catalog = load_catalog()
    schema_fields = ge_info_schema_fields()

    assert set(catalog["top_level_order"]) == schema_fields
    assert set(catalog["fields"]).issubset(schema_fields)


def test_neox_ge_field_catalog_uses_probe_values_not_swagger_placeholders():
    catalog = load_catalog()
    placeholder_paths = [
        path
        for field_name, metadata in catalog["fields"].items()
        for path, value in walk_values(metadata.get("candidate_value"), field_name)
        if value == "string"
    ]

    assert not placeholder_paths


def test_neox_ge_completion_status_covers_swagger_schema_once():
    status = json.loads(COMPLETION_STATUS_FILE.read_text(encoding="utf-8"))
    schema_fields = ge_info_schema_fields()
    standalone = set(status["standalone_max_verified_fields"])
    probe_only = set(status["probe_verified_with_preconditions_fields"])
    pending = set(status["pending_live_probe_fields"])
    known_unverified = set(status["known_unverified_or_failed_fields"])
    categories = [standalone, probe_only, pending, known_unverified]

    for index, left in enumerate(categories):
        for right in categories[index + 1 :]:
            assert left.isdisjoint(right)

    covered_fields = standalone | probe_only | pending | known_unverified
    assert covered_fields == schema_fields
    assert status["summary"]["total_fields"] == len(schema_fields)
    assert status["summary"]["verified_fields"] == len(standalone | probe_only)
    assert status["summary"]["remaining_fields"] == len(pending | known_unverified)


def load_catalog() -> dict[str, Any]:
    return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))


def ge_info_schema_fields() -> set[str]:
    schema = load_baseline_contract()["schemas"]["GePortInfo"]
    return set(schema["properties"]["Content"]["properties"])


def walk_values(value: Any, path: str):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk_values(child, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_values(child, f"{path}[{index}]")
        return
    yield path, value
