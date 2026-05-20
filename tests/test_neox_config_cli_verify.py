from __future__ import annotations

from typing import Any

import pytest

from services.neox_config.service import materialize_ont_payload, ont_config_payload, vlan_case
from tests.support.neox_cli_verification import (
    missing_tokens,
    missing_tokens_by_command,
    neox_cli_credentials,
    run_neox_cli_commands,
    write_neox_cli_verify_report,
)
from utils.assertions import assert_api_success


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.destructive,
    pytest.mark.mutating,
    pytest.mark.readwrite,
]


@pytest.mark.parametrize("case_name", ["min", "max"])
def test_vlan_config_create_cli_verified(
    api_client,
    env_config,
    neox_config_service,
    readwrite_session,
    cleanup_registry,
    case_name,
):
    neox_config_service.verify_required_target_data()
    ssh_username, ssh_password = neox_cli_credentials(env_config, "VLAN")
    vid, payload = vlan_case(case_name)
    path = neox_config_service.vlan_path_for_vid(vid)

    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))
    api_client.request("DELETE", path, session=readwrite_session)
    response = api_client.request("POST", path, session=readwrite_session, json=payload)
    assert_api_success(response)

    command = f"show vlan {vid}"
    output_by_command = run_neox_cli_commands(env_config, (ssh_username, ssh_password), [command])
    expected_tokens = vlan_expected_tokens(vid, payload)
    expected_port_states = vlan_expected_port_states(payload)
    expected_checks = expected_tokens + vlan_port_state_checks(expected_port_states)
    missing = missing_tokens(output_by_command[command], expected_tokens)
    missing.extend(missing_vlan_port_states(output_by_command[command], vid, expected_port_states))
    report_path = write_neox_cli_verify_report(
        neox_config_service,
        "vlan",
        case_name,
        path,
        payload,
        response,
        output_by_command,
        {command: expected_checks},
        {command: missing},
    )

    assert not missing, f"Missing VLAN CLI tokens for VID {vid}: {missing}. Report: {report_path}"


@pytest.mark.parametrize("case_name", ["min", "max"])
def test_ont_config_create_cli_verified(
    api_client,
    env_config,
    neox_config_service,
    readwrite_session,
    cleanup_registry,
    case_name,
):
    neox_config_service.verify_required_target_data()
    ssh_username, ssh_password = neox_cli_credentials(env_config, "ONT")
    target = neox_config_service.target()
    payload = materialize_ont_payload(case_name, target)
    restore_payload = ont_config_payload(target)
    path = neox_config_service.ont_path()

    cleanup_registry.add(lambda: api_client.request("POST", path, session=readwrite_session, json=restore_payload))
    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))
    api_client.request("DELETE", path, session=readwrite_session)
    response = api_client.request("POST", path, session=readwrite_session, json=payload)
    assert_api_success(response)

    xpon = f"{target.ont_slot_id}-{target.ont_port_id}"
    remote_xont = f"{xpon}-{target.ont_id}"
    command_by_name = {
        "running-config": f"show running-config interface xpon {xpon}",
        "xont-by-sn": f"show interface remote xont sn {target.ont_sn}",
    }
    output_by_command = run_neox_cli_commands(env_config, (ssh_username, ssh_password), list(command_by_name.values()))
    expected_by_command = {
        command_by_name["running-config"]: ont_running_config_tokens(remote_xont, payload["Content"]),
        command_by_name["xont-by-sn"]: [remote_xont],
    }
    missing_by_command = missing_tokens_by_command(output_by_command, expected_by_command)
    report_path = write_neox_cli_verify_report(
        neox_config_service,
        "ont",
        case_name,
        path,
        payload,
        response,
        output_by_command,
        expected_by_command,
        missing_by_command,
    )

    missing = {command: tokens for command, tokens in missing_by_command.items() if tokens}
    assert not missing, f"Missing ONT CLI tokens for {remote_xont}: {missing}. Report: {report_path}"


def vlan_expected_tokens(vid: str, payload: dict[str, Any]) -> list[str]:
    tokens = [vid, f"VLAN Name: {payload['vlanname']}"]
    if payload.get("tpid") == "qinq-tpid":
        tokens.append("QinQ")
    elif payload.get("tpid") == "default-tpid":
        tokens.append("default")
    return tokens


def vlan_expected_port_states(payload: dict[str, Any]) -> dict[int, str]:
    fixed_ports = parse_vlan_ports(payload.get("fixedport"))
    untagged_ports = parse_vlan_ports(payload.get("untaggedport"))
    forbidden_ports = parse_vlan_ports(payload.get("forbiddenport"))
    conflicts = untagged_ports & forbidden_ports
    if conflicts:
        raise AssertionError(f"VLAN payload has overlapping untaggedport/forbiddenport values: {sorted(conflicts)}")

    states: dict[int, str] = {}
    for port in range(1, 13):
        if port in forbidden_ports:
            states[port] = "X"
        elif port in fixed_ports and port in untagged_ports:
            states[port] = "U"
        elif port in fixed_ports:
            states[port] = "T"
        else:
            states[port] = "."
    return states


def parse_vlan_ports(value: Any) -> set[int]:
    if value in (None, ""):
        return set()
    ports: set[int] = set()
    for part in str(value).replace(" ", "").split(","):
        if not part:
            continue
        if "~" in part:
            start, end = part.split("~", 1)
            ports.update(range(int(start), int(end) + 1))
        else:
            ports.add(int(part))
    return ports


def vlan_port_state_checks(expected_states: dict[int, str]) -> list[str]:
    return [f"port {port}={state}" for port, state in sorted(expected_states.items())]


def missing_vlan_port_states(output: str, vid: str, expected_states: dict[int, str]) -> list[str]:
    actual_states = parse_vlan_cli_port_states(output, vid)
    if not actual_states and expected_states:
        return [f"vlan {vid} port table"]
    return [
        f"port {port}={expected_state}"
        for port, expected_state in sorted(expected_states.items())
        if actual_states.get(port) != expected_state
    ]


def parse_vlan_cli_port_states(output: str, vid: str) -> dict[int, str]:
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 13 and parts[0] == vid:
            return {port: parts[port] for port in range(1, 13)}
    return {}


def ont_running_config_tokens(remote_xont: str, content: dict[str, Any]) -> list[str]:
    tokens = [f"interface remote xont {remote_xont}", f"sn {neox_cli_sn(content['sn'])}"]
    registid = content.get("registid")
    if registid:
        tokens.append(f"registration-id {registid}")
    description = content.get("ontdescription")
    if description:
        tokens.append(f"description {description}")
    if content.get("adminstate") == "enable":
        tokens.append("adminstate enable")
    if content.get("ontenable") == "enable":
        tokens.append("no inactive")
    return tokens


def neox_cli_sn(sn: str) -> str:
    try:
        raw = bytes.fromhex(sn)
    except ValueError:
        return sn
    prefix = raw[:4]
    if all(32 <= byte < 127 for byte in prefix):
        return prefix.decode("ascii") + sn[8:]
    return sn
