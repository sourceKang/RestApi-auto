from __future__ import annotations

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
    request,
):
    verify_nni_config_create_readwrite(
        api_client,
        env_config,
        neox_config_service,
        session_manager,
        "min",
        request,
    )


def test_nni_config_max_create_readwrite(
    api_client,
    env_config,
    neox_config_service,
    session_manager,
    request,
):
    verify_nni_config_create_readwrite(
        api_client,
        env_config,
        neox_config_service,
        session_manager,
        "max",
        request,
    )


def verify_nni_config_create_readwrite(
    api_client,
    env_config,
    neox_config_service,
    session_manager,
    boundary: str,
    request,
) -> None:
    neox_config_service.verify_required_target_data()

    with session_manager.role_session(SessionRole.READWRITE) as readwrite_session:
        config = nni_payload_config(boundary)
        payload = config["payload"]
        expected_lines = config["running_config_visible_lines"]
        response = api_client.request("POST", neox_config_service.nni_path(), session=readwrite_session, json=payload)
        assert_api_success(response)
        if request.config.getoption("--skip-neox-cli-verify"):
            return

        credentials = neox_cli_credentials(env_config, "NNI")
        target = neox_config_service.target()
        command = f"show running-config interface nni {target.nni_port_id}"
        output_by_command = run_neox_cli_commands(env_config, credentials, [command])

        missing = missing_tokens(output_by_command[command], expected_lines)
        report_path = write_neox_cli_verify_report(
            neox_config_service,
            "nni",
            boundary,
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

        assert not missing, f"Missing NNI running-config lines: {missing}. Report: {report_path}"