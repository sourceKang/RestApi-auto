from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from clients.ssh_cli import SshCliClient
from models.api import SessionRole
from services.neox_config.service import (
    NEOX_PROFILE_READWRITE_TYPES,
    NEOX_PROFILE_TYPES,
    neox_profile_cli_verify_case,
)
from utils.assertions import assert_api_failure, assert_api_success
from utils.redaction import redact


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.neox_profile,
    pytest.mark.destructive,
]


@pytest.mark.mutating
@pytest.mark.readonly
@pytest.mark.parametrize("profile_type", NEOX_PROFILE_TYPES)
def test_neox_profile_create_delete_rejects_readonly(neox_config_service, readonly_session, profile_type):
    neox_config_service.verify_neox_profile_rejected(readonly_session, profile_type)


@pytest.mark.mutating
@pytest.mark.noaccess
@pytest.mark.parametrize("profile_type", NEOX_PROFILE_TYPES)
def test_neox_profile_create_delete_rejects_noaccess(neox_config_service, noaccess_session, profile_type):
    neox_config_service.verify_neox_profile_rejected(noaccess_session, profile_type)


@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("profile_type", NEOX_PROFILE_READWRITE_TYPES, ids=NEOX_PROFILE_READWRITE_TYPES)
def test_neox_profile_min_create_readwrite(
    neox_config_service,
    api_client,
    env_config,
    session_manager,
    readwrite_session,
    cleanup_registry,
    profile_type,
):
    neox_config_service.verify_node3_target()
    ssh_username, ssh_password = neox_profile_cli_credentials(env_config)
    neox_config_service.ensure_neox_profile_dependencies(readwrite_session, cleanup_registry, profile_type)
    path = neox_config_service.neox_profile_path(profile_type)
    payload = neox_config_service.neox_profile_boundary_payload(profile_type, "min")
    cleanup_registry.add(lambda: delete_neox_profile(api_client, session_manager, profile_type, path, readwrite_session))
    api_client.request("DELETE", path, session=readwrite_session)
    response = post_neox_profile(api_client, profile_type, path, readwrite_session, payload)
    assert_api_success(response)
    verify_neox_profile_cli(
        neox_config_service,
        env_config,
        ssh_username,
        ssh_password,
        profile_type,
        "min",
        payload,
        response,
    )


@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("profile_type", NEOX_PROFILE_READWRITE_TYPES, ids=NEOX_PROFILE_READWRITE_TYPES)
def test_neox_profile_max_create_readwrite(
    neox_config_service,
    api_client,
    env_config,
    session_manager,
    readwrite_session,
    cleanup_registry,
    profile_type,
):
    neox_config_service.verify_node3_target()
    ssh_username, ssh_password = neox_profile_cli_credentials(env_config)
    neox_config_service.ensure_neox_profile_dependencies(readwrite_session, cleanup_registry, profile_type)
    path = neox_config_service.neox_profile_path(profile_type)
    payload = neox_config_service.neox_profile_boundary_payload(profile_type, "max")
    cleanup_registry.add(lambda: delete_neox_profile(api_client, session_manager, profile_type, path, readwrite_session))
    api_client.request("DELETE", path, session=readwrite_session)
    response = post_neox_profile(api_client, profile_type, path, readwrite_session, payload)
    assert_api_success(response)
    verify_neox_profile_cli(
        neox_config_service,
        env_config,
        ssh_username,
        ssh_password,
        profile_type,
        "max",
        payload,
        response,
    )


@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("profile_type", NEOX_PROFILE_READWRITE_TYPES, ids=NEOX_PROFILE_READWRITE_TYPES)
def test_neox_profile_clear_readwrite(
    neox_config_service,
    api_client,
    session_manager,
    readwrite_session,
    cleanup_registry,
    profile_type,
):
    neox_config_service.verify_node3_target()
    neox_config_service.ensure_neox_profile_dependencies(readwrite_session, cleanup_registry, profile_type)
    path = neox_config_service.neox_profile_path(profile_type)
    payload = neox_config_service.neox_profile_payload(profile_type)
    cleanup_registry.add(lambda: delete_neox_profile(api_client, session_manager, profile_type, path, readwrite_session))
    api_client.request("DELETE", path, session=readwrite_session)
    response = post_neox_profile(api_client, profile_type, path, readwrite_session, payload)
    assert_api_success(response)
    response = delete_neox_profile(api_client, session_manager, profile_type, path, readwrite_session)
    assert_api_success(response)


@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("profile_type", NEOX_PROFILE_READWRITE_TYPES, ids=NEOX_PROFILE_READWRITE_TYPES)
def test_neox_profile_error_readwrite(
    neox_config_service,
    api_client,
    readwrite_session,
    profile_type,
):
    neox_config_service.verify_node3_target()
    path = neox_config_service.neox_profile_path(profile_type)
    response = api_client.request("POST", path, session=readwrite_session, json={"Content": {"__invalid_field__": "invalid"}})
    assert_api_failure(response, accepted_messages=("invalid field",))


def post_neox_profile(api_client, profile_type: str, path: str, session_id: str, payload: dict[str, Any]):
    original_timeout = api_client.timeout
    if profile_type == "ONTUNIProfile":
        api_client.timeout = neox_profile_post_timeout(original_timeout, read_timeout=1200)
    try:
        return api_client.request("POST", path, session=session_id, json=payload)
    finally:
        api_client.timeout = original_timeout


def delete_neox_profile(api_client, session_manager, profile_type: str, path: str, session_id: str):
    if profile_type != "ONTUNIProfile":
        return api_client.request("DELETE", path, session=session_id)
    with session_manager.role_session(SessionRole.READWRITE) as fresh_session:
        return api_client.request("DELETE", path, session=fresh_session)


def neox_profile_post_timeout(timeout, read_timeout: float):
    if isinstance(timeout, tuple):
        connect_timeout = timeout[0]
        return (connect_timeout, max(float(timeout[1]), read_timeout))
    return (float(timeout), read_timeout)


def neox_profile_cli_credentials(env_config) -> tuple[str, str]:
    ssh_username = os.environ.get("NEOX_SSH_USERNAME") or env_config.readwrite.username
    ssh_password = os.environ.get("NEOX_SSH_PASSWORD") or env_config.readwrite.password
    if not ssh_username or not ssh_password:
        pytest.skip("Set NEOX_SSH_USERNAME and NEOX_SSH_PASSWORD or readwrite credentials to run profile CLI verification.")
    return ssh_username, ssh_password


def verify_neox_profile_cli(
    neox_config_service,
    env_config,
    ssh_username: str,
    ssh_password: str,
    profile_type: str,
    boundary: str,
    payload: dict[str, Any],
    api_response,
) -> None:
    profile_name = neox_config_service.neox_profile_name(profile_type)
    cli_case = neox_profile_cli_verify_case(profile_type, boundary)
    command = cli_case["show_command"].format(profile_name=profile_name)
    expected_tokens = [token.format(profile_name=profile_name) for token in cli_case["expected_tokens"]]

    cli = SshCliClient(env_config.dut.device_ip, ssh_username, ssh_password)
    [cli_result] = cli.run_commands([command])
    missing = [token for token in expected_tokens if token not in cli_result.output]
    report_path = write_neox_profile_cli_report(
        neox_config_service,
        profile_type,
        boundary,
        payload,
        api_response,
        command,
        cli_result.output,
        expected_tokens,
        missing,
    )

    assert not missing, f"Missing NeoX profile CLI tokens for {profile_type}/{boundary}: {missing}. Report: {report_path}"


def write_neox_profile_cli_report(
    neox_config_service,
    profile_type: str,
    boundary: str,
    payload: dict[str, Any],
    api_response,
    command: str,
    cli_output: str,
    expected_tokens: list[str],
    missing_tokens: list[str],
) -> Path:
    root = Path(__file__).resolve().parents[1]
    reports_dir = root / "reports" / "device-verification"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"neox_profile_cli_verify_{profile_type}_{boundary}_{timestamp}.json"
    target = neox_config_service.target()
    data = {
        "target": {
            "node": neox_config_service.env_config.dut.node_key,
            "device_ip": neox_config_service.env_config.dut.device_ip,
            "device_name": target.device_name,
        },
        "profile": {
            "type": profile_type,
            "name": neox_config_service.neox_profile_name(profile_type),
            "boundary": boundary,
        },
        "rest_api": {
            "path": neox_config_service.neox_profile_path(profile_type),
            "request_content": redact(payload["Content"]),
            "response": {
                "status_code": api_response.status_code,
                "retstatus": api_response.retstatus,
                "retresult": api_response.retresult,
            },
        },
        "cli": {
            "transport": "ssh",
            "command": command,
            "output": cli_output,
            "expected_tokens": expected_tokens,
            "missing_tokens": missing_tokens,
        },
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
