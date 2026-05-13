from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from config_loader.simple_yaml import load_simple_yaml
from services.neox_config.service import NEOX_CONTENT_OVERRIDES, ge_port_payload, nni_port_payload


REFERENCE_FILE = Path(__file__).resolve().parents[1] / "configs" / "neox_ug_parameter_reference.yaml"
GE_SWAGGER_PAYLOAD_FILE = Path(__file__).resolve().parents[1] / "configs" / "neox_ge_swagger_payload.json"


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
