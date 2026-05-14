from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from clients.ssh_cli import SshCliClient
from utils.assertions import assert_api_success
from utils.redaction import redact


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.destructive,
    pytest.mark.mutating,
    pytest.mark.readwrite,
]


ENABLE_PROBE_FILE = Path(__file__).resolve().parents[1] / "configs" / "neox_ge_enable_probe.json"
FULL_ACCEPTED_PAYLOAD_FILE = Path(__file__).resolve().parents[1] / "configs" / "neox_ge_full_accepted_payload.json"
SHOW_COMMANDS_FILE = Path(__file__).resolve().parents[1] / "configs" / "neox_ge_show_commands.json"


def test_ge_enable_oriented_probe_collects_feature_show_outputs(
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
        pytest.skip("Set NEOX_SSH_USERNAME and NEOX_SSH_PASSWORD to run GE enable probe.")

    target = neox_config_service.target()
    running_command = f"show running-config interface ge {target.ge_slot_id}-{target.ge_port_id}"
    cli = SshCliClient(env_config.dut.device_ip, ssh_username, ssh_password)
    show_config = json.loads(SHOW_COMMANDS_FILE.read_text(encoding="utf-8"))
    field_to_features = show_config["field_to_features"]
    suffix_by_feature = {item["feature"]: item["command_suffix"] for item in show_config["commands"]}

    cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session))
    api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)
    accepted_content = load_full_accepted_content()
    base_response = api_client.request(
        "POST",
        neox_config_service.ge_path(),
        session=readwrite_session,
        json={"Content": accepted_content},
    )
    assert_api_success(base_response)

    results = []
    for candidate in json.loads(ENABLE_PROBE_FILE.read_text(encoding="utf-8"))["candidates"]:
        field = candidate["field"]
        value = candidate["value"]
        probe_content = dict(accepted_content)
        probe_content[field] = value
        response = api_client.request(
            "POST",
            neox_config_service.ge_path(),
            session=readwrite_session,
            json={"Content": probe_content},
        )
        kept = is_success(response)
        cli_outputs = {}
        if kept:
            accepted_content[field] = value
            cli_outputs["running-config"] = run_cli(cli, running_command)
            for feature in field_to_features.get(field, []):
                suffix = suffix_by_feature.get(feature)
                if suffix:
                    command = f"show interface ge {target.ge_slot_id}-{target.ge_port_id} {suffix}"
                    cli_outputs[feature] = run_cli(cli, command)
        results.append(record_result(field, value, probe_content, response, kept=kept, cli_outputs=cli_outputs))

    api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)
    write_enable_probe_report(neox_config_service, accepted_content, results)


def load_full_accepted_content() -> dict[str, Any]:
    data = json.loads(FULL_ACCEPTED_PAYLOAD_FILE.read_text(encoding="utf-8"))
    return materialize_unique_values(dict(data["payload"]["Content"]))


def materialize_unique_values(content: dict[str, Any]) -> dict[str, Any]:
    mac = unique_mac()
    if "acl_maclist" in content:
        content["acl_maclist"] = [{"aclmac": mac}]
    if "fdb_list" in content:
        content["fdb_list"] = [{"mac": mac, "vid": 1314}]
    return content


def unique_mac() -> str:
    value = int(time.time()) & 0xFFFFFF
    return f"02:13:{(value >> 16) & 0xFF:02x}:{(value >> 8) & 0xFF:02x}:{value & 0xFF:02x}:39"


def is_success(response) -> bool:
    return response.status_code < 500 and isinstance(response.json, dict) and response.json.get("retstatus") == "Success"


def run_cli(cli: SshCliClient, command: str) -> str:
    [result] = cli.run_commands([command])
    return result.output


def record_result(
    field: str,
    value: Any,
    content: dict[str, Any],
    response,
    *,
    kept: bool,
    cli_outputs: dict[str, str],
) -> dict[str, Any]:
    body = response.json if isinstance(response.json, dict) else {"raw": response.text}
    return {
        "field": field,
        "value": value,
        "kept_for_next_request": kept,
        "request_field_count": len(content),
        "response": {
            "status_code": response.status_code,
            "retstatus": body.get("retstatus") if isinstance(body, dict) else None,
            "retresult": body.get("retresult") if isinstance(body, dict) else response.text,
            "retval": redact(body.get("retval")) if isinstance(body, dict) else None,
            "body": redact(body),
        },
        "cli_outputs": cli_outputs,
    }


def write_enable_probe_report(neox_config_service, accepted_content: dict[str, Any], results: list[dict[str, Any]]) -> Path:
    root = Path(__file__).resolve().parents[1]
    reports_dir = root / "reports" / "enable-probes"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"neox_ge_enable_probe_{timestamp}.json"
    target = neox_config_service.target()
    data = {
        "target": {
            "node": neox_config_service.env_config.dut.node_key,
            "device_ip": neox_config_service.env_config.dut.device_ip,
            "device_name": target.device_name,
            "ge_slot_id": target.ge_slot_id,
            "ge_port_id": target.ge_port_id,
        },
        "accepted_content": redact(accepted_content),
        "accepted_fields": list(accepted_content),
        "enabled_or_changed_fields": [
            {"field": result["field"], "value": result["value"]}
            for result in results
            if result["kept_for_next_request"]
        ],
        "failed_fields": [result["field"] for result in results if not result["kept_for_next_request"]],
        "results": results,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
