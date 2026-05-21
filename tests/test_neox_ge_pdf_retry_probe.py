from __future__ import annotations

import copy
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from clients.ssh_cli import SshCliClient
from services.neox_config.service import (
    GE_ENABLE_ACCEPTED_PAYLOAD_FILE,
    GE_PDF_RETRY_CONFIG_FILE,
    NEOX_PROFILE_NAMES,
    vlan_payload,
)
from tests.support.neox_cli_verification import neox_cli_credentials
from utils.assertions import assert_api_success
from utils.redaction import redact


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.neox_probe,
    pytest.mark.destructive,
    pytest.mark.mutating,
    pytest.mark.readwrite,
]


RETRY_CONFIG_FILE = GE_PDF_RETRY_CONFIG_FILE
ENABLE_ACCEPTED_PAYLOAD_FILE = GE_ENABLE_ACCEPTED_PAYLOAD_FILE


def test_ge_pdf_derived_probe_set_readwrite(
    api_client,
    env_config,
    neox_config_service,
    readwrite_session,
    cleanup_registry,
):
    neox_config_service.verify_required_target_data()
    ssh_username, ssh_password = neox_cli_credentials(env_config, "GE PDF-derived retry probe")

    retry_config = json.loads(RETRY_CONFIG_FILE.read_text(encoding="utf-8"))
    target = neox_config_service.target()
    cli = SshCliClient(env_config.dut.device_ip, ssh_username, ssh_password)
    running_command = f"show running-config interface ge {target.ge_slot_id}-{target.ge_port_id}"
    show_commands = [
        running_command,
        f"show interface ge {target.ge_slot_id}-{target.ge_port_id} config",
        f"show interface ge {target.ge_slot_id}-{target.ge_port_id} acl",
        f"show interface ge {target.ge_slot_id}-{target.ge_port_id} dot1x",
        f"show interface ge {target.ge_slot_id}-{target.ge_port_id} dscp",
        f"show interface ge {target.ge_slot_id}-{target.ge_port_id} pvid",
        f"show interface ge {target.ge_slot_id}-{target.ge_port_id} vlan",
        f"show interface ge {target.ge_slot_id}-{target.ge_port_id} qos",
        f"show interface ge {target.ge_slot_id}-{target.ge_port_id} mtu",
    ]

    cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session))
    cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.vlan_path(), session=readwrite_session))
    for profile_type in ("RateLimitProfile", "ShapingProfile", "WeightProfile"):
        cleanup_registry.add(
            lambda profile_type=profile_type: api_client.request(
                "DELETE",
                neox_config_service.neox_profile_path(profile_type),
                session=readwrite_session,
            )
        )

    setup_results = setup_pdf_retry_preconditions(
        api_client,
        neox_config_service,
        readwrite_session,
        retry_config.get("preconditions", {}),
    )

    api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)
    accepted_content = load_enable_accepted_content()
    base_response = api_client.request(
        "POST",
        neox_config_service.ge_path(),
        session=readwrite_session,
        json={"Content": accepted_content},
    )
    assert_api_success(base_response)

    results = []
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
            cli_outputs = run_cli_commands(cli, show_commands)
        results.append(record_candidate_result(candidate, probe_content, response, kept=kept, cli_outputs=cli_outputs))

    final_cli_outputs = run_cli_commands(cli, show_commands)
    api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)
    write_pdf_retry_report(neox_config_service, setup_results, accepted_content, results, final_cli_outputs)


def setup_pdf_retry_preconditions(api_client, neox_config_service, session_id: str, preconditions: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    if preconditions.get("create_vlan"):
        api_client.request("DELETE", neox_config_service.vlan_path(), session=session_id)
        response = api_client.request("POST", neox_config_service.vlan_path(), session=session_id, json=vlan_payload())
        results.append(record_setup_result("create_vlan", response))

    if preconditions.get("create_qos_profiles"):
        for profile_type in ("RateLimitProfile", "ShapingProfile", "WeightProfile"):
            path = neox_config_service.neox_profile_path(profile_type)
            api_client.request("DELETE", path, session=session_id)
            response = api_client.request("POST", path, session=session_id, json=neox_config_service.neox_profile_payload(profile_type))
            results.append(record_setup_result(f"create_{profile_type}", response, expected_name=NEOX_PROFILE_NAMES[profile_type]))
    return results


def load_enable_accepted_content() -> dict[str, Any]:
    data = json.loads(ENABLE_ACCEPTED_PAYLOAD_FILE.read_text(encoding="utf-8"))
    return materialize_unique_values(copy.deepcopy(data["payload"]["Content"]))


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


def run_cli_commands(cli: SshCliClient, commands: list[str]) -> dict[str, str]:
    outputs = {}
    for result in cli.run_commands(commands):
        outputs[result.command] = result.output
    return outputs


def record_setup_result(name: str, response, *, expected_name: str | None = None) -> dict[str, Any]:
    body = response.json if isinstance(response.json, dict) else {"raw": response.text}
    return {
        "name": name,
        "expected_name": expected_name,
        "response": response_summary(response, body),
    }


def record_candidate_result(
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
        "pdf_basis": candidate.get("pdf_basis"),
        "kept_for_next_request": kept,
        "request_field_count": len(content),
        "response": response_summary(response, body),
        "cli_outputs": cli_outputs,
    }


def response_summary(response, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "status_code": response.status_code,
        "retstatus": body.get("retstatus"),
        "retresult": body.get("retresult", response.text),
        "retval": redact(body.get("retval")),
        "body": redact(body),
    }


def write_pdf_retry_report(
    neox_config_service,
    setup_results: list[dict[str, Any]],
    accepted_content: dict[str, Any],
    results: list[dict[str, Any]],
    final_cli_outputs: dict[str, str],
) -> Path:
    root = Path(__file__).resolve().parents[1]
    reports_dir = root / "reports" / "pdf-retry-probes"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"neox_ge_pdf_retry_probe_{timestamp}.json"
    target = neox_config_service.target()
    data = {
        "target": {
            "node": neox_config_service.env_config.dut.node_key,
            "device_ip": neox_config_service.env_config.dut.device_ip,
            "device_name": target.device_name,
            "ge_slot_id": target.ge_slot_id,
            "ge_port_id": target.ge_port_id,
            "vlan_id": target.vlan_id,
        },
        "setup_results": setup_results,
        "accepted_content": redact(accepted_content),
        "accepted_fields": list(accepted_content),
        "successful_candidates": [result["name"] for result in results if result["kept_for_next_request"]],
        "failed_candidates": [result["name"] for result in results if not result["kept_for_next_request"]],
        "results": results,
        "final_cli_outputs": final_cli_outputs,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
