from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from clients.ssh_cli import SshCliClient
from models.api import SessionRole
from utils.assertions import assert_api_success
from utils.redaction import redact


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.neox_profile,
    pytest.mark.destructive,
    pytest.mark.mutating,
    pytest.mark.readwrite,
]


QOS_MINMAX_CASES_FILE = Path(__file__).resolve().parents[1] / "configs" / "neox_profile_qos_minmax_cases.json"


def load_qos_profile_cases() -> list[dict[str, Any]]:
    config = json.loads(QOS_MINMAX_CASES_FILE.read_text(encoding="utf-8"))
    return [case for case in config["cases"] if case.get("enabled") is not False]


def qos_profile_case_id(case: dict[str, Any]) -> str:
    return f"{case['profile_type']}::{case['boundary']}::{case['profile_name']}"


@pytest.mark.parametrize("case", load_qos_profile_cases(), ids=qos_profile_case_id)
def test_neox_qos_profile_minmax_create_readwrite(
    api_client,
    env_config,
    neox_config_service,
    session_manager,
    case,
):
    neox_config_service.verify_required_target_data()
    ssh_username = os.environ.get("NEOX_SSH_USERNAME") or env_config.readwrite.username
    ssh_password = os.environ.get("NEOX_SSH_PASSWORD") or env_config.readwrite.password
    if not ssh_username or not ssh_password:
        pytest.skip("Set NEOX_SSH_USERNAME and NEOX_SSH_PASSWORD or readwrite credentials to run QoS profile CLI verification.")

    cli = SshCliClient(env_config.dut.device_ip, ssh_username, ssh_password)
    with session_manager.role_session(SessionRole.READWRITE) as readwrite_session:
        path = neox_profile_path(neox_config_service, case["profile_type"], case["profile_name"])
        api_client.request("DELETE", path, session=readwrite_session)
        response = api_client.request("POST", path, session=readwrite_session, json=case["payload"])
        assert_api_success(response)

        command = case["show_command"].format(profile_name=case["profile_name"])
        [cli_result] = cli.run_commands([command])
        expected_tokens = [token.format(profile_name=case["profile_name"]) for token in case["expected_tokens"]]
        missing = [token for token in expected_tokens if token not in cli_result.output]
        result = {
            "case": case["profile_name"],
            "profile_type": case["profile_type"],
            "boundary": case["boundary"],
            "path": path,
            "payload": redact(case["payload"]),
            "response": response_summary(response),
            "cli": {
                "command": command,
                "output": cli_result.output,
                "expected_tokens": expected_tokens,
                "missing_tokens": missing,
            },
        }
        api_client.request("DELETE", path, session=readwrite_session)
        assert not missing, f"Missing QoS profile CLI tokens for {case['profile_name']}: {missing}"

    write_qos_profile_report(neox_config_service, [result])


@pytest.mark.parametrize("case", load_qos_profile_cases(), ids=qos_profile_case_id)
def test_neox_qos_profile_minmax_clear_readwrite(
    api_client,
    neox_config_service,
    session_manager,
    case,
):
    neox_config_service.verify_required_target_data()
    with session_manager.role_session(SessionRole.READWRITE) as readwrite_session:
        path = neox_profile_path(neox_config_service, case["profile_type"], case["profile_name"])
        api_client.request("DELETE", path, session=readwrite_session)
        response = api_client.request("POST", path, session=readwrite_session, json=case["payload"])
        assert_api_success(response)
        response = api_client.request("DELETE", path, session=readwrite_session)
        assert_api_success(response)


def neox_profile_path(neox_config_service, profile_type: str, profile_name: str) -> str:
    target = neox_config_service.target()
    return f"/configNeoXSeries/profile/{target.device_name}/{profile_type}/{profile_name}"


def response_summary(response) -> dict[str, Any]:
    return {
        "status_code": response.status_code,
        "retstatus": response.retstatus,
        "retresult": response.retresult,
    }


def write_qos_profile_report(neox_config_service, results: list[dict[str, Any]]) -> Path:
    root = Path(__file__).resolve().parents[1]
    reports_dir = root / "reports" / "device-verification"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"neox_qos_profile_minmax_cli_verify_{timestamp}.json"
    target = neox_config_service.target()
    data = {
        "target": {
            "node": neox_config_service.env_config.dut.node_key,
            "device_ip": neox_config_service.env_config.dut.device_ip,
            "device_name": target.device_name,
        },
        "results": results,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
