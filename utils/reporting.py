from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from cases.registry import case_name_by_id, case_order, permission_summary_specs


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


def write_reports(config: Any, env_config: Any) -> tuple[Path, Path, Path, Path | None, Path | None]:
    root = Path(str(config.rootpath))
    ems_version = str(getattr(env_config, "ems_version", "unknown_ems_version"))
    report_dir = root / "reports" / _safe_path_part(ems_version)
    report_dir.mkdir(parents=True, exist_ok=True)

    report_base_name = _report_base_name(env_config, REPORT_STATE.timestamp)
    txt_path = report_dir / f"{report_base_name}.txt"
    txt_path.write_text(_render_txt_report(env_config), encoding="utf-8")

    current_allure_dir = _current_allure_dir(config, root)
    archive_allure = _option_enabled(config, "archive_allure", "EMS_ARCHIVE_ALLURE")
    generate_allure_html = _option_enabled(config, "generate_allure_html", "EMS_GENERATE_ALLURE_HTML")
    integrated_evidence = not _option_enabled(
        config,
        "skip_integrated_evidence_report",
        "EMS_SKIP_INTEGRATED_EVIDENCE_REPORT",
    )

    allure_results = current_allure_dir
    if archive_allure or generate_allure_html or integrated_evidence:
        allure_results = _archive_allure_results(current_allure_dir, report_dir)

    allure_html = _generate_allure_html(allure_results, report_dir) if generate_allure_html else None

    integrated_html = report_dir / f"{report_base_name}_integrated.html" if integrated_evidence else None
    html_summary = report_dir / f"{report_base_name}.html"
    html_summary.write_text(
        _render_html_report(
            env_config,
            txt_path=txt_path,
            allure_results=allure_results,
            allure_html=allure_html,
            integrated_html=integrated_html,
        ),
        encoding="utf-8",
    )
    if integrated_evidence:
        integrated_html = _generate_integrated_evidence_report(
            txt_path=txt_path,
            html_summary=html_summary,
            allure_results=allure_results,
            report_dir=report_dir,
            report_base_name=report_base_name,
        )
    return txt_path, html_summary, allure_results, allure_html, integrated_html


def _generate_integrated_evidence_report(
    *,
    txt_path: Path,
    html_summary: Path,
    allure_results: Path,
    report_dir: Path,
    report_base_name: str,
) -> Path:
    from tools.generate_integrated_evidence_report import write_integrated_evidence_report

    integrated_html = report_dir / f"{report_base_name}_integrated.html"
    return write_integrated_evidence_report(
        txt_report=txt_path,
        legacy_html=html_summary,
        allure_dir=allure_results,
        output=integrated_html,
    )

def _current_allure_dir(config: Any, root: Path) -> Path:
    configured = getattr(config.option, "allure_report_dir", None)
    return Path(configured) if configured else root / "reports" / ".allure-results-current"


def _archive_allure_results(current_allure_dir: Path, report_dir: Path) -> Path:
    archived_allure_results = report_dir / f"allure-results_{REPORT_STATE.timestamp}"
    if current_allure_dir.exists() and current_allure_dir.resolve() != archived_allure_results.resolve():
        if archived_allure_results.exists():
            shutil.rmtree(archived_allure_results)
        shutil.copytree(current_allure_dir, archived_allure_results)
    else:
        archived_allure_results.mkdir(parents=True, exist_ok=True)
    return archived_allure_results


def _option_enabled(config: Any, option_name: str, env_name: str) -> bool:
    if bool(getattr(config.option, option_name, False)):
        return True
    return os.environ.get(env_name, "").strip().lower() in {"1", "true", "yes", "on"}


def _render_txt_report(env_config: Any) -> str:
    elapsed = time.perf_counter() - REPORT_STATE.started_at
    rendered_results = _rendered_report_results()
    summary = _summary_counts(rendered_results)

    lines = [
        f"Report generated on: {REPORT_STATE.timestamp}",
        f"Total test time: {_format_timedelta(elapsed)} ({elapsed:.2f} seconds)",
        f"Summary: {summary['passed']} Pass / {summary['failed']} Fail",
        f"UI URL: {env_config.base_url}",
        f"EMS Version: {getattr(env_config, 'ems_version', 'unknown')}",
        f"Auth Profile: {env_config.auth_profile}",
        f"RW Account: {env_config.readwrite_account.account_name} ({env_config.readwrite_account.username})",
        f"RO Account: {env_config.readonly_account.account_name} ({env_config.readonly_account.username})",
        f"NA Account: {env_config.noaccess_account.account_name} ({env_config.noaccess_account.username})",
        f"Node Name: {env_config.dut.device_name}",
        f"Node IP: {env_config.dut.device_ip}",
        f"Node Chassis: {env_config.dut.chassis}",
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


def _render_html_report(
    env_config: Any,
    *,
    txt_path: Path | None = None,
    allure_results: Path | None = None,
    allure_html: Path | None = None,
    integrated_html: Path | None = None,
) -> str:
    elapsed = time.perf_counter() - REPORT_STATE.started_at
    rendered_results = _rendered_report_results()
    summary = _summary_counts(rendered_results)
    failed_results = [result for result in rendered_results if result.outcome == "failed"]

    metadata = [
        ("Generated at", REPORT_STATE.timestamp),
        ("Total test time", f"{_format_timedelta(elapsed)} ({elapsed:.2f} seconds)"),
        ("UI URL", getattr(env_config, "base_url", "")),
        ("EMS Version", getattr(env_config, "ems_version", "unknown")),
        ("Auth Profile", getattr(env_config, "auth_profile", "")),
        (
            "RW Account",
            f"{env_config.readwrite_account.account_name} ({env_config.readwrite_account.username})",
        ),
        (
            "RO Account",
            f"{env_config.readonly_account.account_name} ({env_config.readonly_account.username})",
        ),
        (
            "NA Account",
            f"{env_config.noaccess_account.account_name} ({env_config.noaccess_account.username})",
        ),
        ("Node Name", env_config.dut.device_name),
        ("Node IP", env_config.dut.device_ip),
        ("Node Chassis", env_config.dut.chassis),
    ]
    metadata.extend(_split_label_value(line) for line in _card_version_lines(env_config))
    metadata.extend(_split_label_value(line) for line in _target_summary_lines(env_config))

    links = []
    if integrated_html:
        links.append(("Integrated evidence report (open this for case details)", integrated_html))
    if txt_path:
        links.append(("TXT legacy report", txt_path))
    if allure_results:
        links.append(("Allure raw results", allure_results))
    if allure_html:
        links.append(("Allure HTML report", allure_html / "index.html"))

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-Hant">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{escape(_report_base_name(env_config, REPORT_STATE.timestamp))}</title>",
            "<style>",
            _html_report_css(),
            "</style>",
            "</head>",
            "<body>",
            "<main>",
            '<section class="hero">',
            "<div>",
            "<p>EMS REST API summary report</p>",
            f"<h1>{escape(getattr(env_config, 'ems_version', 'unknown'))} / {escape(env_config.dut.device_name)}</h1>",
            f"<span>{escape(REPORT_STATE.timestamp)}</span>",
            "</div>",
            f'<strong class="status status-{escape(_overall_status(summary))}">{escape(_overall_status_label(summary))}</strong>',
            "</section>",
            '<section class="summary-grid">',
            _summary_card("Total", summary["total"], "testcases"),
            _summary_card("Pass", summary["passed"], "passed"),
            _summary_card("Fail", summary["failed"], "failed"),
            _summary_card("Skip", summary["skipped"], "skipped"),
            "</section>",
            _html_section("Test Environment", _metadata_table(metadata)),
            _html_section("Report Files", _links_list(links) if links else "<p>No additional report links.</p>"),
            _html_section("Failed Cases", _results_table(failed_results) if failed_results else "<p>No failed cases in this run.</p>"),
            _html_section("All Testcase Results", _results_table(rendered_results)),
            "</main>",
            "</body>",
            "</html>",
        ]
    )


def _rendered_report_results() -> list["AggregatedReportCase"]:
    return [*_aggregate_case_results(), *_aggregate_permission_summaries()]


def _summary_counts(rendered_results: list["AggregatedReportCase"]) -> dict[str, int]:
    return {
        "total": len(rendered_results),
        "passed": sum(1 for result in rendered_results if result.outcome == "passed"),
        "failed": sum(1 for result in rendered_results if result.outcome == "failed"),
        "skipped": sum(1 for result in rendered_results if result.outcome == "skipped"),
    }


def _split_label_value(line: str) -> tuple[str, str]:
    label, separator, value = line.partition(":")
    if not separator:
        return line, ""
    return label, value.strip()


def _summary_card(label: str, value: int, note: str) -> str:
    return (
        '<article class="summary-card">'
        f"<span>{escape(label)}</span>"
        f"<strong>{value}</strong>"
        f"<small>{escape(note)}</small>"
        "</article>"
    )


def _html_section(title: str, body: str) -> str:
    return f'<section class="panel"><h2>{escape(title)}</h2>{body}</section>'


def _metadata_table(rows: list[tuple[str, Any]]) -> str:
    body = "\n".join(
        f"<tr><th>{escape(str(label))}</th><td>{escape(str(value))}</td></tr>"
        for label, value in rows
    )
    return f'<table class="metadata"><tbody>{body}</tbody></table>'


def _links_list(links: list[tuple[str, Path]]) -> str:
    items = []
    for label, path in links:
        items.append(
            '<li>'
            f'<a href="{escape(_path_href(path))}">{escape(label)}</a>'
            f"<span>{escape(str(path))}</span>"
            "</li>"
        )
    return f'<ul class="links">{"".join(items)}</ul>'


def _results_table(results: list["AggregatedReportCase"]) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td>{escape(result.case_id)}</td>"
        f"<td>{escape(result.name)}</td>"
        f'<td><span class="pill pill-{escape(result.outcome)}">{escape(_outcome_name(result.outcome))}</span></td>'
        f"<td>{escape(_trim_seconds(result.duration))}s</td>"
        "</tr>"
        for result in results
    )
    return (
        '<table class="results">'
        "<thead><tr><th>Case ID</th><th>Testcase</th><th>Result</th><th>Duration</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )


def _path_href(path: Path) -> str:
    try:
        return path.resolve().as_uri()
    except ValueError:
        return str(path)


def _overall_status(summary: dict[str, int]) -> str:
    if summary["failed"]:
        return "failed"
    if summary["total"] and summary["passed"]:
        return "passed"
    return "skipped"


def _overall_status_label(summary: dict[str, int]) -> str:
    if summary["failed"]:
        return "FAIL"
    if summary["total"] and summary["passed"]:
        return "PASS"
    return "SKIP"


def _html_report_css() -> str:
    return """
:root {
  color-scheme: light;
  --bg: #f5f7fb;
  --panel: #ffffff;
  --text: #172033;
  --muted: #647086;
  --line: #dbe2ee;
  --pass: #138a54;
  --fail: #c93b3b;
  --skip: #7a6a21;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 14px/1.55 "Segoe UI", Arial, sans-serif;
}
main {
  width: min(1180px, calc(100% - 32px));
  margin: 24px auto 48px;
}
.hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 28px;
  background: #10233f;
  color: white;
  border-radius: 8px;
}
.hero p, .hero h1 { margin: 0; }
.hero p, .hero span { color: #c9d6e8; }
.hero h1 { font-size: 28px; font-weight: 650; letter-spacing: 0; }
.status {
  min-width: 92px;
  text-align: center;
  border-radius: 6px;
  padding: 10px 14px;
  background: rgba(255,255,255,.14);
}
.status-passed { color: #9df0c2; }
.status-failed { color: #ffb6b6; }
.status-skipped { color: #f1dd84; }
.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 16px 0;
}
.summary-card, .panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
}
.summary-card { padding: 18px; }
.summary-card span, .summary-card small { display: block; color: var(--muted); }
.summary-card strong { display: block; font-size: 28px; margin: 4px 0; }
.panel { margin-top: 16px; padding: 20px; overflow-x: auto; }
h2 { margin: 0 0 14px; font-size: 18px; letter-spacing: 0; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
th { color: var(--muted); font-weight: 600; }
.metadata th { width: 220px; }
.pill { display: inline-block; min-width: 54px; border-radius: 999px; padding: 3px 10px; text-align: center; font-weight: 650; }
.pill-passed { background: #ddf7e9; color: var(--pass); }
.pill-failed { background: #ffe2e2; color: var(--fail); }
.pill-skipped { background: #fbf0bf; color: var(--skip); }
.links { display: grid; gap: 8px; list-style: none; margin: 0; padding: 0; }
.links li { display: flex; gap: 12px; align-items: baseline; flex-wrap: wrap; }
.links span { color: var(--muted); font-size: 12px; }
a { color: #1b62b7; }
@media (max-width: 760px) {
  main { width: min(100% - 20px, 1180px); margin-top: 10px; }
  .hero { align-items: flex-start; flex-direction: column; padding: 20px; }
  .hero h1 { font-size: 22px; }
  .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .metadata th { width: auto; }
}
""".strip()


def _report_base_name(env_config: Any, timestamp: str) -> str:
    ems_version = getattr(env_config, "ems_version", "unknown")
    node = _node_data(env_config)
    chassis = env_config.dut.chassis
    controller = _controller_card_name(env_config, node)
    return f"Web_Ems_Rest_Api_{ems_version}_{chassis}_{controller}_report_{timestamp}"


def _node_data(env_config: Any) -> dict[str, Any]:
    node = getattr(env_config, "node_target", None)
    if isinstance(node, dict):
        return node
    if hasattr(env_config, "hardware"):
        return env_config.hardware.node_target(env_config.dut.node_key)
    return {}


def _controller_card_name(env_config: Any, node: dict[str, Any]) -> str:
    cards = _node_cards(node)
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
    node = _node_data(env_config)
    cards = _node_cards(node)
    configured: list[tuple[str, str, dict[str, Any]]] = []
    if hasattr(env_config, "hardware"):
        configured = env_config.hardware.report_card_entries(env_config.dut.node_key, node)
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


def _node_cards(node: dict[str, Any]) -> dict[str, Any]:
    cards = node.get("cards", {})
    return cards if isinstance(cards, dict) else {}


def _target_summary_lines(env_config: Any) -> list[str]:
    if not hasattr(env_config, "hardware"):
        return []
    target = env_config.hardware.node_target(env_config.dut.node_key)
    if not target:
        return []

    lines = [
        "Test Target Source: YAML",
        "Card/FW Target Note: values above are YAML targets; live EMS mismatches are validated by inventory tests.",
    ]
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
    allure = _allure_executable()
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


def _allure_executable() -> str | None:
    configured = shutil.which("allure")
    if configured:
        return configured
    local_wrapper = Path(__file__).resolve().parents[1] / ".codex-tools" / "bin" / "allure.cmd"
    return str(local_wrapper) if local_wrapper.exists() else None


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


@dataclass
class SummaryMember:
    nodeid: str
    outcome: str
    duration: float
    case_ids: list[str]
    case_names: list[str]


@dataclass
class PermissionSummaryDetail:
    case_id: str
    role: str
    name: str
    outcome: str
    duration: float
    members: list[SummaryMember]


def _aggregate_case_results() -> list[AggregatedReportCase]:
    case_names = _case_name_by_id()
    report_order = _case_order()
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
                name=case_names.get(case_id, fallback_names.get(case_id, case_id)),
                outcome=_combine_outcomes(result.outcome for result in results),
                duration=max((result.duration for result in results), default=0.0),
            )
        )
    aggregates.sort(key=lambda item: (report_order.get(item.case_id, 10**9), item.case_id, item.name))
    return aggregates


def _aggregate_permission_summaries() -> list[AggregatedReportCase]:
    summaries: list[AggregatedReportCase] = []
    for case_id, role, name in _permission_summary_specs():
        detail = permission_summary_detail(role)
        if detail is None:
            continue
        summaries.append(
            AggregatedReportCase(
                case_id=detail.case_id,
                name=detail.name,
                outcome=detail.outcome,
                duration=detail.duration,
            )
        )
    return summaries


def permission_summary_detail(role: str) -> PermissionSummaryDetail | None:
    spec = next((item for item in _permission_summary_specs() if item[1] == role), None)
    if spec is None:
        return None
    case_id, _, name = spec
    results = [result for result in REPORT_STATE.results if _permission_role_for(result.nodeid) == role]
    if not results:
        return None
    members = [
        SummaryMember(
            nodeid=result.nodeid,
            outcome=result.outcome,
            duration=result.duration,
            case_ids=[registration.case_id for registration in result.case_ids if registration.case_id],
            case_names=[registration.name for registration in result.case_ids if registration.name],
        )
        for result in results
    ]
    return PermissionSummaryDetail(
        case_id=case_id,
        role=role,
        name=name,
        outcome=_combine_permission_outcomes(result.outcome for result in results),
        duration=sum(result.duration for result in results),
        members=members,
    )


def permission_summary_breakdown(role: str) -> dict[str, Any]:
    detail = permission_summary_detail(role)
    if detail is None:
        return {
            "case_id": None,
            "role": role,
            "name": None,
            "outcome": "skipped",
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "failed_items": [],
            "members": [],
        }

    failed_items = []
    members = []
    for member in detail.members:
        item = {
            "nodeid": member.nodeid,
            "outcome": member.outcome,
            "duration": member.duration,
            "case_ids": member.case_ids,
            "case_names": member.case_names,
        }
        members.append(item)
        if member.outcome == "failed":
            failed_items.append(item)

    return {
        "case_id": detail.case_id,
        "role": detail.role,
        "name": detail.name,
        "outcome": detail.outcome,
        "total": len(detail.members),
        "passed": sum(1 for member in detail.members if member.outcome == "passed"),
        "failed": sum(1 for member in detail.members if member.outcome == "failed"),
        "skipped": sum(1 for member in detail.members if member.outcome == "skipped"),
        "failed_items": failed_items,
        "members": members,
    }


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


def _permission_summary_specs() -> tuple[tuple[str, str, str], ...]:
    return permission_summary_specs()


def _case_name_by_id() -> dict[str, str]:
    return case_name_by_id()


def _case_order() -> dict[str, int]:
    return case_order()


def _safe_path_part(value: str) -> str:
    for char in '<>:"/\\|?*':
        value = value.replace(char, "_")
    return value.strip() or "unknown"
