from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from services.neox_config.service import ont_config_payload, ont_negative_cases, ont_negative_payload
from models.api import SessionRole
from utils.redaction import redact


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.neox_probe,
    pytest.mark.destructive,
    pytest.mark.mutating,
    pytest.mark.readwrite,
]


def test_neox_ont_config_error_response_probe(
    api_client,
    neox_config_service,
    session_manager,
    readwrite_session,
    cleanup_registry,
):
    neox_config_service.verify_required_target_data()
    target = neox_config_service.target()
    path = neox_config_service.ont_path()
    restore_payload = ont_config_payload(target)
    cleanup_registry.add(lambda: api_client.request("POST", path, session=readwrite_session, json=restore_payload))
    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))

    observations = []
    for negative_case in selected_negative_cases():
        payload = ont_negative_payload(negative_case, target)
        with session_manager.role_session(SessionRole.READWRITE) as case_session:
            api_client.request("DELETE", path, session=case_session)
            response = api_client.request("POST", path, session=case_session, json=payload)
            api_client.request("DELETE", path, session=case_session)
        observations.append(
            {
                "name": negative_case["name"],
                "field": negative_case.get("field"),
                "expected_retstatus": negative_case.get("expected_retstatus"),
                "status_code": response.status_code,
                "retstatus": response.retstatus,
                "retresult": response.retresult,
                "failed_as_expected": response.retstatus == "Fail" or response.status_code >= 400,
                "response": redact(response.json),
            }
        )

    report_path = write_negative_probe_report(neox_config_service, observations)
    unexpected_success = [item for item in observations if not item["failed_as_expected"]]
    assert not unexpected_success, f"ONT negative probe accepted invalid cases. Report: {report_path}"


def write_negative_probe_report(neox_config_service, observations: list[dict]) -> Path:
    reports_dir = Path(__file__).resolve().parents[1] / "reports" / "negative-probes"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"neox_ont_negative_probe_{timestamp}.json"
    target = neox_config_service.target()
    data = {
        "target": {
            "node": neox_config_service.env_config.dut.node_key,
            "device_ip": neox_config_service.env_config.dut.device_ip,
            "device_name": target.device_name,
            "ont_slot_id": target.ont_slot_id,
            "ont_port_id": target.ont_port_id,
            "ont_id": target.ont_id,
        },
        "observations": observations,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def selected_negative_cases() -> list[dict]:
    requested = {
        value.strip()
        for value in os.environ.get("NEOX_ONT_NEGATIVE_CASES", "").split(",")
        if value.strip()
    }
    cases = ont_negative_cases()
    if not requested:
        return cases
    return [
        negative_case
        for negative_case in cases
        if negative_case["name"] in requested or str(negative_case.get("field", "")) in requested
    ]
