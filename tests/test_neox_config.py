from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from services.neox_config.service import (
    GE_FULL_ACCEPTED_PAYLOAD_FILE,
    ge_port_payload,
    materialize_ont_payload,
    nni_min_payload,
    ont_config_payload,
    vlan_case,
)
from tests.support.neox_cli_verification import (
    missing_tokens,
    missing_tokens_by_command,
    neox_cli_credentials,
    run_neox_cli_commands,
    write_neox_cli_verify_report,
)
from tests.support.connectivity import assert_ping_reachable
from utils.assertions import assert_api_success


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.destructive,
]


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ge_config_clear_readwrite(api_client, env_config, neox_config_service, readwrite_session, cleanup_registry):
    with neox_config_connectivity_guard(env_config, "ge", "clear"):
        neox_config_service.verify_required_target_data()
        target = neox_config_service.target()
        command = f"show running-config interface ge {target.ge_slot_id}-{target.ge_port_id}"
        verify_clear_restores_cli_output(
            api_client,
            env_config,
            neox_config_service,
            readwrite_session,
            cleanup_registry,
            "ge",
            "clear",
            neox_config_service.ge_path(),
            ge_port_payload(),
            [command],
            target_extra={"ge_slot_id": target.ge_slot_id, "ge_port_id": target.ge_port_id},
        )


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ge_config_min_create_readwrite(
    api_client,
    env_config,
    neox_config_service,
    readwrite_session,
    cleanup_registry,
):
    with neox_config_connectivity_guard(env_config, "ge", "min"):
        neox_config_service.verify_required_target_data()
        credentials = neox_cli_credentials(env_config, "GE")

        cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session))
        api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)
        payload = ge_port_payload()
        response = api_client.request("POST", neox_config_service.ge_path(), session=readwrite_session, json=payload)
        assert_api_success(response)

        target = neox_config_service.target()
        command = f"show running-config interface ge {target.ge_slot_id}-{target.ge_port_id}"
        output_by_command = run_neox_cli_commands(env_config, credentials, [command])
        assert_neox_config_node_reachable(env_config, "ge", "min", "after_cli_verify")
        checks = ge_cli_checks(payload["Content"])
        missing = missing_tokens(output_by_command[command], checks)
        report_path = write_neox_cli_verify_report(
            neox_config_service,
            "ge",
            "min",
            neox_config_service.ge_path(),
            payload,
            response,
            output_by_command,
            {command: checks},
            {command: missing},
            target_extra={"ge_slot_id": target.ge_slot_id, "ge_port_id": target.ge_port_id},
        )

        assert not missing, f"Missing GE running-config lines: {missing}. Report: {report_path}"


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ge_config_max_create_readwrite(
    api_client,
    env_config,
    neox_config_service,
    readwrite_session,
    cleanup_registry,
):
    with neox_config_connectivity_guard(env_config, "ge", "max"):
        neox_config_service.verify_required_target_data()
        credentials = neox_cli_credentials(env_config, "GE")

        config = json.loads(GE_FULL_ACCEPTED_PAYLOAD_FILE.read_text(encoding="utf-8"))
        payload = config["payload"]
        expected_lines = config["running_config_visible_lines"]

        cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session))
        api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)
        response = api_client.request("POST", neox_config_service.ge_path(), session=readwrite_session, json=payload)
        assert_api_success(response)

        target = neox_config_service.target()
        command = f"show running-config interface ge {target.ge_slot_id}-{target.ge_port_id}"
        output_by_command = run_neox_cli_commands(env_config, credentials, [command])
        assert_neox_config_node_reachable(env_config, "ge", "max", "after_cli_verify")
        missing = missing_tokens(output_by_command[command], expected_lines)
        report_path = write_neox_cli_verify_report(
            neox_config_service,
            "ge",
            "max",
            neox_config_service.ge_path(),
            payload,
            response,
            output_by_command,
            {command: expected_lines},
            {command: missing},
            target_extra={"ge_slot_id": target.ge_slot_id, "ge_port_id": target.ge_port_id},
        )

        assert not missing, f"Missing GE running-config lines: {missing}. Report: {report_path}"


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ge_config_error_readwrite(env_config, neox_config_service, readwrite_session):
    with neox_config_connectivity_guard(env_config, "ge", "error"):
        neox_config_service.verify_ge_config_invalid_payload(readwrite_session)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_nni_config_clear_readwrite(api_client, env_config, neox_config_service, readwrite_session, cleanup_registry):
    with neox_config_connectivity_guard(env_config, "nni", "clear"):
        neox_config_service.verify_required_target_data()
        target = neox_config_service.target()
        command = f"show running-config interface nni {target.nni_port_id}"
        verify_clear_restores_cli_output(
            api_client,
            env_config,
            neox_config_service,
            readwrite_session,
            cleanup_registry,
            "nni",
            "clear",
            neox_config_service.nni_path(),
            nni_min_payload(),
            [command],
            target_extra={"nni_slot_id": target.nni_slot_id, "nni_port_id": target.nni_port_id},
        )


@pytest.mark.mutating
@pytest.mark.readwrite
def test_nni_config_error_readwrite(env_config, neox_config_service, readwrite_session):
    with neox_config_connectivity_guard(env_config, "nni", "error"):
        neox_config_service.verify_nni_config_invalid_payload(readwrite_session)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_vlan_config_min_create_readwrite(api_client, env_config, neox_config_service, readwrite_session, cleanup_registry):
    with neox_config_connectivity_guard(env_config, "vlan", "min"):
        verify_vlan_config_create_cli_verified(
            api_client, env_config, neox_config_service, readwrite_session, cleanup_registry, "min"
        )


@pytest.mark.mutating
@pytest.mark.readwrite
def test_vlan_config_max_create_readwrite(api_client, env_config, neox_config_service, readwrite_session, cleanup_registry):
    with neox_config_connectivity_guard(env_config, "vlan", "max"):
        verify_vlan_config_create_cli_verified(
            api_client, env_config, neox_config_service, readwrite_session, cleanup_registry, "max"
        )


@pytest.mark.mutating
@pytest.mark.readwrite
def test_vlan_config_clear_readwrite(api_client, env_config, neox_config_service, readwrite_session, cleanup_registry):
    with neox_config_connectivity_guard(env_config, "vlan", "clear"):
        neox_config_service.verify_required_target_data()
        vid, payload = vlan_case("max")
        verify_clear_restores_cli_output(
            api_client,
            env_config,
            neox_config_service,
            readwrite_session,
            cleanup_registry,
            "vlan",
            "clear",
            neox_config_service.vlan_path_for_vid(vid),
            payload,
            [f"show vlan {vid}"],
        )


@pytest.mark.mutating
@pytest.mark.readwrite
def test_vlan_config_error_readwrite(env_config, neox_config_service, readwrite_session):
    with neox_config_connectivity_guard(env_config, "vlan", "error"):
        neox_config_service.verify_vlan_config_invalid_payload(readwrite_session)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_config_min_create_readwrite(api_client, env_config, neox_config_service, readwrite_session, cleanup_registry):
    with neox_config_connectivity_guard(env_config, "ont", "min"):
        verify_ont_config_create_cli_verified(
            api_client, env_config, neox_config_service, readwrite_session, cleanup_registry, "min"
        )


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_config_max_create_readwrite(api_client, env_config, neox_config_service, readwrite_session, cleanup_registry):
    with neox_config_connectivity_guard(env_config, "ont", "max"):
        verify_ont_config_create_cli_verified(
            api_client, env_config, neox_config_service, readwrite_session, cleanup_registry, "max"
        )


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_config_clear_readwrite(api_client, env_config, neox_config_service, readwrite_session, cleanup_registry):
    with neox_config_connectivity_guard(env_config, "ont", "clear"):
        neox_config_service.verify_required_target_data()
        target = neox_config_service.target()
        xpon = f"{target.ont_slot_id}-{target.ont_port_id}"
        commands = [
            f"show running-config interface xpon {xpon}",
            f"show interface remote xont sn {target.ont_sn}",
        ]
        verify_clear_restores_cli_output(
            api_client,
            env_config,
            neox_config_service,
            readwrite_session,
            cleanup_registry,
            "ont",
            "clear",
            neox_config_service.ont_path(),
            ont_config_payload(target),
            commands,
            target_extra={"ont_slot_id": target.ont_slot_id, "ont_port_id": target.ont_port_id, "ont_id": target.ont_id},
        )


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_config_error_readwrite(env_config, neox_config_service, readwrite_session):
    with neox_config_connectivity_guard(env_config, "ont", "error"):
        neox_config_service.verify_ont_config_invalid_payload(readwrite_session)


@contextmanager
def neox_config_connectivity_guard(env_config, feature: str, case_name: str) -> Iterator[None]:
    assert_neox_config_node_reachable(env_config, feature, case_name, "before_case")
    try:
        yield
    finally:
        assert_neox_config_node_reachable(env_config, feature, case_name, "after_case")


def assert_neox_config_node_reachable(env_config, feature: str, case_name: str, checkpoint: str) -> None:
    assert_ping_reachable(
        env_config.dut.device_ip,
        checkpoint,
        context={
            "node": env_config.dut.node_key,
            "feature": feature,
            "case": case_name,
        },
    )


def verify_vlan_config_create_cli_verified(
    api_client,
    env_config,
    neox_config_service,
    readwrite_session: str,
    cleanup_registry,
    case_name: str,
) -> None:
    neox_config_service.verify_required_target_data()
    credentials = neox_cli_credentials(env_config, "VLAN")
    vid, payload = vlan_case(case_name)
    path = neox_config_service.vlan_path_for_vid(vid)

    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))
    api_client.request("DELETE", path, session=readwrite_session)
    response = api_client.request("POST", path, session=readwrite_session, json=payload)
    assert_api_success(response)

    command = f"show vlan {vid}"
    output_by_command = run_neox_cli_commands(env_config, credentials, [command])
    assert_neox_config_node_reachable(env_config, "vlan", case_name, "after_cli_verify")
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


def verify_ont_config_create_cli_verified(
    api_client,
    env_config,
    neox_config_service,
    readwrite_session: str,
    cleanup_registry,
    case_name: str,
) -> None:
    neox_config_service.verify_required_target_data()
    credentials = neox_cli_credentials(env_config, "ONT")
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
    output_by_command = run_neox_cli_commands(env_config, credentials, list(command_by_name.values()))
    assert_neox_config_node_reachable(env_config, "ont", case_name, "after_cli_verify")
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


def verify_clear_restores_cli_output(
    api_client,
    env_config,
    neox_config_service,
    session_id: str,
    cleanup_registry,
    feature: str,
    case_name: str,
    path: str,
    payload: dict[str, Any],
    commands: list[str],
    target_extra: dict[str, Any] | None = None,
) -> None:
    credentials = neox_cli_credentials(env_config, feature.upper())
    api_client.request("DELETE", path, session=session_id)
    baseline_by_command = run_neox_cli_commands(env_config, credentials, commands)

    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=session_id))
    response = api_client.request("POST", path, session=session_id, json=payload)
    assert_api_success(response)
    response = api_client.request("DELETE", path, session=session_id)
    assert_api_success(response)

    output_by_command = run_neox_cli_commands(env_config, credentials, commands)
    assert_neox_config_node_reachable(env_config, feature, case_name, "after_cli_verify")
    mismatch_by_command = {
        command: [
            "running-config differs after REST clear",
        ]
        for command in commands
        if normalize_cli_output(output_by_command.get(command, ""))
        != normalize_cli_output(baseline_by_command.get(command, ""))
    }
    report_path = write_neox_cli_verify_report(
        neox_config_service,
        feature,
        case_name,
        path,
        payload,
        response,
        output_by_command,
        {command: [normalize_cli_output(baseline_by_command.get(command, ""))] for command in commands},
        mismatch_by_command,
        target_extra=target_extra,
    )

    assert not mismatch_by_command, f"CLI output did not return to clear baseline after {feature} clear: {report_path}"


def normalize_cli_output(output: str) -> str:
    lines = [line.rstrip() for line in output.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line.strip())


def ge_cli_checks(content: dict[str, Any]) -> list[str]:
    checks = []
    if content.get("portenable") == "enable":
        checks.append("enable")
    if "auto_nego" in content:
        checks.append(f"auto-negotiation {content['auto_nego']}")
    if "flow" in content:
        checks.append(f"flow-control {content['flow']}")
    if "portspeed" in content:
        checks.append(f"speed {content['portspeed']}")
    if "portname" in content:
        checks.append(f"name \"{content['portname']}\"")
    if "arpinspection" in content:
        checks.append(f"arp-inspection {content['arpinspection']}")
    if "copycpbit" in content:
        checks.append(f"vlan copy_cpbit {content['copycpbit']}")
    if "outertpid" in content:
        checks.append(f"vlan outer-tpid {content['outertpid']}")
    if "frametype" in content:
        checks.append(f"frame-type {content['frametype']}")
    return checks


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
