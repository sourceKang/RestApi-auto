from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from services.neox_config.service import GE_FULL_ACCEPTED_PAYLOAD_FILE
from tests.support.neox_cli_verification import neox_cli_credentials, run_neox_cli_commands
from utils.allure_helpers import attach_json
from utils.assertions import assert_api_success


INVALID_UNICAST_MAC = "00:11:22:33:44:66"
MULTICAST_MAC = "33:33:00:00:00:01"
NNI_VID = 1314


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.neox_probe,
    pytest.mark.destructive,
    pytest.mark.mutating,
    pytest.mark.readwrite,
]


def test_neox_ge_smcastmac_multicast_mac_rest_probe(
    api_client,
    env_config,
    neox_config_service,
    readwrite_session,
    cleanup_registry,
):
    neox_config_service.verify_required_target_data()
    target = neox_config_service.target()
    path = neox_config_service.ge_path()
    credentials = neox_cli_credentials(env_config, "GE smcast MAC")
    show_command = f"show running-config interface ge {target.ge_slot_id}-{target.ge_port_id}"
    cleanup_command = f"no smcast mac {MULTICAST_MAC} nni-vlan {NNI_VID}"

    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))
    cleanup_registry.add(
        lambda: run_ge_commands(env_config, target, credentials, [cleanup_command])
    )

    help_outputs = collect_smcast_help(env_config, target, credentials)
    invalid_cli_output = run_ge_commands(
        env_config,
        target,
        credentials,
        [f"smcast mac {INVALID_UNICAST_MAC} nni-vlan {NNI_VID}"],
    )
    run_ge_commands(env_config, target, credentials, [cleanup_command])
    valid_cli_output = run_ge_commands(
        env_config,
        target,
        credentials,
        [f"smcast mac {MULTICAST_MAC} nni-vlan {NNI_VID}"],
    )
    valid_cli_show = run_neox_cli_commands(env_config, credentials, [show_command])

    run_ge_commands(env_config, target, credentials, [cleanup_command])
    api_client.request("DELETE", path, session=readwrite_session)
    payload = smcastmac_payload(MULTICAST_MAC)
    response = post_ge_payload(api_client, path, readwrite_session, payload, read_timeout=180)
    rest_show = run_neox_cli_commands(env_config, credentials, [show_command])

    report = {
        "target": {
            "device_name": target.device_name,
            "ge_slot_id": target.ge_slot_id,
            "ge_port_id": target.ge_port_id,
        },
        "candidate_values": {
            "invalid_unicast_mac": INVALID_UNICAST_MAC,
            "multicast_mac": MULTICAST_MAC,
            "nni_vid": NNI_VID,
        },
        "cli_help": help_outputs,
        "cli_first": {
            "invalid_unicast_output": invalid_cli_output,
            "multicast_output": valid_cli_output,
            "show_after_multicast": valid_cli_show,
        },
        "rest_api": {
            "path": path,
            "request": payload,
            "response": response_summary(response),
            "show_after_rest": rest_show,
        },
        "summary": {
            "invalid_unicast_accepted_by_cli": command_accepted(invalid_cli_output),
            "multicast_accepted_by_cli": command_accepted(valid_cli_output),
            "rest_returned_success": response.retstatus == "Success",
            "rest_cli_token_visible": f"smcast mac {MULTICAST_MAC} nni-vlan {NNI_VID}" in "\n".join(rest_show.values()),
        },
    }
    report_path = write_report(report)
    attach_json("NeoX GE smcast MAC multicast probe", report)
    print(f"NeoX GE smcast MAC probe report: {report_path}")

    assert not command_accepted(invalid_cli_output)
    assert command_accepted(valid_cli_output)
    assert f"smcast mac {MULTICAST_MAC} nni-vlan {NNI_VID}" in "\n".join(valid_cli_show.values())
    assert_api_success(response)
    assert f"smcast mac {MULTICAST_MAC} nni-vlan {NNI_VID}" in "\n".join(rest_show.values())


def collect_smcast_help(env_config, target, credentials: tuple[str, str]) -> dict[str, str]:
    commands = [
        "configure",
        f"interface ge {target.ge_slot_id}-{target.ge_port_id}",
        "smcast ?",
        "smcast mac ?",
        f"smcast mac {MULTICAST_MAC} ?",
        f"smcast mac {MULTICAST_MAC} nni-vlan ?",
        "exit",
        "exit",
    ]
    return run_neox_cli_commands(env_config, credentials, commands)


def run_ge_commands(env_config, target, credentials: tuple[str, str], commands: list[str]) -> dict[str, str]:
    sequence = ["configure", f"interface ge {target.ge_slot_id}-{target.ge_port_id}", *commands, "exit", "exit"]
    return run_neox_cli_commands(env_config, credentials, sequence)


def command_accepted(output_by_command: dict[str, str]) -> bool:
    output = "\n".join(output_by_command.values()).casefold()
    failure_fragments = (
        "invalid input",
        "incomplete command",
        "ambiguous command",
        "does not exist",
        "not found",
        "fail",
        "error",
    )
    return not any(fragment in output for fragment in failure_fragments)


def smcastmac_payload(mac: str) -> dict[str, Any]:
    base_payload = json.loads(GE_FULL_ACCEPTED_PAYLOAD_FILE.read_text(encoding="utf-8"))["payload"]
    payload = copy.deepcopy(base_payload)
    payload.setdefault("Content", {})["smcastmac_list"] = [{"mac": mac, "nnivid": NNI_VID}]
    return payload


def post_ge_payload(api_client, path: str, session_id: str, payload: dict[str, Any], read_timeout: float):
    original_timeout = api_client.timeout
    if isinstance(original_timeout, tuple):
        api_client.timeout = (original_timeout[0], max(float(original_timeout[1]), read_timeout))
    else:
        api_client.timeout = (float(original_timeout), read_timeout)
    try:
        return api_client.request("POST", path, session=session_id, json=payload)
    finally:
        api_client.timeout = original_timeout


def response_summary(response) -> dict[str, Any]:
    return {
        "status_code": response.status_code,
        "retstatus": response.retstatus,
        "retresult": response.retresult,
        "elapsed": response.elapsed,
    }


def write_report(report: dict[str, Any]) -> Path:
    reports_dir = Path("reports/device-verification")
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"neox_ge_smcastmac_probe_{timestamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
