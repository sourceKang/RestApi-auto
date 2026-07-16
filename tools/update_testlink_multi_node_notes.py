from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


STATUS_LABELS = {"p": "Pass", "f": "Fail", "b": "Blocked"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Overwrite TestLink execution notes with multi-node evidence.")
    parser.add_argument("--agent-root", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--node-report", action="append", required=True, metavar="LABEL=PATH")
    parser.add_argument("--project", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--build", required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--throttle", type=float, default=0.2)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--confirm-overwrite", action="store_true")
    args = parser.parse_args()
    if args.write and not args.confirm_overwrite:
        parser.error("--write requires --confirm-overwrite")
    return args


def load_agent(agent_root: Path) -> dict[str, Any]:
    root = str(agent_root.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)
    from testlink_agent_core.client import TestLinkClient
    from testlink_agent_core.config import load_testlink_settings
    from testlink_agent_core.handlers import report as report_handlers
    from testlink_agent_core.reports import parse_report
    from testlink_agent_core.resolver import NameResolver

    return {
        "TestLinkClient": TestLinkClient,
        "load_testlink_settings": load_testlink_settings,
        "report_handlers": report_handlers,
        "parse_report": parse_report,
        "NameResolver": NameResolver,
    }


def parse_report_specs(values: list[str]) -> list[tuple[str, Path]]:
    specs: list[tuple[str, Path]] = []
    labels: set[str] = set()
    for value in values:
        if "=" not in value:
            raise ValueError(f"Invalid --node-report {value!r}; expected LABEL=PATH")
        label, raw_path = value.split("=", 1)
        label = label.strip()
        path = Path(raw_path).resolve()
        if not label or label in labels:
            raise ValueError(f"Node report labels must be non-empty and unique: {label!r}")
        if not path.is_file():
            raise FileNotFoundError(path)
        labels.add(label)
        specs.append((label, path))
    return specs


def index_results(results: list[Any], label: str) -> dict[str, Any]:
    indexed: dict[str, Any] = {}
    for result in results:
        if result.external_id in indexed:
            raise ValueError(f"Duplicate testcase {result.external_id} in {label}")
        indexed[result.external_id] = result
    return indexed


def aggregate_status(results: list[Any]) -> str:
    statuses = {result.status for result in results if result.status}
    if "f" in statuses:
        return "f"
    if "p" in statuses:
        return "p"
    return "b"


def build_notes(external_id: str, reports: list[dict[str, Any]], status: str, test_name: str) -> str:
    lines = [
        "Automation Source: RestApi Auto multi-node full test",
        "",
        f"Aggregate result: {STATUS_LABELS[status]}",
    ]
    for item in reports:
        result = item["results"][external_id]
        header = item["header"]
        node = header.get("Node Name", "")
        node_ip = header.get("Node IP", "")
        chassis = header.get("Node Chassis", "")
        generated = header.get("Report generated on", "")
        lines.extend(
            [
                (
                    f"{item['label']}: Result {result.raw_status}; duration {result.duration_text}; "
                    f"target {node} / {node_ip} / {chassis}; generated {generated}"
                ),
                f"{item['label']} report: {item['path'].name}",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    agent = load_agent(args.agent_root)
    specs = parse_report_specs(args.node_report)
    reports: list[dict[str, Any]] = []
    testcase_ids: set[str] = set()
    for label, path in specs:
        header, parsed = agent["parse_report"](path)
        indexed = index_results(parsed, label)
        testcase_ids.update(indexed)
        reports.append({"label": label, "path": path, "header": header, "results": indexed})

    payload_items: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for external_id in sorted(testcase_ids, key=lambda value: int(value.rsplit("-", 1)[1])):
        missing = [item["label"] for item in reports if external_id not in item["results"]]
        if missing:
            raise ValueError(f"{external_id} is missing from reports: {', '.join(missing)}")
        node_results = [item["results"][external_id] for item in reports]
        status = aggregate_status(node_results)
        primary = next((result for result in reversed(node_results) if result.status), node_results[-1])
        duration_seconds = max((result.duration_seconds or 0.0) for result in node_results)
        notes = build_notes(external_id, reports, status, primary.test_name)
        payload_items.append(
            {
                "testcase_external_id": external_id,
                "status": status,
                "notes": notes,
                "platformname": args.platform,
                "execution_duration": round(duration_seconds / 60.0, 4),
                "overwrite": True,
                "confirm_overwrite": True,
            }
        )
        summary_rows.append(
            {
                "external_id": external_id,
                "status": status,
                "node_statuses": {item["label"]: item["results"][external_id].raw_status for item in reports},
                "notes": notes,
            }
        )

    settings = agent["load_testlink_settings"](env_file=str(args.env_file), timeout=args.timeout)
    client = agent["TestLinkClient"](
        settings.url,
        settings.devkey,
        timeout=settings.timeout,
        max_retries=args.max_retries,
        min_interval_seconds=args.throttle,
    )
    if not client.check_devkey():
        raise RuntimeError("tl.checkDevKey failed")
    resolver = agent["NameResolver"](client)
    result = agent["report_handlers"].report_results_batch(
        client,
        resolver,
        results=payload_items,
        project=args.project,
        plan=args.plan,
        build=args.build,
        platform=args.platform,
        audit_dir=str(args.audit_dir),
        write=args.write,
    )

    output = {
        "mode": "write" if args.write else "preview",
        "node_reports": [{"label": item["label"], "path": str(item["path"])} for item in reports],
        "result_count": len(summary_rows),
        "status_counts": result["status_counts"],
        "success_count": result["success_count"],
        "failure_count": result["failure_count"],
        "audit_log": result.get("audit_log"),
        "results": summary_rows,
        "failures": result["failures"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=True, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {key: value for key, value in output.items() if key not in {"results", "failures"}},
            ensure_ascii=True,
            indent=2,
        )
    )
    return 1 if result["failure_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
