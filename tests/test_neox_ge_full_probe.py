from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from clients.ssh_cli import SshCliClient
from services.neox_config.service import GE_ACCEPTED_INCREMENTAL_PAYLOAD_FILE, GE_SWAGGER_PAYLOAD_FILE
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


SWAGGER_PAYLOAD_FILE = GE_SWAGGER_PAYLOAD_FILE
ACCEPTED_PAYLOAD_FILE = GE_ACCEPTED_INCREMENTAL_PAYLOAD_FILE


FIELD_VALUE_OVERRIDES: dict[str, Any] = {
    "bias_alarm_high": "79",
    "bias_alarm_low": "0",
    "bias_warn_high": "79",
    "bias_warn_low": "0",
    "broadcast_rate": "0",
    "customtype": "0x8100",
    "dlf_rate": "0",
    "dot1xreauthpeiod": 3600,
    "dotlxcircuitinfo": "REST_GE_39",
    "dotlxserverindex": 1,
    "igmp_bandwidth": 0,
    "loopguard_recovertime": 60,
    "maxcount": 0,
    "maxgroup": 1,
    "maxmsg": 1,
    "mtu": 1500,
    "multicast_rate": "0",
    "nnimaxcount": 0,
    "nnivlan": 1314,
    "pbit": 0,
    "profile_aclprofilename": "",
    "pvid": 1314,
    "pwsaving_awake": 0,
    "pwsaving_sleep": 0,
    "ratelimitname": "",
    "rxpower_alarm_high": "0",
    "rxpower_alarm_low": "-127",
    "rxpower_warn_high": "0",
    "rxpower_warn_low": "-127",
    "shapingname": "",
    "snooping_maxlease": 0,
    "snooping_vlanlist": "1314",
    "tel": "0000",
    "temperature_alarm_high": "100",
    "temperature_alarm_low": "-40",
    "temperature_warn_high": "100",
    "temperature_warn_low": "-40",
    "txpower_alarm_high": "6.5",
    "txpower_alarm_low": "-15.3",
    "txpower_warn_high": "6.5",
    "txpower_warn_low": "-15.3",
    "voltage_alarm_high": "3.59",
    "voltage_alarm_low": "2.8",
    "voltage_warn_high": "3.59",
    "voltage_warn_low": "2.8",
    "weightname": "",
    "acl_maclist": [{"aclmac": "00:11:22:33:44:55"}],
    "acl_ouilist": [{"acloui": "001122"}],
    "egress_profile_list": [{"egress_profile": "", "egress_profile_priority": 0}],
    "fdb_list": [{"mac": "00:11:22:33:44:55", "vid": 1314}],
    "igmp_grouppriprofile_list": [{"grouppriprofile": ""}],
    "igmp_mvid_list": [{"igmp_mvid": 1314, "igmp_univid": 1314, "igmp_untag": "disable"}],
    "port_aclprofile_list": [{"aclprofile": "", "aclprofile_priority": 0}],
    "smcastip_list": [{"ip": "239.1.1.1", "nnivid": 1314, "role": "fix"}],
    "smcastmac_list": [{"mac": "01:00:5e:01:01:01", "nnivid": 1314}],
    "staticipfilter_list": [{"ip": "192.0.2.10", "mask": 32, "staticindex": 1}],
    "vlan_list": [{"vid": 1314, "vlanmode": "fixed"}],
    "vlantls_list": [{"spbit": 0, "svid": 1314}],
    "vlantrans_list": [{"cvid": 1314, "spbit": 0, "svlan": 1314, "trans_mode": "uni-vlan", "univid": 1314}],
    "vlantrunk_ether_list": [{"etype": "0800", "spbit": 0, "svid": 1314}],
    "vlantrunk_subnet_list": [{"ip": "192.0.2.0", "mask": "24", "spbit": 0, "svid": 1314}],
    "vlantrunk_untag_list": [{"cvid": 1314, "spbit": 0, "svid": 1314}],
    "vlantrunk_vlan_list": [{"svid": 1314, "univid": 1314}],
}


def test_ge_full_parameter_probe_set_readwrite(
    api_client,
    env_config,
    neox_config_service,
    readwrite_session,
    cleanup_registry,
):
    neox_config_service.verify_required_target_data()
    ssh_username, ssh_password = neox_cli_credentials(env_config, "GE full CLI probe")

    target = neox_config_service.target()
    command = f"show running-config interface ge {target.ge_slot_id}-{target.ge_port_id}"
    cli = SshCliClient(env_config.dut.device_ip, ssh_username, ssh_password)

    cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session))
    api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)

    accepted_content = load_accepted_content()
    base_response = api_client.request(
        "POST",
        neox_config_service.ge_path(),
        session=readwrite_session,
        json={"Content": accepted_content},
    )
    assert_api_success(base_response)
    results = [record_result("accepted_base", None, None, accepted_content, base_response, kept=True, cli_output=run_cli(cli, command))]

    for field in candidate_fields(accepted_content):
        value = candidate_value(field)
        probe_content = dict(accepted_content)
        probe_content[field] = value
        response = api_client.request(
            "POST",
            neox_config_service.ge_path(),
            session=readwrite_session,
            json={"Content": probe_content},
        )
        kept = is_success(response)
        cli_output = None
        if kept:
            accepted_content[field] = value
            cli_output = run_cli(cli, command)
        results.append(record_result(field, field, value, probe_content, response, kept=kept, cli_output=cli_output))

    api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)
    write_full_probe_report(neox_config_service, command, accepted_content, results)


def load_accepted_content() -> dict[str, Any]:
    data = json.loads(ACCEPTED_PAYLOAD_FILE.read_text(encoding="utf-8"))
    return dict(data["payload"]["Content"])


def load_swagger_content() -> dict[str, Any]:
    data = json.loads(SWAGGER_PAYLOAD_FILE.read_text(encoding="utf-8"))
    return data["payload"]["Content"]


def candidate_fields(accepted_content: dict[str, Any]) -> list[str]:
    return [field for field in load_swagger_content() if field not in accepted_content]


def candidate_value(field: str) -> Any:
    if field in FIELD_VALUE_OVERRIDES:
        return FIELD_VALUE_OVERRIDES[field]
    return load_swagger_content()[field]


def is_success(response) -> bool:
    return response.status_code < 500 and isinstance(response.json, dict) and response.json.get("retstatus") == "Success"


def run_cli(cli: SshCliClient, command: str) -> str:
    [result] = cli.run_commands([command])
    return result.output


def record_result(
    case_name: str,
    field: str | None,
    value: Any,
    content: dict[str, Any],
    response,
    *,
    kept: bool,
    cli_output: str | None,
) -> dict[str, Any]:
    body = response.json if isinstance(response.json, dict) else {"raw": response.text}
    return {
        "case": case_name,
        "field": field,
        "value": redact(value),
        "kept_for_next_request": kept,
        "request_field_count": len(content),
        "response": {
            "status_code": response.status_code,
            "retstatus": body.get("retstatus") if isinstance(body, dict) else None,
            "retresult": body.get("retresult") if isinstance(body, dict) else response.text,
            "retval": redact(body.get("retval")) if isinstance(body, dict) else None,
            "body": redact(body),
        },
        "cli_output": cli_output,
    }


def write_full_probe_report(
    neox_config_service,
    command: str,
    accepted_content: dict[str, Any],
    results: list[dict[str, Any]],
) -> Path:
    root = Path(__file__).resolve().parents[1]
    reports_dir = root / "reports" / "full-probes"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"neox_ge_full_probe_{timestamp}.json"
    target = neox_config_service.target()
    data = {
        "target": {
            "node": neox_config_service.env_config.dut.node_key,
            "device_ip": neox_config_service.env_config.dut.device_ip,
            "device_name": target.device_name,
            "ge_slot_id": target.ge_slot_id,
            "ge_port_id": target.ge_port_id,
        },
        "cli_command": command,
        "accepted_content": redact(accepted_content),
        "accepted_fields": list(accepted_content),
        "failed_fields": [result["field"] for result in results if result["field"] and not result["kept_for_next_request"]],
        "results": results,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
