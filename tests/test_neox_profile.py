from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from collections.abc import Iterator
from typing import Any

import pytest

from models.api import SessionRole
from services.neox_config.service import (
    NEOX_PROFILE_READWRITE_TYPES,
    neox_profile_cli_verify_case,
)
from tests.support.neox_profile_api import delete_profile_if_exists
from tests.support.neox_cli_verification import run_neox_cli_commands
from tests.support.connectivity import assert_ping_reachable
from utils.assertions import assert_api_failure, assert_api_success
from utils.allure_helpers import attach_json
from utils.redaction import redact


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
):
    with neox_profile_connectivity_guard(env_config, profile_type, "min_create"):
        neox_config_service.verify_node3_target()
        ssh_username, ssh_password = neox_profile_cli_credentials(env_config)
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
):
    with neox_profile_connectivity_guard(env_config, profile_type, "max_create"):
        neox_config_service.verify_node3_target()
        ssh_username, ssh_password = neox_profile_cli_credentials(env_config)
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
):
    with neox_profile_connectivity_guard(env_config, profile_type, "clear"):
        neox_config_service.verify_node3_target()
        ssh_username, ssh_password = neox_profile_cli_credentials(env_config)
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
):
    with neox_profile_connectivity_guard(env_config, profile_type, "error"):
        neox_config_service.verify_node3_target()
        path = neox_config_service.neox_profile_path(profile_type)
        response = api_client.request("POST", path, session=readwrite_session, json={"Content": {"__invalid_field__": "invalid"}})
        assert_api_failure(response, accepted_messages=("invalid field",))


@contextmanager
def neox_profile_connectivity_guard(env_config, profile_type: str, case_name: str) -> Iterator[None]:
    assert_neox_profile_node_reachable(env_config, profile_type, case_name, "before_case")
    try:
        yield
    finally:
        assert_neox_profile_node_reachable(env_config, profile_type, case_name, "after_case")


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


def neox_profile_cli_credentials(env_config) -> tuple[str, str]:
    ssh_username = os.environ.get("NEOX_SSH_USERNAME") or env_config.readwrite.username
    ssh_password = os.environ.get("NEOX_SSH_PASSWORD") or env_config.readwrite.password
    if not ssh_username or not ssh_password:
        pytest.skip("Set NEOX_SSH_USERNAME and NEOX_SSH_PASSWORD or readwrite credentials to run profile CLI verification.")
    return ssh_username, ssh_password


def neox_profile_show_command(neox_config_service, profile_type: str) -> str:
    profile_name = neox_config_service.neox_profile_name(profile_type)
    cli_case = neox_profile_cli_verify_case(profile_type, "min")
    return cli_case["show_command"].format(profile_name=profile_name)


def run_neox_profile_cli_command(env_config, ssh_username: str, ssh_password: str, command: str) -> str:
    return run_neox_cli_commands(env_config, (ssh_username, ssh_password), [command])[command]


def normalize_cli_output(output: str) -> str:
    lines = [line.rstrip() for line in output.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line.strip())


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
    report_path = write_neox_profile_cli_report(
        neox_config_service,
        profile_type,
        boundary,
        payload,
        api_response,
        command,
        cli_output,
        expected_tokens,
        missing,
    )

    assert not missing, f"Missing NeoX profile CLI tokens for {profile_type}/{boundary}: {missing}. Report: {report_path}"


def neox_profile_expected_tokens(
    profile_type: str,
    payload: dict[str, Any],
    profile_name: str,
    fallback_tokens: list[str],
) -> list[str]:
    content = payload.get("Content", {})
    tokens = [profile_name]
    if profile_type == "IGMPGroupPrivilegeProfile":
        tokens.extend(content_values(content, ("grpbandwidth", "startip", "endip", "prvitype")))
    elif profile_type == "ONTAclProfile":
        tokens.extend(ont_acl_profile_tokens(content))
    elif profile_type == "ONTAlarmProfile":
        tokens.extend(ont_alarm_profile_tokens(content))
    elif profile_type == "ONTBandwidthProfile":
        tokens.extend(content_values(content, ("sir", "air", "pir")))
    elif profile_type == "ONTMulticastProfile":
        tokens.extend(content_values(content, ("univid", "igmp", "mode", "txtagvid", "txtagpbit", "maxgroup", "maxmsg")))
    elif profile_type == "ONTONTProfile":
        tokens.extend(content_values(content, ("fwlevel", "telnetport")))
    elif profile_type == "ONTSecurityProfile":
        tokens.extend(content_values(content, ("spoofingdisable", "fdb")))
    elif profile_type == "ONTServiceProfile":
        tokens.extend(ont_service_profile_tokens(content))
    elif profile_type == "ONTTemplateProfile":
        tokens.extend(ont_template_profile_tokens(content))
    elif profile_type == "ONTUNIProfile":
        tokens.extend(ont_uni_profile_tokens(content))
    elif profile_type == "ONTVoipCommonProfile":
        tokens.extend(content_values(content, content.keys()))
    elif profile_type == "ONTVoipDialPlanProfile":
        tokens.extend(content_values(content, ("max", "critical", "partial", "format", "identifier")))
    elif profile_type == "ONTVoipSipProfile":
        tokens.extend(content_values(content, content.keys()))
    elif profile_type == "RateLimitProfile":
        tokens.extend(rate_limit_profile_tokens(content))
    elif profile_type == "ShapingProfile":
        tokens.extend(content_values(content, sorted(content)))
    elif profile_type == "WeightProfile":
        tokens.extend(content_values(content, sorted(content)))
    else:
        tokens.extend(fallback_tokens)
    return unique_tokens(tokens)


def content_values(content: dict[str, Any], keys: Any) -> list[str]:
    values = []
    for key in keys:
        if key in content:
            values.append(content[key])
            continue
        for content_key, value in content.items():
            if str(content_key).startswith(str(key)):
                values.append(value)
    return [str(value) for value in values if value not in (None, "")]


def ont_acl_profile_tokens(content: dict[str, Any]) -> list[str]:
    tokens = content_values(
        content,
        ("protocol", "srcport", "destport", "srcmask", "destmask", "srcip", "destip", "srcmac", "destmac"),
    )
    if content.get("policy"):
        tokens.append(str(content["policy"]).title())
    if content.get("interface"):
        tokens.append(acl_interface_token(str(content["interface"])))
    for field in ("enable", "logging", "counter"):
        if field in content:
            tokens.append(yes_no_token(content[field]))
    return tokens


def acl_interface_token(value: str) -> str:
    return {
        "both": "LAN&WAN (Both)",
        "lan": "LAN",
        "wan": "WAN",
    }.get(value, value)


def yes_no_token(value: Any) -> str:
    return "Yes" if str(value).casefold() in {"enable", "enabled", "active", "yes", "y", "1"} else "No"


def ont_alarm_profile_tokens(content: dict[str, Any]) -> list[str]:
    tokens = [
        format_fixed_decimal(content.get("lowvolt"), 2),
        format_fixed_decimal(content.get("upvol"), 2),
        str(content.get("lowcurr", "")),
        str(content.get("upcurr", "")),
        str(content.get("lowtemp", "")),
        str(content.get("uptemp", "")),
        str(content.get("lowtxpower", "")),
        str(content.get("uptxpower", "")),
        format_fixed_decimal(content.get("lowrxpower"), 1),
        format_fixed_decimal(content.get("uprxpower"), 1),
    ]
    return [token for token in tokens if token]


def format_fixed_decimal(value: Any, places: int) -> str:
    if value in (None, ""):
        return ""
    return f"{float(value):.{places}f}"


def ont_service_profile_tokens(content: dict[str, Any]) -> list[str]:
    tokens = content_values(content, ("vlan", "pbit", "mode"))
    if content.get("lan"):
        tokens.append(f"port_lan: {content['lan']}")
    if content.get("xlan"):
        tokens.append(f"port_xlan: {content['xlan']}")
    return tokens


def ont_template_profile_tokens(content: dict[str, Any]) -> list[str]:
    tokens = content_values(
        content,
        (
            "dsop",
            "enc_algorithm",
            "alarmprof",
            "secprof",
            "ontprof",
            "mprof",
        ),
    )
    return tokens


def ont_uni_profile_tokens(content: dict[str, Any]) -> list[str]:
    tokens = []
    for key, value in content.items():
        if value in (None, ""):
            continue
        if str(key).endswith("vlan") or "vlan" in str(key) or str(key).endswith("uniport"):
            tokens.append(str(value))
    return tokens


def rate_limit_profile_tokens(content: dict[str, Any]) -> list[str]:
    tokens = []
    for active_key in ("ingressactive", "egressactive"):
        if active_key in content:
            tokens.append(active_token(content[active_key]))
    tokens.extend(content_values(content, ("cirrate", "cbsrate", "eirrate", "ebsrate", "egressrate", "burstrate")))
    return tokens


def active_token(value: Any) -> str:
    return "Y" if str(value).casefold() in {"active", "enable", "enabled", "yes", "y", "1"} else "N"


def unique_tokens(tokens: list[str]) -> list[str]:
    seen = set()
    unique = []
    for token in tokens:
        if token in (None, ""):
            continue
        text = str(token)
        if text not in seen:
            seen.add(text)
            unique.append(text)
    return unique


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
    attach_json(f"NeoX profile CLI verification {profile_type}/{boundary}", data)
    return path
