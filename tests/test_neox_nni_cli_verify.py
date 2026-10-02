from __future__ import annotations

from typing import Any

import pytest

from models.api import SessionRole
from services.neox_config.service import nni_payload_config
from tests.support.neox_cli_verification import (
    missing_tokens,
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


def test_nni_config_min_create_readwrite(
    api_client,
    env_config,
    neox_config_service,
    session_manager,
    cleanup_registry,
    request,
):
    verify_nni_config_create_readwrite(
        api_client,
        env_config,
        neox_config_service,
        session_manager,
        cleanup_registry,
        "min",
        request,
    )


def test_nni_config_max_create_readwrite(
    api_client,
    env_config,
    neox_config_service,
    session_manager,
    cleanup_registry,
    request,
):
    verify_nni_config_create_readwrite(
        api_client,
        env_config,
        neox_config_service,
        session_manager,
        cleanup_registry,
        "max",
        request,
    )


def verify_nni_config_create_readwrite(
    api_client,
    env_config,
    neox_config_service,
    session_manager,
    cleanup_registry,
    boundary: str,
    request,
) -> None:
    neox_config_service.verify_required_target_data()

    config = nni_payload_config(boundary)
    restore_steps = config.get("restore_steps", [])
    restore_state = {"done": not restore_steps}
    if restore_steps:
        # fec/speed survive REST DELETE, so a failed case must still re-POST the restore values.
        cleanup_registry.add_strict_final(
            lambda: restore_state["done"]
            or apply_nni_restore_steps(
                api_client, env_config, neox_config_service, session_manager, boundary, restore_steps, request
            )
        )

    with session_manager.role_session(SessionRole.READWRITE) as readwrite_session:
        payload = config["payload"]
        expected_lines = config["running_config_visible_lines"]
        response = api_client.request("POST", neox_config_service.nni_path(), session=readwrite_session, json=payload)
        assert_api_success(response)
        if not request.config.getoption("--skip-neox-cli-verify"):
            verify_nni_running_config(env_config, neox_config_service, boundary, payload, response, expected_lines)

    if restore_steps:
        apply_nni_restore_steps(
            api_client, env_config, neox_config_service, session_manager, boundary, restore_steps, request
        )
        restore_state["done"] = True


def apply_nni_restore_steps(
    api_client,
    env_config,
    neox_config_service,
    session_manager,
    boundary: str,
    restore_steps: list[dict[str, Any]],
    request,
) -> None:
    with session_manager.role_session(SessionRole.READWRITE) as readwrite_session:
        for index, step in enumerate(restore_steps, start=1):
            payload = step["payload"]
            response = api_client.request(
                "POST", neox_config_service.nni_path(), session=readwrite_session, json=payload
            )
            assert_api_success(response)
            if not request.config.getoption("--skip-neox-cli-verify"):
                verify_nni_running_config(
                    env_config,
                    neox_config_service,
                    f"{boundary}_restore_{index}",
                    payload,
                    response,
                    step["running_config_visible_lines"],
                )


def verify_nni_running_config(
    env_config,
    neox_config_service,
    case_name: str,
    payload: dict[str, Any],
    response,
    expected_lines: list[str],
) -> None:
    credentials = neox_cli_credentials(env_config, "NNI")
    target = neox_config_service.target()
    command = f"show running-config interface nni {target.nni_port_id}"
    output_by_command = run_neox_cli_commands(env_config, credentials, [command])

    missing = missing_tokens(output_by_command[command], expected_lines)
    report_path = write_neox_cli_verify_report(
        neox_config_service,
        "nni",
        case_name,
        neox_config_service.nni_path(),
        payload,
        response,
        output_by_command,
        {command: expected_lines},
        {command: missing},
        target_extra={
            "nni_slot_id": target.nni_slot_id,
            "nni_port_id": target.nni_port_id,
        },
    )

    assert not missing, f"Missing NNI running-config lines for {case_name}: {missing}. Report: {report_path}"
