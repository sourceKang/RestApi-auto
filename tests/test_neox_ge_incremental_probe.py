from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from utils.assertions import assert_api_success
from utils.redaction import redact


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.destructive,
    pytest.mark.mutating,
    pytest.mark.readwrite,
]


CONFIG_FILE = Path(__file__).resolve().parents[1] / "configs" / "neox_ge_incremental_probe.json"


def test_ge_incrementally_adds_parameters_and_collects_responses(
    api_client,
    neox_config_service,
    readwrite_session,
    cleanup_registry,
):
    neox_config_service.verify_required_target_data()
    config = load_probe_config()
    cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session))

    accepted_content = dict(config["base_content"])
    api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)
    base_response = api_client.request(
        "POST",
        neox_config_service.ge_path(),
        session=readwrite_session,
        json={"Content": accepted_content},
    )
    assert_api_success(base_response)

    results = [response_record("base_content", None, None, accepted_content, base_response, kept=True)]
    for candidate in config["candidates"]:
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
        if kept:
            accepted_content[field] = value
        results.append(response_record(candidate.get("name", field), field, value, probe_content, response, kept=kept))

    api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)
    write_probe_report(neox_config_service, config, accepted_content, results)


def load_probe_config() -> dict[str, Any]:
    path = Path(os.environ.get("NEOX_GE_INCREMENTAL_PROBE_FILE", CONFIG_FILE))
    return json.loads(path.read_text(encoding="utf-8"))


def is_success(response) -> bool:
    return response.status_code < 500 and isinstance(response.json, dict) and response.json.get("retstatus") == "Success"


def response_record(
    case_name: str,
    field: str | None,
    value: Any,
    content: dict[str, Any],
    response,
    *,
    kept: bool,
) -> dict[str, Any]:
    body = response.json if isinstance(response.json, dict) else {"raw": response.text}
    return {
        "case": case_name,
        "field": field,
        "value": value,
        "kept_for_next_request": kept,
        "request_content": redact(content),
        "response": {
            "status_code": response.status_code,
            "retstatus": body.get("retstatus") if isinstance(body, dict) else None,
            "retresult": body.get("retresult") if isinstance(body, dict) else response.text,
            "retval": redact(body.get("retval")) if isinstance(body, dict) else None,
            "body": redact(body),
        },
    }


def write_probe_report(
    neox_config_service,
    config: dict[str, Any],
    accepted_content: dict[str, Any],
    results: list[dict[str, Any]],
) -> Path:
    root = Path(__file__).resolve().parents[1]
    reports_dir = root / "reports" / "incremental-probes"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"neox_ge_incremental_probe_{timestamp}.json"
    target = neox_config_service.target()
    data = {
        "target": {
            "node": neox_config_service.env_config.dut.node_key,
            "device_name": target.device_name,
            "ge_slot_id": target.ge_slot_id,
            "ge_port_id": target.ge_port_id,
        },
        "accepted_content": redact(accepted_content),
        "accepted_fields": list(accepted_content),
        "failed_fields": [result["field"] for result in results if result["field"] and not result["kept_for_next_request"]],
        "deferred_fields": config.get("deferred_fields", []),
        "results": compact_duplicate_failure_messages(results),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def compact_duplicate_failure_messages(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_messages: dict[str, str] = {}
    compacted: list[dict[str, Any]] = []
    for result in results:
        item = json.loads(json.dumps(result, ensure_ascii=False))
        if item.get("kept_for_next_request"):
            compacted.append(item)
            continue
        response = item.get("response", {})
        message = response_message(response)
        if not message:
            compacted.append(item)
            continue
        first_case = seen_messages.get(message)
        if first_case is None:
            seen_messages[message] = str(item.get("case"))
            compacted.append(item)
            continue
        response["message_duplicate_of"] = first_case
        response.pop("retresult", None)
        response.pop("retval", None)
        response.pop("body", None)
        compacted.append(item)
    return compacted


def response_message(response: dict[str, Any]) -> str:
    for key in ("retresult", "retval"):
        value = response.get(key)
        if value:
            return str(value)
    body = response.get("body")
    if isinstance(body, dict):
        value = body.get("retresult") or body.get("retval")
        if value:
            return str(value)
    return ""
