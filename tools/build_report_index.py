"""Build a lookup index over historical pytest reports under reports/.

The index only reads txt reports, multi_node summary.json files and, for the
comparisons it renders, the Allure *-result.json files of the two compared
runs. It never moves, rewrites or deletes existing report files; the only
files it writes are inside the index output directory.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.case_step_diff import (  # noqa: E402
    IPV4_RE,
    STYLE as CASE_STYLE,
    load_case_results,
    pair_results,
    render_case_comparison,
    step_entries,
)
from tools.generate_integrated_evidence_report import TxtCase, parse_txt_report  # noqa: E402
from utils.redaction import redact_text  # noqa: E402


DEFAULT_REPORTS_ROOT = PROJECT_ROOT / "reports"
INDEX_DIRNAME = "_index"
CASES_DIRNAME = "cases"
FORMAL_RUNS_FILENAME = "formal_runs.yaml"
# A run counts as full when it covers at least FULL_RUN_RATIO of the largest
# run for the same node in the same build, and at least LINE_RUN_RATIO of the
# largest run in the version line (case counts grow from build to build, so a
# build that only has debug runs should not get a "full" run).
FULL_RUN_RATIO = 0.8
LINE_RUN_RATIO = 0.5

VERSION_DIR_RE = re.compile(
    r"^(?P<number>\d+\.\d+\.\d+)\s*\((?P<project>[^)]+)\)\s*(?P<build>[A-Za-z]+\d+)?(?:_(?P<target>.+))?$"
)
TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}")
RUN_ID_RE = re.compile(r"_report_(?P<run_id>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(?:_.+)?)$")
NODE_LABEL_RE = re.compile(r"^(NODE\d+)(?:_(.+))?$")
PASS = "Pass"
CASE_PAGE_CATEGORIES = ("regression", "fixed", "still_failing")
FAIL = "Fail"


@dataclass(frozen=True)
class BuildInfo:
    dir_name: str
    number: str
    project: str
    build: str
    target: str

    @property
    def version_line(self) -> str:
        return self.number

    def sort_key(self) -> tuple[Any, ...]:
        number = tuple(int(part) for part in self.number.split("."))
        match = re.match(r"([A-Za-z]+)(\d+)", self.build)
        if match:
            # Engineering builds (b1..bN) come before the release (C0, C1...).
            prefix_rank = {"b": 0, "c": 1}.get(match.group(1).lower(), 2)
            build_rank = (prefix_rank, int(match.group(2)))
        else:
            build_rank = (3, 0)
        return (number, build_rank, self.target)


@dataclass
class RunRecord:
    build: BuildInfo
    txt_path: Path
    run_id: str
    run_time: str
    node_ip: str
    node_name: str
    node_label: str
    tag: str
    metadata: dict[str, str]
    cases: list[TxtCase]
    html_path: Path | None = None
    integrated_path: Path | None = None
    allure_dir: Path | None = None
    multi_node_summary: Path | None = None
    pytest_summary: str = ""
    node: str = ""
    kind: str = ""
    formal: str = ""
    formal_note: str = ""

    @property
    def pass_count(self) -> int:
        return sum(1 for case in self.cases if case.result == PASS)

    @property
    def fail_count(self) -> int:
        return sum(1 for case in self.cases if case.result == FAIL)

    @property
    def key(self) -> str:
        return f"{self.build.dir_name}/{self.run_id}"


@dataclass
class FormalEntry:
    run: str
    final: bool = False
    note: str = ""


@dataclass
class ReportIndex:
    reports_root: Path
    runs: list[RunRecord]
    formal: dict[tuple[str, str], list[FormalEntry]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    # Directory the HTML pages are written to; links are made relative to it.
    link_base: Path | None = None

    def link_dir(self) -> Path:
        return self.link_base or self.reports_root / INDEX_DIRNAME

    def builds(self) -> list[BuildInfo]:
        unique = {run.build.dir_name: run.build for run in self.runs}
        return sorted(unique.values(), key=BuildInfo.sort_key)

    def nodes(self) -> list[str]:
        return sorted({run.node for run in self.runs if run.kind != "empty"}, key=_node_sort_key)

    def runs_for(self, build_dir: str, node: str) -> list[RunRecord]:
        return [run for run in self.runs if run.build.dir_name == build_dir and run.node == node]

    def reference_run(self, build_dir: str, node: str) -> RunRecord | None:
        """Formal run marked final (or last listed); otherwise the latest full run."""
        runs = self.runs_for(build_dir, node)
        formal = [run for run in runs if run.formal]
        if formal:
            final = [run for run in formal if run.formal == "final"]
            return (final or formal)[-1]
        full = [run for run in runs if run.kind == "full"]
        return max(full, key=lambda run: run.run_time) if full else None

    def find_run(self, selector: str, node: str | None) -> RunRecord:
        build_dir, _, run_id = selector.partition("/")
        if run_id:
            matches = [run for run in self.runs if run.build.dir_name == build_dir and run.run_id == run_id]
            if node:
                matches = [run for run in matches if run.node == node]
            if not matches:
                raise ValueError(f"run not found: {selector}" + (f" for {node}" if node else ""))
            if len(matches) > 1:
                nodes = ", ".join(sorted(run.node for run in matches))
                raise ValueError(f"{selector} matches runs of several nodes ({nodes}); add --node")
            return matches[0]
        if not node:
            raise ValueError(f"--node is required when selecting a build without a run id: {selector}")
        run = self.reference_run(build_dir, node)
        if run is None:
            raise ValueError(f"no formal or full run for {node} in {build_dir}")
        return run


def _node_sort_key(node: str) -> tuple[int, int, str]:
    match = re.match(r"NODE(\d+)$", node)
    return (0, int(match.group(1)), node) if match else (1, 0, node)


def parse_build_dir(name: str) -> BuildInfo | None:
    match = VERSION_DIR_RE.match(name)
    if not match:
        return None
    return BuildInfo(
        dir_name=name,
        number=match.group("number"),
        project=match.group("project").strip(),
        build=match.group("build") or "",
        target=match.group("target") or "",
    )


def _run_identity(txt_path: Path, metadata: dict[str, str]) -> tuple[str, str, str, str]:
    """Return run_id, run_time, NODE label and extra tag for a txt report."""
    stem = txt_path.stem
    match = RUN_ID_RE.search(stem)
    run_id = match.group("run_id") if match else stem
    generated = metadata.get("Report generated on", "")
    time_match = TIMESTAMP_RE.search(generated) or TIMESTAMP_RE.search(run_id) or TIMESTAMP_RE.search(stem)
    run_time = time_match.group(0) if time_match else ""
    suffix = run_id[len(run_time) + 1 :] if match and run_id.startswith(run_time) else ""
    label_match = NODE_LABEL_RE.match(suffix)
    if label_match:
        return run_id, run_time, label_match.group(1), label_match.group(2) or ""
    return run_id, run_time, "", suffix


def _companion(directory: Path, stem: str, base_stem: str, suffix: str) -> Path | None:
    for candidate_stem in dict.fromkeys((stem, base_stem)):
        candidate = directory / f"{candidate_stem}{suffix}"
        if candidate.exists():
            return candidate
    return None


def _allure_dir(directory: Path, run_id: str, run_time: str, node_label: str) -> Path | None:
    for name in dict.fromkeys(
        (f"allure-results_{run_id}", f"allure-results_{run_time}_{node_label}" if node_label else "", f"allure-results_{run_time}")
    ):
        if name and (directory / name).is_dir():
            return directory / name
    return None


def load_multi_node_summaries(reports_root: Path) -> dict[str, tuple[Path, str]]:
    """Map txt report file names to (summary.json path, pytest summary line)."""
    mapping: dict[str, tuple[Path, str]] = {}
    for summary_path in sorted((reports_root / "multi_node").glob("*/summary.json")):
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for result in data.get("results") or []:
            txt_report = ((result.get("report_paths") or {}).get("txt_report") or "").strip()
            if txt_report:
                name = re.split(r"[\\/]", txt_report)[-1]
                mapping[name] = (summary_path, str(result.get("summary_line") or ""))
    return mapping


def collect_runs(reports_root: Path) -> list[RunRecord]:
    summaries = load_multi_node_summaries(reports_root)
    runs: list[RunRecord] = []
    for directory in sorted(path for path in reports_root.iterdir() if path.is_dir()):
        build = parse_build_dir(directory.name)
        if build is None:
            continue
        for txt_path in sorted(directory.glob("*.txt")):
            metadata, cases = parse_txt_report(txt_path)
            run_id, run_time, node_label, tag = _run_identity(txt_path, metadata)
            base_stem = txt_path.stem
            if node_label and tag:
                base_stem = txt_path.stem[: -(len(tag) + 1)]
            summary = summaries.get(txt_path.name)
            runs.append(
                RunRecord(
                    build=build,
                    txt_path=txt_path,
                    run_id=run_id,
                    run_time=run_time,
                    node_ip=metadata.get("Node IP", ""),
                    node_name=metadata.get("Node Name", ""),
                    node_label=node_label,
                    tag=tag,
                    metadata=metadata,
                    cases=cases,
                    html_path=_companion(directory, txt_path.stem, base_stem, ".html"),
                    integrated_path=_companion(directory, txt_path.stem, base_stem, "_integrated.html"),
                    allure_dir=_allure_dir(directory, run_id, run_time, node_label),
                    multi_node_summary=summary[0] if summary else None,
                    pytest_summary=summary[1] if summary else "",
                )
            )
    _assign_nodes(runs)
    _classify_runs(runs)
    return runs


def _assign_nodes(runs: list[RunRecord]) -> None:
    """Name nodes by NODE label when reports with that IP carry one."""
    labels_by_ip: dict[str, Counter[str]] = defaultdict(Counter)
    names_by_ip: dict[str, Counter[str]] = defaultdict(Counter)
    for run in runs:
        if run.node_label and run.node_ip:
            labels_by_ip[run.node_ip][run.node_label] += 1
        if run.node_name and run.node_ip:
            names_by_ip[run.node_ip][run.node_name] += 1
    for run in runs:
        if run.node_label:
            run.node = run.node_label
        elif run.node_ip in labels_by_ip:
            run.node = labels_by_ip[run.node_ip].most_common(1)[0][0]
        elif run.node_ip in names_by_ip:
            run.node = names_by_ip[run.node_ip].most_common(1)[0][0]
        else:
            run.node = run.node_name or "unknown"


def _classify_runs(runs: list[RunRecord]) -> None:
    build_largest: dict[tuple[str, str], int] = defaultdict(int)
    line_largest: dict[tuple[str, str], int] = defaultdict(int)
    for run in runs:
        build_key = (run.build.dir_name, run.node)
        line_key = (run.build.version_line, run.node)
        build_largest[build_key] = max(build_largest[build_key], len(run.cases))
        line_largest[line_key] = max(line_largest[line_key], len(run.cases))
    for run in runs:
        total = len(run.cases)
        if total == 0:
            run.kind = "empty"
        elif (
            total >= FULL_RUN_RATIO * build_largest[(run.build.dir_name, run.node)]
            and total >= LINE_RUN_RATIO * line_largest[(run.build.version_line, run.node)]
        ):
            run.kind = "full"
        else:
            run.kind = "partial"


def load_formal_runs(path: Path) -> dict[tuple[str, str], list[FormalEntry]]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top level must be a mapping of build directory -> node -> runs")
    formal: dict[tuple[str, str], list[FormalEntry]] = {}
    for build_dir, nodes in data.items():
        if not isinstance(nodes, dict):
            raise ValueError(f"{path}: {build_dir} must map node names to run lists")
        for node, entries in nodes.items():
            parsed: list[FormalEntry] = []
            for entry in entries or []:
                if isinstance(entry, str):
                    parsed.append(FormalEntry(run=entry))
                elif isinstance(entry, dict) and entry.get("run"):
                    parsed.append(
                        FormalEntry(run=str(entry["run"]), final=bool(entry.get("final")), note=str(entry.get("note") or ""))
                    )
                else:
                    raise ValueError(f"{path}: {build_dir}/{node} entries need a 'run' value")
            formal[(str(build_dir), str(node))] = parsed
    return formal


def apply_formal_runs(index: ReportIndex) -> None:
    # run_id is only unique per node: nodes run in parallel can share a timestamp
    # when their txt names carry no _NODEx label.
    by_key: dict[tuple[str, str], list[RunRecord]] = defaultdict(list)
    for run in index.runs:
        by_key[(run.build.dir_name, run.run_id)].append(run)
    for (build_dir, node), entries in index.formal.items():
        for entry in entries:
            candidates = by_key.get((build_dir, entry.run), [])
            if not candidates:
                index.warnings.append(f"formal_runs.yaml: {build_dir} / {node} / {entry.run} 找不到對應的 txt 報表")
                continue
            run = next((candidate for candidate in candidates if candidate.node == node), None)
            if run is None:
                owners = "、".join(sorted({candidate.node for candidate in candidates}))
                index.warnings.append(f"formal_runs.yaml: {build_dir} / {entry.run} 屬於 {owners}，不是 {node}")
                continue
            run.formal = "final" if entry.final else "round"
            run.formal_note = entry.note


def build_index(reports_root: Path, formal_path: Path) -> ReportIndex:
    index = ReportIndex(reports_root=reports_root, runs=collect_runs(reports_root))
    index.formal = load_formal_runs(formal_path)
    apply_formal_runs(index)
    return index


# ---------------------------------------------------------------- comparison


@dataclass
class CaseChange:
    category: str
    case_id: str
    name: str
    before: str
    after: str
    unstable: bool = False
    step_diff: str = ""
    case_page: Path | None = None


CATEGORY_ORDER = ("regression", "still_failing", "fixed", "added", "removed")
CATEGORY_LABELS = {
    "regression": "Regression 候選（Pass → Fail）",
    "still_failing": "既有問題（兩次都 Fail）",
    "fixed": "已修復（Fail → Pass）",
    "added": "新增 case",
    "removed": "移除 case",
}


def _results_by_case(run: RunRecord) -> dict[str, TxtCase]:
    return {case.case_id: case for case in run.cases}


def unstable_cases(index: ReportIndex, run: RunRecord) -> set[str]:
    """Cases that both passed and failed across runs of the same build and node."""
    seen: dict[str, set[str]] = defaultdict(set)
    for other in index.runs_for(run.build.dir_name, run.node):
        for case in other.cases:
            if case.result in (PASS, FAIL):
                seen[case.case_id].add(case.result)
    return {case_id for case_id, results in seen.items() if len(results) > 1}


def compare_runs(index: ReportIndex, before: RunRecord, after: RunRecord, with_steps: bool = True) -> list[CaseChange]:
    old = _results_by_case(before)
    new = _results_by_case(after)
    unstable = unstable_cases(index, after)
    changes: list[CaseChange] = []
    for case_id in sorted(set(old) | set(new)):
        old_case, new_case = old.get(case_id), new.get(case_id)
        if old_case is None:
            category = "added"
        elif new_case is None:
            category = "removed"
        elif old_case.result == PASS and new_case.result == FAIL:
            category = "regression"
        elif old_case.result == FAIL and new_case.result == FAIL:
            category = "still_failing"
        elif old_case.result == FAIL and new_case.result == PASS:
            category = "fixed"
        else:
            continue
        changes.append(
            CaseChange(
                category=category,
                case_id=case_id,
                name=(new_case or old_case).name,
                before=old_case.result if old_case else "-",
                after=new_case.result if new_case else "-",
                unstable=case_id in unstable,
            )
        )
    if with_steps:
        _attach_step_diffs(before, after, [change for change in changes if change.category in CASE_PAGE_CATEGORIES])
    return changes


def flatten_steps(node: dict[str, Any]) -> list[tuple[tuple[str, ...], str, str]]:
    """Return (path, status, message) for every step, depth first."""
    return [
        (path, str(step.get("status") or "unknown"), str((step.get("statusDetails") or {}).get("message") or ""))
        for path, step in step_entries(node)
    ]


def _first_line(text: str, limit: int = 300) -> str:
    # The index is for result lookup; addresses stay in the linked raw reports.
    line = IPV4_RE.sub("<ip>", redact_text(text.strip().splitlines()[0])) if text.strip() else ""
    return line if len(line) <= limit else line[:limit] + "…"


def describe_step_difference(before: dict[str, Any] | None, after: dict[str, Any] | None) -> str:
    if before is None:
        return f"基準沒有同名的 Allure result（{after.get('name') if after else '-'}）"
    if after is None:
        return f"比對沒有同名的 Allure result（{before.get('name')}）"
    old_steps = flatten_steps(before)
    new_steps = flatten_steps(after)
    old_map = {path: (status, message) for path, status, message in old_steps}
    for path, status, message in new_steps:
        old_status = old_map.get(path, ("missing", ""))[0]
        if old_status != status:
            detail = _first_line(message or old_map.get(path, ("", ""))[1])
            text = f"{' › '.join(path)}：{old_status} → {status}"
            return f"{text}；{detail}" if detail else text
    new_paths = {path for path, _, _ in new_steps}
    for path, status, _ in old_steps:
        if path not in new_paths:
            return f"{' › '.join(path)}：{status} → missing"
    old_result, new_result = str(before.get("status")), str(after.get("status"))
    message = _first_line(str((after.get("statusDetails") or {}).get("message") or ""))
    if old_result != new_result or message:
        text = f"步驟狀態相同；result {old_result} → {new_result}"
        return f"{text}；{message}" if message else text
    return "步驟狀態相同"


def _attach_step_diffs(before: RunRecord, after: RunRecord, changes: list[CaseChange]) -> None:
    if not changes:
        return
    if before.allure_dir is None or after.allure_dir is None:
        for change in changes:
            change.step_diff = "沒有 Allure 原始資料，無法比對步驟"
        return
    old_results = load_case_results(before.allure_dir)
    new_results = load_case_results(after.allure_dir)
    for change in changes:
        pairs = pair_results(old_results.get(change.case_id, []), new_results.get(change.case_id, []))
        differing = [
            describe_step_difference(old, new)
            for old, new in pairs
            if old is None or new is None or old.get("status") != new.get("status") or new.get("status") != "passed"
        ]
        change.step_diff = " / ".join(differing) if differing else "步驟狀態相同"


def default_comparisons(index: ReportIndex) -> list[tuple[RunRecord, RunRecord]]:
    """Per node: latest reference run of each target against the previous build."""
    pairs: list[tuple[RunRecord, RunRecord]] = []
    builds = index.builds()
    for node in index.nodes():
        with_reference = [(build, index.reference_run(build.dir_name, node)) for build in builds]
        with_reference = [(build, run) for build, run in with_reference if run is not None]
        for target in sorted({build.target for build, _ in with_reference}):
            same_target = [item for item in with_reference if item[0].target == target]
            latest_build, latest_run = same_target[-1]
            earlier = [item for item in with_reference if item[0].sort_key() < latest_build.sort_key()]
            previous = [item for item in earlier if item[0].target == target] or earlier
            if previous:
                pairs.append((previous[-1][1], latest_run))
    return pairs


# ------------------------------------------------------------------- output


def _rel(path: Path | None, root: Path) -> str:
    if path is None:
        return ""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _href(path: Path | None, base: Path, anchor: str = "") -> str:
    if path is None:
        return ""
    try:
        rel = os.path.relpath(path, base).replace(os.sep, "/")
        link = "/".join(quote(part) for part in rel.split("/"))
    except ValueError:  # different drive on Windows
        link = path.resolve().as_uri()
    return f"{link}#{quote(anchor)}" if anchor else link


def case_link(run: RunRecord, case_id: str, base: Path) -> str:
    if run.integrated_path is not None:
        return _href(run.integrated_path, base, case_id)
    return _href(run.txt_path, base)


def write_runs_csv(index: ReportIndex, path: Path) -> None:
    root = index.reports_root
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "version_line", "build_dir", "build", "target", "platform", "node", "run_id", "run_time",
                "kind", "cases", "pass", "fail", "tag", "formal", "formal_note", "txt", "html",
                "integrated", "allure_dir", "multi_node_summary", "pytest_summary",
            ]
        )
        for run in sorted(index.runs, key=lambda item: (item.build.sort_key(), item.run_time, item.run_id)):
            writer.writerow(
                [
                    run.build.version_line, run.build.dir_name, run.build.build, run.build.target,
                    run.metadata.get("EMS Platform", ""), run.node, run.run_id, run.run_time, run.kind,
                    len(run.cases), run.pass_count, run.fail_count, run.tag, run.formal, run.formal_note,
                    _rel(run.txt_path, root), _rel(run.html_path, root), _rel(run.integrated_path, root),
                    _rel(run.allure_dir, root), _rel(run.multi_node_summary, root), run.pytest_summary,
                ]
            )


def write_case_history_csv(index: ReportIndex, path: Path) -> None:
    root = index.reports_root
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "case_id", "case_name", "version_line", "build_dir", "build", "target", "node", "run_id",
                "run_time", "run_kind", "formal", "result", "duration", "txt", "integrated_case", "allure_dir",
            ]
        )
        for run in sorted(index.runs, key=lambda item: (item.build.sort_key(), item.run_time, item.run_id)):
            for case in run.cases:
                integrated_case = f"{_rel(run.integrated_path, root)}#{case.case_id}" if run.integrated_path else ""
                writer.writerow(
                    [
                        case.case_id, case.name, run.build.version_line, run.build.dir_name, run.build.build,
                        run.build.target, run.node, run.run_id, run.run_time, run.kind, run.formal,
                        case.result, case.duration, _rel(run.txt_path, root), integrated_case, _rel(run.allure_dir, root),
                    ]
                )


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


STYLE = """
:root{--bg:#f5f7fb;--panel:#fff;--ink:#172033;--muted:#64748b;--line:#d9e2ef;--blue:#1d4ed8;--green:#15803d;--red:#b91c1c;--orange:#b45309}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:"Segoe UI","Microsoft JhengHei",Arial,sans-serif;line-height:1.5}
header{padding:24px 32px;color:#fff;background:#111827;border-bottom:4px solid #2563eb}h1{margin:0 0 6px;font-size:24px}header p{margin:0;color:#cbd5e1;font-size:13px}
main{max-width:1600px;margin:0 auto;padding:20px 24px 40px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;margin-bottom:20px;overflow:hidden}
.panel-title{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px;padding:12px 16px;border-bottom:1px solid var(--line);background:#f8fafc}
h2{margin:0;font-size:17px}h3{margin:14px 16px 6px;font-size:15px}.muted{color:var(--muted);font-size:13px}.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}th{position:sticky;top:0;padding:8px 10px;background:#f1f5f9;color:#475569;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
td{padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}
.Pass{color:var(--green);background:#dcfce7}.Fail{color:var(--red);background:#fee2e2}.Skip{color:#475569;background:#e2e8f0}
td.cell{text-align:center;white-space:nowrap}td.cell.unofficial{font-style:italic;opacity:.7}.warn{margin:0 0 20px;padding:12px 14px;border-left:4px solid var(--orange);background:#fff7ed;color:#7c2d12;border-radius:6px;font-size:13px}
.controls{display:flex;flex-wrap:wrap;gap:12px;align-items:center;font-size:13px}input[type=search]{padding:5px 8px;border:1px solid var(--line);border-radius:6px;min-width:220px}
.tag{display:inline-block;padding:1px 6px;border-radius:999px;background:#dbeafe;color:var(--blue);font-size:11px;margin-left:4px}.counts{display:flex;flex-wrap:wrap;gap:8px;padding:10px 16px}
.count{padding:4px 10px;border-radius:6px;background:#f1f5f9;font-size:13px}.count strong{margin-left:4px}tr.empty-run{display:none}body.show-empty tr.empty-run{display:table-row}
"""

SCRIPT = """
function filterRows(input, tableId){var q=input.value.trim().toLowerCase();document.querySelectorAll('#'+tableId+' tbody tr').forEach(function(tr){tr.style.display=(!q||tr.textContent.toLowerCase().indexOf(q)>=0)?'':'none';});}
function changedOnly(box, tableId){document.querySelectorAll('#'+tableId+' tbody tr').forEach(function(tr){if(box.checked&&tr.dataset.changed!=='1'){tr.dataset.hidden='1';tr.style.display='none';}else if(tr.dataset.hidden){delete tr.dataset.hidden;tr.style.display='';}});}
"""


UNMARKED_LABEL = "未標記，暫用最後一次完整執行"


def _run_label(run: RunRecord) -> str:
    return f"{run.build.dir_name} / {run.run_id}"


def _formal_label(run: RunRecord) -> str:
    return {"final": "正式（最終）", "round": "正式"}.get(run.formal, "")


def render_comparison(index: ReportIndex, before: RunRecord, after: RunRecord, changes: list[CaseChange]) -> str:
    root = index.link_dir()
    counts = Counter(change.category for change in changes)
    count_html = "".join(
        f'<span class="count">{esc(CATEGORY_LABELS[category])}<strong>{counts.get(category, 0)}</strong></span>'
        for category in CATEGORY_ORDER
    )
    rows = []
    for category in CATEGORY_ORDER:
        for change in (item for item in changes if item.category == category):
            unstable = '<span class="tag">不穩定</span>' if change.unstable else ""
            side_by_side = (
                f' <a href="{esc(_href(change.case_page, root))}">步驟並排</a>' if change.case_page is not None else ""
            )
            rows.append(
                f"<tr><td>{esc(CATEGORY_LABELS[category])}</td>"
                f"<td>{esc(change.case_id)}{unstable}</td><td>{esc(change.name)}</td>"
                f'<td class="cell {esc(change.before)}"><a href="{esc(case_link(before, change.case_id, root))}">{esc(change.before)}</a></td>'
                f'<td class="cell {esc(change.after)}"><a href="{esc(case_link(after, change.case_id, root))}">{esc(change.after)}</a></td>'
                f"<td>{esc(change.step_diff)}{side_by_side}</td></tr>"
            )
    body = "".join(rows) or '<tr><td colspan="6">兩次結果沒有差異，也沒有失敗的 case。</td></tr>'
    return f"""
<section class="panel">
  <div class="panel-title"><h2>{esc(after.node)}：{esc(before.build.dir_name)} → {esc(after.build.dir_name)}</h2>
  <span class="muted">基準 {esc(_run_label(before))}（{esc(_formal_label(before) or UNMARKED_LABEL)}） → 比對 {esc(_run_label(after))}（{esc(_formal_label(after) or UNMARKED_LABEL)}）</span></div>
  <div class="counts">{count_html}</div>
  <div class="table-wrap"><table><thead><tr><th>分類</th><th>Case</th><th>名稱</th><th>基準</th><th>比對</th><th>步驟差異</th></tr></thead><tbody>{body}</tbody></table></div>
</section>"""


def render_matrix(index: ReportIndex, node: str, table_id: str) -> str:
    root = index.link_dir()
    builds = [build for build in index.builds() if index.runs_for(build.dir_name, node)]
    references = {build.dir_name: index.reference_run(build.dir_name, node) for build in builds}
    latest_seen: dict[tuple[str, str], tuple[str, RunRecord]] = {}
    names: dict[str, str] = {}
    for build in builds:
        for run in sorted(index.runs_for(build.dir_name, node), key=lambda item: item.run_time):
            for case in run.cases:
                latest_seen[(build.dir_name, case.case_id)] = (case.result, run)
                names[case.case_id] = case.name
    header = "".join(
        f'<th title="{esc(_run_label(references[b.dir_name]) if references[b.dir_name] else "沒有正式或完整執行")}">{esc(b.build or b.dir_name)}{"_" + esc(b.target) if b.target else ""}</th>'
        for b in builds
    )
    reference_cases = {
        build_dir: {case.case_id: case for case in run.cases} if run else {} for build_dir, run in references.items()
    }
    rows = []
    for case_id in sorted(names, key=lambda value: int(value.split("-")[-1]) if value.split("-")[-1].isdigit() else 0):
        cells = []
        results = set()
        for build in builds:
            reference = references[build.dir_name]
            reference_case = reference_cases[build.dir_name].get(case_id)
            if reference_case is not None:
                results.add(reference_case.result)
                cells.append(
                    f'<td class="cell {esc(reference_case.result)}"><a href="{esc(case_link(reference, case_id, root))}">{esc(reference_case.result)}</a></td>'
                )
            elif (build.dir_name, case_id) in latest_seen:
                result, run = latest_seen[(build.dir_name, case_id)]
                results.add(result)
                cells.append(
                    f'<td class="cell unofficial {esc(result)}" title="非正式：{esc(run.run_id)}"><a href="{esc(case_link(run, case_id, root))}">{esc(result)}</a></td>'
                )
            else:
                cells.append('<td class="cell">-</td>')
        changed = "1" if len(results - {"Skip"}) > 1 else "0"
        rows.append(f'<tr data-changed="{changed}"><td>{esc(case_id)}</td><td>{esc(names[case_id])}</td>{"".join(cells)}</tr>')
    return f"""
<section class="panel">
  <div class="panel-title"><h2>{esc(node)} Case 歷史</h2>
  <div class="controls"><input type="search" placeholder="搜尋 case ID 或名稱" oninput="filterRows(this,'{table_id}')">
  <label><input type="checkbox" onchange="changedOnly(this,'{table_id}')"> 只看結果有變化的 case</label></div></div>
  <p class="muted" style="margin:8px 16px">每格是該 build 正式執行（或最後一次完整執行）的結果，點擊跳到該 case 的步驟細節；斜體表示正式執行沒有這個 case，改顯示其他執行的最後結果。</p>
  <div class="table-wrap"><table id="{table_id}"><thead><tr><th>Case</th><th>名稱</th>{header}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>
</section>"""


def render_runs_table(index: ReportIndex) -> str:
    root = index.link_dir()
    rows = []
    for run in sorted(index.runs, key=lambda item: (item.build.sort_key(), item.run_time, item.run_id), reverse=True):
        links = " ".join(
            f'<a href="{esc(_href(path, root))}">{label}</a>'
            for label, path in (
                ("txt", run.txt_path), ("integrated", run.integrated_path), ("allure", run.allure_dir),
                ("multi_node", run.multi_node_summary.parent / "summary.html" if run.multi_node_summary else None),
            )
            if path is not None
        )
        formal = _formal_label(run)
        row_class = ' class="empty-run"' if run.kind == "empty" else ""
        rows.append(
            f"<tr{row_class}><td>{esc(run.build.dir_name)}</td><td>{esc(run.node)}</td><td>{esc(run.run_id)}</td>"
            f"<td>{esc(run.kind)}</td><td>{len(run.cases)}</td><td>{run.pass_count}</td><td>{run.fail_count}</td>"
            f"<td>{esc(formal)}</td><td>{esc(run.formal_note or run.pytest_summary)}</td><td>{links}</td></tr>"
        )
    empty_total = sum(1 for run in index.runs if run.kind == "empty")
    return f"""
<section class="panel">
  <div class="panel-title"><h2>所有執行</h2>
  <div class="controls"><input type="search" placeholder="搜尋 build、node、run" oninput="filterRows(this,'runs-table')">
  <label><input type="checkbox" onchange="document.body.classList.toggle('show-empty',this.checked)"> 顯示 0 個 case 的空報表（{empty_total} 份）</label></div></div>
  <div class="table-wrap"><table id="runs-table"><thead><tr><th>Build</th><th>Node</th><th>Run</th><th>類型</th><th>Case</th><th>Pass</th><th>Fail</th><th>正式</th><th>備註／pytest</th><th>連結</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>
</section>"""


def render_page(title: str, subtitle: str, body: str, extra_style: str = "") -> str:
    return f"""<!doctype html>
<html lang="zh-Hant">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title><style>{STYLE}{extra_style}</style></head>
<body>
<header><h1>{esc(title)}</h1><p>{esc(subtitle)}</p></header>
<main>
{body}
</main>
<script>{SCRIPT}</script>
</body>
</html>
"""


def render_index_html(index: ReportIndex, comparisons: list[tuple[RunRecord, RunRecord, list[CaseChange]]]) -> str:
    warnings = "".join(f"<div>{esc(item)}</div>" for item in index.warnings)
    warning_html = f'<section class="warn">{warnings}</section>' if warnings else ""
    comparison_html = "".join(render_comparison(index, before, after, changes) for before, after, changes in comparisons)
    if not comparison_html:
        comparison_html = '<section class="panel"><div class="panel-title"><h2>最新比對</h2></div><p class="muted" style="margin:12px 16px">還沒有可以比對的兩個 build。</p></section>'
    matrices = "".join(render_matrix(index, node, f"matrix-{position}") for position, node in enumerate(index.nodes()))
    non_empty = [run for run in index.runs if run.kind != "empty"]
    subtitle = (
        f"產生時間 {datetime.now().strftime('%Y-%m-%d %H:%M')}；{len(index.builds())} 個 build、"
        f"{len(non_empty)} 次有 case 的執行（另有 {len(index.runs) - len(non_empty)} 份空報表）。"
        f"正式執行由 {INDEX_DIRNAME}/{FORMAL_RUNS_FILENAME} 人工標記。"
    )
    return render_page("RestApi Auto 測試結果索引", subtitle, warning_html + comparison_html + matrices + render_runs_table(index))


def formal_runs_template(index: ReportIndex) -> str:
    lines = [
        "# 各 build × node 的正式判定執行，由人工維護；build_report_index.py 不會覆寫此檔。",
        "# run 填 txt 檔名 _report_ 之後的部分（runs.csv 的 run_id 欄）。",
        "# 同一 build 可列多輪（例如 C0 重測），以 final: true 標出最終判定的那一輪。",
        "# 未列出的 build 會暫用最後一次完整執行，並在索引中標示「未標記」。",
        "#",
        "# 範例：",
        '# "03.00.11 (AAVV.221) b12_redhat":',
        "#   NODE3:",
        "#     - run: 2026-10-02_09-54-36_NODE3_judged",
        "#       final: true",
        "#       note: 7120/6903 依單獨重跑判定 Pass",
        "#",
        "# 目前暫用的執行（取消註解即可確認為正式）：",
    ]
    for build in index.builds():
        entries = [(node, index.reference_run(build.dir_name, node)) for node in index.nodes()]
        entries = [(node, run) for node, run in entries if run is not None]
        if not entries:
            continue
        lines.append(f'# "{build.dir_name}":')
        for node, run in entries:
            lines.extend([f"#   {node}:", f"#     - run: {run.run_id}", "#       final: true"])
    return "\n".join(lines) + "\n"


def _safe_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", value).strip("_")


def _short_build(run: RunRecord) -> str:
    """Build label such as b13 or C0_redhat for file names."""
    label = "_".join(part for part in (run.build.build, run.build.target) if part)
    return _safe_name(label or run.build.dir_name)


def _pair_digest(before: RunRecord, after: RunRecord) -> str:
    return hashlib.sha1(f"{before.key}|{after.key}".encode("utf-8")).hexdigest()[:10]


def write_case_page(index: ReportIndex, before: RunRecord, after: RunRecord, case_id: str, output_dir: Path) -> Path:
    """Side-by-side step comparison of one case, written under <output>/cases/."""
    cases_dir = output_dir / CASES_DIRNAME
    cases_dir.mkdir(parents=True, exist_ok=True)
    path = cases_dir / f"{_safe_name(case_id)}_{_safe_name(after.node)}_{_pair_digest(before, after)}.html"
    body = render_case_comparison(
        case_id,
        _run_label(before),
        _run_label(after),
        before.allure_dir,
        after.allure_dir,
        case_link(before, case_id, cases_dir),
        case_link(after, case_id, cases_dir),
    )
    title = f"{case_id} 步驟比對：{before.build.dir_name} → {after.build.dir_name}"
    path.write_text(render_page(title, f"{after.node}；{_run_label(before)} → {_run_label(after)}", body, CASE_STYLE), encoding="utf-8")
    return path


def write_case_pages(index: ReportIndex, before: RunRecord, after: RunRecord, changes: list[CaseChange], output_dir: Path) -> None:
    if before.allure_dir is None or after.allure_dir is None:
        return
    for change in changes:
        if change.category in CASE_PAGE_CATEGORIES:
            change.case_page = write_case_page(index, before, after, change.case_id, output_dir)


def write_index(index: ReportIndex, output_dir: Path, formal_path: Path, with_steps: bool = True) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    index.link_base = output_dir
    write_runs_csv(index, output_dir / "runs.csv")
    write_case_history_csv(index, output_dir / "case_history.csv")
    comparisons = []
    for before, after in default_comparisons(index):
        changes = compare_runs(index, before, after, with_steps=with_steps)
        if with_steps:
            write_case_pages(index, before, after, changes, output_dir)
        comparisons.append((before, after, changes))
    index_path = output_dir / "index.html"
    index_path.write_text(render_index_html(index, comparisons), encoding="utf-8")
    if not formal_path.exists():
        formal_path.write_text(formal_runs_template(index), encoding="utf-8")
    return index_path


def write_comparison(index: ReportIndex, before: RunRecord, after: RunRecord, output_dir: Path, with_steps: bool = True) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    index.link_base = output_dir
    changes = compare_runs(index, before, after, with_steps=with_steps)
    if with_steps:
        write_case_pages(index, before, after, changes, output_dir)
    # Short label + hash keeps the path under the Windows 260-character limit.
    name = (
        f"compare_{_safe_name(after.node)}_{_short_build(before)}_vs_{_short_build(after)}_"
        f"{_pair_digest(before, after)}.html"
    )
    path = output_dir / name
    title = f"{after.node} 比對：{before.build.dir_name} → {after.build.dir_name}"
    path.write_text(render_page(title, f"{_run_label(before)} → {_run_label(after)}", render_comparison(index, before, after, changes)), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Index historical reports for regression lookup.")
    parser.add_argument("--reports-root", type=Path, default=DEFAULT_REPORTS_ROOT)
    parser.add_argument("--output-dir", type=Path, help=f"default: <reports-root>/{INDEX_DIRNAME}")
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("BEFORE", "AFTER"),
        help="build directory (uses its formal run for --node) or <build directory>/<run_id>",
    )
    parser.add_argument("--node", help="node used with --compare build selectors, e.g. NODE3")
    parser.add_argument("--case", help="with --compare: write only the side-by-side step page of this case, e.g. EMS1-7120")
    parser.add_argument("--no-steps", action="store_true", help="skip Allure step comparison")
    args = parser.parse_args(argv)
    if args.case and not args.compare:
        parser.error("--case requires --compare")

    reports_root = args.reports_root.resolve()
    output_dir = (args.output_dir or reports_root / INDEX_DIRNAME).resolve()
    formal_path = output_dir / FORMAL_RUNS_FILENAME
    index = build_index(reports_root, formal_path)
    for warning in index.warnings:
        print(f"WARNING: {warning}")
    if args.compare:
        before = index.find_run(args.compare[0], args.node)
        after = index.find_run(args.compare[1], args.node)
        if args.case:
            print(f"Wrote {write_case_page(index, before, after, args.case, output_dir)}")
        else:
            print(f"Wrote {write_comparison(index, before, after, output_dir, with_steps=not args.no_steps)}")
        return 0
    path = write_index(index, output_dir, formal_path, with_steps=not args.no_steps)
    print(f"Wrote {path} ({len(index.runs)} runs, {len(index.builds())} builds, {len(index.nodes())} nodes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
