from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from cases.neox_legacy import legacy_test_cases


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
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
    case_registry: dict[str, list[CaseRegistration]] = field(default_factory=dict)
    permission_roles: dict[str, str] = field(default_factory=dict)
    results: list[CaseResult] = field(default_factory=list)


REPORT_STATE = ReportState()


def register_case(case_id: str | None, name: str) -> None:
    if not case_id:
        return
    current = os.environ.get("PYTEST_CURRENT_TEST", "").split(" ", 1)[0]
    if not current:
        return
    registrations = REPORT_STATE.case_registry.setdefault(current, [])
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
    current_allure_dir = root / "reports" / ".allure-results-current"
    current_allure_dir.mkdir(parents=True, exist_ok=True)
    if not getattr(config.option, "allure_report_dir", None):
        config.option.allure_report_dir = str(current_allure_dir)
    if getattr(config.option, "clean_alluredir", None) is None:
        config.option.clean_alluredir = True


def write_reports(config: Any, env_config: Any) -> tuple[Path, Path, Path | None]:
    root = Path(str(config.rootpath))
    ems_version = str(env_config.raw.get("EMS", {}).get("version", "unknown_ems_version"))
    report_dir = root / "reports" / _safe_path_part(ems_version)
    report_dir.mkdir(parents=True, exist_ok=True)

    txt_path = report_dir / f"{_report_base_name(env_config, REPORT_STATE.timestamp)}.txt"
    txt_path.write_text(_render_txt_report(env_config), encoding="utf-8")

    current_allure_dir = Path(getattr(config.option, "allure_report_dir", "")) if getattr(config.option, "allure_report_dir", None) else root / "reports" / ".allure-results-current"
    archived_allure_results = report_dir / f"allure-results_{REPORT_STATE.timestamp}"
    if current_allure_dir.exists() and current_allure_dir.resolve() != archived_allure_results.resolve():
        if archived_allure_results.exists():
            shutil.rmtree(archived_allure_results)
        shutil.copytree(current_allure_dir, archived_allure_results)
    else:
        archived_allure_results.mkdir(parents=True, exist_ok=True)

    html_report = _generate_allure_html(archived_allure_results, report_dir)
    return txt_path, archived_allure_results, html_report


def _render_txt_report(env_config: Any) -> str:
    elapsed = time.perf_counter() - REPORT_STATE.started_at
    case_results = _aggregate_case_results()
    permission_results = _aggregate_permission_summaries()
    rendered_results = [*case_results, *permission_results]
    passed = sum(1 for result in rendered_results if result.outcome == "passed")
    failed = sum(1 for result in rendered_results if result.outcome == "failed")

    lines = [
        f"Report generated on: {REPORT_STATE.timestamp}",
        f"Total test time: {_format_timedelta(elapsed)} ({elapsed:.2f} seconds)",
        f"Summary: {passed} Pass / {failed} Fail",
        f"UI URL: {env_config.base_url}",
        f"EMS Version: {env_config.raw.get('EMS', {}).get('version', 'unknown')}",
        f"Node Name: {env_config.dut.device_name}",
        f"Node IP: {env_config.dut.device_ip}",
        f"Node Chassis: {_node_data(env_config).get('chassis', 'unknown')}",
    ]
    lines.extend(_card_version_lines(env_config))
    lines.extend(_target_summary_lines(env_config))
    lines.extend(["", "Test Results:", "-------------"])

    for result in rendered_results:
        lines.append(
            f"[{result.case_id}][{result.name}] "
            f"Result {_outcome_name(result.outcome)} ({_trim_seconds(result.duration)}s)"
        )
    return "\n".join(lines) + "\n"


def _report_base_name(env_config: Any, timestamp: str) -> str:
    ems_version = env_config.raw.get("EMS", {}).get("version", "unknown")
    node = _node_data(env_config)
    chassis = node.get("chassis", "unknown")
    controller = _controller_card_name(env_config, node)
    return f"Web_Ems_Rest_Api_{ems_version}_{chassis}_{controller}_report_{timestamp}"


def _node_data(env_config: Any) -> dict[str, Any]:
    return env_config.raw.get("ZYXEL_DUT", {}).get(env_config.dut.node_key, {})


def _controller_card_name(env_config: Any, node: dict[str, Any]) -> str:
    cards = node.get("CARDINFO", {})
    if hasattr(env_config, "hardware"):
        configured = env_config.hardware.controller_card_name(env_config.dut.node_key, node)
        if configured:
            return configured
    if "NXC400" in cards:
        return "NXC400"
    for name, card in cards.items():
        if isinstance(card, dict) and str(card.get("port_type", "")).lower() == "network":
            return str(name)
    return next(iter(cards), "unknown")


def _card_version_lines(env_config: Any) -> list[str]:
    cards = _node_data(env_config).get("CARDINFO", {})
    configured: list[tuple[str, str, dict[str, Any]]] = []
    if hasattr(env_config, "hardware"):
        configured = env_config.hardware.report_card_entries(env_config.dut.node_key, _node_data(env_config))
    if configured:
        return _card_lines_for_entries(configured)

    preferred = ("NXC400", "NXP316", "NXA340")
    lines = _card_lines_for_names(cards, preferred)
    if lines:
        return lines
    return _card_lines_for_names(cards, cards.keys())


def _card_lines_for_names(cards: dict[str, Any], names: Any) -> list[str]:
    lines: list[str] = []
    for name in names:
        card = cards.get(name)
        if isinstance(card, dict) and card.get("fw_version"):
            lines.append(f"{name}:{card['fw_version']}")
    return lines


def _card_lines_for_entries(entries: list[tuple[str, str, dict[str, Any]]]) -> list[str]:
    lines: list[str] = []
    for label, _key, card in entries:
        if isinstance(card, dict) and card.get("fw_version"):
            lines.append(f"{label}:{card['fw_version']}")
    return lines


def _target_summary_lines(env_config: Any) -> list[str]:
    if not hasattr(env_config, "hardware"):
        return []
    target = env_config.hardware.node_target(env_config.dut.node_key)
    if not target:
        return []

    lines = ["Test Target Source: YAML"]
    if isinstance(target.get("ont"), dict):
        lines.append(
            "ONT Target: "
            f"slot {env_config.dut.slot_id} / port {env_config.dut.port_id} / "
            f"ont {env_config.dut.ont_id} / sn {env_config.dut.ont_sn}"
        )
        lines.append(f"ONT Template: {env_config.dut.ont_template}")
    if isinstance(target.get("ge_service"), dict):
        lines.append(
            "GE Target: "
            f"slot {env_config.dut.ge_slot_id} / port {env_config.dut.ge_port_id} / "
            f"template {env_config.dut.ge_template}"
        )
    return lines


def _generate_allure_html(results_dir: Path, report_dir: Path) -> Path | None:
    allure = shutil.which("allure")
    if not allure:
        return None
    html_report = report_dir / f"allure-report_{REPORT_STATE.timestamp}"
    if html_report.exists():
        shutil.rmtree(html_report)
    completed = subprocess.run(
        [allure, "generate", str(results_dir), "-o", str(html_report), "--clean"],
        check=False,
        capture_output=True,
        text=True,
    )
    return html_report if completed.returncode == 0 else None


def _format_timedelta(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def _trim_seconds(seconds: float) -> str:
    return f"{seconds:.2f}".rstrip("0").rstrip(".")


def _outcome_name(outcome: str) -> str:
    if outcome == "passed":
        return "Pass"
    if outcome == "failed":
        return "Fail"
    return "Skip"


def _fallback_name(nodeid: str) -> str:
    return nodeid.rsplit("::", 1)[-1].split("[", 1)[0]


@dataclass
class AggregatedReportCase:
    case_id: str
    name: str
    outcome: str
    duration: float


def _aggregate_case_results() -> list[AggregatedReportCase]:
    legacy_names = _legacy_case_name_by_id()
    legacy_order = _legacy_case_order()
    non_permission_case_ids = {
        registration.case_id
        for result in REPORT_STATE.results
        if result.case_ids and not _permission_role_for(result.nodeid)
        for registration in result.case_ids
        if registration.case_id
    }
    grouped: dict[str, list[CaseResult]] = {}
    fallback_names: dict[str, str] = {}
    for result in REPORT_STATE.results:
        role = _permission_role_for(result.nodeid)
        for registration in result.case_ids:
            if not registration.case_id:
                continue
            if role and registration.case_id in non_permission_case_ids:
                continue
            grouped.setdefault(registration.case_id, []).append(result)
            fallback_names.setdefault(registration.case_id, registration.name)

    aggregates: list[AggregatedReportCase] = []
    for case_id, results in grouped.items():
        aggregates.append(
            AggregatedReportCase(
                case_id=case_id,
                name=legacy_names.get(case_id, fallback_names.get(case_id, case_id)),
                outcome=_combine_outcomes(result.outcome for result in results),
                duration=max((result.duration for result in results), default=0.0),
            )
        )
    aggregates.sort(key=lambda item: (legacy_order.get(item.case_id, 10**9), item.case_id, item.name))
    return aggregates


def _aggregate_permission_summaries() -> list[AggregatedReportCase]:
    summaries: list[AggregatedReportCase] = []
    for case_id, role, name in (
        ("PERM-RO", "readonly", "readonly_permission_summary"),
        ("PERM-NA", "noaccess", "noaccess_permission_summary"),
    ):
        results = [result for result in REPORT_STATE.results if _permission_role_for(result.nodeid) == role]
        if not results:
            continue
        summaries.append(
            AggregatedReportCase(
                case_id=case_id,
                name=name,
                outcome=_combine_permission_outcomes(result.outcome for result in results),
                duration=sum(result.duration for result in results),
            )
        )
    return summaries


def _permission_role_for(nodeid: str) -> str | None:
    return REPORT_STATE.permission_roles.get(nodeid)


def _combine_outcomes(outcomes: Any) -> str:
    values = list(outcomes)
    if any(outcome == "failed" for outcome in values):
        return "failed"
    if any(outcome == "skipped" for outcome in values):
        return "skipped"
    if any(outcome == "passed" for outcome in values):
        return "passed"
    return "skipped"


def _combine_permission_outcomes(outcomes: Any) -> str:
    values = list(outcomes)
    if any(outcome == "failed" for outcome in values):
        return "failed"
    if any(outcome == "passed" for outcome in values):
        return "passed"
    return "skipped"


def _legacy_case_name_by_id() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for case in legacy_test_cases():
        case_ids = case.get("case_ids") or []
        if case_ids:
            mapping[str(case_ids[0])] = str(case.get("legacy_name", case_ids[0]))
    return mapping


def _legacy_case_order() -> dict[str, int]:
    order: dict[str, int] = {}
    for index, case in enumerate(legacy_test_cases()):
        case_ids = case.get("case_ids") or []
        if case_ids:
            order.setdefault(str(case_ids[0]), index)
    return order


def _safe_path_part(value: str) -> str:
    for char in '<>:"/\\|?*':
        value = value.replace(char, "_")
    return value.strip() or "unknown"
