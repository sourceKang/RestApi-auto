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
    pytest.mark.destructive,
    pytest.mark.mutating,
    pytest.mark.readwrite,
]


FULL_ACCEPTED_PAYLOAD_FILE = Path(__file__).resolve().parents[1] / "configs" / "neox_nni_full_accepted_payload.json"


def test_nni_config_api_is_applied_to_device_running_config(
    api_client,
    env_config,
    neox_config_service,
    session_manager,
):
    neox_config_service.verify_required_target_data()
    ssh_username = os.environ.get("NEOX_SSH_USERNAME") or env_config.readwrite.username
    ssh_password = os.environ.get("NEOX_SSH_PASSWORD") or env_config.readwrite.password
    if not ssh_username or not ssh_password:
        pytest.skip("Set NEOX_SSH_USERNAME and NEOX_SSH_PASSWORD or readwrite credentials to run NNI CLI verification.")

    with session_manager.role_session(SessionRole.READWRITE) as readwrite_session:
        config = json.loads(FULL_ACCEPTED_PAYLOAD_FILE.read_text(encoding="utf-8"))
        payload = config["payload"]
        expected_lines = config["running_config_visible_lines"]
        response = api_client.request("POST", neox_config_service.nni_path(), session=readwrite_session, json=payload)
        assert_api_success(response)

        target = neox_config_service.target()
        command = f"show running-config interface nni {target.nni_port_id}"
        cli = SshCliClient(env_config.dut.device_ip, ssh_username, ssh_password)
        [result] = cli.run_commands([command])

        missing = [expected for expected in expected_lines if expected not in result.output]
        report_path = write_nni_cli_verify_report(
            neox_config_service,
            payload,
            response,
            command,
            result.output,
            expected_lines,
            missing,
        )

        assert not missing, f"Missing NNI running-config lines: {missing}. Report: {report_path}"


def write_nni_cli_verify_report(
    neox_config_service,
    payload: dict[str, Any],
    api_response,
    command: str,
    cli_output: str,
    expected_lines: list[str],
    missing_lines: list[str],
) -> Path:
    root = Path(__file__).resolve().parents[1]
    reports_dir = root / "reports" / "device-verification"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"nni_cli_verify_{timestamp}.json"
    target = neox_config_service.target()
    data = {
        "target": {
            "node": neox_config_service.env_config.dut.node_key,
            "device_ip": neox_config_service.env_config.dut.device_ip,
            "device_name": target.device_name,
            "nni_slot_id": target.nni_slot_id,
            "nni_port_id": target.nni_port_id,
        },
        "rest_api": {
            "path": neox_config_service.nni_path(),
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
            "expected_lines": expected_lines,
            "missing_lines": missing_lines,
        },
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
