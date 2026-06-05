from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cases.openapi_contract import load_baseline_contract


CATALOG_FILE = Path("configs/neox_config/ont/neox_ont_field_catalog.json")
EXPECTED_ONT_FIELD_ORDER = [
    "ontenable",
    "sn",
    "registid",
    "registmethod",
    "ontdescription",
    "onttype",
    "adminstate",
    "dynamic_vid",
    "dynamic_pbit",
    "static_vid",
    "static_pbit",
    "static_hostip",
    "static_mask",
    "iphost_gateway",
    "iphost_pridns",
    "iphost_secdns",
    "templatename",
    "servicelist",
    "tcontlist",
    "dspir",
    "fwupgrademode",
    "fwupgradeid",
    "fwupgradeomci",
    "fdbmaclist",
    "wifi24glist",
    "wifi5glist",
    "wanlist",
    "voiplist",
]


def test_neox_ont_field_catalog_matches_swagger_schema_order():
    catalog = load_catalog()
    schema_fields = ont_info_schema_fields()

    assert catalog["top_level_order"] == EXPECTED_ONT_FIELD_ORDER
    assert set(catalog["top_level_order"]) == schema_fields
    assert set(catalog["fields"]) == schema_fields


def test_neox_ont_field_catalog_leaf_order_covers_nested_payload_shape():
    catalog = load_catalog()

    assert "servicelist.serviceindex" in catalog["leaf_order"]
    assert "tcontlist.tcontindex" in catalog["leaf_order"]
    assert "wifi24glist.wifi24gssid" in catalog["leaf_order"]
    assert "wanlist.password" in catalog["leaf_order"]
    assert "voiplist.aorurl" in catalog["leaf_order"]


def test_neox_ont_field_catalog_uses_probe_values_not_swagger_placeholders():
    catalog = load_catalog()
    placeholder_paths = [
        path
        for field_name, metadata in catalog["fields"].items()
        for path, value in walk_values(metadata.get("candidate_value"), field_name)
        if value == "string"
    ]

    assert not placeholder_paths


def test_neox_ont_field_catalog_keeps_high_risk_fields_out_of_default_success_group():
    catalog = load_catalog()
    basic_fields = set(catalog["probe_groups"]["basic_current_success"]["fields"])
    firmware_specific_fields = {"fwupgrademode", "fwupgradeid", "fwupgradeomci"}
    identity_fields = {"sn", "registid", "registmethod"}
    high_risk_fields = {
        field
        for group in catalog["probe_groups"].values()
        if group.get("risk") == "high"
        for field in group["fields"]
    } - identity_fields

    assert firmware_specific_fields.isdisjoint(basic_fields)
    assert high_risk_fields.isdisjoint(basic_fields)
    assert catalog["probe_groups"]["firmware_upgrade"]["risk"] == "high"
    assert catalog["probe_groups"]["ont_template"]["status"] == "live_success_official_max_payload_after_template_profile_dependency"


def load_catalog() -> dict[str, Any]:
    return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))


def ont_info_schema_fields() -> set[str]:
    schema = load_baseline_contract()["schemas"]["ONTInfo"]
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
