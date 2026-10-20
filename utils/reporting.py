"""Session report state shared by clients, services and pytest hooks.

Rendering and writing the reports lives in tests/support/report_writer.py.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


def _report_timestamp() -> str:
    base = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    suffix = os.environ.get("EMS_REPORT_SUFFIX", "").strip()
    return f"{base}_{_safe_env_suffix(suffix)}" if suffix else base


def _safe_env_suffix(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)

@dataclass
class CaseRegistration:
    case_id: str
    name: str


@dataclass
class CaseResult:
    nodeid: str
    case_ids: list[CaseRegistration]
    outcome: str
    duration: float


@dataclass
class ReportState:
    started_at: float = field(default_factory=time.perf_counter)
    timestamp: str = field(default_factory=_report_timestamp)
    case_registry: dict[str, list[CaseRegistration]] = field(default_factory=dict)
    permission_roles: dict[str, str] = field(default_factory=dict)
    results: list[CaseResult] = field(default_factory=list)
    session_metrics: dict[str, Any] = field(default_factory=dict)
    report_notes: dict[str, str] = field(default_factory=dict)
    connection_events: list["ConnectionEvent"] = field(default_factory=list)
    slow_requests: list["SlowRequest"] = field(default_factory=list)


@dataclass
class ConnectionEvent:
    nodeid: str
    method: str
    path: str
    error: str
    attempt: int
    max_attempts: int
    action: str  # "retried" or "raised"
    recovered: bool = False


@dataclass
class SlowRequest:
    nodeid: str
    method: str
    path: str
    elapsed: float
    attempts: int
    status_code: int
    threshold: float


REPORT_STATE = ReportState()


def record_report_note(label: str, value: str) -> None:
    """Add a run-level note shown in the txt and HTML report headers (e.g. a slow EMS sync)."""
    REPORT_STATE.report_notes[label] = value


def record_connection_event(
    method: str,
    path: str,
    error: str,
    *,
    attempt: int,
    max_attempts: int,
    action: str,
) -> ConnectionEvent:
    """Record an EMS transport error (connect/read timeout, reset) for the report header."""
    event = ConnectionEvent(
        nodeid=_current_nodeid(),
        method=method,
        path=path,
        error=error,
        attempt=attempt,
        max_attempts=max_attempts,
        action=action,
    )
    REPORT_STATE.connection_events.append(event)
    return event


def record_slow_request(
    method: str,
    path: str,
    elapsed: float,
    *,
    attempts: int,
    status_code: int,
    threshold: float,
) -> None:
    """Record an EMS request whose total time (all attempts and waits) exceeded the slow threshold."""
    REPORT_STATE.slow_requests.append(
        SlowRequest(
            nodeid=_current_nodeid(),
            method=method,
            path=path,
            elapsed=elapsed,
            attempts=attempts,
            status_code=status_code,
            threshold=threshold,
        )
    )


def _current_nodeid() -> str:
    return os.environ.get("PYTEST_CURRENT_TEST", "").split(" ", 1)[0]

SESSION_METRIC_FIELDS = (
    "login_requests",
    "logout_requests",
    "fresh_logins",
    "cached_logins",
    "cache_hits",
    "cache_misses",
    "proactive_refreshes",
    "authorization_refreshes",
    "safe_retries",
    "mutation_not_retried",
)


def register_case(case_id: str | None, name: str) -> None:
    if not case_id:
        return
    current = os.environ.get("PYTEST_CURRENT_TEST", "").split(" ", 1)[0]
    if not current:
        return
    registrations = REPORT_STATE.case_registry.setdefault(current, [])
    if not any(item.case_id == case_id and item.name == name for item in registrations):
        registrations.append(CaseRegistration(case_id=case_id, name=name))


def register_node_case(nodeid: str, case_id: str | None, name: str) -> None:
    if not case_id:
        return
    registrations = REPORT_STATE.case_registry.setdefault(nodeid, [])
    if not any(item.case_id == case_id and item.name == name for item in registrations):
        registrations.append(CaseRegistration(case_id=case_id, name=name))


def register_permission_role(nodeid: str, role: str | None) -> None:
    if role in {"readonly", "noaccess"}:
        REPORT_STATE.permission_roles[nodeid] = role


def record_result(nodeid: str, outcome: str, duration: float) -> None:
    case_ids = REPORT_STATE.case_registry.get(nodeid, [])
    REPORT_STATE.results.append(
        CaseResult(
            nodeid=nodeid,
            case_ids=case_ids,
            outcome=outcome,
            duration=duration,
        )
    )


def ensure_report_dirs(config: Any) -> None:
    root = Path(str(config.rootpath))
    configured_allure_dir = getattr(config.option, "allure_report_dir", None)
    if configured_allure_dir:
        Path(str(configured_allure_dir)).mkdir(parents=True, exist_ok=True)
    else:
        current_allure_dir = root / "reports" / ".allure-results-current"
        if current_allure_dir.exists():
            shutil.rmtree(current_allure_dir)
        current_allure_dir.mkdir(parents=True, exist_ok=True)
        config.option.allure_report_dir = str(current_allure_dir)
    if getattr(config.option, "clean_alluredir", None) is None:
        config.option.clean_alluredir = True



def ensure_worker_report_dirs(config: Any) -> None:
    root = Path(str(config.rootpath))
    configured_allure_dir = getattr(config.option, "allure_report_dir", None)
    current_allure_dir = (
        Path(str(configured_allure_dir))
        if configured_allure_dir
        else root / "reports" / ".allure-results-current"
    )
    current_allure_dir.mkdir(parents=True, exist_ok=True)
    config.option.allure_report_dir = str(current_allure_dir)
    config.option.clean_alluredir = False


def set_session_metrics(metrics: dict[str, Any]) -> None:
    safe: dict[str, Any] = {"mode": "on" if str(metrics.get("mode", "off")).lower() == "on" else "off"}
    for field_name in SESSION_METRIC_FIELDS:
        try:
            safe[field_name] = max(0, int(metrics.get(field_name, 0)))
        except (TypeError, ValueError):
            safe[field_name] = 0
    raw_generations = metrics.get("session_generations", {})
    if isinstance(raw_generations, dict):
        safe["session_generations"] = {
            role: max(0, int(raw_generations.get(role, 0)))
            for role in ("readwrite", "readonly", "noaccess")
            if str(raw_generations.get(role, "")).isdigit()
        }
    REPORT_STATE.session_metrics = safe
