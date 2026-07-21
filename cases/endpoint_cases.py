from __future__ import annotations

import json
from typing import Any

from cases.payloads import ge_service_payload, ont_service_payload, remote_console_payload
from models.api import EndpointCase


def _active_alarm_filter(env: Any, unique_name: str) -> dict[str, Any]:
    return {"alarmfilter": json.dumps({"KeyWord": []})}


def _history_alarm_filter(env: Any, unique_name: str) -> dict[str, Any]:
    return {"alarmfilter": json.dumps({"KeyWord": []})}


def _ont_service_filter(env: Any, unique_name: str) -> dict[str, Any]:
    return {"ontservicefilter": json.dumps({"SN": env.dut.ont_sn})}


def _ge_service_filter(env: Any, unique_name: str) -> dict[str, Any]:
    return {"geservicefilter": json.dumps({"IP": env.dut.device_ip})}


READ_ENDPOINTS = [
    EndpointCase("active_alarm_list", "GET", "alarm", "/activealarm", case_id="EMS1-6641", params_factory=_active_alarm_filter),
    EndpointCase("history_alarm_list", "GET", "alarm", "/historyalarm", case_id="EMS1-6642", params_factory=_history_alarm_filter),
    EndpointCase("device_list", "GET", "inventory", "/device", case_id="EMS1-6643"),
    EndpointCase("device_by_name", "GET", "inventory", lambda env: f"/device/{env.dut.device_name}", case_id="EMS1-6679"),
    EndpointCase("slot_list", "GET", "inventory", "/slot", case_id="EMS1-6644"),
    EndpointCase("slot_by_device", "GET", "inventory", lambda env: f"/slot/{env.dut.device_name}", case_id="EMS1-6680"),
    EndpointCase("slot_by_id", "GET", "inventory", lambda env: f"/slot/{env.dut.device_name}/{env.dut.slot_id}", case_id="EMS1-6681"),
    EndpointCase("port_by_device", "GET", "inventory", lambda env: f"/port/{env.dut.device_name}", case_id="EMS1-6682"),
    EndpointCase("port_by_slot", "GET", "inventory", lambda env: f"/port/{env.dut.device_name}/{env.dut.ge_slot_id}", case_id="EMS1-6683"),
    EndpointCase("port_by_id", "GET", "inventory", lambda env: f"/port/{env.dut.device_name}/{env.dut.ge_slot_id}/{env.dut.ge_port_id}", case_id="EMS1-6684"),
    EndpointCase("ont_by_device", "GET", "ont", lambda env: f"/ont/{env.dut.device_name}", case_id="EMS1-6675"),
    EndpointCase("ont_by_slot", "GET", "ont", lambda env: f"/ont/{env.dut.device_name}/{env.dut.slot_id}", case_id="EMS1-6676"),
    EndpointCase("ont_by_port", "GET", "ont", lambda env: f"/ont/{env.dut.device_name}/{env.dut.slot_id}/{env.dut.port_id}", case_id="EMS1-6677"),
    EndpointCase("ont_by_id", "GET", "ont", lambda env: f"/ont/{env.dut.device_name}/{env.dut.slot_id}/{env.dut.port_id}/{env.dut.ont_id}", case_id="EMS1-6678"),
    EndpointCase("ont_by_sn", "GET", "ont", lambda env: f"/ont/sn/{env.dut.ont_sn}", case_id="EMS1-6671"),
    EndpointCase("ont_by_description", "GET", "ont", lambda env: f"/ont/description/{env.dut.ont_description}", case_id="EMS1-6673"),
    EndpointCase("ont_service_list", "GET", "provision", "/ontservice", case_id="EMS1-6647", params_factory=_ont_service_filter),
    EndpointCase("ont_service_by_sn", "GET", "provision", lambda env: f"/ontservice/{env.dut.ont_sn}", case_id="EMS1-6665"),
    EndpointCase("ge_service_list", "GET", "provision", "/geservice", case_id="EMS1-6648", params_factory=_ge_service_filter),
    EndpointCase("ge_service_by_port", "GET", "provision", lambda env: f"/geservice/{env.dut.device_name}/{env.dut.ge_slot_id}/{env.dut.ge_port_id}", case_id="EMS1-6660"),
]


MUTATING_ENDPOINTS = [
    EndpointCase(
        "create_ont_service",
        "POST",
        "provision",
        lambda env: f"/ontservice/{env.dut.ont_sn}",
        case_id="EMS1-6666",
        payload_factory=ont_service_payload,
    ),
    EndpointCase(
        "modify_ont_service",
        "PUT",
        "provision",
        lambda env: f"/ontservice/{env.dut.ont_sn}",
        case_id="EMS1-6667",
        payload_factory=ont_service_payload,
    ),
    EndpointCase(
        "delete_ont_service",
        "DELETE",
        "provision",
        lambda env: f"/ontservice/{env.dut.ont_sn}",
        case_id="EMS1-6669",
    ),
    EndpointCase(
        "create_ge_service",
        "POST",
        "provision",
        lambda env: f"/geservice/{env.dut.device_name}/{env.dut.ge_slot_id}/{env.dut.ge_port_id}",
        case_id="EMS1-6661",
        payload_factory=ge_service_payload,
    ),
    EndpointCase(
        "modify_ge_service_placeholder",
        "PUT",
        "provision",
        "/geservice/0",
        case_id="EMS1-6662",
        payload_factory=ge_service_payload,
    ),
    EndpointCase("delete_ge_service_placeholder", "DELETE", "provision", "/geservice/0", case_id="EMS1-6664"),
    EndpointCase(
        "remote_console",
        "POST",
        "remote",
        lambda env: f"/remote/{env.dut.device_name}",
        case_id="EMS1-6652",
        payload_factory=remote_console_payload,
    ),
]
