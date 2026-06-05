from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from tests.support.neox_cli_verification import neox_cli_credentials, run_neox_cli_commands
from utils.allure_helpers import attach_json


CUSTOMTYPE_PAYLOAD = {
    "Content": {
        "packfiltertype": "custom",
        "customtype": "ip",
    }
}


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.neox_probe,
    pytest.mark.destructive,
    pytest.mark.mutating,
    pytest.mark.readwrite,
]


def test_neox_ge_customtype_custom_ip_rest_cli_probe(
    api_client,
    env_config,
    neox_config_service,
    readwrite_session,
    cleanup_registry,
):
    neox_config_service.verify_required_target_data()
    target = neox_config_service.target()
    path = neox_config_service.ge_path()
    credentials = neox_cli_credentials(env_config, "GE customtype")
    cli_commands = [
        f"show interface ge {target.ge_slot_id}-{target.ge_port_id} acl packet-filter",
        f"show running-config interface ge {target.ge_slot_id}-{target.ge_port_id}",
    ]

    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))
    api_client.request("DELETE", path, session=readwrite_session)
    response = post_ge_payload(api_client, path, readwrite_session, CUSTOMTYPE_PAYLOAD, read_timeout=180)
    output_by_command = run_neox_cli_commands(env_config, credentials, cli_commands)

    report = {
        "target": {
            "device_name": target.device_name,
            "ge_slot_id": target.ge_slot_id,
            "ge_port_id": target.ge_port_id,
        },
        "rest_api": {
            "path": path,
            "request": CUSTOMTYPE_PAYLOAD,
            "response": response_summary(response),
        },
        "cli": output_by_command,
        "summary": {
            "rest_returned_success": response.retstatus == "Success",
            "packet_filter_show_contains_custom": "custom" in "\n".join(output_by_command.values()).casefold(),
            "packet_filter_show_contains_ip": "ip" in "\n".join(output_by_command.values()).casefold(),
        },
    }
    report_path = write_report(report)
    attach_json("NeoX GE customtype custom/ip probe", report)
    print(f"NeoX GE customtype probe report: {report_path}")

    assert response.retstatus == "Success", report
    combined_output = "\n".join(output_by_command.values()).casefold()
    assert "custom" in combined_output and "ip" in combined_output, report


def post_ge_payload(api_client, path: str, session_id: str, payload: dict, read_timeout: float):
    original_timeout = api_client.timeout
    if isinstance(original_timeout, tuple):
        api_client.timeout = (original_timeout[0], max(float(original_timeout[1]), read_timeout))
    else:
        api_client.timeout = (float(original_timeout), read_timeout)
    try:
        return api_client.request("POST", path, session=session_id, json=payload)
    finally:
        api_client.timeout = original_timeout


def response_summary(response) -> dict:
    return {
        "status_code": response.status_code,
        "retstatus": response.retstatus,
        "retresult": response.retresult,
        "elapsed": response.elapsed,
    }


def write_report(report: dict) -> Path:
    reports_dir = Path("reports/device-verification")
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"neox_ge_customtype_probe_{timestamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
