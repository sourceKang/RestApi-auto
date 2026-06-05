from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path

import pytest
import requests

from services.neox_config.service import GE_FULL_ACCEPTED_PAYLOAD_FILE
from tests.support.neox_cli_verification import neox_cli_credentials, run_neox_cli_commands
from utils.allure_helpers import attach_json
from utils.assertions import assert_api_success


DDMI_REQUEST = {
    "bias_alarm_high": "90",
    "bias_alarm_low": "5",
    "bias_warn_high": "88",
    "bias_warn_low": "6",
    "temperature_alarm_high": "100",
    "temperature_alarm_low": "-40",
    "temperature_warn_high": "95",
    "temperature_warn_low": "-35",
    "voltage_alarm_high": "3.59",
    "voltage_alarm_low": "2.8",
    "voltage_warn_high": "3.5",
    "voltage_warn_low": "2.9",
    "txpower_alarm_high": "6.5",
    "txpower_alarm_low": "-15.3",
    "txpower_warn_high": "5.5",
    "txpower_warn_low": "-14.3",
    "rxpower_alarm_high": "0",
    "rxpower_alarm_low": "-127",
    "rxpower_warn_high": "-1",
    "rxpower_warn_low": "-126",
}

DDMI_VISIBLE_EXPECTATIONS = {
    "bias_alarm_high": ("TX Bias(mA)", "high", "90.00"),
    "bias_alarm_low": ("TX Bias(mA)", "low", "5.00"),
    "temperature_alarm_high": ("Temperature(C)", "high", "100.00"),
    "temperature_alarm_low": ("Temperature(C)", "low", "-40.00"),
    "voltage_alarm_high": ("Voltage(V)", "high", "3.59"),
    "voltage_alarm_low": ("Voltage(V)", "low", "2.80"),
    "txpower_alarm_high": ("TX Power(dBm)", "high", "6.50"),
    "txpower_alarm_low": ("TX Power(dBm)", "low", "-15.30"),
    "rxpower_alarm_high": ("RX Power(dBm)", "high", "0.00"),
    "rxpower_alarm_low": ("RX Power(dBm)", "low", "-127.00"),
}


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.neox_probe,
    pytest.mark.destructive,
    pytest.mark.mutating,
    pytest.mark.readwrite,
]


def test_neox_ge_ddmi_all_fields_rest_probe(
    api_client,
    env_config,
    neox_config_service,
    readwrite_session,
    cleanup_registry,
):
    neox_config_service.verify_required_target_data()
    target = neox_config_service.target()
    path = neox_config_service.ge_path()
    credentials = neox_cli_credentials(env_config, "GE DDMI")
    show_command = f"show interface ge {target.ge_slot_id}-{target.ge_port_id} ddmi config"

    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))
    api_client.request("DELETE", path, session=readwrite_session)
    baseline_output = run_neox_cli_commands(env_config, credentials, [show_command])[show_command]

    payload = ddmi_payload()
    response = None
    rest_error = None
    try:
        response = post_ddmi_payload(api_client, path, readwrite_session, payload, read_timeout=180)
    except requests.exceptions.RequestException as exc:
        rest_error = {
            "type": type(exc).__name__,
            "message": str(exc),
        }

    after_output = run_neox_cli_commands(env_config, credentials, [show_command])[show_command]
    report = build_ddmi_report(target, payload, response, rest_error, baseline_output, after_output)
    report_path = write_ddmi_report(report)
    attach_json("NeoX GE DDMI all-field probe", report)

    print(f"NeoX GE DDMI all-field probe report: {report_path}")
    if response is None:
        pytest.fail(f"DDMI REST POST failed before Success response; report: {report_path}")
    assert_api_success(response)


def ddmi_payload() -> dict:
    base_payload = json.loads(GE_FULL_ACCEPTED_PAYLOAD_FILE.read_text(encoding="utf-8"))["payload"]
    payload = copy.deepcopy(base_payload)
    payload.setdefault("Content", {}).update(DDMI_REQUEST)
    return payload


def post_ddmi_payload(api_client, path: str, session_id: str, payload: dict, read_timeout: float):
    original_timeout = api_client.timeout
    if isinstance(original_timeout, tuple):
        api_client.timeout = (original_timeout[0], max(float(original_timeout[1]), read_timeout))
    else:
        api_client.timeout = (float(original_timeout), read_timeout)
    try:
        return api_client.request("POST", path, session=session_id, json=payload)
    finally:
        api_client.timeout = original_timeout


def build_ddmi_report(target, payload, response, rest_error, baseline_output: str, after_output: str) -> dict:
    baseline = parse_ddmi_config(baseline_output)
    after = parse_ddmi_config(after_output)
    visible_results = {}
    for field, (row_name, side, expected) in DDMI_VISIBLE_EXPECTATIONS.items():
        baseline_actual = baseline.get(row_name, {}).get(side)
        actual = after.get(row_name, {}).get(side)
        visible_results[field] = {
            "requested": DDMI_REQUEST[field],
            "expected_cli": expected,
            "baseline_cli": baseline_actual,
            "actual_cli": actual,
            "changed_from_baseline": actual != baseline_actual,
            "changed_to_requested": actual == expected,
        }
    warning_results = {
        field: {
            "requested": DDMI_REQUEST[field],
            "status": "not_visible_in_show_interface_ge_ddmi_config",
        }
        for field in DDMI_REQUEST
        if field not in DDMI_VISIBLE_EXPECTATIONS
    }
    return {
        "target": {
            "device_name": target.device_name,
            "ge_slot_id": target.ge_slot_id,
            "ge_port_id": target.ge_port_id,
        },
        "rest_api": {
            "request": payload,
            "response": response_summary(response),
            "error": rest_error,
        },
        "cli": {
            "show_command": f"show interface ge {target.ge_slot_id}-{target.ge_port_id} ddmi config",
            "baseline_output": baseline_output,
            "after_rest_output": after_output,
            "baseline_parsed": baseline,
            "after_rest_parsed": after,
        },
        "visible_alarm_results": visible_results,
        "warning_field_results": warning_results,
        "summary": {
            "requested_fields": len(DDMI_REQUEST),
            "visible_alarm_fields": len(visible_results),
            "visible_alarm_fields_changed_from_baseline": sum(
                1 for result in visible_results.values() if result["changed_from_baseline"]
            ),
            "visible_alarm_fields_changed_to_requested": sum(
                1 for result in visible_results.values() if result["changed_to_requested"]
            ),
            "warning_fields_not_visible": len(warning_results),
        },
    }


def response_summary(response) -> dict | None:
    if response is None:
        return None
    return {
        "status_code": response.status_code,
        "retstatus": response.retstatus,
        "retresult": response.retresult,
        "elapsed": response.elapsed,
    }


def parse_ddmi_config(output: str) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for line in output.splitlines():
        if "|" not in line:
            continue
        content = line.split("|", 1)[1].strip()
        parts = content.rsplit(None, 2)
        if len(parts) != 3:
            continue
        name, high, low = parts
        if name in {"Type", ""} or name.startswith("Type"):
            continue
        rows[name.strip()] = {"high": high, "low": low}
    return rows


def write_ddmi_report(report: dict) -> Path:
    reports_dir = Path("reports/device-verification")
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"neox_ge_ddmi_all_fields_probe_{timestamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
