from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


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
    passed = sum(_result_weight(result) for result in REPORT_STATE.results if result.outcome == "passed")
    failed = sum(_result_weight(result) for result in REPORT_STATE.results if result.outcome == "failed")

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
    lines.extend(["", "Test Results:", "-------------"])

    for result in REPORT_STATE.results:
        registrations = result.case_ids or [CaseRegistration(case_id="NO_CASE_ID", name=_fallback_name(result.nodeid))]
        for registration in registrations:
            lines.append(
                f"[{registration.case_id}][{registration.name}] "
                f"Result {_outcome_name(result.outcome)} ({_trim_seconds(result.duration)}s)"
            )
    return "\n".join(lines) + "\n"


def _report_base_name(env_config: Any, timestamp: str) -> str:
    ems_version = env_config.raw.get("EMS", {}).get("version", "unknown")
    node = _node_data(env_config)
    chassis = node.get("chassis", "unknown")
    controller = _controller_card_name(node)
    return f"Web_Ems_Rest_Api_{ems_version}_{chassis}_{controller}_report_{timestamp}"


def _node_data(env_config: Any) -> dict[str, Any]:
    return env_config.raw.get("ZYXEL_DUT", {}).get(env_config.dut.node_key, {})


def _controller_card_name(node: dict[str, Any]) -> str:
    cards = node.get("CARDINFO", {})
    if "NXC400" in cards:
        return "NXC400"
    for name, card in cards.items():
        if isinstance(card, dict) and str(card.get("port_type", "")).lower() == "network":
            return str(name)
    return next(iter(cards), "unknown")


def _card_version_lines(env_config: Any) -> list[str]:
    cards = _node_data(env_config).get("CARDINFO", {})
    preferred = ("NXC400", "NXP316", "NXA340")
    lines: list[str] = []
    for name in preferred:
        card = cards.get(name)
        if isinstance(card, dict) and card.get("fw_version"):
            lines.append(f"{name}:{card['fw_version']}")
    if lines:
        return lines
    for name, card in cards.items():
        if isinstance(card, dict) and card.get("fw_version"):
            lines.append(f"{name}:{card['fw_version']}")
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


def _result_weight(result: CaseResult) -> int:
    return max(len(result.case_ids), 1)


def _safe_path_part(value: str) -> str:
    for char in '<>:"/\\|?*':
        value = value.replace(char, "_")
    return value.strip() or "unknown"
