"""Move loose top-level files of reports/ into reports/_archive/<version line>/<category>/.

Dry run by default: prints the plan and changes nothing. With --apply it moves
(renames) each entry, verifies file count and size after the move, and appends
the moves to _archive/<version line>/MANIFEST.csv. It never deletes anything.

Entries stay in place when code or config writes/reads them, when a versioned
file in the repository refers to them as reports/<name>, or when no category
rule matches them.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.build_report_index import INDEX_DIRNAME, parse_build_dir  # noqa: E402


ARCHIVE_DIRNAME = "_archive"
# Written or read by tools/tests at fixed paths (see docs/project-context.md).
KEEP_NAMES = {
    ".allure-results-current",
    INDEX_DIRNAME,
    ARCHIVE_DIRNAME,
    "multi_node",
    "device-verification",
    "stale_cleanup",
    "swagger-readonly",
    "neox_ug_text.txt",
    "testlink_backfill_steps.json",
    "testlink_agent_backfill_results.json",
    "testlink_agent_payloads",
}
# Consolidated QA reports named YYYYMMDD_<version>_<node>_*.html stay at the top as the entry point.
KEEP_PATTERNS = (re.compile(r"^\d{8}_.+\.html$"),)
CATEGORY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("logs", re.compile(r"\.log$", re.I)),
    ("testlink", re.compile(r"^(testlink|use_?testlink)", re.I)),
    ("probes", re.compile(r"(^|[-_])probes?([-_.]|$)|^cli-discovery$|^live-runs$|^\.live-|\.xml$", re.I)),
    ("runs", re.compile(r"^node3_(full|ge_config|neox_config)_|^rerun$|^multi_node_launcher$|^allure-report-", re.I)),
    ("analysis", re.compile(r"\.(html|png|md)$|^bug_link_|^sop_", re.I)),
)
CATEGORY_NOTES = {
    "logs": "pytest／allure 執行時的 stdout、stderr log",
    "testlink": "TestLink 預覽、回填、上傳紀錄與 UseTestlink 相關檔案",
    "probes": "探測與除錯輸出（probe、CLI discovery、junit xml、暫存 live run）",
    "runs": "非 multi_node 的單次執行資料夾、重跑、舊 allure html report",
    "analysis": "分析／預覽報表、截圖、比對紀錄、SOP 素材",
}
SCANNED_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".ini", ".toml", ".txt", ".ps1", ".bat"}
SKIPPED_DIRS = {".git", ".venv", "reports", "local", "tmp", "__pycache__", ".pytest_cache", "node_modules", "worktrees"}


@dataclass
class PlanItem:
    name: str
    action: str  # move / keep / unclassified
    reason: str
    destination: Path | None = None
    files: int = 0
    size: int = 0


def referenced_report_names(repo_root: Path) -> dict[str, str]:
    """Top-level reports/ names that versioned repository files refer to, with one referring file."""
    pattern = re.compile(r"reports[/\\]+([^/\\\"'`\s)，。、；：）]+)")
    found: dict[str, str] = {}
    for directory, subdirs, files in os.walk(repo_root):
        subdirs[:] = [name for name in subdirs if name not in SKIPPED_DIRS]
        for file_name in files:
            path = Path(directory) / file_name
            if path.suffix.lower() not in SCANNED_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for match in pattern.finditer(text):
                found.setdefault(match.group(1), path.relative_to(repo_root).as_posix())
    return found


def _measure(path: Path) -> tuple[int, int]:
    if path.is_file():
        return 1, path.stat().st_size
    files = size = 0
    for directory, _, names in os.walk(path):
        for name in names:
            files += 1
            size += (Path(directory) / name).stat().st_size
    return files, size


def classify(name: str) -> str | None:
    for category, rule in CATEGORY_RULES:
        if rule.search(name):
            return category
    return None


def build_plan(reports_root: Path, version_line: str, references: dict[str, str]) -> list[PlanItem]:
    archive_root = reports_root / ARCHIVE_DIRNAME / version_line
    plan: list[PlanItem] = []
    for entry in sorted(reports_root.iterdir(), key=lambda path: path.name.lower()):
        name = entry.name
        if name in KEEP_NAMES:
            plan.append(PlanItem(name, "keep", "程式固定讀寫的路徑"))
        elif parse_build_dir(name) is not None:
            plan.append(PlanItem(name, "keep", "build 報表資料夾"))
        elif any(pattern.match(name) for pattern in KEEP_PATTERNS):
            plan.append(PlanItem(name, "keep", "統整報表（YYYYMMDD_ 開頭）"))
        elif name in references:
            plan.append(PlanItem(name, "keep", f"被 {references[name]} 引用"))
        else:
            category = classify(name)
            if category is None:
                plan.append(PlanItem(name, "unclassified", "沒有符合的分類規則，保留原位"))
                continue
            files, size = _measure(entry)
            plan.append(PlanItem(name, "move", category, archive_root / category / name, files, size))
    return plan


def apply_plan(reports_root: Path, version_line: str, plan: list[PlanItem]) -> list[str]:
    """Move planned entries; return problems (an entry with a problem is left where it was)."""
    archive_root = reports_root / ARCHIVE_DIRNAME / version_line
    problems: list[str] = []
    moved: list[PlanItem] = []
    for item in plan:
        if item.action != "move" or item.destination is None:
            continue
        if item.destination.exists():
            problems.append(f"{item.name}: 目的地已存在 {item.destination}")
            continue
        item.destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(reports_root / item.name, item.destination)
        except OSError as error:
            problems.append(f"{item.name}: 搬移失敗 {error}")
            continue
        if _measure(item.destination) != (item.files, item.size):
            problems.append(f"{item.name}: 搬移後檔案數或大小不一致")
        moved.append(item)
    if moved:
        _write_manifest(archive_root, reports_root, moved)
        _write_readme(archive_root, version_line)
    return problems


def _write_manifest(archive_root: Path, reports_root: Path, moved: list[PlanItem]) -> None:
    manifest = archive_root / "MANIFEST.csv"
    new_file = not manifest.exists()
    with manifest.open("a", encoding="utf-8-sig" if new_file else "utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(["moved_at", "original", "archived_to", "category", "files", "bytes"])
        stamp = datetime.now().isoformat(timespec="seconds")
        for item in moved:
            writer.writerow(
                [stamp, item.name, item.destination.relative_to(reports_root).as_posix(), item.reason, item.files, item.size]
            )


def _write_readme(archive_root: Path, version_line: str) -> None:
    readme = archive_root / "README.md"
    if readme.exists():
        return
    lines = [
        f"# {version_line} 歸檔",
        "",
        "由 tools/archive_reports.py 從 reports/ 最上層搬入；原始位置與搬移時間見 MANIFEST.csv。",
        "此版本線依 docs/project-context.md「報表保存」規則，於下一條版本線第一個 build 有結果後整批處理。",
        "",
    ]
    lines += [f"- `{category}/`：{note}" for category, note in CATEGORY_NOTES.items()]
    readme.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _format_size(size: int) -> str:
    return f"{size / 1_000_000:.1f} MB" if size >= 100_000 else f"{size / 1000:.0f} KB"


def print_plan(plan: list[PlanItem]) -> None:
    for action, title in (("move", "搬移"), ("keep", "保留原位"), ("unclassified", "未分類（保留原位）")):
        items = [item for item in plan if item.action == action]
        if not items:
            continue
        print(f"\n== {title}：{len(items)} 項")
        for item in items:
            if action == "move":
                print(f"  [{item.reason}] {item.name}  ({item.files} 檔, {_format_size(item.size)})")
            else:
                print(f"  {item.name}  — {item.reason}")
    moving = [item for item in plan if item.action == "move"]
    print(
        f"\n合計搬移 {len(moving)} 項、{sum(item.files for item in moving)} 檔、"
        f"{_format_size(sum(item.size for item in moving))}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Archive loose top-level entries of reports/ (dry run by default).")
    parser.add_argument("--version-line", required=True, help="version line the entries belong to, e.g. 03.00.11")
    parser.add_argument("--reports-root", type=Path, default=PROJECT_ROOT / "reports")
    parser.add_argument("--repo-root", type=Path, default=PROJECT_ROOT, help="repository scanned for reports/<name> references")
    parser.add_argument("--apply", action="store_true", help="actually move the entries")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version_line):
        parser.error("--version-line must look like 03.00.11")

    reports_root = args.reports_root.resolve()
    plan = build_plan(reports_root, args.version_line, referenced_report_names(args.repo_root.resolve()))
    print_plan(plan)
    if not args.apply:
        print("\n(dry run：沒有搬移任何檔案；確認後加 --apply 執行)")
        return 0
    problems = apply_plan(reports_root, args.version_line, plan)
    for problem in problems:
        print(f"ERROR: {problem}")
    print(f"\n完成；清單記錄在 {reports_root / ARCHIVE_DIRNAME / args.version_line / 'MANIFEST.csv'}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
