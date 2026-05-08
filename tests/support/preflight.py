from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from clients.session import SessionManager
from clients import EmsApiClient
from config_loader import load_environment
from utils.assertions import assert_api_success


DUT_DEPENDENT_MARKERS = {
    "alarm",
    "authmatrix",
    "inventory",
    "mutating",
    "noaccess",
    "ont",
    "profile",
    "provision",
    "readonly",
    "readwrite",
    "remoteconsole",
    "session",
}


@dataclass(frozen=True)
class DutPreflightResult:
    ok: bool
    reason: str = ""


def skip_unready_dut_items(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--skip-dut-preflight"):
        return

    dut_items = [item for item in items if is_dut_dependent(item)]
    if not dut_items:
        return

    result = run_dut_preflight(
        node=config.getoption("--ems-node"),
        auth_profile=config.getoption("--auth-profile"),
    )
    if not result.ok:
        skip_dut = pytest.mark.skip(reason=f"DUT preflight failed: {result.reason}")
        for item in dut_items:
            item.add_marker(skip_dut)
        return


def is_dut_dependent(item: pytest.Item) -> bool:
    return any(marker in item.keywords for marker in DUT_DEPENDENT_MARKERS)


def run_dut_preflight(node: str | None, auth_profile: str | None) -> DutPreflightResult:
    try:
        env_config = load_environment(node=node, auth_profile=auth_profile)
        api_client = EmsApiClient(env_config)
        session_manager = SessionManager(api_client, env_config)
        with session_manager.credentials_session(env_config.readwrite) as session_id:
            checks = [
                _check_success(
                    api_client,
                    session_id,
                    f"/device/{env_config.dut.device_name}",
                    "device inventory",
                ),
                _check_success(
                    api_client,
                    session_id,
                    f"/ont/sn/{env_config.dut.ont_sn}",
                    "ONT inventory",
                ),
            ]
            for check in checks:
                if not check.ok:
                    return check

        return DutPreflightResult(True)
    except Exception as error:
        return DutPreflightResult(False, str(error))


def _check_success(api_client: EmsApiClient, session_id: str, path: str, label: str) -> DutPreflightResult:
    response = api_client.request("GET", path, session=session_id)
    try:
        assert_api_success(response)
    except AssertionError:
        return DutPreflightResult(False, f"{label} is not ready: {_format_preflight_response(response)}")

    down_reason = _find_down_reason(response.json)
    if down_reason:
        return DutPreflightResult(False, f"{label} reports device down: {down_reason}")
    return DutPreflightResult(True)


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
