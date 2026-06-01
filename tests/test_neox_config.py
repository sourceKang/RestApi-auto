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
from services.neox_config.cli_expectations import (
    clear_ignored_line_prefixes,
    ge_cli_checks,
    normalize_cli_output,
    ont_running_config_tokens,
    vlan_cli_expectation,
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
def test_ge_config_clear_readwrite(api_client, env_config, neox_config_service, readwrite_session, cleanup_registry, request):
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
            request,
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
    request,
):
    with neox_config_connectivity_guard(env_config, "ge", "min"):
        neox_config_service.verify_required_target_data()

        cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session))
        api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)
        payload = ge_port_payload()
        response = api_client.request("POST", neox_config_service.ge_path(), session=readwrite_session, json=payload)
        assert_api_success(response)
        if skip_neox_cli_verify(request):
            return

        credentials = neox_cli_credentials(env_config, "GE")
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
    request,
):
    with neox_config_connectivity_guard(env_config, "ge", "max"):
        neox_config_service.verify_required_target_data()

        config = json.loads(GE_FULL_ACCEPTED_PAYLOAD_FILE.read_text(encoding="utf-8"))
        payload = config["payload"]
        expected_lines = config["running_config_visible_lines"]

        cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session))
        api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)
        response = api_client.request("POST", neox_config_service.ge_path(), session=readwrite_session, json=payload)
        assert_api_success(response)
        if skip_neox_cli_verify(request):
            return

        credentials = neox_cli_credentials(env_config, "GE")
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
@pytest.mark.skip(reason="NeoX error-readwrite cases are not complete yet.")
def test_ge_config_error_readwrite(env_config, neox_config_service, readwrite_session):
    with neox_config_connectivity_guard(env_config, "ge", "error"):
        neox_config_service.verify_ge_config_invalid_payload(readwrite_session)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_nni_config_clear_readwrite(api_client, env_config, neox_config_service, readwrite_session, cleanup_registry, request):
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
            request,
            target_extra={"nni_slot_id": target.nni_slot_id, "nni_port_id": target.nni_port_id},
        )


@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.skip(reason="NeoX error-readwrite cases are not complete yet.")
def test_nni_config_error_readwrite(env_config, neox_config_service, readwrite_session):
    with neox_config_connectivity_guard(env_config, "nni", "error"):
        neox_config_service.verify_nni_config_invalid_payload(readwrite_session)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_vlan_config_min_create_readwrite(api_client, env_config, neox_config_service, readwrite_session, cleanup_registry, request):
    with neox_config_connectivity_guard(env_config, "vlan", "min"):
        verify_vlan_config_create_cli_verified(
            api_client, env_config, neox_config_service, readwrite_session, cleanup_registry, "min", request
        )


@pytest.mark.mutating
@pytest.mark.readwrite
def test_vlan_config_max_create_readwrite(api_client, env_config, neox_config_service, readwrite_session, cleanup_registry, request):
    with neox_config_connectivity_guard(env_config, "vlan", "max"):
        verify_vlan_config_create_cli_verified(
            api_client, env_config, neox_config_service, readwrite_session, cleanup_registry, "max", request
        )


@pytest.mark.mutating
@pytest.mark.readwrite
def test_vlan_config_clear_readwrite(api_client, env_config, neox_config_service, readwrite_session, cleanup_registry, request):
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
            request,
        )


@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.skip(reason="NeoX error-readwrite cases are not complete yet.")
def test_vlan_config_error_readwrite(env_config, neox_config_service, readwrite_session):
    with neox_config_connectivity_guard(env_config, "vlan", "error"):
        neox_config_service.verify_vlan_config_invalid_payload(readwrite_session)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_config_min_create_readwrite(api_client, env_config, neox_config_service, readwrite_session, cleanup_registry, request):
    with neox_config_connectivity_guard(env_config, "ont", "min"):
        verify_ont_config_create_cli_verified(
            api_client, env_config, neox_config_service, readwrite_session, cleanup_registry, "min", request
        )


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_config_max_create_readwrite(api_client, env_config, neox_config_service, readwrite_session, cleanup_registry, request):
    with neox_config_connectivity_guard(env_config, "ont", "max"):
        verify_ont_config_create_cli_verified(
            api_client, env_config, neox_config_service, readwrite_session, cleanup_registry, "max", request
        )


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_config_clear_readwrite(api_client, env_config, neox_config_service, readwrite_session, cleanup_registry, request):
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
            request,
            target_extra={"ont_slot_id": target.ont_slot_id, "ont_port_id": target.ont_port_id, "ont_id": target.ont_id},
        )


@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.skip(reason="NeoX error-readwrite cases are not complete yet.")
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


def skip_neox_cli_verify(request) -> bool:
    return bool(request.config.getoption("--skip-neox-cli-verify"))


def verify_vlan_config_create_cli_verified(
    api_client,
    env_config,
    neox_config_service,
    readwrite_session: str,
    cleanup_registry,
    case_name: str,
    request,
) -> None:
    neox_config_service.verify_required_target_data()
    vid, payload = vlan_case(case_name)
    path = neox_config_service.vlan_path_for_vid(vid)

    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))
    api_client.request("DELETE", path, session=readwrite_session)
    response = api_client.request("POST", path, session=readwrite_session, json=payload)
    assert_api_success(response)
    if skip_neox_cli_verify(request):
        return

    credentials = neox_cli_credentials(env_config, "VLAN")
    command = f"show vlan {vid}"
    output_by_command = run_neox_cli_commands(env_config, credentials, [command])
    assert_neox_config_node_reachable(env_config, "vlan", case_name, "after_cli_verify")
    expectation = vlan_cli_expectation(vid, payload, output_by_command[command])
    report_path = write_neox_cli_verify_report(
        neox_config_service,
        "vlan",
        case_name,
        path,
        payload,
        response,
        output_by_command,
        {command: expectation.expected_checks},
        {command: expectation.missing},
    )

    assert not expectation.missing, f"Missing VLAN CLI tokens for VID {vid}: {expectation.missing}. Report: {report_path}"


def verify_ont_config_create_cli_verified(
    api_client,
    env_config,
    neox_config_service,
    readwrite_session: str,
    cleanup_registry,
    case_name: str,
    request,
) -> None:
    neox_config_service.verify_required_target_data()
    target = neox_config_service.target()
    payload = materialize_ont_payload(case_name, target)
    restore_payload = ont_config_payload(target)
    path = neox_config_service.ont_path()

    cleanup_registry.add(lambda: api_client.request("POST", path, session=readwrite_session, json=restore_payload))
    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))
    api_client.request("DELETE", path, session=readwrite_session)
    response = api_client.request("POST", path, session=readwrite_session, json=payload)
    assert_api_success(response)
    if skip_neox_cli_verify(request):
        return

    credentials = neox_cli_credentials(env_config, "ONT")
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
    request,
    target_extra: dict[str, Any] | None = None,
) -> None:
    api_client.request("DELETE", path, session=session_id)
    if not skip_neox_cli_verify(request):
        credentials = neox_cli_credentials(env_config, feature.upper())
        baseline_by_command = run_neox_cli_commands(env_config, credentials, commands)
    else:
        credentials = None
        baseline_by_command = {}

    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=session_id))
    response = api_client.request("POST", path, session=session_id, json=payload)
    assert_api_success(response)
    response = api_client.request("DELETE", path, session=session_id)
    assert_api_success(response)
    if skip_neox_cli_verify(request):
        return

    assert credentials is not None
    output_by_command = run_neox_cli_commands(env_config, credentials, commands)
    assert_neox_config_node_reachable(env_config, feature, case_name, "after_cli_verify")
    ignored_line_prefixes = clear_ignored_line_prefixes(feature)
    mismatch_by_command = {
        command: [
            "running-config differs after REST clear",
        ]
        for command in commands
        if normalize_cli_output(output_by_command.get(command, ""), ignored_line_prefixes)
        != normalize_cli_output(baseline_by_command.get(command, ""), ignored_line_prefixes)
    }
    report_path = write_neox_cli_verify_report(
        neox_config_service,
        feature,
        case_name,
        path,
        payload,
        response,
        output_by_command,
        {
            command: [normalize_cli_output(baseline_by_command.get(command, ""), ignored_line_prefixes)]
            for command in commands
        },
        mismatch_by_command,
        target_extra=target_extra,
        metadata={
            "clear_compare": {
                "ignored_line_prefixes": list(ignored_line_prefixes),
            },
        },
    )

    assert not mismatch_by_command, f"CLI output did not return to clear baseline after {feature} clear: {report_path}"
