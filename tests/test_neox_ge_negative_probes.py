from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from services.neox_config.service import ge_port_payload
from utils.redaction import redact


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.destructive,
    pytest.mark.mutating,
    pytest.mark.readwrite,
]


GE_NEGATIVE_PROBES = [
    # Fallback only; primary cases come from configs/neox_ge_negative_cases.json.
]


def test_ge_negative_payload_probe_set_readwrite(
    api_client,
    neox_config_service,
    readwrite_session,
    cleanup_registry,
):
    neox_config_service.verify_required_target_data()
    cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session))

    results = []
    unexpected_successes = []
    for case in load_negative_cases():
        case_name = case["name"]
        field = case["field"]
        value = case["value"]
        api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)
        payload = invalid_ge_payload(field, value)
        response = api_client.request("POST", neox_config_service.ge_path(), session=readwrite_session, json=payload)
        result = response_record(case_name, field, value, payload, response)
        results.append(result)
        if not is_expected_negative_response(response, case):
            unexpected_successes.append(result)
        api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)

    report_path = write_probe_report(neox_config_service, results)
    assert not unexpected_successes, f"Unexpected GE negative probe success. Report: {report_path}"


def invalid_ge_payload(field: str, value: Any) -> dict[str, Any]:
    payload = deepcopy(ge_port_payload())
    payload["Content"][field] = value
    return payload


def load_negative_cases() -> list[dict[str, Any]]:
    root = Path(__file__).resolve().parents[1]
    path = root / "configs" / "neox_ge_negative_cases.json"
    if not path.exists():
        return [{"name": name, "field": field, "value": value} for name, field, value in GE_NEGATIVE_PROBES]
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["cases"]


def is_expected_negative_response(response, case: dict[str, Any]) -> bool:
    if response.status_code != case.get("expected_status_code"):
        return False
    if isinstance(response.json, dict):
        if response.json.get("retstatus") != case.get("expected_retstatus"):
            return False
        message = str(response.json.get("retresult") or response.json.get("retval") or response.json)
    else:
        message = response.text
    expected_message = case.get("expected_message_contains")
    return not expected_message or expected_message in message


def response_record(case_name: str, field: str, value: Any, payload: dict[str, Any], response) -> dict[str, Any]:
    body = response.json if isinstance(response.json, dict) else {"raw": response.text}
    return {
        "case": case_name,
        "field": field,
        "value": value,
        "request_content": redact(payload["Content"]),
        "response": {
            "status_code": response.status_code,
            "retstatus": body.get("retstatus") if isinstance(body, dict) else None,
            "retresult": body.get("retresult") if isinstance(body, dict) else response.text,
            "retval": redact(body.get("retval")) if isinstance(body, dict) else None,
            "body": redact(body),
        },
    }


def write_probe_report(neox_config_service, results: list[dict[str, Any]]) -> Path:
    root = Path(__file__).resolve().parents[1]
    reports_dir = root / "reports" / "negative-probes"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"neox_ge_negative_probe_{timestamp}.json"
    target = neox_config_service.target()
    data = {
        "target": {
            "node": neox_config_service.env_config.dut.node_key,
            "device_name": target.device_name,
            "ge_slot_id": target.ge_slot_id,
            "ge_port_id": target.ge_port_id,
        },
        "results": results,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
