from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

import pytest

from services.neox_config.service import GE_FULL_ACCEPTED_PAYLOAD_FILE
from tests.support.neox_cli_verification import missing_tokens, neox_cli_credentials, run_neox_cli_commands
from utils.assertions import assert_api_success


CATALOG_FILE = Path("configs/neox_config/ge/neox_ge_field_catalog.json")
PROBE_GROUPS = (
    "mtu",
    "accepted_enable_cli_delta",
    "oui_filter",
    "nni_vlan_max_count",
    "tel_number",
    "maxcount",
    "multicast_rate",
    "loopguard_enable",
    "mac_filter",
    "outer_tpid",
    "pppoe_policy",
    "power_saving",
    "spoofing_action",
    "igmp_basic",
    "dhcp_binding_limits",
    "static_ip_filtering",
    "smcast_ip",
    "smcast_mac",
    "igmp_mvid",
    "igmp_privilege_profile",
    "qos_profiles",
    "acl_profile_name",
    "acl_profile_list",
    "ddmi_temperature_voltage_alarm",
    "vlan_membership",
    "vlan_translation",
    "vlan_tls",
    "vlan_trunk_untag",
    "vlan_trunk_ether",
    "vlan_trunk_subnet",
    "vlan_trunk_vlan",
)


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.neox_probe,
    pytest.mark.destructive,
    pytest.mark.mutating,
    pytest.mark.readwrite,
]


@pytest.mark.parametrize("group_name", PROBE_GROUPS, ids=PROBE_GROUPS)
def test_neox_ge_config_cli_first_rest_probe(
    api_client,
    env_config,
    neox_config_service,
    readwrite_session,
    cleanup_registry,
    group_name,
):
    catalog = load_catalog()
    group = catalog["probe_groups"][group_name]
    require_requested_probe_group(group_name)
    require_high_risk_opt_in(group_name, group)

    neox_config_service.verify_required_target_data()
    target = neox_config_service.target()
    path = neox_config_service.ge_path()
    probe_payload = materialize_probe_payload(catalog, group)
    cli_commands = materialize_commands(group.get("cli_first_commands", []), target)
    cleanup_commands = materialize_commands(group.get("cleanup_commands", []), target)

    if not cli_commands:
        pytest.skip(f"{group_name} has no confirmed CLI-first command mapping yet.")

    ensure_setup_profiles(neox_config_service, api_client, readwrite_session, cleanup_registry, group)
    ensure_setup_global_commands(env_config, target, cleanup_registry, group)
    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))
    cleanup_registry.add(lambda: run_ge_config_commands(env_config, target, cleanup_commands))

    api_client.request("DELETE", path, session=readwrite_session)
    cli_first_output = run_ge_config_commands(env_config, target, cli_commands)
    assert_cli_commands_accepted(cli_first_output, "cli_first")
    assert_cli_tokens(env_config, target, catalog, group, "cli_first")

    run_ge_config_commands(env_config, target, cleanup_commands)
    api_client.request("DELETE", path, session=readwrite_session)
    response = post_ge_probe(api_client, path, readwrite_session, probe_payload, group)
    assert_api_success(response)
    assert_cli_tokens(env_config, target, catalog, group, "rest_probe")


def require_requested_probe_group(group_name: str) -> None:
    requested = {
        value.strip()
        for value in os.environ.get("NEOX_GE_PROBE_GROUPS", "").split(",")
        if value.strip()
    }
    if group_name not in requested:
        pytest.skip(f"Set NEOX_GE_PROBE_GROUPS={group_name} to run this GE probe group.")


def require_high_risk_opt_in(group_name: str, group: dict[str, Any]) -> None:
    if group.get("risk") != "high":
        return
    if not truthy_env("NEOX_GE_ALLOW_HIGH_RISK_PROBE"):
        pytest.skip(f"High-risk GE probe {group_name} requires NEOX_GE_ALLOW_HIGH_RISK_PROBE=1.")


def truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def load_catalog() -> dict[str, Any]:
    return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))


def materialize_probe_payload(catalog: dict[str, Any], group: dict[str, Any]) -> dict[str, Any]:
    base_payload = json.loads(GE_FULL_ACCEPTED_PAYLOAD_FILE.read_text(encoding="utf-8"))["payload"]
    payload = copy.deepcopy(base_payload)
    content = payload.setdefault("Content", {})
    for field in group["fields"]:
        content[field] = copy.deepcopy(catalog["fields"][field]["candidate_value"])
    return payload


def materialize_commands(commands: list[str], target) -> list[str]:
    return [
        command.replace("{ge_slot_id}", target.ge_slot_id).replace("{ge_port_id}", target.ge_port_id)
        for command in commands
    ]


def ensure_setup_profiles(neox_config_service, api_client, session_id: str, cleanup_registry, group: dict[str, Any]) -> None:
    for profile_type in group.get("setup_profile_types", []):
        path = neox_config_service.neox_profile_path(profile_type)
        payload = neox_config_service.neox_profile_payload(profile_type)
        neox_config_service.ensure_neox_profile_dependencies(session_id, cleanup_registry, profile_type, payload)
        cleanup_registry.add(lambda p=path: api_client.request("DELETE", p, session=session_id))
        neox_config_service.delete_neox_profile_if_exists(path, session_id)
        response = api_client.request("POST", path, session=session_id, json=payload)
        assert_api_success(response)


def ensure_setup_global_commands(env_config, target, cleanup_registry, group: dict[str, Any]) -> None:
    setup_commands = materialize_commands(group.get("setup_global_commands", []), target)
    cleanup_commands = materialize_commands(group.get("cleanup_global_commands", []), target)
    if not setup_commands and not cleanup_commands:
        return
    cleanup_registry.add(lambda: run_global_config_commands(env_config, cleanup_commands))
    if setup_commands:
        setup_output = run_global_config_commands(env_config, setup_commands)
        assert_cli_commands_accepted(setup_output, "global_setup")


def post_ge_probe(api_client, path: str, session_id: str, payload: dict[str, Any], group: dict[str, Any]):
    original_timeout = api_client.timeout
    timeout_seconds = group.get("rest_timeout_seconds")
    if timeout_seconds:
        read_timeout = float(timeout_seconds)
        if isinstance(original_timeout, tuple):
            api_client.timeout = (original_timeout[0], max(float(original_timeout[1]), read_timeout))
        else:
            api_client.timeout = (float(original_timeout), read_timeout)
    try:
        return api_client.request("POST", path, session=session_id, json=payload)
    finally:
        api_client.timeout = original_timeout


def run_ge_config_commands(env_config, target, commands: list[str]) -> dict[str, str]:
    if not commands:
        return {}
    credentials = neox_cli_credentials(env_config, "GE")
    cli_sequence = ["configure", f"interface ge {target.ge_slot_id}-{target.ge_port_id}", *commands, "exit", "exit"]
    return run_neox_cli_commands(env_config, credentials, cli_sequence)


def run_global_config_commands(env_config, commands: list[str]) -> dict[str, str]:
    if not commands:
        return {}
    credentials = neox_cli_credentials(env_config, "GE")
    cli_sequence = ["configure", *commands, "exit"]
    return run_neox_cli_commands(env_config, credentials, cli_sequence)


def assert_cli_commands_accepted(output_by_command: dict[str, str], phase: str) -> None:
    failure_fragments = (
        "invalid input",
        "incomplete command",
        "ambiguous command",
        "does not exist",
        "not found",
        "fail",
        "error",
    )
    failures = {
        command: output
        for command, output in output_by_command.items()
        if any(fragment in output.casefold() for fragment in failure_fragments)
    }
    assert not failures, f"GE CLI command failed during {phase}: {failures}"


def assert_cli_tokens(env_config, target, catalog: dict[str, Any], group: dict[str, Any], phase: str) -> None:
    credentials = neox_cli_credentials(env_config, "GE")
    commands = materialize_commands(group.get("show_commands", []), target)
    if not commands:
        commands = [f"show running-config interface ge {target.ge_slot_id}-{target.ge_port_id}"]
    output_by_command = run_neox_cli_commands(env_config, credentials, commands)
    expected_tokens = expected_group_tokens(catalog, group)
    combined_output = "\n".join(output_by_command.values())
    missing = missing_tokens(combined_output, expected_tokens)
    assert not missing, f"Missing GE CLI tokens after {phase}: {missing}\nCLI output:\n{combined_output}"


def expected_group_tokens(catalog: dict[str, Any], group: dict[str, Any]) -> list[str]:
    tokens = []
    for field in group["fields"]:
        metadata = catalog["fields"][field]
        if metadata.get("cli_expected_token"):
            tokens.append(metadata["cli_expected_token"])
        tokens.extend(metadata.get("cli_expected_tokens", []))
    return [token for token in tokens if token]
