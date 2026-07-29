from __future__ import annotations

import json
import copy
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from clients.ssh_cli import SshCliClient
from models.api import SessionRole
from services.neox_config.service import (
    ge_full_accepted_config,
    ge_max_variants_config,
    ge_negative_cases_config,
    ge_port_payload,
    materialize_ont_payload,
    nni_min_payload,
    ont_negative_cases,
    ont_negative_payload,
    ont_config_payload,
    ont_provision_template_sfu_payload,
    PROVISION_TEMPLATE_SFU_NAME,
    provision_template_sfu_payload,
    sanitize_ge_payload,
    vlan_case,
    vlan_negative_cases_config,
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
from tests.support.ont_cli_status import wait_for_ont_cli_config_absent, wait_for_ont_cli_is, wait_for_ont_cli_state
from tests.support.ont_cli_status import wait_for_ont_cli_config_tokens
from tests.support.options import option_or_full_testcases
from utils.assertions import assert_api_failure, assert_api_success
from utils.allure_helpers import attach_json
from utils.redaction import redact


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.destructive,
]

GE_MAX_VARIANT_GROUPS = tuple(ge_max_variants_config()["variant_order"])
ONT_BASELINE_STABLE_SAMPLES = 4


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

        config = ge_full_accepted_config()
        payload = config["payload"]
        expected_lines = config["running_config_visible_lines"]
        target = neox_config_service.target()

        ensure_ge_profile_dependencies(neox_config_service, api_client, readwrite_session, cleanup_registry, config)
        ensure_ge_global_setup_commands(env_config, target, cleanup_registry, config)
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
@pytest.mark.parametrize("variant_group", GE_MAX_VARIANT_GROUPS, ids=GE_MAX_VARIANT_GROUPS)
def test_ge_config_max_variant_readwrite(
    api_client,
    env_config,
    neox_config_service,
    readwrite_session,
    cleanup_registry,
    request,
    variant_group,
):
    with neox_config_connectivity_guard(env_config, "ge", f"max_variant_{variant_group}"):
        neox_config_service.verify_required_target_data()

        config = ge_full_accepted_config()
        variants = load_ge_max_variants()
        group = variants["variants"][variant_group]
        payload = materialize_ge_variant_payload(config["payload"], group)
        target = neox_config_service.target()
        path = neox_config_service.ge_path()

        variant_base_config = materialize_ge_variant_base_config(config, group)
        cleanup_commands = materialize_ge_interface_commands(group.get("cleanup_commands", []), target)
        cleanup_registry.add(lambda: run_ge_interface_config_commands(env_config, target, cleanup_commands))
        cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))

        api_client.request("DELETE", path, session=readwrite_session)
        run_ge_interface_config_commands(env_config, target, cleanup_commands)
        ensure_ge_profile_dependencies(neox_config_service, api_client, readwrite_session, cleanup_registry, variant_base_config)
        ensure_ge_profile_dependencies(neox_config_service, api_client, readwrite_session, cleanup_registry, group)
        ensure_ge_global_setup_commands(env_config, target, cleanup_registry, variant_base_config)
        ensure_ge_global_setup_commands(env_config, target, cleanup_registry, group)
        response = post_neox_config_payload(
            api_client,
            path,
            readwrite_session,
            payload,
            group.get("rest_timeout_seconds") or config.get("rest_timeout_seconds"),
        )
        assert_api_success(response)
        if skip_neox_cli_verify(request):
            return

        commands = materialize_ge_global_commands(group.get("show_commands", []), target)
        if not commands:
            commands = [f"show running-config interface ge {target.ge_slot_id}-{target.ge_port_id}"]
        credentials = neox_cli_credentials(env_config, "GE")
        output_by_command = run_neox_cli_commands(env_config, credentials, commands)
        assert_neox_config_node_reachable(env_config, "ge", f"max_variant_{variant_group}", "after_cli_verify")
        expected_tokens = expected_ge_variant_tokens(group)
        combined_output = "\n".join(output_by_command.values())
        missing = missing_tokens(combined_output, expected_tokens)
        combined_key = f"combined GE max variant CLI output: {variant_group}"
        report_outputs = {**output_by_command, combined_key: combined_output}
        expected_by_command = {command: [] for command in output_by_command}
        expected_by_command[combined_key] = expected_tokens
        missing_by_command = {command: [] for command in output_by_command}
        missing_by_command[combined_key] = missing
        report_path = write_neox_cli_verify_report(
            neox_config_service,
            "ge",
            f"max_variant_{variant_group}",
            path,
            payload,
            response,
            report_outputs,
            expected_by_command,
            missing_by_command,
            target_extra={"ge_slot_id": target.ge_slot_id, "ge_port_id": target.ge_port_id},
            metadata={
                "testlink_case_id": "EMS1-7120",
                "variant_group": variant_group,
                "variant_fields": group.get("fields", []),
            },
        )

        assert not missing, f"Missing GE max variant CLI tokens for {variant_group}: {missing}. Report: {report_path}"


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
        vid, payload = vlan_clear_case()
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
@pytest.mark.parametrize("case_name", ("max", "max_dynamic"), ids=("max_static", "max_dynamic"))
def test_ont_config_max_create_readwrite(
    api_client,
    env_config,
    neox_config_service,
    readwrite_session,
    cleanup_registry,
    request,
    case_name,
):
    with neox_config_connectivity_guard(env_config, "ont", case_name):
        verify_ont_config_create_cli_verified(
            api_client, env_config, neox_config_service, readwrite_session, cleanup_registry, case_name, request
        )


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_config_apply_provision_template_sfu_readwrite(
    api_client,
    env_config,
    neox_config_service,
    services,
    session_manager,
    readwrite_session,
    cleanup_registry,
    request,
):
    with neox_config_connectivity_guard(env_config, "ont", "provision_template_sfu"):
        neox_config_service.verify_required_target_data()
        target = neox_config_service.target()
        template_paths = neox_config_service.ensure_provision_template_sfu(readwrite_session)
        template_path = template_paths[PROVISION_TEMPLATE_SFU_NAME]

        path = neox_config_service.ont_path()
        restore_payload = ont_config_payload(target)
        payload = ont_provision_template_sfu_payload(target)
        ont_read_path = f"/ont/sn/{target.ont_sn}"
        xpon = f"{target.ont_slot_id}-{target.ont_port_id}"
        remote_xont = f"{xpon}-{target.ont_id}"
        cli_verify = not skip_neox_cli_verify(request)
        def cleanup_scenario():
            cleanup_ont_provision_template_scenario(
                api_client,
                env_config,
                services,
                readwrite_session,
                PROVISION_TEMPLATE_SFU_NAME,
                remote_xont,
                path,
                restore_payload,
                ont_read_path,
                [target.ont_id, target.ont_sn, "REST_API_NEOX_ONT"],
                verify_cli=cli_verify,
                session_manager=session_manager,
            )

        cleanup_registry.add_strict_final(cleanup_scenario)

        services.inventory.upsert_ont_service(readwrite_session, PROVISION_TEMPLATE_SFU_NAME)
        services.inventory.wait_for_ont_service_state(
            readwrite_session,
            {"Success"},
            timeout=180,
            interval=15,
            initial_delay=30,
        )

        api_client.request("DELETE", path, session=readwrite_session)
        response = api_client.request("POST", path, session=readwrite_session, json=payload)
        assert_api_success(response)

        ont_response = wait_for_rest_tokens(
            api_client,
            ont_read_path,
            readwrite_session,
            [
                target.ont_id,
                target.ont_sn,
                "REST_API_PROVISION_TEMPLATE_SFU",
                PROVISION_TEMPLATE_SFU_NAME,
            ],
            timeout=300,
        )

        attach_json(
            "NeoX provision template SFU REST verification",
            redact(
                {
                    "case_id": "EMS1-7223",
                    "target": {
                        "device_name": target.device_name,
                        "ont_slot_id": target.ont_slot_id,
                        "ont_port_id": target.ont_port_id,
                        "ont_id": target.ont_id,
                        "ont_sn": target.ont_sn,
                    },
                    "template_path": template_path,
                    "template_payload": provision_template_sfu_payload(),
                    "ont_path": path,
                    "ont_read_path": ont_read_path,
                    "ont_payload": payload,
                }
            ),
        )

        if not cli_verify:
            return

        credentials = neox_cli_credentials(env_config, "ONT provision template SFU")
        command_by_name = {
            "running-config": f"show running-config interface xpon {xpon}",
            "xont-by-sn": f"show interface remote xont sn {target.ont_sn}",
        }
        output_by_command = run_neox_cli_commands(env_config, credentials, list(command_by_name.values()))
        assert_neox_config_node_reachable(env_config, "ont", "provision_template_sfu", "after_cli_verify")
        expected_by_command = {
            command_by_name["running-config"]: ont_running_config_tokens(remote_xont, payload["Content"]),
            command_by_name["xont-by-sn"]: [remote_xont, target.ont_sn],
        }
        missing_by_command = missing_tokens_by_command(output_by_command, expected_by_command)
        report_path = write_neox_cli_verify_report(
            neox_config_service,
            "ont",
            "provision_template_sfu",
            path,
            payload,
            response,
            output_by_command,
            expected_by_command,
            missing_by_command,
            target_extra={
                "ont_slot_id": target.ont_slot_id,
                "ont_port_id": target.ont_port_id,
                "ont_id": target.ont_id,
                "ont_sn": target.ont_sn,
            },
            metadata={
                "testcase_id": "EMS1-7223",
                "template_path": template_path,
                "rest_read_path": ont_read_path,
                "rest_read_response": {
                    "status_code": ont_response.status_code,
                    "retstatus": ont_response.retstatus,
                    "retresult": ont_response.retresult,
                },
            },
        )

        missing = {command: tokens for command, tokens in missing_by_command.items() if tokens}
        assert not missing, f"Missing ONT provision template CLI tokens for {remote_xont}: {missing}. Report: {report_path}"


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_config_clear_readwrite(
    api_client,
    env_config,
    neox_config_service,
    session_manager,
    readwrite_session,
    cleanup_registry,
    request,
):
    with neox_config_connectivity_guard(env_config, "ont", "clear"):
        neox_config_service.verify_required_target_data()
        target = neox_config_service.target()
        xpon = f"{target.ont_slot_id}-{target.ont_port_id}"
        remote_xont = f"{xpon}-{target.ont_id}"
        restore_payload = ont_config_payload(target)
        cleanup_registry.add_strict_final(
            lambda: restore_ont_config_exact_baseline(
                api_client,
                env_config,
                session_manager,
                neox_config_service.ont_path(),
                restore_payload,
                f"/ont/sn/{target.ont_sn}",
                [target.ont_id, target.ont_sn, "REST_API_NEOX_ONT"],
                remote_xont,
                verify_cli=not skip_neox_cli_verify(request),
                attachment_name="ONT clear strict baseline convergence",
            )
        )
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
            restore_payload,
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
    cleanup_registry,
    request,
):
    if not option_or_full_testcases(request.config, "--run-neox-ont-error"):
        pytest.skip("EMS1-7133 NeoX ONT error matrix is slow; use --run-neox-ont-error to run it.")
    with neox_config_connectivity_guard(env_config, "ont", "error"):
        with session_manager.role_session(SessionRole.READWRITE) as readwrite_session:
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
        "{ge_slot_id}": target.ge_slot_id,
        "{ge_port_id}": target.ge_port_id,
    }
    for command, tokens in raw_checks.items():
        materialized_command = materialize_ge_template(command, replacements)
        checks[materialized_command] = [materialize_ge_template(token, replacements) for token in tokens]
    return checks


def materialize_ge_template(value: str, replacements: dict[str, str]) -> str:
    for placeholder, replacement in replacements.items():
        value = value.replace(placeholder, replacement)
    return value


def load_ge_max_variants() -> dict[str, Any]:
    return ge_max_variants_config()


def materialize_ge_variant_payload(
    base_payload: dict[str, Any],
    group: dict[str, Any],
) -> dict[str, Any]:
    payload = copy.deepcopy(base_payload)
    content = payload.setdefault("Content", {})
    for field in group.get("exclude_fields", []):
        content.pop(field, None)
    content.update(copy.deepcopy(group.get("payload_patch", {})))
    return sanitize_ge_payload(payload)


def materialize_ge_variant_base_config(config: dict[str, Any], group: dict[str, Any]) -> dict[str, Any]:
    variant_config = copy.deepcopy(config)
    excluded_setup = set(group.get("exclude_setup_global_commands", []))
    if excluded_setup:
        variant_config["setup_global_commands"] = [
            command for command in config.get("setup_global_commands", []) if command not in excluded_setup
        ]
    excluded_cleanup = set(group.get("exclude_cleanup_global_commands", []))
    if excluded_cleanup:
        variant_config["cleanup_global_commands"] = [
            command for command in config.get("cleanup_global_commands", []) if command not in excluded_cleanup
        ]
    return variant_config


def materialize_ge_interface_commands(commands: list[str], target) -> list[str]:
    return materialize_ge_global_commands(commands, target)


def run_ge_interface_config_commands(env_config, target, commands: list[str]) -> dict[str, str]:
    if not commands:
        return {}
    credentials = neox_cli_credentials(env_config, "GE")
    cli_sequence = [
        "configure",
        f"interface ge {target.ge_slot_id}-{target.ge_port_id}",
        *commands,
        "exit",
        "exit",
    ]
    return run_neox_cli_commands(env_config, credentials, cli_sequence)


def expected_ge_variant_tokens(group: dict[str, Any]) -> list[str]:
    return [token for token in group.get("expected_tokens", []) if token]


def ensure_ge_profile_dependencies(
    neox_config_service,
    api_client,
    session_id: str,
    cleanup_registry,
    config: dict[str, Any],
) -> None:
    for profile_type in config.get("setup_profile_types", []):
        path = neox_config_service.neox_profile_path(profile_type)
        payload = neox_config_service.neox_profile_payload(profile_type)
        neox_config_service.ensure_neox_profile_dependencies(session_id, cleanup_registry, profile_type, payload)
        cleanup_registry.add(lambda p=path: api_client.request("DELETE", p, session=session_id))
        neox_config_service.delete_neox_profile_if_exists(path, session_id)
        response = api_client.request("POST", path, session=session_id, json=payload)
        assert_api_success(response)


def ensure_ge_global_setup_commands(env_config, target, cleanup_registry, config: dict[str, Any]) -> None:
    setup_commands = materialize_ge_global_commands(config.get("setup_global_commands", []), target)
    cleanup_commands = materialize_ge_global_commands(config.get("cleanup_global_commands", []), target)
    if cleanup_commands:
        cleanup_commands, run_cleanup_last = ge_acl_profile_mode_cleanup_plan(cleanup_commands)
        cleanup_runner = lambda commands=cleanup_commands, fresh=run_cleanup_last: run_ge_global_config_commands(
            env_config,
            commands,
            fresh_session=fresh,
        )
        if run_cleanup_last:
            cleanup_registry.add_final(cleanup_runner)
        else:
            cleanup_registry.add(cleanup_runner)
    if not setup_commands:
        return

    prepare_ge_acl_profile_mode_switch(env_config, setup_commands)
    output_by_command = run_ge_global_config_commands(env_config, setup_commands)
    failures = {
        command: output
        for command, output in output_by_command.items()
        if command != "y" and ge_cli_command_failed(output)
    }
    assert not failures, f"GE global setup command failed: {failures}"
    settle_ge_acl_profile_mode_if_needed(env_config, target, setup_commands)


def ge_acl_profile_mode_cleanup_plan(commands: list[str]) -> tuple[list[str], bool]:
    if len(commands) >= 2 and commands[0] == "acl-profile mode port" and commands[1] == "y":
        return [*commands[2:], *commands[:2]], True
    return commands, False


def prepare_ge_acl_profile_mode_switch(env_config, setup_commands: list[str]) -> None:
    if "acl-profile mode profile" not in setup_commands:
        return
    profile_names = ge_acl_profile_names_from_commands(setup_commands)
    if not profile_names:
        return
    cleanup_commands = [f"no acl-profile {profile_name}" for profile_name in profile_names]
    run_ge_global_config_commands(env_config, cleanup_commands)


def ge_acl_profile_names_from_commands(commands: list[str]) -> list[str]:
    names = []
    for command in commands:
        parts = command.split()
        if len(parts) == 2 and parts[0] == "acl-profile" and parts[1] != "mode":
            names.append(parts[1])
    return names


def settle_ge_acl_profile_mode_if_needed(env_config, target, setup_commands: list[str]) -> None:
    if "acl-profile mode profile" not in setup_commands:
        return
    seconds = float(os.environ.get("NEOX_GE_ACL_PROFILE_MODE_SETTLE_SECONDS", "2"))
    if seconds <= 0:
        return
    started = time.monotonic()
    time.sleep(seconds)
    attach_json(
        "GE ACL profile mode settle",
        {
            "node": env_config.dut.node_key,
            "device_ip": env_config.dut.device_ip,
            "ge_slot_id": target.ge_slot_id,
            "ge_port_id": target.ge_port_id,
            "requested_seconds": seconds,
            "actual_seconds": round(time.monotonic() - started, 3),
        },
    )


def materialize_ge_global_commands(commands: list[str], target) -> list[str]:
    replacements = {
        "{slot_id}": target.ge_slot_id,
        "{port_id}": target.ge_port_id,
        "{ge_slot_id}": target.ge_slot_id,
        "{ge_port_id}": target.ge_port_id,
    }
    return [materialize_ge_template(command, replacements) for command in commands]


def run_ge_global_config_commands(env_config, commands: list[str], *, fresh_session: bool = False) -> dict[str, str]:
    if not commands:
        return {}
    if fresh_session:
        return run_ge_global_config_command_batch_fresh(env_config, commands)
    mode_prefix = ge_acl_mode_switch_prefix(commands)
    if mode_prefix:
        return run_ge_global_acl_mode_switch_commands(env_config, commands, mode_prefix)
    return run_ge_global_config_command_batch(env_config, commands)


def run_ge_global_acl_mode_switch_commands(
    env_config,
    commands: list[str],
    mode_prefix: list[str],
) -> dict[str, str]:
    outputs = run_ge_global_config_command_batch_fresh(env_config, mode_prefix)
    settle_ge_acl_mode_switch(env_config, mode_prefix[0])
    expected_mode = mode_prefix[0].rsplit(" ", 1)[-1]
    ensure_ge_acl_profile_mode(env_config, expected_mode)
    remaining_commands = commands[len(mode_prefix) :]
    if remaining_commands:
        outputs.update(run_ge_global_config_command_batch_fresh(env_config, remaining_commands))
    return outputs


def run_ge_global_config_command_batch(env_config, commands: list[str]) -> dict[str, str]:
    credentials = neox_cli_credentials(env_config, "GE")
    return run_neox_cli_commands(env_config, credentials, ["configure", *commands, "exit"])


def run_ge_global_config_command_batch_fresh(env_config, commands: list[str]) -> dict[str, str]:
    ssh_username, ssh_password = neox_cli_credentials(env_config, "GE")
    client = SshCliClient(env_config.dut.ssh_host, ssh_username, ssh_password)
    results = client.run_commands(["configure", *commands, "exit"])
    return {result.command: result.output for result in results}


def ensure_ge_acl_profile_mode(env_config, expected_mode: str) -> None:
    output = ge_acl_profile_mode_output(env_config)
    expected_line = f"Acl-profile mode : {expected_mode}"
    if expected_line not in output:
        mode_command = f"acl-profile mode {expected_mode}"
        retry_output = run_ge_global_config_command_batch_fresh(env_config, [mode_command, "y"])
        settle_ge_acl_mode_switch(env_config, mode_command)
        output = ge_acl_profile_mode_output(env_config)
        attach_json(
            "GE ACL profile mode retry",
            {
                "node": env_config.dut.node_key,
                "device_ip": env_config.dut.device_ip,
                "expected_mode": expected_mode,
                "retry_output": retry_output,
                "show_output": output,
            },
        )
    assert expected_line in output, f"Expected GE ACL profile mode {expected_mode!r}, got: {output}"


def ge_acl_profile_mode_output(env_config) -> str:
    ssh_username, ssh_password = neox_cli_credentials(env_config, "GE")
    client = SshCliClient(env_config.dut.ssh_host, ssh_username, ssh_password)
    results = client.run_commands(["show acl-profile mode"])
    return results[0].output if results else ""


def ge_acl_mode_switch_prefix(commands: list[str]) -> list[str]:
    if len(commands) >= 2 and commands[0].startswith("acl-profile mode ") and commands[1] == "y":
        return commands[:2]
    return []


def settle_ge_acl_mode_switch(env_config, mode_command: str) -> None:
    seconds = float(os.environ.get("NEOX_GE_ACL_MODE_SWITCH_SETTLE_SECONDS", "3"))
    if seconds <= 0:
        return
    started = time.monotonic()
    time.sleep(seconds)
    attach_json(
        "GE ACL mode switch settle",
        {
            "node": env_config.dut.node_key,
            "device_ip": env_config.dut.device_ip,
            "mode_command": mode_command,
            "requested_seconds": seconds,
            "actual_seconds": round(time.monotonic() - started, 3),
        },
    )


def ge_cli_command_failed(output: str) -> bool:
    failure_fragments = (
        "invalid input",
        "incomplete command",
        "ambiguous command",
        "does not exist",
        "not found",
        "fail",
        "error",
    )
    normalized = output.casefold()
    return any(fragment in normalized for fragment in failure_fragments)


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
    data = ge_negative_cases_config()
    cases = []
    for raw_case in data["cases"]:
        payload = ge_port_payload()
        payload["Content"][raw_case["field"]] = raw_case["value"]
        cases.append(
            {
                "name": raw_case["name"],
                "field": raw_case.get("field"),
                "payload": payload,
                "error_layer": raw_case.get("error_layer") or infer_error_layer(raw_case),
                "expected_status_code": raw_case.get("expected_status_code"),
                "expected_retstatus": raw_case.get("expected_retstatus"),
                "expected_message_contains": raw_case.get("expected_message_contains"),
            }
        )
    return cases


def nni_config_negative_cases() -> list[dict[str, Any]]:
    raw_cases = [
        {
            "name": "invalid_portenable",
            "field": "portenable",
            "value": "invalid",
            "error_layer": "api_schema",
            "expected_status_code": 400,
            "expected_retstatus": "Fail",
            "expected_message_contains": "Invalid JSON input",
        },
        {
            "name": "invalid_mode",
            "field": "mode",
            "value": "invalid",
            "error_layer": "device_cli",
            "expected_retstatus": "Fail",
        },
        {
            "name": "mtu_above_max",
            "field": "mtu",
            "value": 100000,
            "error_layer": "device_cli",
            "expected_retstatus": "Fail",
        },
        {
            "name": "pvid_above_max",
            "field": "pvid",
            "value": 4095,
            "error_layer": "device_cli",
            "expected_retstatus": "Fail",
        },
    ]
    cases = []
    for raw_case in raw_cases:
        payload = copy.deepcopy(nni_min_payload())
        payload["Content"][raw_case["field"]] = raw_case["value"]
        cases.append(
            {
                "name": raw_case["name"],
                "field": raw_case["field"],
                "payload": payload,
                "error_layer": raw_case["error_layer"],
                "expected_status_code": raw_case.get("expected_status_code"),
                "expected_retstatus": raw_case.get("expected_retstatus"),
                "expected_message_contains": raw_case.get("expected_message_contains"),
            }
        )
    return cases


def vlan_config_negative_cases() -> list[dict[str, Any]]:
    return vlan_negative_cases_config()


def vlan_clear_case() -> tuple[str, dict[str, Any]]:
    _, payload = vlan_case("min")
    payload = copy.deepcopy(payload)
    payload["vlanname"] = "REST_API_VLAN_CLEAR"
    return "4094", payload


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
        response = api_client.request("POST", path, session=readwrite_session, json=payload)
        assert_invalid_config_post_did_not_succeed(feature, negative_case, response)
        cli_observation = {}
        cli_failures = []
        observation = {
            "case": negative_case.get("name"),
            "field": negative_case.get("field"),
            "request": redact(payload),
            "expected": {
                "error_layer": negative_case.get("error_layer") or infer_error_layer(negative_case),
                "status_code": negative_case.get("expected_status_code"),
                "retstatus": negative_case.get("expected_retstatus"),
                "message_contains": negative_case.get("expected_message_contains"),
                "message_assertion": error_message_assertion_mode(negative_case),
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
            "Each invalid payload clears the target config before POST. API/schema-layer cases assert the "
            "stable status/message contract; device CLI-layer cases assert failure and a non-empty error "
            "message without pinning device wording. CLI verification is intentionally disabled for config "
            "error-readwrite cases."
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


def write_neox_rest_response_report(
    neox_config_service,
    feature: str,
    case_name: str,
    phase: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    response,
    target_extra: dict[str, Any] | None = None,
) -> Path:
    reports_dir = Path(__file__).resolve().parents[1] / "reports" / "device-verification"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"neox_config_{feature}_rest_{case_name}_{phase}_{timestamp}.json"
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
        "workflow": "REST request/response is saved before API success assertion so failure body is preserved.",
        "rest_api": {
            "phase": phase,
            "method": method,
            "path": path,
            "request": redact(payload) if payload is not None else None,
            "response": {
                "status_code": response.status_code,
                "retstatus": response.retstatus,
                "retresult": response.retresult,
                "body": redact(response.json),
                "text": redact(response.text),
            },
        },
    }
    report_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    attach_json(f"NeoX {feature} REST response {case_name}/{phase}", {"report": str(report_path), **data})
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
    cli_verify = not skip_neox_cli_verify(request)
    command = f"show vlan {vid}"
    credentials = None
    if cli_verify:
        credentials = neox_cli_credentials(env_config, "VLAN")
        baseline_output_by_command = run_neox_cli_commands(env_config, credentials, [command])
        assert_neox_config_node_reachable(env_config, "vlan", case_name, "before_rest_cli_baseline")
        attach_json(
            f"NeoX VLAN {case_name} pre-REST CLI baseline",
            {
                "command": command,
                "output": redact(baseline_output_by_command),
            },
        )

    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))
    api_client.request("DELETE", path, session=readwrite_session)
    response = api_client.request("POST", path, session=readwrite_session, json=payload)
    write_neox_rest_response_report(neox_config_service, "vlan", case_name, "post", "POST", path, payload, response)
    assert_api_success(response)
    if not cli_verify:
        return

    assert credentials is not None
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
    xpon = f"{target.ont_slot_id}-{target.ont_port_id}"
    remote_xont = f"{xpon}-{target.ont_id}"
    cleanup_registry.add_strict_final(
        lambda: restore_ont_config_exact_baseline(
            api_client,
            env_config,
            session_manager,
            path,
            restore_payload,
            f"/ont/sn/{target.ont_sn}",
            [target.ont_id, target.ont_sn, "REST_API_NEOX_ONT"],
            remote_xont,
            verify_cli=not skip_neox_cli_verify(request),
            attachment_name="ONT error strict baseline convergence",
        )
    )

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
                observation = {
                    "case": negative_case.get("name"),
                    "field": negative_case.get("field"),
                    "request": redact(payload),
                    "expected": {
                        "error_layer": negative_case.get("error_layer") or infer_error_layer(negative_case),
                        "status_code": negative_case.get("expected_status_code"),
                        "retstatus": negative_case.get("expected_retstatus"),
                        "message_contains": negative_case.get("expected_message_contains"),
                        "message_assertion": error_message_assertion_mode(negative_case),
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
                except AssertionError as error:
                    failures.append({"case": negative_case.get("name"), "error": str(error), "observation": observation})

    report_path = write_neox_ont_error_report(neox_config_service, observations, failures)
    attach_json("NeoX ONT error matrix", {"report": str(report_path), "failures": failures, "observations": observations})
    assert not failures, f"ONT config error matrix had {len(failures)} mismatches. Report: {report_path}"


def batched_cases(cases: list[dict[str, Any]], size: int):
    for index in range(0, len(cases), size):
        yield cases[index : index + size]


def assert_neox_config_error_response(negative_case: dict[str, Any], response) -> None:
    if is_api_schema_error_case(negative_case):
        assert_expected_error_status(negative_case, response)
        assert_expected_error_message(negative_case, response)
        return

    assert_failure_response(negative_case, response)
    failure_message = response_failure_message(response)
    assert failure_message, (
        f"{negative_case['name']} expected a non-empty device/API failure message, got response: {response.text}"
    )


def assert_expected_error_status(negative_case: dict[str, Any], response) -> None:
    expected_status_code = negative_case.get("expected_status_code")
    if expected_status_code is not None:
        assert response.status_code == int(expected_status_code), (
            f"{negative_case['name']} expected HTTP {expected_status_code}, got {response.status_code}: {response.text}"
        )

    assert_failure_response(negative_case, response)


def assert_failure_response(negative_case: dict[str, Any], response) -> None:
    expected_retstatus = negative_case.get("expected_retstatus")
    if expected_retstatus:
        assert response.retstatus == expected_retstatus, (
            f"{negative_case['name']} expected retstatus {expected_retstatus!r}, got {response.retstatus!r}: {response.text}"
        )
        return

    assert response.retstatus == "Fail" or response.status_code >= 400, (
        f"{negative_case['name']} expected failure response, got HTTP={response.status_code}: {response.text}"
    )


def assert_expected_error_message(negative_case: dict[str, Any], response) -> None:
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


def infer_error_layer(negative_case: dict[str, Any]) -> str:
    expected_message = negative_case.get("expected_message_contains")
    expected_status_code = negative_case.get("expected_status_code")
    if expected_status_code == 400 and expected_message == "Invalid JSON input":
        return "api_schema"
    return "device_cli"


def is_api_schema_error_case(negative_case: dict[str, Any]) -> bool:
    return str(negative_case.get("error_layer") or infer_error_layer(negative_case)) == "api_schema"


def error_message_assertion_mode(negative_case: dict[str, Any]) -> str:
    if is_api_schema_error_case(negative_case):
        return "contains_expected_text"
    return "non_empty_only"


def response_failure_message(response) -> str:
    values = [response.retresult]
    if isinstance(response.json, dict):
        values.extend(response.json.get(key) for key in ("retresult", "retval", "message", "error"))
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
            "API/schema-layer cases assert the stable status/message contract; device CLI-layer cases assert "
            "failure and a non-empty error message without pinning device wording. CLI verification is "
            "intentionally disabled for config error-readwrite cases."
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


def restore_ont_config_baseline(
    api_client,
    env_config,
    path: str,
    session_id: str,
    payload: dict[str, Any],
    *,
    verify_cli: bool,
):
    response = api_client.request("POST", path, session=session_id, json=payload)
    assert_api_success(response)
    if verify_cli:
        wait_for_ont_cli_is(env_config, timeout=180, interval=15)
    return response


def restore_ont_config_exact_baseline(
    api_client,
    env_config,
    session_manager,
    config_path: str,
    restore_payload: dict[str, Any],
    read_path: str,
    expected_rest_tokens: list[str],
    remote_xont: str,
    *,
    verify_cli: bool,
    attachment_name: str,
) -> None:
    restore_content = restore_payload.get("Content", {})
    expected_description = str(restore_content.get("ontdescription") or "")
    expected_template_name = str(restore_content.get("templatename") or "")

    def rest_baseline_matches(response) -> bool:
        payload = response.json if isinstance(response.json, dict) else {}
        ont_info = ((payload.get("retval") or {}).get("ontinfo") or {})
        actual_description = str(ont_info.get("description") or "")
        actual_template_name = str(ont_info.get("templateName") or ont_info.get("ontTemplate") or "")
        return actual_description == expected_description and actual_template_name == expected_template_name

    attempts = []
    for attempt, timeout in ((1, 120), (2, 180)):
        attempt_errors = []
        try:
            with session_manager.role_session(SessionRole.READWRITE) as cleanup_session:
                restore_ont_config_baseline(
                    api_client,
                    env_config,
                    config_path,
                    cleanup_session,
                    restore_payload,
                    verify_cli=False,
                )
                wait_for_rest_tokens(
                    api_client,
                    read_path,
                    cleanup_session,
                    expected_rest_tokens,
                    timeout=timeout,
                    interval=15,
                    response_validator=rest_baseline_matches,
                    consecutive_successes=ONT_BASELINE_STABLE_SAMPLES,
                )
        except Exception as error:
            attempt_errors.append(f"REST baseline convergence: {error}")

        if verify_cli:
            try:
                wait_for_ont_cli_is(env_config, timeout=timeout, interval=15)
                wait_for_ont_cli_config_tokens(
                    env_config,
                    expected_tokens=(remote_xont, f"description {expected_description}"),
                    absent_tokens=(f"template {PROVISION_TEMPLATE_SFU_NAME}",),
                    consecutive_successes=ONT_BASELINE_STABLE_SAMPLES,
                    timeout=timeout,
                    interval=15,
                )
            except Exception as error:
                attempt_errors.append(f"CLI baseline convergence: {error}")

        attempts.append(
            {
                "attempt": attempt,
                "timeout": timeout,
                "errors": attempt_errors,
            }
        )
        if not attempt_errors:
            attach_json(
                attachment_name,
                {
                    "config_path": config_path,
                    "read_path": read_path,
                    "expected_description": expected_description,
                    "expected_template_name": expected_template_name,
                    "attempts": attempts,
                    "converged": True,
                },
            )
            return

    attach_json(
        attachment_name,
        {
            "config_path": config_path,
            "read_path": read_path,
            "expected_description": expected_description,
            "expected_template_name": expected_template_name,
            "attempts": attempts,
            "converged": False,
        },
    )
    raise AssertionError(f"restore ONT exact baseline did not converge: {attempts}")


def cleanup_ont_provision_template_scenario(
    api_client,
    env_config,
    services,
    session_id: str,
    template_name: str,
    remote_xont: str,
    config_path: str,
    restore_payload: dict[str, Any],
    read_path: str,
    expected_rest_tokens: list[str],
    *,
    verify_cli: bool,
    session_manager=None,
) -> None:
    errors = []

    def cleanup_session_scope():
        if session_manager is None:
            return nullcontext(session_id)
        return session_manager.role_session(SessionRole.READWRITE)

    try:
        with cleanup_session_scope() as cleanup_session:
            services.provision.delete_ont_service_if_uses_template(
                cleanup_session,
                template_name,
                timeout=180,
                interval=15,
            )
    except Exception as error:
        errors.append(f"delete provision-template service: {error}")

    config_clear_requested = False
    try:
        with cleanup_session_scope() as cleanup_session:
            clear_response = api_client.request("DELETE", config_path, session=cleanup_session)
            if clear_response.retstatus != "Success":
                assert_api_failure(
                    clear_response,
                    accepted_messages=("no data", "not found", "does not exist", "no such data"),
                )
        config_clear_requested = True
    except Exception as error:
        errors.append(f"clear ONT config through REST: {error}")

    config_cleared = False
    if config_clear_requested:
        try:
            wait_for_ont_cli_config_absent(
                env_config,
                remote_xont,
                timeout=300,
                interval=15,
            )
            config_cleared = True
        except Exception as error:
            errors.append(f"wait for ONT CLI config clear: {error}")

    if config_cleared:
        try:
            wait_for_ont_cli_state(env_config, "UnReg", timeout=180, interval=15)
        except Exception as error:
            errors.append(f"wait for ONT unregister after config clear: {error}")

    restore_attempts = []
    restore_content = restore_payload.get("Content", {})
    expected_description = str(restore_content.get("ontdescription") or "")
    expected_template_name = str(restore_content.get("templatename") or "")

    def rest_baseline_matches(response) -> bool:
        payload = response.json if isinstance(response.json, dict) else {}
        ont_info = ((payload.get("retval") or {}).get("ontinfo") or {})
        actual_description = str(ont_info.get("description") or "")
        actual_template_name = str(ont_info.get("templateName") or ont_info.get("ontTemplate") or "")
        return actual_description == expected_description and actual_template_name == expected_template_name

    restore_converged = False
    for attempt, timeout in ((1, 120), (2, 180)):
        attempt_errors = []
        try:
            with cleanup_session_scope() as cleanup_session:
                restore_ont_config_baseline(
                    api_client,
                    env_config,
                    config_path,
                    cleanup_session,
                    restore_payload,
                    verify_cli=False,
                )
                try:
                    wait_for_rest_tokens(
                        api_client,
                        read_path,
                        cleanup_session,
                        expected_rest_tokens,
                        timeout=timeout,
                        interval=15,
                        response_validator=rest_baseline_matches,
                        consecutive_successes=ONT_BASELINE_STABLE_SAMPLES,
                    )
                except Exception as error:
                    attempt_errors.append(f"REST convergence: {error}")
        except Exception as error:
            attempt_errors.append(f"cleanup session or POST baseline: {error}")

        if verify_cli:
            try:
                wait_for_ont_cli_is(env_config, timeout=timeout, interval=15)
                wait_for_ont_cli_config_tokens(
                    env_config,
                    expected_tokens=(f"description {expected_description}",),
                    absent_tokens=(f"template {template_name}",),
                    consecutive_successes=ONT_BASELINE_STABLE_SAMPLES,
                    timeout=timeout,
                    interval=15,
                )
            except Exception as error:
                attempt_errors.append(f"CLI convergence: {error}")

        restore_attempts.append(
            {
                "attempt": attempt,
                "timeout": timeout,
                "errors": attempt_errors,
            }
        )
        if not attempt_errors:
            restore_converged = True
            break

    attach_json(
        "ONT provision-template cleanup baseline convergence",
        {
            "config_path": config_path,
            "read_path": read_path,
            "attempts": restore_attempts,
            "converged": restore_converged,
        },
    )
    if not restore_converged:
        errors.append(f"restore ONT baseline did not converge: {restore_attempts}")

    assert not errors, "ONT provision-template cleanup failed: " + "; ".join(errors)


def wait_for_rest_tokens(
    api_client,
    path: str,
    session_id: str,
    expected_tokens: list[str],
    *,
    timeout: float = 300,
    interval: float = 10,
    max_interval: float = 30,
    response_validator=None,
    consecutive_successes: int = 1,
    sleeper=time.sleep,
    clock=time.monotonic,
):
    if consecutive_successes < 1:
        raise ValueError("consecutive_successes must be at least 1")
    deadline = clock() + timeout
    last_response = None
    last_missing = expected_tokens
    delay = max(0.0, interval)
    stable_hits = 0
    while clock() <= deadline:
        last_response = api_client.request("GET", path, session=session_id)
        if last_response.retstatus == "Fail" and "not authorized" in last_response.retresult.casefold():
            raise AssertionError(
                f"REST polling lost authorization for {path}; obtain a fresh session before retrying"
            )
        if last_response.retstatus == "Success":
            body = json.dumps(last_response.json, ensure_ascii=False)
            last_missing = [token for token in expected_tokens if token not in body]
            response_matches = response_validator is None or response_validator(last_response)
            if not last_missing and response_matches:
                stable_hits += 1
                if stable_hits >= consecutive_successes:
                    return last_response
            else:
                stable_hits = 0
        else:
            stable_hits = 0

        remaining = deadline - clock()
        if remaining <= 0:
            break
        sleep_for = min(delay, remaining)
        sleeper(sleep_for)
        delay = min(max_interval, max(delay * 2, 1.0))

    assert last_response is not None
    if last_response.retstatus != "Success":
        assert_api_success(last_response)
    body = json.dumps(last_response.json, ensure_ascii=False)
    assert not last_missing, f"Missing expected REST response tokens {last_missing}: {body}"
    assert response_validator is None or response_validator(last_response), (
        "REST response did not match the required exact baseline fields: " + body
    )
    assert stable_hits >= consecutive_successes, (
        f"REST response was not stable for {consecutive_successes} consecutive samples; "
        f"last stable count={stable_hits}: {body}"
    )
    return last_response


def assert_response_contains_tokens(response, expected_tokens: list[str]) -> None:
    assert_api_success(response)
    body = json.dumps(response.json, ensure_ascii=False)
    missing = [token for token in expected_tokens if token not in body]
    assert not missing, f"Missing expected REST response tokens {missing}: {body}"


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
    if feature in {"vlan", "ont"}:
        write_neox_rest_response_report(neox_config_service, feature, case_name, "post", "POST", path, payload, response, target_extra)
    assert_api_success(response)
    response = api_client.request("DELETE", path, session=session_id)
    if feature in {"vlan", "ont"}:
        write_neox_rest_response_report(neox_config_service, feature, case_name, "delete", "DELETE", path, None, response, target_extra)
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







