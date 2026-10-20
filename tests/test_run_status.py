from __future__ import annotations

import json
import os

import pytest

from tools.run_status import format_status, latest_run_dir, parse_log, run_status


pytestmark = pytest.mark.offline

NOW = 1_800_000_000.0

LOG_HEAD = (
    "collecting ... collected 731 items / 415 deselected / 316 selected\n"
    "tests/test_provision.py::test_post_ont_service_by_sn PASSED              [  0%]\n"
    "tests/test_inventory.py::test_ont_inventory_ready_after_post FAILED      [  0%]\n"
    "tests/test_session.py::test_login[readonly] SKIPPED (requires --run-x)   [  1%]\n"
)


def write_run(tmp_path, log: str, *, minutes_ago: float, summary: dict | None = None, allure_results: int = 0):
    run_dir = tmp_path / "2026-10-20_10-00-00"
    run_dir.mkdir()
    log_path = run_dir / "NODE3.log"
    log_path.write_text(log, encoding="utf-8")
    os.utime(log_path, (NOW - minutes_ago * 60, NOW - minutes_ago * 60))
    allure = run_dir / "NODE3_allure-current"
    allure.mkdir()
    for index in range(allure_results):
        (allure / f"{index:04d}-result.json").write_text("{}", encoding="utf-8")
    (allure / "0000-attachment.txt").write_text("not a result", encoding="utf-8")
    if summary is not None:
        (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return run_dir


def test_running_node_reports_progress_and_last_test(tmp_path):
    run_dir = write_run(tmp_path, LOG_HEAD, minutes_ago=2, allure_results=2)

    [node] = run_status(run_dir, now=NOW, tail=0)["nodes"]

    assert node["state"] == "running"
    assert (node["done"], node["selected"]) == (3, 316)
    assert node["counts"] == {"PASSED": 1, "FAILED": 1, "SKIPPED": 1}
    assert node["last_test"] == "tests/test_session.py::test_login[readonly]"
    assert node["allure_results"] == 2
    assert node["last_update_minutes"] == 2.0


def test_node_without_log_updates_is_flagged_stale(tmp_path):
    run_dir = write_run(tmp_path, LOG_HEAD, minutes_ago=20)

    status = run_status(run_dir, now=NOW, stale_minutes=15, tail=0)

    assert status["nodes"][0]["state"] == "stale"
    assert "check the EMS and the pytest process" in format_status(status)


def test_summary_json_marks_node_finished_with_returncode(tmp_path):
    log = LOG_HEAD + "============== 1 passed, 1 failed, 1 skipped in 12.50s ===============\n"
    summary = {"results": [{"node": "NODE3", "returncode": 1, "skipped": False}]}
    run_dir = write_run(tmp_path, log, minutes_ago=60, summary=summary)

    status = run_status(run_dir, now=NOW, tail=0)
    [node] = status["nodes"]

    assert status["summary_written"] is True
    assert (node["state"], node["returncode"]) == ("finished", 1)
    assert node["final_line"] == "1 passed, 1 failed, 1 skipped in 12.50s"


def test_runner_skipped_node_is_reported_as_skipped(tmp_path):
    summary = {"results": [{"node": "NODE3", "returncode": None, "skipped": True}]}
    run_dir = write_run(tmp_path, "DUT preflight failed: DevStatus=4\n", minutes_ago=1, summary=summary)

    assert run_status(run_dir, now=NOW, tail=0)["nodes"][0]["state"] == "skipped"


def test_parse_log_reads_xdist_lines():
    log = (
        "collected 10 items\n"
        "[gw0] [ 10%] PASSED tests/test_a.py::test_one\n"
        "[gw1] [ 20%] ERROR tests/test_b.py::test_two[x]\n"
    )

    counts, selected, last_test, final_line = parse_log(log)

    assert counts == {"PASSED": 1, "ERROR": 1}
    assert (selected, last_test, final_line) == (10, "tests/test_b.py::test_two[x]", None)


def test_tail_lines_are_redacted(tmp_path):
    run_dir = write_run(tmp_path, LOG_HEAD + "request body password=hunter22 registration-id OntPw1\n", minutes_ago=1)

    [node] = run_status(run_dir, now=NOW, tail=2)["nodes"]

    assert "hunter22" not in repr(node["tail"]) and "OntPw1" not in repr(node["tail"])
    assert node["tail"][-1].count("***REDACTED***") == 2


def test_latest_run_dir_picks_newest_directory(tmp_path):
    older = tmp_path / "2026-10-01_09-00-00"
    newer = tmp_path / "2026-10-02_09-00-00"
    older.mkdir()
    newer.mkdir()
    (tmp_path / "run11_NODE3_20261014.log").write_text("", encoding="utf-8")
    os.utime(older, (NOW - 7200, NOW - 7200))
    os.utime(newer, (NOW - 60, NOW - 60))

    assert latest_run_dir(tmp_path) == newer
    assert latest_run_dir(tmp_path / "missing") is None
