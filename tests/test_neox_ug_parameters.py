from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from config_loader.simple_yaml import load_simple_yaml
from services.neox_config.service import (
    GE_SWAGGER_PAYLOAD_FILE,
    NEOX_CONTENT_OVERRIDES,
    NEOX_UG_PARAMETER_REFERENCE_FILE,
    ge_port_payload,
    neox_profile_dependency_types,
    neox_profile_minmax_payload,
    nni_port_payload,
)
from services.neox_config.profiles import NEOX_PROFILE_NAMES


REFERENCE_FILE = NEOX_UG_PARAMETER_REFERENCE_FILE


def test_neox_ug_reference_loads():
    reference = load_simple_yaml(REFERENCE_FILE)

    assert reference["source"]["pdf"]
    assert reference["ge_port"]["api_schema"] == "GePortInfo.Content"
    assert reference["nni_port"]["api_schema"] == "NniPortInfo.Content"
    assert "ONTBandwidthProfile" in reference["profiles"]


def test_ge_smoke_payload_uses_documented_values():
    reference = load_simple_yaml(REFERENCE_FILE)
    fields = reference["ge_port"]["fields"]
    smoke_safe_fields = set(reference["ge_port"]["test_field_groups"]["smoke_safe"]["fields"])
    content = ge_port_payload()["Content"]

    assert set(content).issubset(fields)
    assert set(content).issubset(smoke_safe_fields)
    assert_allowed(content, fields)
    assert len(content["portname"]) <= fields["portname"]["max_length"]


def test_ge_smoke_payload_fields_exist_in_swagger_ui_example():
    swagger_example = json.loads(GE_SWAGGER_PAYLOAD_FILE.read_text(encoding="utf-8"))
    swagger_content = swagger_example["payload"]["Content"]
    smoke_content = ge_port_payload()["Content"]

    assert len(swagger_content) >= 100
    assert set(smoke_content).issubset(swagger_content)
    assert not uses_swagger_placeholder(smoke_content)


def test_nni_smoke_payload_uses_documented_values():
    reference = load_simple_yaml(REFERENCE_FILE)
    fields = reference["nni_port"]["fields"]
    content = nni_port_payload()["Content"]

    assert set(content).issubset(fields)
    assert_allowed(content, fields)


def test_neox_profile_override_payloads_use_documented_ranges():
    reference = load_simple_yaml(REFERENCE_FILE)
    profile_references = reference["profiles"]

    for profile_type, content in NEOX_CONTENT_OVERRIDES.items():
        if not content or profile_type not in profile_references:
            continue
        fields = profile_references[profile_type]["fields"]
        assert set(content).issubset(fields), profile_type
        assert_allowed(content, fields, profile_type=profile_type)
        assert_in_ranges(content, fields, profile_type=profile_type)

    bandwidth = NEOX_CONTENT_OVERRIDES["ONTBandwidthProfile"]
    sir = Decimal(str(bandwidth["sir"]))
    air = Decimal(str(bandwidth["air"]))
    pir = Decimal(str(bandwidth["pir"]))
    assert pir >= sir + air
    assert sir + air <= Decimal("8509952")


def test_ont_uni_profile_payloads_are_minimal_and_nonempty():
    expected_keys = set(NEOX_CONTENT_OVERRIDES["ONTUNIProfile"])
    payloads = {
        "default": {"Content": NEOX_CONTENT_OVERRIDES["ONTUNIProfile"]},
        "min": neox_profile_minmax_payload("ONTUNIProfile", "min"),
    }

    for label, payload in payloads.items():
        content = payload["Content"]
        assert set(content) == expected_keys, label
        assert len(content) == 10, label
        assert all(value not in (None, "") for value in content.values()), label


def test_ont_uni_profile_max_payload_covers_full_neox_schema():
    payload = neox_profile_minmax_payload("ONTUNIProfile", "max")
    content = payload["Content"]

    assert len(content) == 590
    assert all(value is not None for value in content.values())
    assert {"lanvlan1", "xlanvlan32", "veipvlan32", "potsportactive2", "videoactive1"}.issubset(content)


def test_ont_multicast_profile_groupprofile_requires_igmp_dependency():
    expected_name = NEOX_PROFILE_NAMES["IGMPGroupPrivilegeProfile"]

    for boundary in ("min", "max"):
        payload = neox_profile_minmax_payload("ONTMulticastProfile", boundary)
        content = payload["Content"]

        assert content["groupprofile"] == expected_name
        assert neox_profile_dependency_types("ONTMulticastProfile", payload) == ["IGMPGroupPrivilegeProfile"]

    assert neox_profile_dependency_types("ONTMulticastProfile", {"Content": {"groupprofile": ""}}) == []


def assert_allowed(content: dict[str, Any], fields: dict[str, Any], profile_type: str | None = None) -> None:
    label = f"{profile_type}: " if profile_type else ""
    for key, value in content.items():
        allowed = fields[key].get("allowed")
        if allowed:
            assert str(value) in allowed, f"{label}{key}={value!r} not in {allowed!r}"


def assert_in_ranges(content: dict[str, Any], fields: dict[str, Any], profile_type: str | None = None) -> None:
    label = f"{profile_type}: " if profile_type else ""
    for key, value in content.items():
        field = fields[key]
        value_text = str(value)
        if "range" in field:
            low, high = [Decimal(str(bound)) for bound in field["range"]]
            current = Decimal(value_text)
            assert low <= current <= high, f"{label}{key}={value!r} outside {low}..{high}"
        if "multiple_of" in field:
            multiple = Decimal(str(field["multiple_of"]))
            assert Decimal(value_text) % multiple == 0, f"{label}{key}={value!r} is not multiple of {multiple}"
        if "max_length" in field:
            assert len(value_text) <= field["max_length"], f"{label}{key} exceeds max length"


def uses_swagger_placeholder(content: dict[str, Any]) -> bool:
    return any(value in ("string", 0) for value in content.values())
