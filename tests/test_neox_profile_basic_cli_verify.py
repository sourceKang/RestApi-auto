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


BASIC_PROFILE_CASES_FILE = Path(__file__).resolve().parents[1] / "configs" / "neox_profile_basic_cases.json"


def test_neox_basic_profiles_create_and_cli_verify(
    api_client,
    env_config,
    neox_config_service,
    session_manager,
):
    neox_config_service.verify_required_target_data()
    ssh_username = os.environ.get("NEOX_SSH_USERNAME") or env_config.readwrite.username
    ssh_password = os.environ.get("NEOX_SSH_PASSWORD") or env_config.readwrite.password
    if not ssh_username or not ssh_password:
        pytest.skip("Set NEOX_SSH_USERNAME and NEOX_SSH_PASSWORD or readwrite credentials to run profile CLI verification.")

    cli = SshCliClient(env_config.dut.device_ip, ssh_username, ssh_password)
    config = json.loads(BASIC_PROFILE_CASES_FILE.read_text(encoding="utf-8"))
    results = []
    with session_manager.role_session(SessionRole.READWRITE) as readwrite_session:
        for case in config["cases"]:
            path = neox_profile_path(neox_config_service, case["profile_type"], case["profile_name"])
            api_client.request("DELETE", path, session=readwrite_session)
            response = api_client.request("POST", path, session=readwrite_session, json=case["payload"])
            assert_api_success(response)

            command = case["show_command"].format(profile_name=case["profile_name"])
            [cli_result] = cli.run_commands([command])
            expected_tokens = [token.format(profile_name=case["profile_name"]) for token in case["expected_tokens"]]
            missing = [token for token in expected_tokens if token not in cli_result.output]
            results.append(
                {
                    "profile_type": case["profile_type"],
                    "profile_name": case["profile_name"],
                    "request_content": redact(case["payload"]["Content"]),
                    "response": {
                        "retstatus": response.retstatus,
                        "retresult": response.retresult,
                    },
                    "cli": {
                        "command": command,
                        "missing_tokens": missing,
                        "output": cli_result.output,
                    },
                }
            )
            api_client.request("DELETE", path, session=readwrite_session)
            assert not missing, f"Missing NeoX profile CLI tokens for {case['profile_name']}: {missing}"

    report_path = write_basic_profile_report(neox_config_service, results)
    assert results, f"No NeoX basic profile cases executed. Report: {report_path}"


def neox_profile_path(neox_config_service, profile_type: str, profile_name: str) -> str:
    target = neox_config_service.target()
    return f"/configNeoXSeries/profile/{target.device_name}/{profile_type}/{profile_name}"


def write_basic_profile_report(neox_config_service, results: list[dict[str, Any]]) -> Path:
    reports_dir = Path(__file__).resolve().parents[1] / "reports" / "device-verification"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"neox_basic_profile_cli_verify_{timestamp}.json"
    target = neox_config_service.target()
    data = {
        "target": {
            "node": neox_config_service.env_config.dut.node_key,
            "device_ip": neox_config_service.env_config.dut.device_ip,
            "device_name": target.device_name,
        },
        "workflow": "Swagger determines JSON keys; NeoX UG determines value/range; CLI show verifies device state.",
        "results": results,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
