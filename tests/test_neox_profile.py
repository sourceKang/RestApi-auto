from __future__ import annotations

import copy
import json
import time
from datetime import datetime
from pathlib import Path
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
    neox_profile_negative_cases_config,
)
from services.neox_config.profile_api import delete_profile_if_exists
from tests.support.neox_cli_verification import neox_cli_credentials, run_neox_cli_commands, write_neox_cli_verify_report
from tests.support.connectivity import assert_ping_reachable
from utils.assertions import assert_api_success
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
        path = neox_config_service.neox_profile_path(profile_type)
        payload = neox_config_service.neox_profile_boundary_payload(profile_type, "min")
        neox_config_service.ensure_neox_profile_dependencies(readwrite_session, cleanup_registry, profile_type, payload)
        cleanup_registry.add(lambda: delete_neox_profile(api_client, session_manager, profile_type, path, readwrite_session))
        delete_profile_if_exists(api_client, path, readwrite_session)
        response = post_neox_profile(api_client, profile_type, path, readwrite_session, payload, phase="min")
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
        path = neox_config_service.neox_profile_path(profile_type)
        payload = neox_config_service.neox_profile_boundary_payload(profile_type, "max")
        neox_config_service.ensure_neox_profile_dependencies(readwrite_session, cleanup_registry, profile_type, payload)
        cleanup_registry.add(lambda: delete_neox_profile(api_client, session_manager, profile_type, path, readwrite_session))
        delete_profile_if_exists(api_client, path, readwrite_session)
        response = post_neox_profile(api_client, profile_type, path, readwrite_session, payload, phase="max")
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
        path = neox_config_service.neox_profile_path(profile_type)
        payload = neox_config_service.neox_profile_payload(profile_type)
        neox_config_service.ensure_neox_profile_dependencies(readwrite_session, cleanup_registry, profile_type, payload)
        cleanup_registry.add(lambda: delete_neox_profile(api_client, session_manager, profile_type, path, readwrite_session))
        delete_profile_if_exists(api_client, path, readwrite_session)
        command = neox_profile_show_command(neox_config_service, profile_type)
        baseline_output = run_neox_profile_cli_command(env_config, ssh_username, ssh_password, command)
        response = post_neox_profile(api_client, profile_type, path, readwrite_session, payload, phase="clear_seed")
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
    session_manager,
    readwrite_session,
    cleanup_registry,
    profile_type,
    request,
):
    with neox_profile_connectivity_guard(env_config, profile_type, "error", neox_profile_delay_seconds(request)):
        neox_config_service.verify_node3_target()
        verify_neox_profile_error_cases(
            neox_config_service,
            api_client,
            session_manager,
            readwrite_session,
            cleanup_registry,
            profile_type,
        )


def neox_profile_negative_cases(profile_type: str) -> list[dict[str, Any]]:
    cases = neox_profile_negative_cases_config(profile_type)
    if not cases:
        pytest.fail(f"No NeoX profile negative cases configured for {profile_type}")
    return cases


def verify_neox_profile_error_cases(
    neox_config_service,
    api_client,
    session_manager,
    readwrite_session: str,
    cleanup_registry,
    profile_type: str,
) -> None:
    path = neox_config_service.neox_profile_path(profile_type)
    profile_name = neox_config_service.neox_profile_name(profile_type)
    cleanup_registry.add(lambda: delete_neox_profile(api_client, session_manager, profile_type, path, readwrite_session))
    observations = []
    failures = []
    for negative_case in neox_profile_negative_cases(profile_type):
        payload = negative_case["payload"]
        delete_profile_if_exists(api_client, path, readwrite_session)
        response = post_neox_profile(api_client, profile_type, path, readwrite_session, payload, phase="error")
        assert_invalid_profile_post_did_not_succeed(profile_type, negative_case, response)
        observation = {
            "case": negative_case.get("name"),
            "field": negative_case.get("field"),
            "request": payload,
            "expected": {
                "error_layer": negative_case.get("error_layer"),
                "status_code": negative_case.get("expected_status_code"),
                "retstatus": negative_case.get("expected_retstatus"),
                "message_contains": negative_case.get("expected_message_contains"),
                "message_assertion": profile_error_message_assertion_mode(negative_case),
            },
            "response": {
                "status_code": response.status_code,
                "retstatus": response.retstatus,
                "retresult": response.retresult,
                "body": response.json,
            },
        }
        observations.append(observation)
        try:
            assert_neox_profile_error_response(negative_case, response)
        except AssertionError as error:
            failures.append({"case": negative_case.get("name"), "error": str(error), "observation": observation})

    report_path = write_neox_profile_error_report(
        neox_config_service,
        profile_type,
        profile_name,
        path,
        observations,
        failures,
    )
    attach_json(
        f"NeoX {profile_type} error matrix",
        {"report": str(report_path), "failures": failures, "observations": observations},
    )
    assert not failures, f"{profile_type} profile error matrix had {len(failures)} mismatches. Report: {report_path}"


def assert_invalid_profile_post_did_not_succeed(profile_type: str, negative_case: dict[str, Any], response) -> None:
    if response.retstatus == "Success" and response.status_code < 400:
        pytest.fail(
            f"{profile_type} {negative_case['name']} invalid POST unexpectedly succeeded: "
            f"HTTP={response.status_code}, retstatus={response.retstatus!r}, body={response.text}"
        )


def assert_neox_profile_error_response(negative_case: dict[str, Any], response) -> None:
    if is_profile_api_schema_error_case(negative_case):
        assert_expected_profile_error_status(negative_case, response)
        assert_expected_profile_error_message(negative_case, response)
        return

    assert_profile_failure_response(negative_case, response)
    failure_message = profile_response_failure_message(response)
    assert failure_message, (
        f"{negative_case['name']} expected a non-empty device/API failure message, got response: {response.text}"
    )


def assert_expected_profile_error_status(negative_case: dict[str, Any], response) -> None:
    expected_status_code = negative_case.get("expected_status_code")
    if expected_status_code is not None:
        assert response.status_code == int(expected_status_code), (
            f"{negative_case['name']} expected HTTP {expected_status_code}, got {response.status_code}: {response.text}"
        )
    assert_profile_failure_response(negative_case, response)


def assert_profile_failure_response(negative_case: dict[str, Any], response) -> None:
    expected_retstatus = negative_case.get("expected_retstatus")
    if expected_retstatus:
        assert response.retstatus == expected_retstatus, (
            f"{negative_case['name']} expected retstatus {expected_retstatus!r}, got {response.retstatus!r}: {response.text}"
        )
        return

    assert response.retstatus == "Fail" or response.status_code >= 400, (
        f"{negative_case['name']} expected failure response, got HTTP={response.status_code}: {response.text}"
    )


def assert_expected_profile_error_message(negative_case: dict[str, Any], response) -> None:
    expected_message = negative_case.get("expected_message_contains")
    if not expected_message:
        failure_message = profile_response_failure_message(response)
        assert failure_message, (
            f"{negative_case['name']} expected a non-empty failure message, got response: {response.text}"
        )
        return

    expected_messages = [expected_message] if isinstance(expected_message, str) else list(expected_message)
    response_text = json.dumps(response.json, ensure_ascii=False, default=str)
    missing = [message for message in expected_messages if str(message).lower() not in response_text.lower()]
    assert not missing, f"{negative_case['name']} missing expected error text {missing}: {response_text}"


def is_profile_api_schema_error_case(negative_case: dict[str, Any]) -> bool:
    return str(negative_case.get("error_layer")) == "api_schema"


def profile_error_message_assertion_mode(negative_case: dict[str, Any]) -> str:
    if is_profile_api_schema_error_case(negative_case):
        return "contains_expected_text"
    return "non_empty_only"


def profile_response_failure_message(response) -> str:
    values = [response.retresult]
    if isinstance(response.json, dict):
        values.extend(response.json.get(key) for key in ("retresult", "retval", "message", "error"))
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def write_neox_profile_error_report(
    neox_config_service,
    profile_type: str,
    profile_name: str,
    path: str,
    observations: list[dict],
    failures: list[dict],
) -> Path:
    reports_dir = Path(__file__).resolve().parents[1] / "reports" / "device-verification"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"neox_config_profile_error_matrix_{profile_type}_{timestamp}.json"
    data = {
        "target": {
            "node": neox_config_service.env_config.dut.node_key,
            "device_ip": neox_config_service.env_config.dut.device_ip,
            "device_name": neox_config_service.target().device_name,
            "profile_type": profile_type,
            "profile_name": profile_name,
        },
        "rest_api": {"path": path},
        "workflow": (
            "Each profile invalid payload clears the profile before POST. API/schema-layer cases assert the "
            "stable status/message contract; device CLI-layer cases assert failure and a non-empty error "
            "message without pinning device wording. CLI verification is intentionally disabled for profile "
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


def post_neox_profile(
    api_client,
    profile_type: str,
    path: str,
    session_id: str,
    payload: dict[str, Any],
    *,
    phase: str = "post",
):
    original_timeout = api_client.timeout
    if profile_type == "ONTUNIProfile":
        api_client.timeout = neox_profile_post_timeout(original_timeout, read_timeout=1200)
    elif profile_type == "IGMPGroupPrivilegeProfile":
        api_client.timeout = neox_profile_post_timeout(original_timeout, read_timeout=300)

    effective_timeout = api_client.timeout
    started = time.monotonic()
    response = None
    error_text = None
    try:
        response = api_client.request("POST", path, session=session_id, json=payload)
        return response
    except Exception as error:
        error_text = f"{type(error).__name__}: {error}"
        raise
    finally:
        elapsed = time.monotonic() - started
        write_neox_profile_post_timing(
            profile_type,
            phase,
            path,
            payload,
            effective_timeout,
            elapsed,
            response,
            error_text,
        )
        api_client.timeout = original_timeout


def write_neox_profile_post_timing(
    profile_type: str,
    phase: str,
    path: str,
    payload: dict[str, Any],
    timeout,
    elapsed_seconds: float,
    response,
    error_text: str | None,
) -> Path:
    reports_dir = Path(__file__).resolve().parents[1] / "reports" / "device-verification"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    report_path = reports_dir / f"neox_profile_post_timing_{safe_report_name(profile_type)}_{safe_report_name(phase)}_{timestamp}.json"
    data = {
        "profile_type": profile_type,
        "phase": phase,
        "method": "POST",
        "path": path,
        "timeout": timeout_to_report(timeout),
        "timing": {
            "wall_elapsed_seconds": round(elapsed_seconds, 3),
            "http_elapsed_seconds": response_elapsed_seconds(response),
        },
        "payload_shape": profile_payload_shape(payload),
        "response": profile_post_response_summary(response),
        "error": error_text,
    }
    report_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    attach_json(f"NeoX profile POST timing {profile_type}/{phase}", {"report": str(report_path), **data})
    return report_path


def timeout_to_report(timeout) -> dict[str, float | None] | float | None:
    if timeout is None:
        return None
    if isinstance(timeout, tuple):
        connect_timeout = float(timeout[0]) if timeout[0] is not None else None
        read_timeout = float(timeout[1]) if timeout[1] is not None else None
        return {"connect_seconds": connect_timeout, "read_seconds": read_timeout}
    return float(timeout)


def response_elapsed_seconds(response) -> float | None:
    if response is None:
        return None
    return round(float(getattr(response, "elapsed", 0.0) or 0.0), 3)


def profile_post_response_summary(response) -> dict[str, Any] | None:
    if response is None:
        return None
    return {
        "status_code": response.status_code,
        "retstatus": response.retstatus,
        "retresult": response.retresult,
    }


def profile_payload_shape(payload: dict[str, Any]) -> dict[str, Any]:
    content = payload.get("Content", {})
    content_keys = sorted(content) if isinstance(content, dict) else []
    return {
        "content_key_count": len(content_keys),
        "leaf_value_count": count_payload_leaf_values(content),
        "content_keys": content_keys,
    }


def count_payload_leaf_values(value: Any) -> int:
    if isinstance(value, dict):
        return sum(count_payload_leaf_values(item) for item in value.values())
    if isinstance(value, list):
        return sum(count_payload_leaf_values(item) for item in value)
    return 1


def safe_report_name(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "_" for character in value)


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
