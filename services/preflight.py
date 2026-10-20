"""DUT readiness checks shared by the pytest collection hook and tools/run_multi_node.py.

run_startup_preflight syncs slot data from the DUT CLI, then checks the device inventory
through EMS. It connects to EMS and the DUT, so callers decide when it may run.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from clients import EmsApiClient
from clients.session import SessionManager
from config_loader import load_environment
from services.target_sync import sync_target_data_from_cli
from utils.assertions import assert_api_success


@dataclass(frozen=True)
class DutPreflightResult:
    ok: bool
    reason: str = ""


def run_startup_preflight(node: str | None, auth_profile: str | None) -> DutPreflightResult:
    target_sync = sync_target_data_from_cli(node, auth_profile)
    if not target_sync.ok:
        return DutPreflightResult(False, target_sync.reason)
    return run_device_preflight(node, auth_profile)


def device_preflight_attempts() -> int:
    return max(1, int(os.environ.get("DUT_PREFLIGHT_ATTEMPTS", "6") or "6"))


def device_preflight_interval_seconds() -> float:
    return max(0.0, float(os.environ.get("DUT_PREFLIGHT_INTERVAL_SECONDS", "20") or "20"))


def run_dut_preflight(node: str | None, auth_profile: str | None) -> DutPreflightResult:
    startup = run_startup_preflight(node, auth_profile)
    if not startup.ok:
        return startup
    return run_ont_preflight(node, auth_profile)


def run_device_preflight(node: str | None, auth_profile: str | None) -> DutPreflightResult:
    try:
        env_config = load_environment(node=node, auth_profile=auth_profile)
        api_client = EmsApiClient(env_config)
        session_manager = SessionManager(api_client, env_config)
        with session_manager.credentials_session(env_config.readwrite) as session_id:
            return _check_success(
                api_client,
                session_id,
                f"/device/{env_config.dut.device_name}",
                "device inventory",
                attempts=device_preflight_attempts(),
                interval_seconds=device_preflight_interval_seconds(),
            )
    except Exception as error:
        return DutPreflightResult(False, str(error))


def run_ont_preflight(node: str | None, auth_profile: str | None) -> DutPreflightResult:
    try:
        env_config = load_environment(node=node, auth_profile=auth_profile)
        api_client = EmsApiClient(env_config)
        session_manager = SessionManager(api_client, env_config)
        with session_manager.credentials_session(env_config.readwrite) as session_id:
            return _check_success(
                api_client,
                session_id,
                f"/ont/sn/{env_config.dut.ont_sn}",
                "ONT inventory",
            )

    except Exception as error:
        return DutPreflightResult(False, str(error))


def _check_success(
    api_client: EmsApiClient,
    session_id: str,
    path: str,
    label: str,
    *,
    attempts: int = 1,
    interval_seconds: float = 0.0,
) -> DutPreflightResult:
    total_attempts = max(1, attempts)
    last_result = DutPreflightResult(False, f"{label} preflight did not run")
    for attempt in range(total_attempts):
        response = api_client.request("GET", path, session=session_id)
        last_result = _evaluate_preflight_response(response, label)
        if last_result.ok:
            return last_result
        if label != "device inventory" or attempt >= total_attempts - 1:
            return last_result
        if interval_seconds > 0:
            time.sleep(interval_seconds)
    return last_result


def _evaluate_preflight_response(response, label: str) -> DutPreflightResult:
    try:
        assert_api_success(response)
    except AssertionError:
        return DutPreflightResult(False, f"{label} is not ready: {_format_preflight_response(response)}")

    if label == "device inventory":
        devstatus_reason = _find_unready_devstatus(response.json)
        if devstatus_reason:
            return DutPreflightResult(False, f"{label} reports device not ready: {devstatus_reason}")

    down_reason = _find_down_reason(response.json)
    if down_reason:
        return DutPreflightResult(False, f"{label} reports device down: {down_reason}")
    return DutPreflightResult(True)


def _find_unready_devstatus(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("deviceinfo", "device", "devinfo"):
            device = value.get(key)
            if isinstance(device, dict):
                return _devstatus_reason(device)

        for key in ("deviceinfolist", "devicelist", "devices"):
            devices = value.get(key)
            if isinstance(devices, list):
                for device in devices:
                    if isinstance(device, dict):
                        reason = _devstatus_reason(device)
                        if reason:
                            return reason

        retval = value.get("retval")
        if isinstance(retval, (dict, list)):
            return _find_unready_devstatus(retval)

    if isinstance(value, list):
        for item in value:
            reason = _find_unready_devstatus(item)
            if reason:
                return reason
    return None


def _devstatus_reason(device: dict[str, Any]) -> str | None:
    if "DevStatus" not in device:
        return None
    devstatus = str(device.get("DevStatus"))
    if devstatus == "1":
        return None

    devname = device.get("DevName") or device.get("devname") or "<unknown>"
    ip_address = device.get("IPAddress") or device.get("ipaddress") or "<unknown>"
    return f"DevStatus={devstatus} DevName={devname} IPAddress={ip_address}; expected DevStatus=1"


def _find_down_reason(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in {"result", "retresult", "state", "devstatus", "operationstatus"}:
                text = str(item)
                if _looks_down(text):
                    return f"{key}={text}"
            found = _find_down_reason(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_down_reason(item)
            if found:
                return found
    return None


def _looks_down(text: str) -> bool:
    normalized = text.lower()
    return ("device " in normalized and " down" in normalized) or normalized in {"down", "fail", "failed"}


def _format_preflight_response(response) -> str:
    detail = f"{response.method} {response.url} HTTP={response.status_code}"
    if isinstance(response.json, dict):
        retstatus = response.json.get("retstatus")
        retresult = response.json.get("retresult")
        if retstatus is not None:
            detail += f" retstatus={retstatus}"
        if retresult:
            detail += f" retresult={retresult}"
    return detail
