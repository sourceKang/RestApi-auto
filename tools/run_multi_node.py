from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config_loader.hardware import HardwareConfigError, load_hardware_config
from tests.support.options import validate_neox_parallel_settings, xdist_worker_count
from tests.support.preflight import run_startup_preflight


REPORT_ROOT = PROJECT_ROOT / "reports" / "multi_node"
COMMON_FULL_TESTCASE_OPTIONS = (
    "--auth-matrix",
    "--run-remote",
    "--run-alarm-delete",
    "--run-live-swagger-check",
)
NEOX_ONLY_OPTIONS = {
    "--run-neox-config",
    "--run-neox-ont-error",
}
REPORT_LINE_PREFIXES = {
    "integrated_html": "EMS HTML report:",
    "html_summary": "EMS html summary (legacy):",
    "txt_report": "EMS txt report:",
    "allure_results": "EMS allure results:",
    "allure_html": "EMS allure report:",
}


@dataclass(frozen=True)
class NodePlan:
    node: str
    chassis: str
    is_neox: bool
    command: list[str]
    omitted_options: list[str]
    auth_profile: str | None = None


@dataclass(frozen=True)
class NodeResult:
    node: str
    chassis: str
    is_neox: bool
    returncode: int
    duration_seconds: float
    command: list[str]
    log_path: str
    summary_line: str
    report_paths: dict[str, str]
    omitted_options: list[str]
    skipped: bool = False
    skip_reason: str = ""


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, pytest_args = parser.parse_known_args(argv)

    nodes = parse_nodes(args.nodes)
    if not nodes:
        parser.error("--nodes must include at least one node key")

    report_dir = Path(args.report_dir) if args.report_dir else default_report_dir()
    report_dir.mkdir(parents=True, exist_ok=True)

    requested_auth_profile = selected_option_value(pytest_args, "--auth-profile")
    auth_profiles = parse_optional_csv(args.auth_profiles)
    if auth_profiles and requested_auth_profile:
        parser.error("--auth-profiles cannot be used together with pytest --auth-profile")

    plans = [
        build_node_plan(
            node=node,
            pytest_args=pytest_args,
            run_full_testcases=args.run_full_testcases,
            python_executable=args.python,
            auth_profile_override=auth_profile_for_node(auth_profiles, index),
        )
        for index, node in enumerate(nodes)
    ]

    try:
        validate_parallel_node_auth_profiles(
            plans,
            1 if args.stop_on_failure else args.jobs,
        )
    except ValueError as error:
        parser.error(str(error))

    if args.dry_run:
        for plan in plans:
            print(render_plan_line(plan), flush=True)
        write_summary(report_dir, plans, [])
        print(f"Dry-run summary: {report_dir / 'summary.html'}", flush=True)
        return 0

    for plan in plans:
        print(render_plan_line(plan), flush=True)

    results = run_node_plans(
        plans,
        report_dir,
        preflight=not args.skip_dut_preflight,
        jobs=args.jobs,
        stop_on_failure=args.stop_on_failure,
    )

    summary = write_summary(report_dir, plans, results)
    print(f"Multi-node summary: {summary}", flush=True)
    return 1 if any(result.returncode != 0 for result in results) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run pytest for multiple EMS nodes, keeping NeoX-only config tests on NeoX chassis "
            "and writing a compact multi-node summary."
        )
    )
    parser.add_argument(
        "--nodes",
        required=True,
        help="Comma-separated EMS node keys, for example NODE1,NODE3,NODE6.",
    )
    parser.add_argument(
        "--run-full-testcases",
        action="store_true",
        help=(
            "Run the full suite per node. NeoX nodes receive --run-full-testcases; "
            "non-NeoX nodes receive the full-suite common options without NeoX-only config options."
        ),
    )
    parser.add_argument(
        "--report-dir",
        default=None,
        help="Directory for multi-node logs and summary. Defaults to reports/multi_node/<timestamp>.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable used to invoke pytest. Defaults to the current interpreter.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print per-node pytest commands and write the summary without executing pytest.",
    )
    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="Stop after the first node exits with a non-zero code.",
    )
    parser.add_argument(
        "--skip-dut-preflight",
        action="store_true",
        help="Do not do the multi-node runner node-level DUT readiness check before invoking pytest.",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Maximum number of nodes to run in parallel. Defaults to 1 for conservative EMS load.",
    )
    parser.add_argument(
        "--auth-profiles",
        default=None,
        help="Comma-separated auth profiles assigned to nodes in order, for example default,ems_local_rw2.",
    )
    return parser


def parse_nodes(value: str) -> list[str]:
    return parse_optional_csv(value)


def parse_optional_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def auth_profile_for_node(auth_profiles: list[str], index: int) -> str | None:
    if not auth_profiles:
        return None
    return auth_profiles[index % len(auth_profiles)]


def validate_parallel_node_auth_profiles(plans: list[NodePlan], jobs: int) -> None:
    if max(1, jobs) <= 1 or len(plans) <= 1:
        return

    nodes_by_profile: dict[str, list[str]] = {}
    for plan in plans:
        profile = plan.auth_profile or "default"
        nodes_by_profile.setdefault(profile, []).append(plan.node)
    duplicates = {
        profile: nodes
        for profile, nodes in nodes_by_profile.items()
        if len(nodes) > 1
    }
    if not duplicates:
        return

    conflicts = "; ".join(
        f"{profile}={','.join(nodes)}"
        for profile, nodes in sorted(duplicates.items())
    )
    raise ValueError(
        "Parallel node runs require a distinct auth profile per node because EMS logins "
        "using the same account can invalidate active sessions. "
        f"Conflicts: {conflicts}. Use --auth-profiles default,ems_local_rw2 "
        "or run with --jobs 1."
    )


def default_report_dir() -> Path:
    return REPORT_ROOT / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def build_node_plan(
    *,
    node: str,
    pytest_args: list[str],
    run_full_testcases: bool,
    python_executable: str,
    auth_profile_override: str | None = None,
) -> NodePlan:
    chassis = node_chassis(node)
    is_neox = chassis.startswith("NeoX")
    sanitized_args, omitted_options = sanitize_pytest_args(pytest_args, is_neox=is_neox)
    validate_parallel_pytest_args(sanitized_args, is_neox=is_neox)
    auth_profile = auth_profile_override or selected_option_value(sanitized_args, "--auth-profile")
    command = [python_executable, "-m", "pytest", "--ems-node", node]
    if auth_profile_override:
        command.extend(["--auth-profile", auth_profile_override])

    if run_full_testcases:
        if is_neox:
            command.append("--run-full-testcases")
        else:
            command.extend(COMMON_FULL_TESTCASE_OPTIONS)
            omitted_options.append("--run-neox-config")
            omitted_options.append("--run-neox-ont-error")

    command.extend(sanitized_args)
    return NodePlan(
        node=node,
        chassis=chassis,
        is_neox=is_neox,
        command=command,
        omitted_options=dedupe_preserve_order(omitted_options),
        auth_profile=auth_profile,
    )


def node_chassis(node: str) -> str:
    try:
        hardware = load_hardware_config()
    except HardwareConfigError as error:
        raise SystemExit(f"Cannot load hardware config: {error}") from error
    target = hardware.node_target(node)
    if not target:
        raise SystemExit(f"{node} is not defined in configs/test_targets.yaml")
    return str(target.get("chassis") or "unknown")


def sanitize_pytest_args(pytest_args: list[str], *, is_neox: bool) -> tuple[list[str], list[str]]:
    sanitized: list[str] = []
    omitted: list[str] = []
    skip_next = False
    for index, arg in enumerate(pytest_args):
        if skip_next:
            skip_next = False
            continue
        if arg == "--ems-node":
            omitted.append(arg)
            skip_next = index + 1 < len(pytest_args)
            continue
        if arg.startswith("--ems-node="):
            omitted.append("--ems-node")
            continue
        if not is_neox and arg in NEOX_ONLY_OPTIONS:
            omitted.append(arg)
            continue
        sanitized.append(arg)
    return sanitized, omitted




def selected_option_value(args: list[str], option_name: str) -> str | None:
    prefix = f"{option_name}="
    for index, arg in enumerate(args):
        if arg == option_name and index + 1 < len(args):
            return args[index + 1]
        if arg.startswith(prefix):
            return arg[len(prefix) :]
    return None


def validate_parallel_pytest_args(args: list[str], *, is_neox: bool) -> None:
    worker_count = xdist_worker_count(selected_xdist_worker_value(args))
    if worker_count <= 1:
        return
    if not is_neox:
        raise ValueError("Per-node xdist is only supported for NeoX config/profile collections.")
    validate_neox_parallel_settings(
        worker_count,
        selected_option_value(args, "--neox-parallel-mode") or "off",
        selected_option_value(args, "--dist") or "no",
        selected_option_value(args, "--neox-parallel-auth-profiles") or "",
    )


def selected_xdist_worker_value(args: list[str]) -> str | None:
    value = selected_option_value(args, "-n") or selected_option_value(args, "--numprocesses")
    if value is not None:
        return value
    for arg in args:
        if arg.startswith("-n="):
            return arg[3:]
        if arg.startswith("-n") and len(arg) > 2:
            return arg[2:]
    return None


def run_node_plans(
    plans: list[NodePlan],
    report_dir: Path,
    *,
    preflight: bool = True,
    jobs: int = 1,
    stop_on_failure: bool = False,
) -> list[NodeResult]:
    effective_jobs = 1 if stop_on_failure else jobs
    validate_parallel_node_auth_profiles(plans, effective_jobs)
    max_workers = max(1, effective_jobs)
    if max_workers == 1:
        results: list[NodeResult] = []
        for plan in plans:
            result = run_node_plan(plan, report_dir, preflight=preflight)
            results.append(result)
            print_node_result(result)
            if result.returncode != 0 and stop_on_failure:
                break
        return results

    results_by_node: dict[str, NodeResult] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_by_node = {
            executor.submit(run_node_plan, plan, report_dir, preflight=preflight): plan.node
            for plan in plans
        }
        for future in as_completed(future_by_node):
            node = future_by_node[future]
            try:
                result = future.result()
            except Exception as error:
                plan = next(item for item in plans if item.node == node)
                result = NodeResult(
                    node=plan.node,
                    chassis=plan.chassis,
                    is_neox=plan.is_neox,
                    returncode=1,
                    duration_seconds=0.0,
                    command=plan.command,
                    log_path=str(report_dir / f"{safe_name(plan.node)}.log"),
                    summary_line=f"runner failed: {type(error).__name__}: {error}",
                    report_paths={},
                    omitted_options=plan.omitted_options,
                )
            results_by_node[node] = result
            print_node_result(result)
    return [results_by_node[plan.node] for plan in plans if plan.node in results_by_node]


def print_node_result(result: NodeResult) -> None:
    print(
        f"[{result.node}] finished with exit code {result.returncode} in {format_duration(result.duration_seconds)}",
        flush=True,
    )


def run_node_plan(plan: NodePlan, report_dir: Path, *, preflight: bool = True) -> NodeResult:
    log_path = report_dir / f"{safe_name(plan.node)}.log"
    started = time.perf_counter()
    output_lines: list[str] = []
    if preflight:
        preflight_started = time.perf_counter()
        print(
            f"[{plan.node}] preflight started"
            f"{format_auth_profile_for_status(plan.auth_profile)}",
            flush=True,
        )
        preflight_result = run_startup_preflight(plan.node, plan.auth_profile)
        preflight_duration = time.perf_counter() - preflight_started
        if not preflight_result.ok:
            reason = f"DUT preflight failed: {preflight_result.reason}"
            log_path.write_text(reason + "\n", encoding="utf-8")
            print(
                f"[{plan.node}] preflight failed in {format_duration(preflight_duration)}: "
                f"{preflight_result.reason}",
                flush=True,
            )
            print(f"[{plan.node}] skipped: {reason}", flush=True)
            return NodeResult(
                node=plan.node,
                chassis=plan.chassis,
                is_neox=plan.is_neox,
                returncode=0,
                duration_seconds=round(time.perf_counter() - started, 3),
                command=plan.command,
                log_path=str(log_path),
                summary_line=reason,
                report_paths={},
                omitted_options=plan.omitted_options,
                skipped=True,
                skip_reason=reason,
            )
        print(f"[{plan.node}] preflight passed in {format_duration(preflight_duration)}", flush=True)
    command = command_with_runner_preflight_skip(plan.command) if preflight else list(plan.command)
    command = command_with_parallel_report_dir(command, report_dir, plan.node)
    process_env = os.environ.copy()
    process_env.setdefault("EMS_REPORT_SUFFIX", safe_name(plan.node))
    if not preflight:
        print(f"[{plan.node}] preflight skipped", flush=True)
    print(f"[{plan.node}] pytest started; log={log_path}", flush=True)
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=process_env,
        )
        assert process.stdout is not None
        for line in process.stdout:
            if os.environ.get("MULTI_NODE_ECHO_CHILD_OUTPUT", "0") == "1":
                print(f"[{plan.node}] {line}", end="", flush=True)
            log_file.write(line)
            output_lines.append(line.rstrip("\n"))
        returncode = process.wait()
    duration = time.perf_counter() - started
    return NodeResult(
        node=plan.node,
        chassis=plan.chassis,
        is_neox=plan.is_neox,
        returncode=returncode,
        duration_seconds=round(duration, 3),
        command=command,
        log_path=str(log_path),
        summary_line=parse_pytest_summary_line(output_lines),
        report_paths=parse_report_paths(output_lines),
        omitted_options=plan.omitted_options,
    )


def format_auth_profile_for_status(auth_profile: str | None) -> str:
    return f" (auth_profile={auth_profile})" if auth_profile else ""


def command_with_parallel_report_dir(command: list[str], report_dir: Path, node: str) -> list[str]:
    if "--alluredir" in command or any(part.startswith("--alluredir=") for part in command):
        return list(command)
    alluredir = report_dir / f"{safe_name(node)}_allure-current"
    return [*command, "--alluredir", str(alluredir)]


def command_with_runner_preflight_skip(command: list[str]) -> list[str]:
    if "--skip-dut-preflight" in command:
        return list(command)
    return [*command, "--skip-dut-preflight"]


def parse_pytest_summary_line(lines: Iterable[str]) -> str:
    for line in reversed(list(lines)):
        stripped = line.strip()
        if stripped.startswith("=") and stripped.endswith("=") and " in " in stripped:
            return " ".join(stripped.strip("= ").split())
    return ""


def parse_report_paths(lines: Iterable[str]) -> dict[str, str]:
    paths: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        for key, prefix in REPORT_LINE_PREFIXES.items():
            if stripped.startswith(prefix):
                value = stripped[len(prefix) :].strip()
                if value and value.lower() != "skipped; use --generate-allure-html when needed.":
                    paths[key] = value
    return paths


def write_summary(report_dir: Path, plans: list[NodePlan], results: list[NodeResult]) -> Path:
    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "plans": [asdict(plan) for plan in plans],
        "results": [asdict(result) for result in results],
    }
    json_path = report_dir / "summary.json"
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    html_path = report_dir / "summary.html"
    html_path.write_text(render_html_summary(plans, results, json_path), encoding="utf-8")
    return html_path


def render_html_summary(plans: list[NodePlan], results: list[NodeResult], json_path: Path) -> str:
    result_by_node = {result.node: result for result in results}
    rows = []
    for plan in plans:
        result = result_by_node.get(plan.node)
        status = "Not run" if result is None else ("Pass" if result.returncode == 0 else "Fail")
        summary = "" if result is None else result.summary_line
        duration = "" if result is None else format_duration(result.duration_seconds)
        log_link = "" if result is None else link(result.log_path, "log")
        report_links = "" if result is None else " ".join(
            link(path, label) for label, path in result.report_paths.items()
        )
        rows.append(
            "<tr>"
            f"<td>{escape(plan.node)}</td>"
            f"<td>{escape(plan.chassis)}</td>"
            f"<td>{'yes' if plan.is_neox else 'no'}</td>"
            f"<td>{escape(status)}</td>"
            f"<td>{escape(duration)}</td>"
            f"<td>{escape(summary)}</td>"
            f"<td>{escape(', '.join(plan.omitted_options))}</td>"
            f"<td>{log_link} {report_links}</td>"
            "</tr>"
        )

    commands = "\n".join(
        f"{plan.node}: {' '.join(quote_for_display(part) for part in plan.command)}" for plan in plans
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Multi-node pytest summary</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #202124; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
    th, td {{ border: 1px solid #dadce0; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f1f3f4; }}
    code, pre {{ background: #f8f9fa; }}
    pre {{ padding: 12px; overflow-x: auto; }}
    a {{ color: #0b57d0; }}
  </style>
</head>
<body>
  <h1>Multi-node pytest summary</h1>
  <p>JSON summary: {link(str(json_path), "summary.json")}</p>
  <table>
    <thead>
      <tr>
        <th>Node</th>
        <th>Chassis</th>
        <th>NeoX</th>
        <th>Status</th>
        <th>Duration</th>
        <th>Pytest Summary</th>
        <th>Omitted Options</th>
        <th>Artifacts</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
  <h2>Commands</h2>
  <pre>{escape(commands)}</pre>
</body>
</html>
"""


def render_plan_line(plan: NodePlan) -> str:
    omitted = f" omitted={','.join(plan.omitted_options)}" if plan.omitted_options else ""
    return (
        f"[{plan.node}] chassis={plan.chassis} neox={'yes' if plan.is_neox else 'no'}{omitted}\n"
        f"  {' '.join(quote_for_display(part) for part in plan.command)}"
    )


def format_duration(seconds: float) -> str:
    minutes, remainder = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {remainder}s"
    if minutes:
        return f"{minutes}m {remainder}s"
    return f"{seconds:.1f}s"


def link(path: str, label: str) -> str:
    href = Path(path).as_posix()
    return f'<a href="{escape(href)}">{escape(label)}</a>'


def quote_for_display(value: str) -> str:
    if not any(char.isspace() for char in value):
        return value
    return f'"{value}"'


def safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)


def dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
