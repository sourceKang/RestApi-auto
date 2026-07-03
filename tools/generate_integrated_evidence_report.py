from __future__ import annotations

import argparse
import html
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CASE_RE = re.compile(r"^\[(EMS1-\d+)\]\[(.*?)\] Result (\w+) \((.*?)\)")


@dataclass
class TxtCase:
    case_id: str
    name: str
    result: str
    duration: str


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_txt_report(path: Path) -> tuple[dict[str, str], list[TxtCase]]:
    metadata: dict[str, str] = {}
    cases: list[TxtCase] = []
    for line in read_text(path).splitlines():
        if ":" in line and not line.startswith("["):
            key, value = line.split(":", 1)
            key = key.strip()
            if key in {
                "Report generated on",
                "Total test time",
                "Summary",
                "UI URL",
                "EMS Version",
                "Auth Profile",
                "Node Name",
                "Node IP",
                "Node Chassis",
                "ONT Target",
                "GE Target",
            }:
                metadata[key] = value.strip()
        match = CASE_RE.match(line)
        if match:
            cases.append(TxtCase(*match.groups()))
    return metadata, cases


def load_allure_results(allure_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in sorted(allure_dir.glob("*-result.json")):
        data = json.loads(read_text(path))
        data["_source_file"] = path.name
        results.append(data)
    return results


def result_case_ids(result: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for link in result.get("links") or []:
        if link.get("type") == "tms":
            value = link.get("name") or link.get("url")
            if value:
                ids.append(str(value))
    return ids


def result_name_case_ids(result: dict[str, Any]) -> list[str]:
    return re.findall(r"\[(EMS1-\d+)\]", str(result.get("name") or ""))


def case_metadata_records(result: dict[str, Any], allure_dir: Path) -> list[tuple[str, str, dict[str, Any]]]:
    records: list[tuple[str, str, dict[str, Any]]] = []
    for attachment in result.get("attachments") or []:
        if str(attachment.get("name") or "").lower() != "case metadata":
            continue
        source = attachment.get("source")
        if not source:
            continue
        path = allure_dir / str(source)
        if not path.exists():
            continue
        try:
            data = json.loads(read_text(path))
        except Exception:
            continue
        case_name = str(data.get("name") or "")
        for case_id in data.get("case_ids") or []:
            records.append((str(case_id), case_name, attachment))
    return records


def step_matches_case_name(step: dict[str, Any], case_name: str) -> bool:
    name = str(step.get("name") or "")
    rules = {
        "test_post_remote_console": lambda value: value.startswith("POST /remote/"),
        "test_get_active_alarm": lambda value: value == "GET /activealarm",
        "test_get_active_alarm_by_id": lambda value: value.startswith("GET /activealarm/"),
        "test_patch_active_alarm_by_id": lambda value: value.startswith("PATCH /activealarm/"),
        "test_delete_active_alarm_by_id": lambda value: value.startswith("DELETE /activealarm/"),
        "test_get_history_alarm": lambda value: value == "GET /historyalarm",
        "test_get_history_alarm_by_id": lambda value: value.startswith("GET /historyalarm/"),
        "test_delete_history_alarm_by_id": lambda value: value.startswith("DELETE /historyalarm/"),
    }
    matcher = rules.get(case_name)
    return matcher(name) if matcher else True


def clone_result_for_case(
    result: dict[str, Any], case_id: str, case_name: str, metadata_attachment: dict[str, Any]
) -> dict[str, Any]:
    clone = dict(result)
    clone["name"] = f"[{case_id}][{case_name}]" if case_name else result.get("name")
    clone["links"] = [{"type": "tms", "url": case_id, "name": case_id}]
    clone["attachments"] = [metadata_attachment]
    matched_steps = [step for step in result.get("steps") or [] if step_matches_case_name(step, case_name)]
    clone["steps"] = matched_steps or list(result.get("steps") or [])
    clone["_split_from"] = result.get("_source_file")
    return clone


def index_results_by_case(results: list[dict[str, Any]], allure_dir: Path) -> dict[str, list[dict[str, Any]]]:
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        metadata_records = case_metadata_records(result, allure_dir)
        if len(metadata_records) > 1:
            for case_id, case_name, metadata_attachment in metadata_records:
                by_case[case_id].append(clone_result_for_case(result, case_id, case_name, metadata_attachment))
            continue
        case_ids = result_name_case_ids(result) or result_case_ids(result)
        for case_id in case_ids:
            by_case[case_id].append(result)
    return by_case


def duration_ms(node: dict[str, Any]) -> str:
    start = node.get("start")
    stop = node.get("stop")
    if isinstance(start, int) and isinstance(stop, int) and stop >= start:
        elapsed = stop - start
        if elapsed >= 1000:
            return f"{elapsed / 1000:.2f}s"
        return f"{elapsed}ms"
    return "-"


def badge(status: str) -> str:
    lowered = (status or "").lower()
    cls = {
        "pass": "pass",
        "passed": "pass",
        "fail": "fail",
        "failed": "fail",
        "broken": "fail",
        "skip": "skip",
        "skipped": "skip",
    }.get(lowered, "info")
    label = status or "unknown"
    return f'<span class="badge {cls}">{esc(label)}</span>'


def attachment_category(name: str, atype: str) -> str:
    lowered = f"{name} {atype}".lower()
    if "request" in lowered or "payload" in lowered:
        return "Request / payload"
    if "response" in lowered:
        return "EMS response"
    if "cli" in lowered or "command" in lowered or "token" in lowered:
        return "CLI / verification"
    if "contract" in lowered or "swagger" in lowered or "yaml" in lowered:
        return "Contract verification"
    if "failure" in lowered or "trace" in lowered:
        return "Failure detail"
    return "Attachment"


def load_attachment_preview(allure_dir: Path, source: str, limit: int = 6000) -> str:
    path = allure_dir / source
    if not path.exists():
        return "(missing attachment file)"
    text = read_text(path)
    stripped = text.strip()
    if source.endswith(".json"):
        try:
            parsed = json.loads(stripped)
            stripped = json.dumps(parsed, indent=2, ensure_ascii=False)
        except Exception:
            pass
    if len(stripped) > limit:
        stripped = stripped[:limit] + "\n... (truncated in integrated report; open raw attachment for full content)"
    return stripped


def render_attachment(allure_rel: str, allure_dir: Path, attachment: dict[str, Any]) -> str:
    name = str(attachment.get("name") or "attachment")
    source = str(attachment.get("source") or "")
    atype = str(attachment.get("type") or "")
    category = attachment_category(name, atype)
    preview = load_attachment_preview(allure_dir, source) if source else "(missing attachment source)"
    href = f"{allure_rel}/{html.escape(source, quote=True)}" if source else "#"
    return f"""
<div class="evidence-box">
  <h4>{esc(category)} <span>{esc(name)}</span></h4>
  <pre>{esc(preview)}</pre>
  <a class="raw" href="{href}">open raw attachment</a>
</div>"""


def render_step(step: dict[str, Any], allure_rel: str, allure_dir: Path, depth: int = 0) -> str:
    attachments = step.get("attachments") or []
    child_steps = step.get("steps") or []
    attachment_html = "".join(render_attachment(allure_rel, allure_dir, item) for item in attachments)
    children_html = "".join(render_step(child, allure_rel, allure_dir, depth + 1) for child in child_steps)
    indent_class = " nested" if depth else ""
    if attachment_html:
        attachment_html = f'<div class="evidence-grid">{attachment_html}</div>'
    return f"""
<div class="step-block{indent_class}">
  <h3>{esc(step.get("name"))} {badge(step.get("status") or "")}<span>{duration_ms(step)}</span></h3>
  {attachment_html}
  {children_html}
</div>"""


def render_result(result: dict[str, Any], allure_rel: str, allure_dir: Path) -> str:
    title = result.get("name") or result.get("fullName") or result.get("uuid")
    full_name = result.get("fullName") or "-"
    status = result.get("status") or "unknown"
    status_details = result.get("statusDetails") or {}
    steps = result.get("steps") or []
    attachments = result.get("attachments") or []
    labels = result.get("labels") or []
    tags = [item.get("value") for item in labels if item.get("name") == "tag"]
    step_names = [step.get("name") for step in steps[:8] if step.get("name")]
    verification = "; ".join(step_names) if step_names else "No step-level verification recorded."
    if len(steps) > 8:
        verification += f"; ... {len(steps) - 8} more step(s)"
    attachment_html = "".join(render_attachment(allure_rel, allure_dir, item) for item in attachments)
    step_html = "".join(render_step(step, allure_rel, allure_dir) for step in steps)
    detail_html = ""
    if status_details:
        detail_html = f"""
<div class="evidence-box full">
  <h4>Status detail</h4>
  <pre>{esc(json.dumps(status_details, indent=2, ensure_ascii=False))}</pre>
</div>"""
    if attachment_html:
        attachment_html = f'<div class="evidence-grid">{attachment_html}</div>'
    return f"""
<details class="allure-result">
  <summary>
    <div>
      <div class="test-title">{esc(title)}</div>
      <div class="test-meta">{esc(full_name)}</div>
      <div class="test-note">Verification: {esc(verification)}</div>
      <div class="test-note">Tags: {esc(", ".join(str(t) for t in tags) if tags else "-")}</div>
    </div>
    {badge(status)}
    <span>{duration_ms(result)}</span>
  </summary>
  <div class="detail">
    {detail_html}
    {attachment_html}
    {step_html if step_html else '<div class="missing">No request/response/CLI step attachments were recorded for this result.</div>'}
  </div>
</details>"""


def render_case(case: TxtCase, results: list[dict[str, Any]], allure_rel: str, allure_dir: Path) -> str:
    status_counts: dict[str, int] = defaultdict(int)
    for result in results:
        status_counts[str(result.get("status") or "unknown")] += 1
    status_summary = ", ".join(f"{key}:{value}" for key, value in sorted(status_counts.items())) or "no allure result"
    result_html = "".join(render_result(result, allure_rel, allure_dir) for result in results)
    if not result_html:
        result_html = '<div class="missing">No matching Allure result found for this TestLink case.</div>'
    return f"""
<details class="case-row">
  <summary>
    <div>
      <div class="test-title">{esc(case.case_id)} / {esc(case.name)}</div>
      <div class="test-meta">TestLink result: {esc(case.result)} ({esc(case.duration)})</div>
      <div class="test-note">Allure result records: {len(results)}; {esc(status_summary)}</div>
    </div>
    {badge(case.result)}
    <span>{esc(case.duration)}</span>
  </summary>
  <div class="detail">
    {result_html}
  </div>
</details>"""


def render_photo_comparison() -> str:
    rows = [
        ("RM 255983 / EMS1-7216", 'NNI config create min payload returned % Invalid command "y"', "Fixed", "test_nni_config_min_create_readwrite / EMS1-7123 Pass", "#EMS1-7123"),
        ("RM 255982 / EMS1-7217", "NNI clear sent duplicate confirmation y", "Fixed", "test_nni_config_clear_readwrite / EMS1-7122 Pass", "#EMS1-7122"),
        ("RM 255967 / EMS1-7218", 'GE config DELETE returned % Invalid command "y"', "Fixed", "test_ge_config_clear_readwrite / EMS1-7118 Pass", "#EMS1-7118"),
        ("RM 255916 / EMS1-7120", "GE LLDP System TLV returned Success but was not applied", "Fixed", "test_ge_config_max_create_readwrite / EMS1-7120 Pass", "#EMS1-7120"),
        ("RM 255915 / EMS1-7120", "GE staticfilter_ipmacbinding returned Success but was not applied", "Fixed", "EMS1-7120 Pass; static_ip_filtering probe Pass", "#EMS1-7120"),
        ("RM 255908 / EMS1-7120", "GE snooping_ipmacbinding returned Success but was not applied", "Fixed", "EMS1-7120 Pass; DHCP snooping CLI token is visible", "#EMS1-7120"),
        ("RM 255709 / EMS1-7120", "YAML GePortInfo warning threshold keys", "Partial", "Original 10 GePortInfo warning-key diff is gone, but DDMI still rejects bias_warn_high", "#EMS1-7120"),
        ("RM 255425 / EMS1-6666", "ontservice Per-GEM Port VLAN Translation Config", "Partial", "EMS1-6666 functional case passed; Live Swagger OntServiceInfo.qoss still differs", "#EMS1-6666"),
    ]
    body = []
    for rm, issue, status, evidence, href in rows:
        body.append(
            f"<tr><td>{esc(rm)}</td><td>{esc(issue)}</td><td>{badge(status)}</td>"
            f'<td>{esc(evidence)}<br><a href="{href}">jump to case evidence</a></td></tr>'
        )
    return "".join(body)


def render_failures(cases: list[TxtCase]) -> str:
    rows = []
    for case in cases:
        if case.result.lower() == "fail":
            rows.append(
                f'<tr><td>{esc(case.case_id)}</td><td>{esc(case.name)}</td>'
                f"<td>{badge(case.result)}</td><td>{esc(case.duration)}</td>"
                f'<td><a href="#{esc(case.case_id)}">open detail</a></td></tr>'
            )
    return "".join(rows) or '<tr><td colspan="5">No failed TestLink cases.</td></tr>'


def render_report(
    metadata: dict[str, str],
    cases: list[TxtCase],
    by_case: dict[str, list[dict[str, Any]]],
    allure_dir: Path,
    txt_rel: str,
    legacy_html_rel: str,
    stdout_rel: str | None,
) -> str:
    allure_rel = html.escape(allure_dir.name, quote=True)
    pass_count = sum(1 for case in cases if case.result.lower() == "pass")
    fail_count = sum(1 for case in cases if case.result.lower() == "fail")
    report_title = f"{metadata.get('EMS Version', 'EMS')} / {metadata.get('Node Name', 'Node')} Integrated Evidence Report"
    case_html = "\n".join(
        f'<section id="{esc(case.case_id)}">{render_case(case, by_case.get(case.case_id, []), allure_rel, allure_dir)}</section>'
        for case in cases
    )
    stdout_link = (
        f'<a class="link-card" href="{esc(stdout_rel)}"><strong>pytest stdout log</strong><span>Complete pytest output</span></a>'
        if stdout_rel
        else ""
    )
    photo_issue_section = ""
    if os.environ.get("EMS_INCLUDE_PHOTO_ISSUE_COMPARISON", "").strip().lower() in {"1", "true", "yes", "on"}:
        photo_issue_section = f"""
  <section class="panel">
    <div class="panel-title"><h2>Photo Issue Comparison</h2><span>Mapped by screenshot title, live result, and evidence</span></div>
    <div class="table-wrap"><table><thead><tr><th>RM / RelTC</th><th>Issue Summary</th><th>Status</th><th>Evidence</th></tr></thead><tbody>{render_photo_comparison()}</tbody></table></div>
  </section>
"""
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(report_title)}</title>
<style>
:root{{--bg:#f5f7fb;--panel:#fff;--ink:#172033;--muted:#64748b;--line:#d9e2ef;--blue:#1d4ed8;--green:#15803d;--orange:#b45309;--red:#b91c1c;--code:#0f172a;--codeink:#e5e7eb}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:"Segoe UI","Microsoft JhengHei",Arial,sans-serif;line-height:1.5}}header{{padding:28px 36px 22px;color:#fff;background:#111827;border-bottom:4px solid #2563eb}}h1{{margin:0 0 8px;font-size:28px;letter-spacing:0}}header p{{margin:0;color:#cbd5e1;font-size:14px}}main{{max-width:1520px;margin:0 auto;padding:24px 28px 44px}}.cards{{display:grid;grid-template-columns:repeat(4,minmax(180px,1fr));gap:14px;margin-bottom:20px}}.card,.panel{{background:var(--panel);border:1px solid var(--line);border-radius:8px;box-shadow:0 1px 2px rgba(15,23,42,.05)}}.card{{padding:16px}}.label{{color:var(--muted);font-size:12px;font-weight:700;text-transform:uppercase}}.value{{margin-top:7px;font-size:22px;font-weight:800}}.note,.test-meta,.test-note{{margin-top:4px;color:var(--muted);font-size:13px}}.panel{{margin-bottom:20px;overflow:hidden}}.panel-title{{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:15px 18px;border-bottom:1px solid var(--line);background:#f8fafc}}h2{{margin:0;font-size:18px}}.panel-title span{{color:var(--muted);font-size:13px}}table{{width:100%;border-collapse:collapse;font-size:14px}}th{{padding:10px 12px;color:#475569;background:#f8fafc;border-bottom:1px solid var(--line);text-align:left;font-size:12px;text-transform:uppercase;white-space:nowrap}}td{{padding:11px 12px;border-bottom:1px solid var(--line);vertical-align:top}}tr:last-child td{{border-bottom:0}}.badge{{display:inline-flex;min-width:58px;justify-content:center;border-radius:999px;padding:4px 9px;font-size:12px;font-weight:700;white-space:nowrap}}.pass{{color:var(--green);background:#dcfce7}}.fail{{color:var(--red);background:#fee2e2}}.skip{{color:#475569;background:#e2e8f0}}.partial{{color:var(--orange);background:#ffedd5}}.info{{color:var(--blue);background:#dbeafe}}code{{padding:2px 5px;border-radius:4px;background:#eef2ff;color:#1e3a8a;font-family:Consolas,"Courier New",monospace;font-size:12px}}a{{color:var(--blue);text-decoration:none}}a:hover{{text-decoration:underline}}.links{{display:grid;grid-template-columns:repeat(3,minmax(190px,1fr));gap:12px;padding:16px}}.link-card{{display:block;border:1px solid var(--line);border-radius:8px;padding:12px;background:#fff;color:var(--ink)}}.link-card strong{{display:block;margin-bottom:4px;color:var(--blue)}}.link-card span{{color:var(--muted);font-size:12px}}summary{{display:grid;grid-template-columns:1fr 95px 105px;gap:12px;align-items:center;padding:14px 18px;cursor:pointer;list-style:none}}summary::-webkit-details-marker{{display:none}}summary:hover{{background:#f8fafc}}.test-title{{font-weight:800;word-break:break-word}}.detail{{padding:0 18px 18px;background:#fbfdff}}.case-row,.allure-result{{border-top:1px solid var(--line);background:#fff}}.case-row:first-child{{border-top:0}}.allure-result{{border:1px solid var(--line);border-radius:8px;margin-top:12px;overflow:hidden}}.step-block{{margin-top:14px;border:1px solid var(--line);border-radius:8px;background:#fff;overflow:hidden}}.step-block.nested{{margin-left:18px}}.step-block h3{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0;padding:10px 12px;border-bottom:1px solid var(--line);background:#f8fafc;font-size:14px}}.evidence-grid{{display:grid;grid-template-columns:repeat(2,minmax(320px,1fr));gap:14px;padding:12px}}.evidence-box{{border:1px solid var(--line);border-radius:8px;background:#fff;overflow:hidden;min-width:0}}.evidence-box.full{{margin-top:14px}}.evidence-box h4{{display:flex;justify-content:space-between;gap:12px;margin:0;padding:10px 12px;border-bottom:1px solid var(--line);background:#f8fafc;font-size:14px}}.evidence-box h4 span{{font-weight:400;color:var(--muted)}}pre{{margin:0;max-height:420px;overflow:auto;padding:12px;background:var(--code);color:var(--codeink);font-family:Consolas,"Courier New",monospace;font-size:12px;white-space:pre-wrap;word-break:break-word}}.raw{{display:block;padding:8px 12px;border-top:1px solid var(--line);font-size:12px;background:#f8fafc}}.callout{{margin:0 0 20px;border-left:4px solid var(--orange);background:#fff7ed;color:#7c2d12;padding:12px 14px;border-radius:6px;font-size:13px}}.missing{{padding:14px;color:var(--red)}}.case-row>summary{{background:#fff}}.case-row[open]>summary{{background:#eef6ff;border-left:4px solid #2563eb;padding-left:14px}}.case-row>.detail{{padding:16px 18px 20px;background:#f7fbff;border-top:1px solid #bfd7f4}}.allure-result{{border-color:#b8c9de;background:#fff}}.allure-result>summary{{background:#fffaf0;border-left:4px solid #b45309;padding-left:14px}}.allure-result[open]>summary{{background:#fffbeb;border-bottom:1px solid #f1d7a8}}.allure-result>.detail{{background:#fffef8;border-top:0;padding-top:12px}}.step-block{{border-color:#c9d4e5;background:#fff}}.step-block h3{{border-bottom-color:#c9d4e5;background:#eef2f7}}.evidence-grid{{background:#f8fafc}}.evidence-box{{border-color:#cbd5e1;background:#fff}}.evidence-box h4{{border-bottom-color:#cbd5e1;background:#ecfdf5}}.raw{{border-top-color:#cbd5e1;background:#f1f5f9}}@media(max-width:1100px){{main{{padding:18px}}header{{padding:22px}}.cards,.links,.evidence-grid{{grid-template-columns:1fr}}summary{{grid-template-columns:1fr}}.table-wrap{{overflow-x:auto}}}}
</style>
</head>
<body>
<header>
  <h1>{esc(report_title)}</h1>
  <p>Single-page view of TestLink cases, request payloads, EMS responses, CLI/token verification, failure details, and raw Allure attachments.</p>
</header>
<main>
  <section class="cards">
    <div class="card"><div class="label">EMS Version</div><div class="value">b7</div><div class="note">{esc(metadata.get("EMS Version", "03.00.11 (AAVV.221) b7"))}</div></div>
    <div class="card"><div class="label">Node</div><div class="value">Node3</div><div class="note">{esc(metadata.get("Node Name", "Taiwan_NeoX-03_169.58"))} / {esc(metadata.get("Node Chassis", "NXC400"))}</div></div>
    <div class="card"><div class="label">pytest raw</div><div class="value">422 / 28 / 5</div><div class="note">passed / failed / skipped; failed includes Allure 26 failed + 2 broken</div></div>
    <div class="card"><div class="label">TestLink report</div><div class="value">{pass_count} / {fail_count}</div><div class="note">Pass / Fail, {len(cases)} cases</div></div>
  </section>

  <section class="callout">HTML report and Allure raw evidence are merged below. Open any TestLink case to see matching Allure result records, request payloads, EMS responses, verification steps, CLI/contract evidence, status details, and raw attachment links.</section>

  <section class="panel">
    <div class="panel-title"><h2>Report Files</h2><span>{esc(metadata.get("Total test time", ""))} / {esc(metadata.get("Summary", ""))}</span></div>
    <div class="links">
      <a class="link-card" href="#all-case-evidence"><strong>Merged case evidence</strong><span>This page: all {len(cases)} TestLink cases with Allure evidence</span></a>
      <a class="link-card" href="{esc(txt_rel)}"><strong>TXT report</strong><span>Original TestLink registered summary</span></a>
      {stdout_link}
    </div>
  </section>

{photo_issue_section}

  <section class="panel">
    <div class="panel-title"><h2>8 Failures in txt Report</h2><span>Jump directly to merged case evidence</span></div>
    <div class="table-wrap"><table><thead><tr><th>Case</th><th>Test</th><th>Result</th><th>Duration</th><th>Detail</th></tr></thead><tbody>{render_failures(cases)}</tbody></table></div>
  </section>

  <section class="panel" id="all-case-evidence">
    <div class="panel-title"><h2>All TestLink Case Evidence</h2><span>{len(cases)} cases; each expands into payload / response / verification / result details</span></div>
    {case_html}
  </section>

  <section class="panel">
    <div class="panel-title"><h2>Supporting Raw Folder</h2><span>Available for full attachment download when a preview is truncated</span></div>
    <div class="links">
      <a class="link-card" href="{esc(legacy_html_rel)}"><strong>Original HTML summary</strong><span>Legacy TestLink-style report</span></a>
      <a class="link-card" href="{allure_rel}/"><strong>Allure raw folder</strong><span>Raw JSON/TXT attachments referenced above</span></a>
      {stdout_link}
    </div>
  </section>
</main>
</body>
</html>
"""


def _relative_or_name(path: Path | None, base: Path) -> str | None:
    if path is None:
        return None
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def write_integrated_evidence_report(
    *,
    txt_report: Path,
    legacy_html: Path,
    allure_dir: Path,
    output: Path,
    stdout_log: Path | None = None,
) -> Path:
    metadata, cases = parse_txt_report(txt_report)
    results = load_allure_results(allure_dir)
    by_case = index_results_by_case(results, allure_dir)
    base = output.parent
    html_text = render_report(
        metadata,
        cases,
        by_case,
        allure_dir,
        _relative_or_name(txt_report, base) or txt_report.as_posix(),
        _relative_or_name(legacy_html, base) or legacy_html.as_posix(),
        _relative_or_name(stdout_log, base),
    )
    output.write_text(html_text, encoding="utf-8")
    return output

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--txt-report", required=True, type=Path)
    parser.add_argument("--legacy-html", required=True, type=Path)
    parser.add_argument("--allure-dir", required=True, type=Path)
    parser.add_argument("--stdout-log", required=False, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    output = write_integrated_evidence_report(
        txt_report=args.txt_report,
        legacy_html=args.legacy_html,
        allure_dir=args.allure_dir,
        stdout_log=args.stdout_log,
        output=args.output,
    )
    metadata, cases = parse_txt_report(args.txt_report)
    results = load_allure_results(args.allure_dir)
    print(f"Wrote {output} with {len(cases)} cases and {len(results)} Allure result records.")


if __name__ == "__main__":
    main()
