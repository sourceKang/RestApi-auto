from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from html import escape
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clients import EmsApiClient, SessionManager
from config_loader import load_environment
from services.profile import ProfileService


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    env = load_environment(node=args.node, auth_profile=args.auth_profile)
    client = EmsApiClient(env)
    profile = ProfileService(client, env_config=env, registry_root=args.registry_dir)
    scan = profile.stale_temporary_graphs(min_age_hours=args.min_age_hours)

    if scan.records:
        manager = SessionManager(client, env, cache_enabled=False)
        try:
            credentials = env.readwrite if args.cleanup_stale_test_data else env.readonly
            with manager.credentials_session(credentials) as session_id:
                report = profile.reconcile_stale_temporary_graphs(
                    session_id,
                    min_age_hours=args.min_age_hours,
                    delete=args.cleanup_stale_test_data,
                )
        finally:
            manager.close()
    else:
        report = {
            "mode": "delete" if args.cleanup_stale_test_data else "audit",
            "minimum_age_hours": args.min_age_hours,
            "node": env.dut.node_key,
            "invalid_registry_files": list(scan.invalid_files),
            "records": [],
        }

    report_path = write_html_report(report, Path(args.report_dir), env.ems_version)
    print_summary(report, report_path)
    if not args.cleanup_stale_test_data:
        return 0
    unresolved = {
        "cleanup_failed",
        "skipped_referenced",
        "skipped_inspection_failed",
        "skipped_reference_unknown",
    }
    return 1 if any(item.get("status") in unresolved for item in report["records"]) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit locally registered stale RestApi Auto temporary profile graphs. "
            "The default is read-only; deletion requires --cleanup-stale-test-data."
        )
    )
    parser.add_argument("--node", required=True, help="Configured node key, for example NODE1.")
    parser.add_argument("--auth-profile", default="default", help="EMS auth profile used for read-only inspection.")
    parser.add_argument(
        "--min-age-hours",
        type=float,
        default=24,
        help="Only inspect manifests at least this old. Defaults to 24 hours.",
    )
    parser.add_argument(
        "--cleanup-stale-test-data",
        action="store_true",
        help=(
            "Delete eligible automation-owned profiles after exact GET and target-service reference checks. "
            "Without this option the command is audit-only."
        ),
    )
    parser.add_argument(
        "--registry-dir",
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--report-dir",
        default=str(PROJECT_ROOT / "reports" / "stale_cleanup"),
        help="Directory for the HTML audit report.",
    )
    return parser


def write_html_report(report: dict, report_dir: Path, ems_version: str) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_node = "".join(char for char in str(report["node"]) if char.isalnum() or char in "-_")
    path = report_dir / f"stale_test_data_{safe_node}_{timestamp}.html"
    rows = []
    for item in report["records"]:
        details = {
            "profile_status": item.get("profile_status", []),
            "reference_status": item.get("reference_status"),
            "reference_details": item.get("reference_details", []),
            "error": item.get("error"),
        }
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('created_at', '')))}</td>"
            f"<td>{escape(str(item.get('root_name', '')))}</td>"
            f"<td>{escape(str(item.get('status', '')))}</td>"
            f"<td>{escape(', '.join(item.get('profiles', [])))}</td>"
            f"<td><pre>{escape(json.dumps(details, ensure_ascii=False, indent=2))}</pre></td>"
            "</tr>"
        )
    invalid = escape(json.dumps(report.get("invalid_registry_files", []), ensure_ascii=False, indent=2))
    body = f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><title>Stale test data audit</title>
<style>body{{font-family:Segoe UI,sans-serif;margin:2rem}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccc;padding:.5rem;text-align:left}}pre{{background:#f5f5f5;padding:1rem}}</style>
</head><body><h1>Temporary test data：{escape(str(report['mode']))}</h1>
<p>Node：{escape(str(report['node']))}｜EMS：{escape(str(ems_version))}｜Minimum age：{escape(str(report['minimum_age_hours']))} hours</p>
<p>候選數量：{len(report['records'])}</p>
<table><thead><tr><th>建立時間</th><th>Root profile</th><th>狀態</th><th>Profile graph</th><th>檢查細節</th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan="5">沒有符合條件的候選資料</td></tr>'}</tbody></table>
<h2>無效 manifest</h2><pre>{invalid}</pre></body></html>"""
    path.write_text(body, encoding="utf-8")
    return path


def print_summary(report: dict, report_path: Path) -> None:
    counts: dict[str, int] = {}
    for item in report["records"]:
        status = str(item.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    print(f"Mode: {report['mode']}")
    print(f"Node: {report['node']}")
    print(f"Candidates: {len(report['records'])}")
    if counts:
        print("Statuses: " + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())))
    print(f"HTML report: {report_path}")


if __name__ == "__main__":
    raise SystemExit(main())
