from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from models.api import SessionRole
from services.neox_config.cli_expectations import normalize_cli_output
from services.neox_config.profile_expectations import neox_profile_cli_field_mismatches, neox_profile_expected_tokens
from services.neox_config.service import (
    NEOX_PROFILE_READWRITE_TYPES,
    neox_profile_cli_verify_case,
)
from services.neox_config.profile_api import delete_profile_if_exists
from tests.support.neox_cli_verification import neox_cli_credentials, run_neox_cli_commands, write_neox_cli_verify_report
from tests.support.connectivity import assert_ping_reachable
from utils.assertions import assert_api_failure, assert_api_success
from utils.allure_helpers import attach_json


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.neox_profile,
    pytest.mark.destructive,
]


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
    request,
):
    with neox_profile_connectivity_guard(env_config, profile_type, "min_create", neox_profile_delay_seconds(request)):
        neox_config_service.verify_node3_target()
        ssh_username, ssh_password = neox_cli_credentials(env_config, "PROFILE")
        neox_config_service.ensure_neox_profile_dependencies(readwrite_session, cleanup_registry, profile_type)
        path = neox_config_service.neox_profile_path(profile_type)
        payload = neox_config_service.neox_profile_boundary_payload(profile_type, "min")
        cleanup_registry.add(lambda: delete_neox_profile(api_client, session_manager, profile_type, path, readwrite_session))
        delete_profile_if_exists(api_client, path, readwrite_session)
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
    request,
):
    with neox_profile_connectivity_guard(env_config, profile_type, "max_create", neox_profile_delay_seconds(request)):
        neox_config_service.verify_node3_target()
        ssh_username, ssh_password = neox_cli_credentials(env_config, "PROFILE")
        neox_config_service.ensure_neox_profile_dependencies(readwrite_session, cleanup_registry, profile_type)
        path = neox_config_service.neox_profile_path(profile_type)
        payload = neox_config_service.neox_profile_boundary_payload(profile_type, "max")
        cleanup_registry.add(lambda: delete_neox_profile(api_client, session_manager, profile_type, path, readwrite_session))
        delete_profile_if_exists(api_client, path, readwrite_session)
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
    env_config,
    session_manager,
    readwrite_session,
    cleanup_registry,
    profile_type,
    request,
):
    with neox_profile_connectivity_guard(env_config, profile_type, "clear", neox_profile_delay_seconds(request)):
        neox_config_service.verify_node3_target()
        ssh_username, ssh_password = neox_cli_credentials(env_config, "PROFILE")
        neox_config_service.ensure_neox_profile_dependencies(readwrite_session, cleanup_registry, profile_type)
        path = neox_config_service.neox_profile_path(profile_type)
        payload = neox_config_service.neox_profile_payload(profile_type)
        cleanup_registry.add(lambda: delete_neox_profile(api_client, session_manager, profile_type, path, readwrite_session))
        delete_profile_if_exists(api_client, path, readwrite_session)
        command = neox_profile_show_command(neox_config_service, profile_type)
        baseline_output = run_neox_profile_cli_command(env_config, ssh_username, ssh_password, command)
        response = post_neox_profile(api_client, profile_type, path, readwrite_session, payload)
        assert_api_success(response)
        response = delete_neox_profile(api_client, session_manager, profile_type, path, readwrite_session)
        assert_api_success(response)
        clear_output = run_neox_profile_cli_command(env_config, ssh_username, ssh_password, command)
        assert_neox_profile_node_reachable(env_config, profile_type, "clear", "after_cli_verify")
        assert normalize_cli_output(clear_output) == normalize_cli_output(baseline_output), (
            f"Profile clear CLI output differs for {profile_type}: {command}"
        )


@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("profile_type", NEOX_PROFILE_READWRITE_TYPES, ids=NEOX_PROFILE_READWRITE_TYPES)
def test_neox_profile_error_readwrite(
    neox_config_service,
    api_client,
    env_config,
    readwrite_session,
    profile_type,
    request,
):
    with neox_profile_connectivity_guard(env_config, profile_type, "error", neox_profile_delay_seconds(request)):
        neox_config_service.verify_node3_target()
        path = neox_config_service.neox_profile_path(profile_type)
        response = api_client.request("POST", path, session=readwrite_session, json={"Content": {"__invalid_field__": "invalid"}})
        assert_api_failure(response, accepted_messages=("invalid field",))


@contextmanager
def neox_profile_connectivity_guard(
    env_config,
    profile_type: str,
    case_name: str,
    delay_seconds: float,
) -> Iterator[None]:
    assert_neox_profile_node_reachable(env_config, profile_type, case_name, "before_case")
    try:
        yield
    finally:
        try:
            assert_neox_profile_node_reachable(env_config, profile_type, case_name, "after_case")
        finally:
            delay_between_neox_profile_cases(env_config, profile_type, case_name, delay_seconds)


def neox_profile_delay_seconds(request) -> float:
    value = request.config.getoption("--neox-profile-delay-seconds")
    if value < 0:
        pytest.fail("--neox-profile-delay-seconds must be greater than or equal to 0")
    return float(value)


def delay_between_neox_profile_cases(env_config, profile_type: str, case_name: str, delay_seconds: float) -> None:
    if delay_seconds <= 0:
        return
    started = time.monotonic()
    time.sleep(delay_seconds)
    attach_json(
        "NeoX profile inter-case delay",
        {
            "node": env_config.dut.node_key,
            "device_ip": env_config.dut.device_ip,
            "profile_type": profile_type,
            "case": case_name,
            "requested_seconds": delay_seconds,
            "actual_seconds": round(time.monotonic() - started, 3),
        },
    )


def assert_neox_profile_node_reachable(env_config, profile_type: str, case_name: str, checkpoint: str) -> None:
    assert_ping_reachable(
        env_config.dut.device_ip,
        checkpoint,
        context={
            "node": env_config.dut.node_key,
            "profile_type": profile_type,
            "case": case_name,
        },
    )


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


def neox_profile_show_command(neox_config_service, profile_type: str) -> str:
    profile_name = neox_config_service.neox_profile_name(profile_type)
    cli_case = neox_profile_cli_verify_case(profile_type, "min")
    return cli_case["show_command"].format(profile_name=profile_name)


def run_neox_profile_cli_command(env_config, ssh_username: str, ssh_password: str, command: str) -> str:
    return run_neox_cli_commands(env_config, (ssh_username, ssh_password), [command])[command]


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
    fallback_tokens = [token.format(profile_name=profile_name) for token in cli_case["expected_tokens"]]
    expected_tokens = neox_profile_expected_tokens(profile_type, payload, profile_name, fallback_tokens)

    cli_output = run_neox_profile_cli_command(env_config, ssh_username, ssh_password, command)
    assert_neox_profile_node_reachable(env_config, profile_type, boundary, "after_cli_verify")
    missing = [token for token in expected_tokens if token not in cli_output]
    field_mismatches = neox_profile_cli_field_mismatches(profile_type, payload, cli_output)
    cli_failures = missing + field_mismatches
    report_path = write_neox_cli_verify_report(
        neox_config_service,
        "profile",
        f"{profile_type}_{boundary}",
        neox_config_service.neox_profile_path(profile_type),
        payload,
        api_response,
        {command: cli_output},
        {command: expected_tokens},
        {command: cli_failures},
        metadata={
            "profile": {
                "type": profile_type,
                "name": profile_name,
                "boundary": boundary,
            },
        },
    )

    assert not cli_failures, (
        f"NeoX profile CLI verification failed for {profile_type}/{boundary}: {cli_failures}. Report: {report_path}"
    )
