from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from clients.ssh_cli import SshCliClient
from services.neox_config.service import ge_port_payload, vlan_payload
from utils.assertions import assert_api_success
from utils.redaction import redact


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.destructive,
    pytest.mark.mutating,
    pytest.mark.readwrite,
]


FULL_ACCEPTED_PAYLOAD_FILE = Path(__file__).resolve().parents[1] / "configs" / "neox_ge_full_accepted_payload.json"
ENABLE_ACCEPTED_PAYLOAD_FILE = Path(__file__).resolve().parents[1] / "configs" / "neox_ge_enable_accepted_payload.json"


def test_ge_config_min_create_readwrite(
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
        pytest.skip("Set NEOX_SSH_USERNAME and NEOX_SSH_PASSWORD to run GE CLI verification.")

    cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session))
    api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)
    payload = ge_port_payload()
    response = api_client.request("POST", neox_config_service.ge_path(), session=readwrite_session, json=payload)
    assert_api_success(response)

    target = neox_config_service.target()
    command = f"show running-config interface ge {target.ge_slot_id}-{target.ge_port_id}"
    cli = SshCliClient(env_config.dut.device_ip, ssh_username, ssh_password)
    [result] = cli.run_commands([command])
    checks = ge_cli_checks(payload["Content"])
    missing = [expected for expected in checks if expected not in result.output]
    report_path = write_cli_verify_report(neox_config_service, payload, response, command, result.output, checks, missing)

    assert not missing, f"Missing GE running-config lines: {missing}. Report: {report_path}"


def test_ge_config_max_create_readwrite(
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
        pytest.skip("Set NEOX_SSH_USERNAME and NEOX_SSH_PASSWORD to run GE CLI verification.")

    config = json.loads(FULL_ACCEPTED_PAYLOAD_FILE.read_text(encoding="utf-8"))
    payload = config["payload"]
    expected_lines = config["running_config_visible_lines"]

    cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session))
    api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)
    response = api_client.request("POST", neox_config_service.ge_path(), session=readwrite_session, json=payload)
    assert_api_success(response)

    target = neox_config_service.target()
    command = f"show running-config interface ge {target.ge_slot_id}-{target.ge_port_id}"
    cli = SshCliClient(env_config.dut.device_ip, ssh_username, ssh_password)
    [result] = cli.run_commands([command])
    missing = [expected for expected in expected_lines if expected not in result.output]
    report_path = write_cli_verify_report(neox_config_service, payload, response, command, result.output, expected_lines, missing)

    assert not missing, f"Missing GE running-config lines: {missing}. Report: {report_path}"


def test_ge_config_set_readwrite(
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
        pytest.skip("Set NEOX_SSH_USERNAME and NEOX_SSH_PASSWORD to run GE CLI verification.")

    payload = load_enable_accepted_payload()
    content = payload["Content"]
    mac = content["fdb_list"][0]["mac"]
    expected_running_lines = [
        "enable",
        "auto-negotiation enable",
        "flow-control enable",
        "speed auto",
        "name \"REST_GE_39\"",
        f"acl mac-filter mac {mac}",
        "acl oui-filter enable",
        "acl oui-filter mac 00:11:22",
        "arp-inspection enable",
        "vlan copy_cpbit enable",
        "frame-type all",
        "acl packet-filter pppoe-only",
        "pvid 1314 pbit 0",
        "dscp active",
        "fdb nni-vlan-max-count 1 nni-vlan 1314",
        f"fdb mac {mac} vlan 1314",
        "dhcp l2agent snooping dhcp untrust",
        "dhcp l2agent snooping dhcpv6 untrust",
        "dhcp l2agent opt82-policy policy keep",
        "dhcp l2agent opt-ldra-policy policy keep",
        "dhcp l2agent opt-ldra-policy linklocal skip-src",
        "dot1x active",
        "dot1x auth-once",
        "dot1x circuit-id option-info REST_GE_39",
        "lldp notification",
        "lldp basic-tlv management-address",
        "lldp basic-tlv port-description",
        "lldp basic-tlv system-capabilities",
        "lldp basic-tlv system-description",
        "lldp basic-tlv system-name",
        "lldp org-specific-tlv dot1 port-vlan-id",
        "lldp org-specific-tlv dot3 link-aggregation",
        "lldp org-specific-tlv dot3 mac-phy",
        "lldp org-specific-tlv dot3 max-frame-size",
    ]

    cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session))
    cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.vlan_path(), session=readwrite_session))
    api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)
    api_client.request("DELETE", neox_config_service.vlan_path(), session=readwrite_session)
    vlan_response = api_client.request("POST", neox_config_service.vlan_path(), session=readwrite_session, json=vlan_payload())
    assert_api_success(vlan_response)
    response = api_client.request("POST", neox_config_service.ge_path(), session=readwrite_session, json=payload)
    assert_api_success(response)

    target = neox_config_service.target()
    command_by_name = {
        "running-config": f"show running-config interface ge {target.ge_slot_id}-{target.ge_port_id}",
        "config": f"show interface ge {target.ge_slot_id}-{target.ge_port_id} config",
        "dot1x": f"show interface ge {target.ge_slot_id}-{target.ge_port_id} dot1x",
        "dscp": f"show interface ge {target.ge_slot_id}-{target.ge_port_id} dscp",
        "frame-type": f"show interface ge {target.ge_slot_id}-{target.ge_port_id} frame-type",
        "pvid": f"show interface ge {target.ge_slot_id}-{target.ge_port_id} pvid",
        "fdb": f"show interface ge {target.ge_slot_id}-{target.ge_port_id} fdb",
    }
    cli = SshCliClient(env_config.dut.device_ip, ssh_username, ssh_password)
    command_results = cli.run_commands(list(command_by_name.values()))
    output_by_name = {
        name: result.output
        for name, result in zip(command_by_name, command_results)
    }
    expected_by_output = {
        "running-config": expected_running_lines,
        "config": ["Flow-Ctrl", "enable", "REST_GE_39"],
        "dot1x": ["1-39", "REST_GE_39"],
        "dscp": ["DSCP mode Enable"],
        "frame-type": ["1-39"],
        "pvid": ["1-39", "1314", "0"],
        "fdb": ["Maximum MAC entry counts by NNI-VLAN 1314 : 1"],
    }
    missing_by_output = {
        name: [expected for expected in expected_lines if expected not in output_by_name.get(name, "")]
        for name, expected_lines in expected_by_output.items()
    }
    report_path = write_cli_multi_verify_report(
        neox_config_service,
        payload,
        response,
        command_by_name,
        output_by_name,
        expected_by_output,
        missing_by_output,
    )

    missing = {name: lines for name, lines in missing_by_output.items() if lines}
    assert not missing, f"Missing GE CLI verification lines: {missing}. Report: {report_path}"


def ge_cli_checks(content: dict[str, Any]) -> list[str]:
    checks = []
    if content.get("portenable") == "enable":
        checks.append("enable")
    if "auto_nego" in content:
        checks.append(f"auto-negotiation {content['auto_nego']}")
    if "flow" in content:
        checks.append(f"flow-control {content['flow']}")
    if "portspeed" in content:
        checks.append(f"speed {content['portspeed']}")
    if "portname" in content:
        checks.append(f"name \"{content['portname']}\"")
    if "arpinspection" in content:
        checks.append(f"arp-inspection {content['arpinspection']}")
    if "copycpbit" in content:
        checks.append(f"vlan copy_cpbit {content['copycpbit']}")
    if "outertpid" in content:
        checks.append(f"vlan outer-tpid {content['outertpid']}")
    if "frametype" in content:
        checks.append(f"frame-type {content['frametype']}")
    return checks


def load_enable_accepted_payload() -> dict[str, Any]:
    data = json.loads(ENABLE_ACCEPTED_PAYLOAD_FILE.read_text(encoding="utf-8"))
    payload = data["payload"]
    content = dict(payload["Content"])
    mac = unique_mac()
    for entry in content.get("acl_maclist", []):
        if entry.get("aclmac") == "__UNIQUE_MAC__":
            entry["aclmac"] = mac
    for entry in content.get("fdb_list", []):
        if entry.get("mac") == "__UNIQUE_MAC__":
            entry["mac"] = mac
    return {"Content": content}


def unique_mac() -> str:
    value = int(time.time()) & 0xFFFFFF
    return f"02:13:{(value >> 16) & 0xFF:02x}:{(value >> 8) & 0xFF:02x}:{value & 0xFF:02x}:39"


def write_cli_verify_report(
    neox_config_service,
    payload: dict[str, Any],
    api_response,
    command: str,
    cli_output: str,
    expected_lines: list[str],
    missing_lines: list[str],
) -> Path:
    root = Path(__file__).resolve().parents[1]
    reports_dir = root / "reports" / "device-verification"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"ge_cli_verify_{timestamp}.json"
    target = neox_config_service.target()
    data = {
        "target": {
            "node": neox_config_service.env_config.dut.node_key,
            "device_ip": neox_config_service.env_config.dut.device_ip,
            "device_name": target.device_name,
            "ge_slot_id": target.ge_slot_id,
            "ge_port_id": target.ge_port_id,
        },
        "rest_api": {
            "path": neox_config_service.ge_path(),
            "request_content": redact(payload["Content"]),
            "response": {
                "status_code": api_response.status_code,
                "retstatus": api_response.retstatus,
                "retresult": api_response.retresult,
            },
        },
        "cli": {
            "transport": "ssh",
            "command": command,
            "output": cli_output,
            "expected_lines": expected_lines,
            "missing_lines": missing_lines,
        },
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_cli_multi_verify_report(
    neox_config_service,
    payload: dict[str, Any],
    api_response,
    command_by_name: dict[str, str],
    output_by_name: dict[str, str],
    expected_by_output: dict[str, list[str]],
    missing_by_output: dict[str, list[str]],
) -> Path:
    root = Path(__file__).resolve().parents[1]
    reports_dir = root / "reports" / "device-verification"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"ge_cli_multi_verify_{timestamp}.json"
    target = neox_config_service.target()
    data = {
        "target": {
            "node": neox_config_service.env_config.dut.node_key,
            "device_ip": neox_config_service.env_config.dut.device_ip,
            "device_name": target.device_name,
            "ge_slot_id": target.ge_slot_id,
            "ge_port_id": target.ge_port_id,
        },
        "rest_api": {
            "path": neox_config_service.ge_path(),
            "request_content": redact(payload["Content"]),
            "response": {
                "status_code": api_response.status_code,
                "retstatus": api_response.retstatus,
                "retresult": api_response.retresult,
            },
        },
        "cli": {
            name: {
                "transport": "ssh",
                "command": command_by_name[name],
                "output": output_by_name.get(name, ""),
                "expected_lines": expected_by_output.get(name, []),
                "missing_lines": missing_by_output.get(name, []),
            }
            for name in command_by_name
        },
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
