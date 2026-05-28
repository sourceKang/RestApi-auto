from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from clients.ssh_cli import SshCliClient
from utils.allure_helpers import attach_json
from utils.redaction import redact


def neox_cli_credentials(env_config, feature: str) -> tuple[str, str]:
    ssh_username = os.environ.get("NEOX_SSH_USERNAME") or env_config.readwrite.username
    ssh_password = os.environ.get("NEOX_SSH_PASSWORD") or env_config.readwrite.password
    if not ssh_username or not ssh_password:
        pytest.skip(
            f"Set NEOX_SSH_USERNAME and NEOX_SSH_PASSWORD or readwrite credentials to run {feature} CLI verification."
        )
    return ssh_username, ssh_password


def run_neox_cli_commands(env_config, credentials: tuple[str, str], commands: list[str]) -> dict[str, str]:
    ssh_username, ssh_password = credentials
    client = SshCliClient(env_config.dut.device_ip, ssh_username, ssh_password)
    started = time.monotonic()
    try:
        results = client.run_commands(commands)
    except Exception as error:
        attach_json(
            "NeoX SSH failure diagnostics",
            {
                "node": env_config.dut.node_key,
                "device_name": env_config.dut.device_name,
                "target": env_config.dut.device_ip,
                "username": ssh_username,
                "commands": commands,
                "timeout_seconds": client.timeout,
                "duration_seconds": round(time.monotonic() - started, 3),
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
        raise
    return {result.command: result.output for result in results}


def missing_tokens(output: str, expected_tokens: list[str]) -> list[str]:
    normalized_output = output.casefold()
    return [token for token in expected_tokens if token.casefold() not in normalized_output]


def missing_tokens_by_command(
    output_by_command: dict[str, str],
    expected_by_command: dict[str, list[str]],
) -> dict[str, list[str]]:
    return {
        command: missing_tokens(output_by_command.get(command, ""), expected_tokens)
        for command, expected_tokens in expected_by_command.items()
    }


def write_neox_cli_verify_report(
    neox_config_service,
    feature: str,
    case_name: str,
    api_path: str,
    payload: dict[str, Any],
    api_response,
    output_by_command: dict[str, str],
    expected_by_command: dict[str, list[str]],
    missing_by_command: dict[str, list[str]],
    target_extra: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Path:
    reports_dir = Path(__file__).resolve().parents[2] / "reports" / "device-verification"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"neox_config_{feature}_cli_verify_{case_name}_{timestamp}.json"
    target = neox_config_service.target()
    target_data = {
        "node": neox_config_service.env_config.dut.node_key,
        "device_ip": neox_config_service.env_config.dut.device_ip,
        "device_name": target.device_name,
    }
    if target_extra:
        target_data.update(target_extra)
    data = {
        "target": target_data,
        "workflow": "REST API creates the NeoX config. CLI show commands verify device state.",
        "rest_api": {
            "path": api_path,
            "request": redact(payload),
            "response": {
                "status_code": api_response.status_code,
                "retstatus": api_response.retstatus,
                "retresult": api_response.retresult,
            },
        },
        "cli": {
            command: _cli_report_entry(
                output_by_command.get(command, ""),
                expected_by_command.get(command, []),
                missing_by_command.get(command, []),
            )
            for command in output_by_command
        },
    }
    if metadata:
        data["metadata"] = redact(metadata)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    attach_json(f"NeoX CLI verification {feature}/{case_name}", data)
    return path


def _cli_report_entry(output: str, expected_tokens: list[str], missing_tokens: list[str]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "transport": "ssh",
        "output_lines": _split_lines(output),
        "expected_tokens": [token for token in expected_tokens if not _is_multiline(token)],
        "missing_tokens": missing_tokens,
    }
    expected_output_lines = [_split_lines(token) for token in expected_tokens if _is_multiline(token)]
    if expected_output_lines:
        entry["expected_output_lines"] = expected_output_lines
    return entry


def _split_lines(value: str) -> list[str]:
    return value.replace("\r\n", "\n").replace("\r", "\n").splitlines()


def _is_multiline(value: str) -> bool:
    return "\n" in value or "\r" in value
