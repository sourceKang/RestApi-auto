from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from clients.ssh_cli import SshCliClient
from services.neox_config.service import ge_port_payload
from utils.assertions import assert_api_success
from utils.redaction import redact


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.destructive,
    pytest.mark.mutating,
    pytest.mark.readwrite,
]


def test_ge_config_api_is_applied_to_device_running_config(
    api_client,
    env_config,
    neox_config_service,
    readwrite_session,
    cleanup_registry,
):
    neox_config_service.verify_required_target_data()
    ssh_username = os.environ.get("NEOX_SSH_USERNAME")
    ssh_password = os.environ.get("NEOX_SSH_PASSWORD")
    if not ssh_username or not ssh_password:
        pytest.skip("Set NEOX_SSH_USERNAME and NEOX_SSH_PASSWORD to run GE CLI verification.")

    cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session))
    api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)
    payload = ge_port_payload()
    response = api_client.request("POST", neox_config_service.ge_path(), session=readwrite_session, json=payload)
    assert_api_success(response)

    target = neox_config_service.target()
    command = f"show running-config interface ge {target.ge_slot_id}-{target.ge_port_id}"
    cli = SshCliClient(env_config.dut.device_ip, ssh_username, ssh_password)
    [result] = cli.run_commands([command])
    checks = ge_cli_checks(payload["Content"])
    missing = [expected for expected in checks if expected not in result.output]
    report_path = write_cli_verify_report(neox_config_service, payload, response, command, result.output, checks, missing)

    assert not missing, f"Missing GE running-config lines: {missing}. Report: {report_path}"


def ge_cli_checks(content: dict[str, Any]) -> list[str]:
    checks = []
    if content.get("portenable") == "enable":
        checks.append("enable")
    if "auto_nego" in content:
        checks.append(f"auto-negotiation {content['auto_nego']}")
    if "flow" in content:
        checks.append(f"flow-control {content['flow']}")
    if "portspeed" in content:
        checks.append(f"speed {content['portspeed']}")
    if "portname" in content:
        checks.append(f"name \"{content['portname']}\"")
    if "arpinspection" in content:
        checks.append(f"arp-inspection {content['arpinspection']}")
    if "copycpbit" in content:
        checks.append(f"vlan copy_cpbit {content['copycpbit']}")
    if "outertpid" in content:
        checks.append(f"vlan outer-tpid {content['outertpid']}")
    if "frametype" in content:
        checks.append(f"frame-type {content['frametype']}")
    return checks


def write_cli_verify_report(
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
    path = reports_dir / f"ge_cli_verify_{timestamp}.json"
    target = neox_config_service.target()
    data = {
        "target": {
            "node": neox_config_service.env_config.dut.node_key,
            "device_ip": neox_config_service.env_config.dut.device_ip,
            "device_name": target.device_name,
            "ge_slot_id": target.ge_slot_id,
            "ge_port_id": target.ge_port_id,
        },
        "rest_api": {
            "path": neox_config_service.ge_path(),
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
