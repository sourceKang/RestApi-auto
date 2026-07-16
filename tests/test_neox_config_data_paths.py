from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from services.neox_config.service import (
    NEOX_CONFIG_DATA_FILES,
    NEOX_CONFIG_DIR,
    NEOX_PROFILE_TYPES,
    PROFILE_MINMAX_PAYLOAD_DIR,
    ge_full_accepted_config,
    ge_max_variants_config,
    sanitize_ge_payload,
)
from tests.support.collection import neox_parallel_group_for_name, neox_parallel_scope_for_name
from tests.support.options import neox_parallel_auth_profile_for_worker
from tests.test_neox_config import ge_acl_profile_mode_cleanup_plan
from utils.cleanup import CleanupRegistry


CONFIG_PATH_PATTERN = re.compile(r"configs/neox_config/[A-Za-z0-9_./-]+\.(?:json|ya?ml|md)")

FORBIDDEN_EXPLICIT_FIELDS = {
    "bias_warn_high",
    "bias_warn_low",
    "rxpower_warn_high",
    "rxpower_warn_low",
    "temperature_warn_high",
    "temperature_warn_low",
    "txpower_warn_high",
    "txpower_warn_low",
    "voltage_warn_high",
    "voltage_warn_low",
}

EXPECTED_DDMI_ALARM_FIELDS = {
    "temperature_alarm_high": "100",
    "temperature_alarm_low": "-40",
    "voltage_alarm_high": "3.59",
    "voltage_alarm_low": "2.8",
    "txpower_alarm_high": "1600",
    "txpower_alarm_low": "160",
    "rxpower_alarm_high": "1200",
    "rxpower_alarm_low": "30",
}


def test_neox_parallel_auth_profile_mapping_is_disabled_by_default():
    assert neox_parallel_auth_profile_for_worker("default", "off", "default,ems_local_rw2", "gw1") == "default"
    assert neox_parallel_auth_profile_for_worker("default", "resource", "", "gw1") == "default"
    assert neox_parallel_auth_profile_for_worker("default", "resource", "default,ems_local_rw2", None) == "default"


def test_neox_parallel_auth_profile_mapping_assigns_xdist_workers():
    assert neox_parallel_auth_profile_for_worker(None, "resource", "default,ems_local_rw2", "gw0") == "default"
    assert neox_parallel_auth_profile_for_worker(None, "resource", "default,ems_local_rw2", "gw1") == "ems_local_rw2"
    with pytest.raises(ValueError, match="defines 1 profile"):
        neox_parallel_auth_profile_for_worker(None, "resource", "default", "gw1")

def test_neox_parallel_grouping_defaults_to_off():
    assert neox_parallel_group_for_name("test_ge_config_min_create_readwrite", {"neox_config"}, "off") is None


def test_neox_parallel_conservative_groups_all_neox_config_cases_together():
    assert (
        neox_parallel_group_for_name(
            "test_ge_config_min_create_readwrite",
            {"neox_config"},
            "conservative",
            node_key="NODE3",
        )
        == "node3_node_config"
    )
    assert (
        neox_parallel_group_for_name(
            "test_neox_profile_max_create_readwrite",
            {"neox_config", "neox_profile"},
            "conservative",
            node_key="NODE3",
        )
        == "node3_node_config"
    )


def test_neox_parallel_resource_grouping_uses_node_prefixed_resources_for_rest_only():
    assert (
        neox_parallel_group_for_name(
            "test_ge_config_max_create_readwrite",
            {"neox_config"},
            "resource",
            node_key="NODE3",
            cli_verify=False,
        )
        == "node3_ge_port"
    )
    assert (
        neox_parallel_group_for_name(
            "test_nni_config_max_create_readwrite",
            {"neox_config"},
            "resource",
            node_key="NODE3",
            cli_verify=False,
        )
        == "node3_nni_port"
    )
    assert (
        neox_parallel_group_for_name(
            "test_vlan_config_max_create_readwrite",
            {"neox_config"},
            "resource",
            node_key="NODE3",
            cli_verify=False,
        )
        == "node3_vlan"
    )
    assert (
        neox_parallel_group_for_name(
            "test_ont_config_max_create_readwrite",
            {"neox_config"},
            "resource",
            node_key="NODE3",
            cli_verify=False,
        )
        == "node3_ont_1"
    )
    assert (
        neox_parallel_group_for_name(
            "test_neox_profile_clear_readwrite",
            {"neox_config", "neox_profile"},
            "resource",
            node_key="NODE3",
            cli_verify=False,
        )
        == "node3_profile_ns"
    )


def test_neox_parallel_resource_grouping_serializes_node_cli_mutating_cases():
    assert (
        neox_parallel_group_for_name(
            "test_nni_config_max_create_readwrite",
            {"neox_config", "mutating"},
            "resource",
            node_key="NODE3",
            cli_verify=True,
        )
        == "node3_node_config"
    )
    assert (
        neox_parallel_group_for_name(
            "test_neox_profile_min_create_readwrite",
            {"neox_config", "neox_profile", "mutating"},
            "resource",
            node_key="NODE3",
            cli_verify=True,
        )
        == "node3_node_config"
    )


def test_neox_parallel_scoped_cases_are_identified():
    assert neox_parallel_scope_for_name("test_ge_config_max_variant_readwrite", {"neox_config"}) == "device"
    assert neox_parallel_scope_for_name("test_custom", {"neox_config", "ems_scoped"}) == "ems"
    assert (
        neox_parallel_group_for_name(
            "test_ge_config_max_variant_readwrite",
            {"neox_config", "mutating"},
            "resource",
            node_key="NODE3",
            cli_verify=True,
        )
        == "node3_node_config"
    )

def test_cleanup_registry_add_final_runs_after_lifo_callbacks():
    events = []
    registry = CleanupRegistry()

    registry.add(lambda: events.append("normal1"))
    registry.add_final(lambda: events.append("final"))
    registry.add(lambda: events.append("normal2"))
    registry.run()

    assert events == ["normal2", "normal1", "final"]


def test_ge_acl_profile_mode_cleanup_plan_restores_port_last():
    commands = [
        "acl-profile mode port",
        "y",
        "no acl-profile RestApiGeAcl",
        "no igmp-mld mvlan 1314",
    ]

    planned_commands, run_cleanup_last = ge_acl_profile_mode_cleanup_plan(commands)

    assert run_cleanup_last is True
    assert planned_commands == [
        "no acl-profile RestApiGeAcl",
        "no igmp-mld mvlan 1314",
        "acl-profile mode port",
        "y",
    ]

def test_neox_config_data_files_exist():
    missing = [str(path) for path in NEOX_CONFIG_DATA_FILES if not path.exists()]
    assert not missing


def test_neox_profile_split_minmax_files_exist():
    missing = []
    for profile_type in NEOX_PROFILE_TYPES:
        path = PROFILE_MINMAX_PAYLOAD_DIR / f"{profile_type}.json"
        if not path.exists():
            missing.append(str(path))
    assert not missing


def test_neox_config_internal_path_references_exist():
    missing = []
    root = NEOX_CONFIG_DIR.parents[1]

    for path in NEOX_CONFIG_DIR.rglob("*"):
        if path.suffix not in {".json", ".yaml", ".yml", ".md"}:
            continue
        for match in CONFIG_PATH_PATTERN.findall(path.read_text(encoding="utf-8")):
            target = root / Path(match)
            if not target.exists():
                missing.append(f"{path}: {match}")

    assert not missing


def test_ge_full_accepted_payload_has_no_forbidden_future_fields():
    config = ge_full_accepted_config()

    assert not forbidden_payload_paths(config["payload"])


def test_ge_full_accepted_payload_keeps_temperature_voltage_alarm_fields():
    config = ge_full_accepted_config()
    content = config["payload"]["Content"]

    for field, value in EXPECTED_DDMI_ALARM_FIELDS.items():
        assert content[field] == value

    ddmi_tokens = config["additional_cli_visible_checks"][
        "show interface ge {slot_id}-{port_id} ddmi config"
    ]
    assert "Temperature(C)        100.00       -40.00" in ddmi_tokens
    assert "Voltage(V)          3.59         2.80" in ddmi_tokens
    assert "TX Power(uW)" in ddmi_tokens
    assert "1600.00" in ddmi_tokens
    assert "160.00" in ddmi_tokens
    assert "RX Power(uW)" in ddmi_tokens
    assert "1200.00" in ddmi_tokens
    assert "30.00" in ddmi_tokens


def test_ge_full_accepted_payload_keeps_power_saving_fields():
    config = ge_full_accepted_config()
    content = config["payload"]["Content"]

    assert content["pwsaving"] == "enable"
    assert content["pwsaving_sleep"] == 120
    assert content["pwsaving_awake"] == 10
    assert "power-saving enable" in config["running_config_visible_lines"]
    assert "power-saving sleep-interval 120" in config["running_config_visible_lines"]
    assert "power-saving awake-interval 10" in config["running_config_visible_lines"]


def test_ge_max_variants_keep_payload_and_cli_expectations_in_official_config():
    data = ge_max_variants_config()

    assert set(data["variant_order"]) == set(data["variants"])
    for variant_name in data["variant_order"]:
        variant = data["variants"][variant_name]
        fields = variant["fields"]
        payload_patch = variant["payload_patch"]
        expected_tokens = variant["expected_tokens"]

        assert fields, variant_name
        assert expected_tokens, variant_name
        assert set(fields) <= set(payload_patch), variant_name


def test_sanitize_ge_payload_removes_future_forbidden_fields():
    payload = {
        "Content": {
            "portenable": "enable",
            "bias_warn_high": "88",
            "bias_warn_low": "6",
            "rxpower_warn_high": "-1",
            "rxpower_warn_low": "-126",
            "temperature_warn_high": "95",
            "temperature_warn_low": "-35",
            "txpower_warn_high": "5.5",
            "txpower_warn_low": "-14.3",
            "voltage_warn_high": "3.5",
            "voltage_warn_low": "2.9",
            "txpower_alarm_high": "1600",
            "txpower_alarm_low": "160",
            "rxpower_alarm_high": "1200",
            "rxpower_alarm_low": "30",
            "nested": [{"rxpower_alarm_high": "1200"}],
        }
    }

    sanitized = sanitize_ge_payload(payload)

    assert sanitized == {
        "Content": {
            "portenable": "enable",
            "txpower_alarm_high": "1600",
            "txpower_alarm_low": "160",
            "rxpower_alarm_high": "1200",
            "rxpower_alarm_low": "30",
            "nested": [{"rxpower_alarm_high": "1200"}],
        }
    }


def forbidden_payload_paths(value: Any, path: str = "$") -> list[str]:
    if isinstance(value, dict):
        paths = []
        for key, child in value.items():
            child_path = f"{path}.{key}"
            key_text = str(key)
            if key_text in FORBIDDEN_EXPLICIT_FIELDS or "_warn_" in key_text.casefold():
                paths.append(child_path)
            paths.extend(forbidden_payload_paths(child, child_path))
        return paths
    if isinstance(value, list):
        paths = []
        for index, child in enumerate(value):
            paths.extend(forbidden_payload_paths(child, f"{path}[{index}]"))
        return paths
    return []



