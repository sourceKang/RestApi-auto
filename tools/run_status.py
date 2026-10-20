"""Read-only progress of a tools/run_multi_node.py run.

Replaces hand-written polling while a full regression (about 1.5-2 h) runs in a detached process:

    python tools/run_status.py                      # latest run under reports/multi_node
    python tools/run_status.py reports/multi_node/2026-10-14_13-22-42 --tail 10
    python tools/run_status.py <run_dir> --json

It only reads <run_dir>/<NODE>.log, <NODE>_allure-current/ and summary.json; it never starts,
stops or contacts anything. A node with no log update for --stale-minutes is flagged, since a
stuck run and a slow EMS look the same from outside; check the EMS and the process before acting.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.redaction import redact_text  # noqa: E402

MULTI_NODE_ROOT = PROJECT_ROOT / "reports" / "multi_node"
OUTCOMES = ("PASSED", "FAILED", "ERROR", "SKIPPED", "XFAIL", "XPASS")
# `pytest -vv`: "tests/x.py::name PASSED   [ 42%]"; with xdist: "[gw0] [ 42%] PASSED tests/x.py::name".
_OUTCOME = "(?P<outcome>" + "|".join(OUTCOMES) + ")"
_SERIAL_RE = re.compile(r"^(?P<nodeid>\S+::\S.*?) " + _OUTCOME + r"\b")
_XDIST_RE = re.compile(r"^\[gw\d+\] \[\s*\d+%\] " + _OUTCOME + r" (?P<nodeid>\S+::\S.*)$")
_SELECTED_RE = re.compile(r"collected \d+ items?(?: / \d+ deselected)?(?: / (?P<selected>\d+) selected)?")
_COLLECTED_RE = re.compile(r"collected (?P<collected>\d+) items?")
_FINAL_RE = re.compile(r"^=+ (?P<line>.+ in [\d.]+s.*?) =+$")


@dataclass
class NodeStatus:
    node: str
    state: str
    counts: dict[str, int] = field(default_factory=dict)
    done: int = 0
    selected: int | None = None
    last_test: str | None = None
    last_update_minutes: float | None = None
    allure_results: int = 0
    final_line: str | None = None
    returncode: int | None = None
    tail: list[str] = field(default_factory=list)


def latest_run_dir(root: Path = MULTI_NODE_ROOT) -> Path | None:
    runs = [path for path in root.iterdir() if path.is_dir()] if root.is_dir() else []
    return max(runs, key=lambda path: path.stat().st_mtime, default=None)


def parse_log(text: str) -> tuple[Counter, int | None, str | None, str | None]:
    counts: Counter = Counter()
    selected = None
    last_test = None
    final_line = None
    for line in text.splitlines():
        line = line.rstrip()
        match = _SERIAL_RE.match(line) or _XDIST_RE.match(line)
        if match:
            counts[match.group("outcome")] += 1
            last_test = match.group("nodeid").strip()
            continue
        if selected is None:
            selected_match = _SELECTED_RE.search(line)
            if selected_match:
                value = selected_match.group("selected")
                selected = int(value) if value else int(_COLLECTED_RE.search(line).group("collected"))
                continue
        final_match = _FINAL_RE.match(line)
        if final_match and (" passed" in line or " failed" in line or " error" in line):
            final_line = final_match.group("line")
    return counts, selected, last_test, final_line


def node_status(run_dir: Path, node: str, summary: dict | None, *, now: float, stale_minutes: float, tail: int) -> NodeStatus:
    log_path = run_dir / f"{node}.log"
    text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    counts, selected, last_test, final_line = parse_log(text)
    allure_dir = run_dir / f"{node}_allure-current"
    status = NodeStatus(
        node=node,
        state="running",
        counts=dict(counts),
        done=sum(counts.values()),
        selected=selected,
        last_test=last_test,
        allure_results=sum(1 for _ in allure_dir.glob("*-result.json")) if allure_dir.is_dir() else 0,
        final_line=final_line,
        tail=[redact_text(line) for line in text.splitlines()[-tail:]] if tail > 0 else [],
    )
    if log_path.exists():
        status.last_update_minutes = round((now - log_path.stat().st_mtime) / 60, 1)
    result = next((item for item in (summary or {}).get("results", []) if item.get("node") == node), None)
    if result is not None:
        status.returncode = result.get("returncode")
        status.state = "skipped" if result.get("skipped") else "finished"
    elif final_line:
        status.state = "finished"
    elif status.last_update_minutes is not None and status.last_update_minutes >= stale_minutes:
        status.state = "stale"
    return status


def run_status(run_dir: Path, *, now: float | None = None, stale_minutes: float = 15, tail: int = 5) -> dict:
    now = time.time() if now is None else now
    summary_path = run_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else None
    nodes = sorted(path.stem for path in run_dir.glob("*.log"))
    return {
        "run_dir": run_dir.as_posix(),
        "summary_written": summary is not None,
        "nodes": [asdict(node_status(run_dir, node, summary, now=now, stale_minutes=stale_minutes, tail=tail)) for node in nodes],
    }


def format_status(status: dict) -> str:
    lines = [f"Run: {status['run_dir']}  summary.json: {'yes' if status['summary_written'] else 'not yet'}"]
    for node in status["nodes"]:
        total = f"/{node['selected']}" if node["selected"] else ""
        counts = ", ".join(f"{key.lower()} {value}" for key, value in sorted(node["counts"].items())) or "no results yet"
        age = f"{node['last_update_minutes']} min ago" if node["last_update_minutes"] is not None else "no log"
        rc = f" returncode={node['returncode']}" if node["returncode"] is not None else ""
        lines.append(f"[{node['node']}] {node['state']}{rc}: {node['done']}{total} done ({counts}); log updated {age}")
        lines.append(f"  allure results: {node['allure_results']}; last test: {node['last_test'] or '-'}")
        if node["final_line"]:
            lines.append(f"  pytest: {node['final_line']}")
        if node["state"] == "stale":
            lines.append("  no log update for a while: check the EMS and the pytest process before acting")
        lines.extend(f"  | {line}" for line in node["tail"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only progress of a run_multi_node run.")
    parser.add_argument("run_dir", nargs="?", type=Path, help="reports/multi_node/<timestamp>; defaults to the latest run")
    parser.add_argument("--stale-minutes", type=float, default=15, help="flag a node whose log has not changed for this long")
    parser.add_argument("--tail", type=int, default=5, help="redacted log lines to show per node (0 to hide)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args(argv)

    run_dir = args.run_dir or latest_run_dir()
    if run_dir is None or not run_dir.is_dir():
        print(f"No run directory found: {run_dir or MULTI_NODE_ROOT}", file=sys.stderr)
        return 2
    status = run_status(run_dir, stale_minutes=args.stale_minutes, tail=args.tail)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2) if args.json else format_status(status))
    return 0


if __name__ == "__main__":
    sys.exit(main())
