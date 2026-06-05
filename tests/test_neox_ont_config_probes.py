from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

import pytest

from services.neox_config.cli_expectations import neox_cli_sn
from services.neox_config.service import ont_config_payload
from tests.support.neox_cli_verification import missing_tokens, neox_cli_credentials, run_neox_cli_commands
from utils.assertions import assert_api_success


CATALOG_FILE = Path("configs/neox_config/ont/neox_ont_field_catalog.json")
PROBE_GROUPS = (
    "ip_host_dynamic",
    "ip_host_static",
    "dspir",
    "service_tcont",
    "fdbmac",
    "wifi_wan_voip",
    "firmware_upgrade",
)


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.neox_probe,
    pytest.mark.destructive,
    pytest.mark.mutating,
    pytest.mark.readwrite,
]


@pytest.mark.parametrize("group_name", PROBE_GROUPS, ids=PROBE_GROUPS)
def test_neox_ont_config_cli_first_rest_probe(
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
    remote_xont = f"{target.ont_slot_id}-{target.ont_port_id}-{target.ont_id}"
    path = neox_config_service.ont_path()
    base_payload = ont_config_payload(target)
    probe_payload = materialize_probe_payload(catalog, group, target)
    cli_commands = materialize_commands(group.get("cli_first_commands", []), target)
    cleanup_commands = materialize_commands(group.get("cleanup_commands", default_cleanup_commands(group_name)), target)

    if not cli_commands:
        pytest.skip(f"{group_name} has no confirmed CLI-first command mapping yet.")

    ensure_probe_dependencies(api_client, neox_config_service, readwrite_session, cleanup_registry, group_name)

    cleanup_registry.add(lambda: api_client.request("POST", path, session=readwrite_session, json=base_payload))
    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))
    cleanup_registry.add(lambda: run_ont_config_commands(env_config, remote_xont, cleanup_commands))

    api_client.request("DELETE", path, session=readwrite_session)
    response = api_client.request("POST", path, session=readwrite_session, json=base_payload)
    assert_api_success(response)

    run_ont_config_commands(env_config, remote_xont, cli_commands)
    assert_cli_tokens(env_config, target, catalog, group, "cli_first")

    run_ont_config_commands(env_config, remote_xont, cleanup_commands)
    api_client.request("DELETE", path, session=readwrite_session)
    response = api_client.request("POST", path, session=readwrite_session, json=probe_payload)
    assert_api_success(response)
    assert_cli_tokens(env_config, target, catalog, group, "rest_probe")


def require_requested_probe_group(group_name: str) -> None:
    requested = {
        value.strip()
        for value in os.environ.get("NEOX_ONT_PROBE_GROUPS", "").split(",")
        if value.strip()
    }
    if group_name not in requested:
        pytest.skip(f"Set NEOX_ONT_PROBE_GROUPS={group_name} to run this ONT probe group.")


def require_high_risk_opt_in(group_name: str, group: dict[str, Any]) -> None:
    if group.get("risk") != "high":
        return
    if group_name == "firmware_upgrade" and not truthy_env("NEOX_ONT_ALLOW_FIRMWARE_PROBE"):
        pytest.skip("Firmware ONT probe requires NEOX_ONT_ALLOW_FIRMWARE_PROBE=1.")
    if not truthy_env("NEOX_ONT_ALLOW_HIGH_RISK_PROBE"):
        pytest.skip("High-risk ONT probe requires NEOX_ONT_ALLOW_HIGH_RISK_PROBE=1.")


def truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def ensure_probe_dependencies(api_client, neox_config_service, session_id: str, cleanup_registry, group_name: str) -> None:
    if group_name != "service_tcont":
        return
    profile_type = "ONTBandwidthProfile"
    path = neox_config_service.neox_profile_path(profile_type)
    payload = neox_config_service.neox_profile_boundary_payload(profile_type, "max")
    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=session_id))
    neox_config_service.delete_neox_profile_if_exists(path, session_id)
    response = api_client.request("POST", path, session=session_id, json=payload)
    assert_api_success(response)


def load_catalog() -> dict[str, Any]:
    return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))


def materialize_probe_payload(catalog: dict[str, Any], group: dict[str, Any], target) -> dict[str, Any]:
    content: dict[str, Any] = {}
    for field in group["fields"]:
        value = catalog["fields"][field]["candidate_value"]
        content[field] = materialize_value(value, target)
    return {"Content": content}


def materialize_value(value: Any, target) -> Any:
    if isinstance(value, str):
        return (
            value.replace("{ont_sn}", target.ont_sn)
            .replace("{ont_password}", target.ont_password)
            .replace("{ont_fw_image}", ont_fw_image(target))
        )
    if isinstance(value, list):
        return [materialize_value(item, target) for item in value]
    if isinstance(value, dict):
        return {key: materialize_value(item, target) for key, item in value.items()}
    return copy.deepcopy(value)


def materialize_commands(commands: list[str], target) -> list[str]:
    return [
        command.replace("{ont_sn}", target.ont_sn)
        .replace("{ont_password}", target.ont_password)
        .replace("{ont_fw_image}", ont_fw_image(target))
        for command in commands
    ]


def ont_fw_image(target) -> str:
    return str(getattr(target, "ont_fw_image", "") or "V542ABYY2Z0")


def default_cleanup_commands(group_name: str) -> list[str]:
    return {
        "ip_host_dynamic": ["no ip-host"],
        "ip_host_static": ["no ip-host"],
        "dspir": ["no ds-pir"],
        "service_tcont": ["no service all", "no tcont all"],
        "fdbmac": ["no fdb mac 00:11:22:33:44:55 vlan 1314 cvlan 1314"],
        "wifi_wan_voip": ["no wifi all", "no wan", "no voip"],
        "firmware_upgrade": ["no ont-fw-upgrade mode", "no ont-fw-upgrade fw-id", "no ont-fw-upgrade omci-method"],
    }.get(group_name, [])


def run_ont_config_commands(env_config, remote_xont: str, commands: list[str]) -> dict[str, str]:
    if not commands:
        return {}
    credentials = neox_cli_credentials(env_config, "ONT")
    cli_sequence = ["configure", f"interface remote xont {remote_xont}", *commands, "exit", "exit"]
    return run_neox_cli_commands(env_config, credentials, cli_sequence)


def assert_cli_tokens(env_config, target, catalog: dict[str, Any], group: dict[str, Any], phase: str) -> None:
    credentials = neox_cli_credentials(env_config, "ONT")
    remote_xont = f"{target.ont_slot_id}-{target.ont_port_id}-{target.ont_id}"
    commands = [
        f"show running-config interface xpon {target.ont_slot_id}-{target.ont_port_id}",
        f"show interface remote xont sn {target.ont_sn}",
    ]
    output_by_command = run_neox_cli_commands(env_config, credentials, commands)
    expected_tokens = expected_group_tokens(catalog, group, target, remote_xont)
    combined_output = "\n".join(output_by_command.values())
    missing = missing_tokens(combined_output, expected_tokens)
    assert not missing, f"Missing ONT CLI tokens after {phase}: {missing}"


def expected_group_tokens(catalog: dict[str, Any], group: dict[str, Any], target, remote_xont: str) -> list[str]:
    tokens = [f"interface remote xont {remote_xont}"]
    for field in group["fields"]:
        metadata = catalog["fields"][field]
        for token in expected_tokens_from_metadata(metadata):
            tokens.append(
                token.replace("{ont_sn}", target.ont_sn)
                .replace("{ont_sn_cli}", neox_cli_sn(target.ont_sn))
                .replace("{ont_password}", target.ont_password)
                .replace("{ont_fw_image}", ont_fw_image(target))
            )
    return [token for token in tokens if token]


def expected_tokens_from_metadata(metadata: dict[str, Any]) -> list[str]:
    if metadata.get("cli_expected_token"):
        return [metadata["cli_expected_token"]]
    if metadata.get("cli_expected_tokens"):
        return list(metadata["cli_expected_tokens"])
    return []
