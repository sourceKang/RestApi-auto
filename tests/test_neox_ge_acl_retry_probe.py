from __future__ import annotations

import copy
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from clients.ssh_cli import SshCliClient
from services.neox_config.service import vlan_payload
from utils.assertions import assert_api_success
from utils.redaction import redact


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.destructive,
    pytest.mark.mutating,
    pytest.mark.readwrite,
]


ACL_RETRY_CONFIG_FILE = Path(__file__).resolve().parents[1] / "configs" / "neox_ge_acl_retry_probe.json"
ENABLE_ACCEPTED_PAYLOAD_FILE = Path(__file__).resolve().parents[1] / "configs" / "neox_ge_enable_accepted_payload.json"


def test_ge_acl_retry_probe_set_readwrite(
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
        pytest.skip("Set NEOX_SSH_USERNAME and NEOX_SSH_PASSWORD to run GE ACL retry probe.")

    retry_config = json.loads(ACL_RETRY_CONFIG_FILE.read_text(encoding="utf-8"))
    target = neox_config_service.target()
    cli = SshCliClient(env_config.dut.device_ip, ssh_username, ssh_password)
    commands = [
        f"show running-config interface ge {target.ge_slot_id}-{target.ge_port_id}",
        f"show interface ge {target.ge_slot_id}-{target.ge_port_id} acl",
    ]

    cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session))
    cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.vlan_path(), session=readwrite_session))
    api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)
    api_client.request("DELETE", neox_config_service.vlan_path(), session=readwrite_session)
    vlan_response = api_client.request("POST", neox_config_service.vlan_path(), session=readwrite_session, json=vlan_payload())
    assert_api_success(vlan_response)

    base_content = load_enable_accepted_content()
    base_response = api_client.request(
        "POST",
        neox_config_service.ge_path(),
        session=readwrite_session,
        json={"Content": base_content},
    )
    assert_api_success(base_response)

    results = []
    accepted_content = copy.deepcopy(base_content)
    for candidate in retry_config["candidates"]:
        probe_content = copy.deepcopy(accepted_content)
        probe_content.update(copy.deepcopy(candidate["fields"]))
        response = api_client.request(
            "POST",
            neox_config_service.ge_path(),
            session=readwrite_session,
            json={"Content": probe_content},
        )
        kept = is_success(response)
        cli_outputs = {}
        if kept:
            accepted_content.update(copy.deepcopy(candidate["fields"]))
            cli_outputs = run_cli_commands(cli, commands)
        results.append(record_result(candidate, probe_content, response, kept=kept, cli_outputs=cli_outputs))

    final_cli_outputs = run_cli_commands(cli, commands)
    api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)
    write_acl_retry_report(neox_config_service, accepted_content, results, final_cli_outputs)


def load_enable_accepted_content() -> dict[str, Any]:
    data = json.loads(ENABLE_ACCEPTED_PAYLOAD_FILE.read_text(encoding="utf-8"))
    content = copy.deepcopy(data["payload"]["Content"])
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


def run_cli_commands(cli: SshCliClient, commands: list[str]) -> dict[str, str]:
    return {result.command: result.output for result in cli.run_commands(commands)}


def record_result(
    candidate: dict[str, Any],
    content: dict[str, Any],
    response,
    *,
    kept: bool,
    cli_outputs: dict[str, str],
) -> dict[str, Any]:
    body = response.json if isinstance(response.json, dict) else {"raw": response.text}
    return {
        "name": candidate["name"],
        "fields": redact(candidate["fields"]),
        "kept_for_next_request": kept,
        "request_field_count": len(content),
        "response": {
            "status_code": response.status_code,
            "retstatus": body.get("retstatus"),
            "retresult": body.get("retresult", response.text),
            "retval": redact(body.get("retval")),
            "body": redact(body),
        },
        "cli_outputs": cli_outputs,
    }


def write_acl_retry_report(
    neox_config_service,
    accepted_content: dict[str, Any],
    results: list[dict[str, Any]],
    final_cli_outputs: dict[str, str],
) -> Path:
    root = Path(__file__).resolve().parents[1]
    reports_dir = root / "reports" / "acl-retry-probes"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"neox_ge_acl_retry_probe_{timestamp}.json"
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
        "successful_candidates": [result["name"] for result in results if result["kept_for_next_request"]],
        "failed_candidates": [result["name"] for result in results if not result["kept_for_next_request"]],
        "results": results,
        "final_cli_outputs": final_cli_outputs,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
