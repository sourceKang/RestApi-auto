from __future__ import annotations

import csv

from tools import archive_reports as archive


def _make_reports(root):
    reports = root / "reports"
    for directory in (
        "03.00.11 (AAVV.221) b12_redhat",
        "multi_node",
        "acl-retry-probes",
        "rerun",
        "full-probes",
        "mystery_dir",
    ):
        (reports / directory).mkdir(parents=True)
    (reports / "acl-retry-probes" / "probe.json").write_text("{}", encoding="utf-8")
    (reports / "rerun" / "a.txt").write_text("abc", encoding="utf-8")
    for name in (
        "20261001_03.00.11-AAVV.221-b12_redhat_NODE3_regression.html",
        "node3-full.xml",
        "testlink_agent_preview_all.json",
        "testlink_backfill_steps.json",
        "full_node3_b7_2026-06-26.out.log",
        "node3_b7_integrated_evidence_report_2026-06-26.html",
        "notes.bin",
    ):
        (reports / name).write_text("x", encoding="utf-8")
    repo = root / "repo"
    (repo / "configs").mkdir(parents=True)
    (repo / "configs" / "payload.json").write_text('{"report": "reports/full-probes/p.json"}', encoding="utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "status.md").write_text("見 reports/mystery_dir。", encoding="utf-8")
    return reports, repo


def test_build_plan_keeps_referenced_and_code_paths_and_classifies_the_rest(tmp_path):
    reports, repo = _make_reports(tmp_path)

    references = archive.referenced_report_names(repo)
    plan = {item.name: item for item in archive.build_plan(reports, "03.00.11", references)}

    assert references["mystery_dir"] == "docs/status.md"
    keep = {name for name, item in plan.items() if item.action == "keep"}
    assert keep == {
        "03.00.11 (AAVV.221) b12_redhat",
        "multi_node",
        "full-probes",
        "mystery_dir",
        "testlink_backfill_steps.json",
        "20261001_03.00.11-AAVV.221-b12_redhat_NODE3_regression.html",
    }
    moves = {name: item.reason for name, item in plan.items() if item.action == "move"}
    assert moves == {
        "acl-retry-probes": "probes",
        "node3-full.xml": "probes",
        "rerun": "runs",
        "testlink_agent_preview_all.json": "testlink",
        "full_node3_b7_2026-06-26.out.log": "logs",
        "node3_b7_integrated_evidence_report_2026-06-26.html": "analysis",
    }
    assert plan["notes.bin"].action == "unclassified"
    assert plan["rerun"].destination == reports / "_archive" / "03.00.11" / "runs" / "rerun"
    assert (plan["rerun"].files, plan["rerun"].size) == (1, 3)


def test_main_dry_run_moves_nothing(tmp_path, capsys):
    reports, repo = _make_reports(tmp_path)
    before = sorted(path.name for path in reports.iterdir())

    exit_code = archive.main(["--version-line", "03.00.11", "--reports-root", str(reports), "--repo-root", str(repo)])

    assert exit_code == 0
    assert sorted(path.name for path in reports.iterdir()) == before
    assert "dry run" in capsys.readouterr().out


def test_main_apply_moves_entries_and_records_manifest(tmp_path):
    reports, repo = _make_reports(tmp_path)
    args = ["--version-line", "03.00.11", "--reports-root", str(reports), "--repo-root", str(repo), "--apply"]

    assert archive.main(args) == 0

    archived = reports / "_archive" / "03.00.11"
    assert (archived / "runs" / "rerun" / "a.txt").read_text(encoding="utf-8") == "abc"
    assert (archived / "probes" / "acl-retry-probes" / "probe.json").exists()
    assert not (reports / "rerun").exists()
    assert (reports / "notes.bin").exists()
    assert (reports / "full-probes").exists()
    with (archived / "MANIFEST.csv").open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["original"] for row in rows} == {
        "acl-retry-probes",
        "node3-full.xml",
        "rerun",
        "testlink_agent_preview_all.json",
        "full_node3_b7_2026-06-26.out.log",
        "node3_b7_integrated_evidence_report_2026-06-26.html",
    }
    assert "runs/" in (archived / "README.md").read_text(encoding="utf-8")

    assert archive.main(args) == 0
    with (archived / "MANIFEST.csv").open(encoding="utf-8-sig") as handle:
        assert len(list(csv.DictReader(handle))) == 6


def test_apply_plan_refuses_to_overwrite_existing_destination(tmp_path):
    reports, repo = _make_reports(tmp_path)
    plan = archive.build_plan(reports, "03.00.11", archive.referenced_report_names(repo))
    existing = reports / "_archive" / "03.00.11" / "runs" / "rerun"
    existing.mkdir(parents=True)

    problems = archive.apply_plan(reports, "03.00.11", plan)

    assert any("rerun" in problem and "已存在" in problem for problem in problems)
    assert (reports / "rerun" / "a.txt").exists()
