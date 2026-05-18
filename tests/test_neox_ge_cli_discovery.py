from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from clients.ssh_cli import SshCliClient


COMMANDS_FILE = Path(__file__).resolve().parents[1] / "configs" / "neox_ge_show_commands.json"


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.neox_probe,
]


def test_ge_show_feature_commands_discovery(env_config, neox_config_service):
    neox_config_service.verify_required_target_data()
    ssh_username = os.environ.get("NEOX_SSH_USERNAME")
    ssh_password = os.environ.get("NEOX_SSH_PASSWORD")
    if not ssh_username or not ssh_password:
        pytest.skip("Set NEOX_SSH_USERNAME and NEOX_SSH_PASSWORD to run GE CLI discovery.")

    config = json.loads(COMMANDS_FILE.read_text(encoding="utf-8"))
    target = neox_config_service.target()
    commands = [
        {
            "feature": item["feature"],
            "command": f"show interface ge {target.ge_slot_id}-{target.ge_port_id} {item['command_suffix']}",
        }
        for item in config["commands"]
    ]
    cli = SshCliClient(env_config.dut.device_ip, ssh_username, ssh_password)
    outputs = cli.run_commands([item["command"] for item in commands])
    results = []
    for item, output in zip(commands, outputs):
        results.append(
            {
                "feature": item["feature"],
                "command": item["command"],
                "usable": is_usable_output(output.output),
                "output": output.output,
            }
        )

    report_path = write_discovery_report(neox_config_service, results)
    assert any(result["usable"] for result in results), f"No usable GE show command discovered. Report: {report_path}"


def is_usable_output(output: str) -> bool:
    lowered = output.lower()
    return "% invalid" not in lowered and "% incomplete" not in lowered and "% unknown" not in lowered


def write_discovery_report(neox_config_service, results: list[dict[str, Any]]) -> Path:
    root = Path(__file__).resolve().parents[1]
    reports_dir = root / "reports" / "cli-discovery"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"ge_show_feature_{timestamp}.json"
    target = neox_config_service.target()
    data = {
        "target": {
            "node": neox_config_service.env_config.dut.node_key,
            "device_ip": neox_config_service.env_config.dut.device_ip,
            "device_name": target.device_name,
            "ge_slot_id": target.ge_slot_id,
            "ge_port_id": target.ge_port_id,
        },
        "usable_features": [result["feature"] for result in results if result["usable"]],
        "unusable_features": [result["feature"] for result in results if not result["usable"]],
        "results": results,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
