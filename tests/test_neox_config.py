from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from models.api import SessionRole
from services.neox_config.service import (
    GE_FULL_ACCEPTED_PAYLOAD_FILE,
    GE_NEGATIVE_CASES_FILE,
    ge_port_payload,
    materialize_ont_payload,
    nni_min_payload,
    ont_negative_cases,
    ont_negative_payload,
    ont_config_payload,
    vlan_case,
)
from services.neox_config.cli_expectations import (
    clear_ignored_line_prefixes,
    ge_cli_checks,
    neox_cli_sn,
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
from utils.allure_helpers import attach_json
from utils.redaction import redact


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
        response = post_neox_config_payload(
            api_client,
            neox_config_service.ge_path(),
            readwrite_session,
            payload,
            config.get("rest_timeout_seconds"),
        )
        assert_api_success(response)
        if skip_neox_cli_verify(request):
            return

        credentials = neox_cli_credentials(env_config, "GE")
        target = neox_config_service.target()
        command = f"show running-config interface ge {target.ge_slot_id}-{target.ge_port_id}"
        additional_checks = materialize_ge_additional_cli_checks(config.get("additional_cli_visible_checks", {}), target)
        commands = [command, *additional_checks]
        output_by_command = run_neox_cli_commands(env_config, credentials, commands)
        assert_neox_config_node_reachable(env_config, "ge", "max", "after_cli_verify")
        expected_by_command = {command: expected_lines, **additional_checks}
        missing_by_command = missing_tokens_by_command(output_by_command, expected_by_command)
        missing = {item: tokens for item, tokens in missing_by_command.items() if tokens}
        report_path = write_neox_cli_verify_report(
            neox_config_service,
            "ge",
            "max",
            neox_config_service.ge_path(),
            payload,
            response,
            output_by_command,
            expected_by_command,
            missing_by_command,
            target_extra={"ge_slot_id": target.ge_slot_id, "ge_port_id": target.ge_port_id},
        )

        assert not missing, f"Missing GE running-config lines: {missing}. Report: {report_path}"


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ge_config_error_readwrite(api_client, env_config, neox_config_service, readwrite_session, cleanup_registry, request):
    with neox_config_connectivity_guard(env_config, "ge", "error"):
        neox_config_service.verify_required_target_data()
        target = neox_config_service.target()
        verify_interface_config_error_cases(
            api_client,
            env_config,
            neox_config_service,
            readwrite_session,
            cleanup_registry,
            request,
            feature="ge",
            path=neox_config_service.ge_path(),
            cases=ge_config_negative_cases(),
            cli_commands=[f"show running-config interface ge {target.ge_slot_id}-{target.ge_port_id}"],
            target_extra={"ge_slot_id": target.ge_slot_id, "ge_port_id": target.ge_port_id},
        )


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
def test_nni_config_error_readwrite(api_client, env_config, neox_config_service, readwrite_session, cleanup_registry, request):
    with neox_config_connectivity_guard(env_config, "nni", "error"):
        neox_config_service.verify_required_target_data()
        target = neox_config_service.target()
        verify_interface_config_error_cases(
            api_client,
            env_config,
            neox_config_service,
            readwrite_session,
            cleanup_registry,
            request,
            feature="nni",
            path=neox_config_service.nni_path(),
            cases=nni_config_negative_cases(),
            cli_commands=[f"show running-config interface nni {target.nni_port_id}"],
            target_extra={"nni_slot_id": target.nni_slot_id, "nni_port_id": target.nni_port_id},
        )


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
def test_vlan_config_error_readwrite(api_client, env_config, neox_config_service, readwrite_session, cleanup_registry, request):
    with neox_config_connectivity_guard(env_config, "vlan", "error"):
        verify_interface_config_error_cases(
            api_client,
            env_config,
            neox_config_service,
            readwrite_session,
            cleanup_registry,
            request,
            feature="vlan",
            path=neox_config_service.vlan_path_for_vid("4094"),
            cases=vlan_config_negative_cases(),
            cli_commands=["show vlan 4094"],
        )


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
def test_ont_config_error_readwrite(
    api_client,
    env_config,
    neox_config_service,
    session_manager,
    readwrite_session,
    cleanup_registry,
    request,
):
    with neox_config_connectivity_guard(env_config, "ont", "error"):
        verify_ont_config_error_cases(
            api_client,
            env_config,
            neox_config_service,
            session_manager,
            readwrite_session,
            cleanup_registry,
            request,
        )


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


def materialize_ge_additional_cli_checks(raw_checks: dict[str, list[str]], target) -> dict[str, list[str]]:
    checks = {}
    replacements = {
        "{slot_id}": target.ge_slot_id,
        "{port_id}": target.ge_port_id,
    }
    for command, tokens in raw_checks.items():
        materialized_command = materialize_ge_template(command, replacements)
        checks[materialized_command] = [materialize_ge_template(token, replacements) for token in tokens]
    return checks


def materialize_ge_template(value: str, replacements: dict[str, str]) -> str:
    for placeholder, replacement in replacements.items():
        value = value.replace(placeholder, replacement)
    return value


def post_neox_config_payload(
    api_client,
    path: str,
    session_id: str,
    payload: dict,
    rest_timeout_seconds: int | float | None = None,
):
    original_timeout = api_client.timeout
    if rest_timeout_seconds:
        read_timeout = float(rest_timeout_seconds)
        if isinstance(original_timeout, tuple):
            api_client.timeout = (original_timeout[0], max(float(original_timeout[1]), read_timeout))
        else:
            api_client.timeout = (float(original_timeout), read_timeout)
    try:
        return api_client.request("POST", path, session=session_id, json=payload)
    finally:
        api_client.timeout = original_timeout


def ge_config_negative_cases() -> list[dict[str, Any]]:
    data = json.loads(GE_NEGATIVE_CASES_FILE.read_text(encoding="utf-8"))
    cases = []
    for raw_case in data["cases"]:
        payload = ge_port_payload()
        payload["Content"][raw_case["field"]] = raw_case["value"]
        cases.append(
            {
                "name": raw_case["name"],
                "field": raw_case.get("field"),
                "payload": payload,
                "expected_status_code": raw_case.get("expected_status_code"),
                "expected_retstatus": raw_case.get("expected_retstatus"),
                "expected_message_contains": raw_case.get("expected_message_contains"),
            }
        )
    return cases


def nni_config_negative_cases() -> list[dict[str, Any]]:
    payload = nni_min_payload()
    payload["Content"]["portenable"] = "invalid"
    return [
        {
            "name": "invalid_portenable",
            "field": "portenable",
            "payload": payload,
            "expected_retstatus": "Fail",
            "expected_message_contains": "Invalid JSON input",
        }
    ]


def vlan_config_negative_cases() -> list[dict[str, Any]]:
    return [
        {
            "name": "invalid_tpid",
            "field": "tpid",
            "payload": {"vlanname": "REST_API_BAD_VLAN", "tpid": "invalid-tpid"},
            "expected_retstatus": "Fail",
            "expected_message_contains": "Invalid JSON input",
        }
    ]


def verify_interface_config_error_cases(
    api_client,
    env_config,
    neox_config_service,
    readwrite_session: str,
    cleanup_registry,
    request,
    feature: str,
    path: str,
    cases: list[dict[str, Any]],
    cli_commands: list[str],
    target_extra: dict[str, Any] | None = None,
) -> None:
    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))
    observations = []
    failures = []
    for negative_case in cases:
        payload = negative_case["payload"]
        api_client.request("DELETE", path, session=readwrite_session)
        baseline_by_command = {}
        if not skip_neox_cli_verify(request):
            baseline_by_command = read_neox_cli_outputs(env_config, feature, cli_commands)
        response = api_client.request("POST", path, session=readwrite_session, json=payload)
        assert_invalid_config_post_did_not_succeed(feature, negative_case, response)
        cli_observation = {}
        cli_failures = []
        if not skip_neox_cli_verify(request):
            cli_observation, cli_failures = verify_invalid_post_kept_cli_unchanged(
                env_config,
                feature,
                negative_case,
                cli_commands,
                baseline_by_command,
            )
        observation = {
            "case": negative_case.get("name"),
            "field": negative_case.get("field"),
            "request": redact(payload),
            "expected": {
                "status_code": negative_case.get("expected_status_code"),
                "retstatus": negative_case.get("expected_retstatus"),
                "message_contains": negative_case.get("expected_message_contains"),
            },
            "response": {
                "status_code": response.status_code,
                "retstatus": response.retstatus,
                "retresult": response.retresult,
                "body": redact(response.json),
            },
            "cli": cli_observation,
        }
        observations.append(observation)
        try:
            assert_neox_config_error_response(negative_case, response)
            assert not cli_failures, (
                f"{feature} {negative_case['name']} invalid POST changed CLI output: {cli_failures}"
            )
        except AssertionError as error:
            failures.append({"case": negative_case.get("name"), "error": str(error), "observation": observation})

    report_path = write_neox_interface_error_report(neox_config_service, feature, path, observations, failures, target_extra)
    attach_json(
        f"NeoX {feature.upper()} error matrix",
        {"report": str(report_path), "failures": failures, "observations": observations},
    )
    assert not failures, f"{feature.upper()} config error matrix had {len(failures)} mismatches. Report: {report_path}"


def read_neox_cli_outputs(env_config, feature: str, commands: list[str]) -> dict[str, str]:
    credentials = neox_cli_credentials(env_config, f"{feature.upper()} error")
    return run_neox_cli_commands(env_config, credentials, commands)


def verify_invalid_post_kept_cli_unchanged(
    env_config,
    feature: str,
    negative_case: dict[str, Any],
    commands: list[str],
    baseline_by_command: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    output_by_command = read_neox_cli_outputs(env_config, feature, commands)
    ignored_prefixes = clear_ignored_line_prefixes(feature)
    diffs = []
    cli_by_command = {}
    for command in commands:
        baseline = normalize_cli_output(baseline_by_command.get(command, ""), ignored_prefixes)
        after = normalize_cli_output(output_by_command.get(command, ""), ignored_prefixes)
        cli_by_command[command] = {
            "baseline_lines": baseline.splitlines(),
            "after_invalid_post_lines": after.splitlines(),
            "unchanged": baseline == after,
        }
        if baseline != after:
            diffs.append(
                {
                    "command": command,
                    "baseline_lines": baseline.splitlines(),
                    "after_invalid_post_lines": after.splitlines(),
                }
            )
    observation = {
        "case": negative_case.get("name"),
        "commands": commands,
        "cli_by_command": cli_by_command,
    }
    attach_json(f"NeoX {feature.upper()} invalid POST CLI unchanged {negative_case.get('name')}", observation)
    return observation, diffs


def assert_invalid_config_post_did_not_succeed(feature: str, negative_case: dict[str, Any], response) -> None:
    if response.retstatus == "Success" and response.status_code < 400:
        pytest.fail(
            f"{feature} {negative_case['name']} invalid POST unexpectedly succeeded: "
            f"HTTP={response.status_code}, retstatus={response.retstatus!r}, body={response.text}"
        )


def write_neox_interface_error_report(
    neox_config_service,
    feature: str,
    path: str,
    observations: list[dict],
    failures: list[dict],
    target_extra: dict[str, Any] | None = None,
) -> Path:
    reports_dir = Path(__file__).resolve().parents[1] / "reports" / "device-verification"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"neox_config_{feature}_error_matrix_{timestamp}.json"
    target = neox_config_service.target()
    target_data = {
        "node": neox_config_service.env_config.dut.node_key,
        "device_ip": neox_config_service.env_config.dut.device_ip,
        "device_name": target.device_name,
    }
    if target_extra:
        target_data.update(target_extra)
    data = {
        "target": target_data,
        "rest_api": {"path": path},
        "workflow": (
            "Each invalid payload clears the target config before POST, asserts HTTP status, retstatus, "
            "and failure message, then compares CLI show output before and after the invalid POST to "
            "verify no config was applied."
        ),
        "summary": {
            "total": len(observations),
            "failures": len(failures),
        },
        "failures": failures,
        "observations": observations,
    }
    report_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path


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

    ensure_ont_template_dependency_if_needed(
        api_client,
        neox_config_service,
        readwrite_session,
        cleanup_registry,
        payload,
    )
    cleanup_registry.add(lambda: api_client.request("POST", path, session=readwrite_session, json=restore_payload))
    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))
    ensure_ont_firmware_cleanup_if_needed(env_config, cleanup_registry, payload, target)
    cleanup_ont_firmware_config_if_needed(env_config, payload, target)
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


def verify_ont_config_error_cases(
    api_client,
    env_config,
    neox_config_service,
    session_manager,
    readwrite_session: str,
    cleanup_registry,
    request,
) -> None:
    neox_config_service.verify_required_target_data()
    target = neox_config_service.target()
    path = neox_config_service.ont_path()
    restore_payload = ont_config_payload(target)

    cleanup_registry.add(lambda: api_client.request("POST", path, session=readwrite_session, json=restore_payload))
    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))

    observations = []
    failures = []
    for batch in batched_cases(ont_negative_cases(), size=8):
        with session_manager.role_session(SessionRole.READWRITE) as case_session:
            for negative_case in batch:
                payload = ont_negative_payload(negative_case, target)
                api_client.request("DELETE", path, session=case_session)
                response = api_client.request("POST", path, session=case_session, json=payload)
                assert_invalid_ont_post_did_not_succeed(negative_case, response)
                cli_observation = {}
                cli_failures = []
                if not skip_neox_cli_verify(request):
                    cli_observation, cli_failures = verify_ont_invalid_post_not_applied_cli(
                        env_config,
                        neox_config_service,
                        negative_case,
                    )
                observation = {
                    "case": negative_case.get("name"),
                    "field": negative_case.get("field"),
                    "request": redact(payload),
                    "expected": {
                        "status_code": negative_case.get("expected_status_code"),
                        "retstatus": negative_case.get("expected_retstatus"),
                        "message_contains": negative_case.get("expected_message_contains"),
                    },
                    "response": {
                        "status_code": response.status_code,
                        "retstatus": response.retstatus,
                        "retresult": response.retresult,
                        "body": redact(response.json),
                    },
                    "cli": cli_observation,
                }
                observations.append(observation)
                try:
                    assert_neox_config_error_response(negative_case, response)
                    assert not cli_failures, (
                        f"{negative_case['name']} invalid POST unexpectedly appeared in CLI output: {cli_failures}"
                    )
                except AssertionError as error:
                    failures.append({"case": negative_case.get("name"), "error": str(error), "observation": observation})

    report_path = write_neox_ont_error_report(neox_config_service, observations, failures)
    attach_json("NeoX ONT error matrix", {"report": str(report_path), "failures": failures, "observations": observations})
    assert not failures, f"ONT config error matrix had {len(failures)} mismatches. Report: {report_path}"


def batched_cases(cases: list[dict[str, Any]], size: int):
    for index in range(0, len(cases), size):
        yield cases[index : index + size]


def assert_neox_config_error_response(negative_case: dict[str, Any], response) -> None:
    expected_status_code = negative_case.get("expected_status_code")
    if expected_status_code is not None:
        assert response.status_code == int(expected_status_code), (
            f"{negative_case['name']} expected HTTP {expected_status_code}, got {response.status_code}: {response.text}"
        )

    expected_retstatus = negative_case.get("expected_retstatus")
    if expected_retstatus:
        assert response.retstatus == expected_retstatus, (
            f"{negative_case['name']} expected retstatus {expected_retstatus!r}, got {response.retstatus!r}: {response.text}"
        )
    else:
        assert response.retstatus == "Fail" or response.status_code >= 400, (
            f"{negative_case['name']} expected failure response, got HTTP={response.status_code}: {response.text}"
        )

    expected_message = negative_case.get("expected_message_contains")
    if not expected_message:
        failure_message = response_failure_message(response)
        assert failure_message, (
            f"{negative_case['name']} expected a non-empty failure message, got response: {response.text}"
        )
        return
    expected_messages = [expected_message] if isinstance(expected_message, str) else list(expected_message)
    response_text = json.dumps(response.json, ensure_ascii=False, default=str)
    missing = [message for message in expected_messages if str(message).lower() not in response_text.lower()]
    assert not missing, f"{negative_case['name']} missing expected error text {missing}: {response_text}"


def response_failure_message(response) -> str:
    values = [response.retresult]
    if isinstance(response.json, dict):
        values.extend(response.json.get(key) for key in ("retresult", "message", "error"))
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def assert_invalid_ont_post_did_not_succeed(negative_case: dict[str, Any], response) -> None:
    if response.retstatus == "Success" and response.status_code < 400:
        pytest.fail(
            f"{negative_case['name']} invalid ONT POST unexpectedly succeeded: "
            f"HTTP={response.status_code}, retstatus={response.retstatus!r}, body={response.text}"
        )


def verify_ont_invalid_post_not_applied_cli(
    env_config,
    neox_config_service,
    negative_case: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    target = neox_config_service.target()
    credentials = neox_cli_credentials(env_config, "ONT error")
    commands, forbidden_by_command = ont_invalid_post_cli_absence_checks(target)
    output_by_command = run_neox_cli_commands(env_config, credentials, commands)
    present_by_command = present_tokens_by_command(output_by_command, forbidden_by_command)
    failures = [
        {"command": command, "present_tokens": tokens}
        for command, tokens in present_by_command.items()
        if tokens
    ]
    observation = {
        "case": negative_case.get("name"),
        "commands": commands,
        "forbidden_tokens_by_command": forbidden_by_command,
        "present_tokens_by_command": present_by_command,
    }
    attach_json(f"NeoX ONT invalid POST CLI absence {negative_case.get('name')}", observation)
    return observation, failures


def ont_invalid_post_cli_absence_checks(target) -> tuple[list[str], dict[str, list[str]]]:
    xpon = f"{target.ont_slot_id}-{target.ont_port_id}"
    remote_xont = f"{xpon}-{target.ont_id}"
    running_config_command = f"show running-config interface xpon {xpon}"
    xont_by_sn_command = f"show interface remote xont sn {target.ont_sn}"
    commands = [running_config_command, xont_by_sn_command]
    return commands, {
        running_config_command: [
            f"interface remote xont {remote_xont}",
            f"sn {neox_cli_sn(target.ont_sn)}",
            f"registration-id {target.ont_password}",
        ],
        xont_by_sn_command: [remote_xont],
    }


def present_tokens_by_command(
    output_by_command: dict[str, str],
    forbidden_by_command: dict[str, list[str]],
) -> dict[str, list[str]]:
    return {
        command: present_tokens(output_by_command.get(command, ""), forbidden_tokens)
        for command, forbidden_tokens in forbidden_by_command.items()
    }


def present_tokens(output: str, forbidden_tokens: list[str]) -> list[str]:
    normalized_output = output.casefold()
    return [token for token in forbidden_tokens if token.casefold() in normalized_output]


def write_neox_ont_error_report(neox_config_service, observations: list[dict], failures: list[dict]) -> Path:
    reports_dir = Path(__file__).resolve().parents[1] / "reports" / "device-verification"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"neox_config_ont_error_matrix_{timestamp}.json"
    target = neox_config_service.target()
    data = {
        "target": {
            "node": neox_config_service.env_config.dut.node_key,
            "device_ip": neox_config_service.env_config.dut.device_ip,
            "device_name": target.device_name,
            "ont_slot_id": target.ont_slot_id,
            "ont_port_id": target.ont_port_id,
            "ont_id": target.ont_id,
        },
        "workflow": (
            "Each ONT invalid payload starts from the min payload plus one invalid field/list. "
            "The test clears the target before POST, asserts HTTP status, retstatus, and stable "
            "schema-validation messages, then uses CLI show commands to verify the invalid POST "
            "did not create the target ONT config."
        ),
        "summary": {
            "total": len(observations),
            "failures": len(failures),
        },
        "failures": failures,
        "observations": observations,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def ensure_ont_firmware_cleanup_if_needed(env_config, cleanup_registry, payload: dict[str, Any], target) -> None:
    if not ont_payload_has_firmware_config(payload):
        return
    cleanup_registry.add(lambda: cleanup_ont_firmware_config_if_needed(env_config, payload, target))


def cleanup_ont_firmware_config_if_needed(env_config, payload: dict[str, Any], target) -> None:
    if not ont_payload_has_firmware_config(payload):
        return
    credentials = neox_cli_credentials(env_config, "ONT")
    remote_xont = f"{target.ont_slot_id}-{target.ont_port_id}-{target.ont_id}"
    commands = [
        "configure",
        f"interface remote xont {remote_xont}",
        "no ont-fw-upgrade mode",
        "no ont-fw-upgrade fw-id",
        "no ont-fw-upgrade omci-method",
        "exit",
        "exit",
    ]
    run_neox_cli_commands(env_config, credentials, commands)


def ont_payload_has_firmware_config(payload: dict[str, Any]) -> bool:
    content = payload.get("Content", {})
    return any(content.get(field) for field in ("fwupgrademode", "fwupgradeid", "fwupgradeomci"))


def ensure_ont_template_dependency_if_needed(
    api_client,
    neox_config_service,
    readwrite_session: str,
    cleanup_registry,
    payload: dict[str, Any],
) -> None:
    template_name = payload.get("Content", {}).get("templatename")
    if not template_name:
        return
    expected_name = neox_config_service.neox_profile_name("ONTTemplateProfile")
    if template_name != expected_name:
        pytest.fail(f"ONT payload templatename {template_name!r} does not match configured template {expected_name!r}")

    template_payload = neox_config_service.neox_profile_boundary_payload("ONTTemplateProfile", "max")
    neox_config_service.ensure_neox_profile_dependencies(
        readwrite_session,
        cleanup_registry,
        "ONTTemplateProfile",
        template_payload,
    )
    ensure_ont_bandwidth_profile_supports_service_tcont(
        api_client,
        neox_config_service,
        readwrite_session,
        cleanup_registry,
        payload,
    )
    template_path = neox_config_service.neox_profile_path("ONTTemplateProfile")
    cleanup_registry.add(lambda: api_client.request("DELETE", template_path, session=readwrite_session))
    neox_config_service.delete_neox_profile_if_exists(template_path, readwrite_session)
    response = api_client.request("POST", template_path, session=readwrite_session, json=template_payload)
    assert_api_success(response)


def ensure_ont_bandwidth_profile_supports_service_tcont(
    api_client,
    neox_config_service,
    readwrite_session: str,
    cleanup_registry,
    payload: dict[str, Any],
) -> None:
    content = payload.get("Content", {})
    if not content.get("servicelist") and not content.get("tcontlist"):
        return
    profile_type = "ONTBandwidthProfile"
    path = neox_config_service.neox_profile_path(profile_type)
    profile_payload = neox_config_service.neox_profile_boundary_payload(profile_type, "max")
    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))
    neox_config_service.delete_neox_profile_if_exists(path, readwrite_session)
    response = api_client.request("POST", path, session=readwrite_session, json=profile_payload)
    assert_api_success(response)


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
