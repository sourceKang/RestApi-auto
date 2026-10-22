from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.support import report_writer, reporting_hooks
from tests.support.collection import _record_expected_items
from tests.test_reporting import _fake_env
from tools import run_multi_node
from utils import reporting


pytestmark = pytest.mark.offline

RAN = "tests/test_provision.py::test_put_ont_service_by_sn"
NEVER_RAN = "tests/test_provision.py::test_patch_ont_service_by_sn"
NO_CASE_ID = "tests/test_inventory.py::test_ont_inventory_ready_after_post"


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState(timestamp="2026-10-22_12-00-00"))
    reporting.register_node_case(RAN, "EMS1-6667", "test_put_ont_service_by_sn")
    reporting.register_node_case(NEVER_RAN, "EMS1-6668", "test_patch_ont_service_by_sn")
    return reporting.REPORT_STATE


def _txt_lines():
    return report_writer._render_txt_report(_fake_env()).splitlines()


def test_selected_test_without_result_makes_the_report_incomplete(state):
    reporting.record_expected_items([RAN, NEVER_RAN, NO_CASE_ID])
    reporting.record_result(RAN, "passed", 1.0)

    lines = _txt_lines()

    assert "Completeness: Incomplete (1/3 selected tests have a result)" in lines
    assert f"Missing Test #1: EMS1-6668 {NEVER_RAN}" in lines
    assert f"Missing Test #2: {NO_CASE_ID}" in lines
    # Missing tests stay in the header: corp reads only `[id][name] Result ...` rows.
    assert not any(line.startswith("[EMS1-6668]") for line in lines)


def test_every_selected_test_with_a_result_is_complete(state):
    reporting.record_expected_items([RAN, NEVER_RAN])
    reporting.record_result(RAN, "passed", 1.0)
    reporting.record_result(NEVER_RAN, "skipped", 0.0)

    lines = _txt_lines()

    assert "Completeness: Complete (2/2 selected tests have a result)" in lines
    assert not any(line.startswith("Missing Test") for line in lines)


def test_interrupted_run_is_incomplete_even_when_every_test_reported(state):
    reporting.record_expected_items([RAN])
    reporting.record_result(RAN, "passed", 1.0)
    reporting.mark_interrupted()

    assert "Completeness: Incomplete (1/1 selected tests have a result; run interrupted)" in _txt_lines()


def test_xdist_run_reports_completeness_as_not_evaluated(state):
    reporting.mark_completeness_unavailable("xdist run; the controller does not collect test items")
    reporting.record_result(RAN, "passed", 1.0)

    assert "Completeness: not evaluated (xdist run; the controller does not collect test items)" in _txt_lines()


def test_missing_tests_are_capped_in_the_header(state):
    nodeids = [f"tests/test_x.py::test_{index}" for index in range(35)]
    reporting.record_expected_items([RAN, *nodeids])
    reporting.record_result(RAN, "passed", 1.0)

    lines = _txt_lines()

    assert sum(line.startswith("Missing Test #") for line in lines) == report_writer.MAX_CONNECTION_EVENT_LINES
    assert "Missing Test (more): 5 further tests without a result" in lines


def test_collection_records_selected_items_or_marks_xdist_unavailable(state):
    items = [SimpleNamespace(nodeid=RAN), SimpleNamespace(nodeid=NEVER_RAN)]

    _record_expected_items(SimpleNamespace(config=SimpleNamespace(option=SimpleNamespace(dist="no")), items=items))
    assert state.expected_nodeids == (RAN, NEVER_RAN)

    _record_expected_items(SimpleNamespace(config=SimpleNamespace(option=SimpleNamespace(dist="loadgroup")), items=[]))
    assert state.completeness_unavailable


def test_session_finish_marks_interrupt_and_prints_the_runner_line(monkeypatch, state, tmp_path):
    reporting.record_expected_items([RAN, NEVER_RAN])
    reporting.record_result(RAN, "passed", 1.0)
    written = []
    terminal = SimpleNamespace(write_line=written.append)
    config = SimpleNamespace(
        getoption=lambda name: None,
        pluginmanager=SimpleNamespace(get_plugin=lambda name: terminal),
    )
    monkeypatch.setattr(reporting_hooks, "load_environment", lambda **kwargs: _fake_env())
    report = tmp_path / "report.txt"
    monkeypatch.setattr(reporting_hooks, "write_reports", lambda config, env: (report, report, report, report, None))

    reporting_hooks.pytest_sessionfinish(SimpleNamespace(config=config), pytest.ExitCode.INTERRUPTED)

    assert state.interrupted
    assert "EMS completeness: Incomplete (1/2 selected tests have a result; run interrupted)" in written


def _node_result(**overrides):
    values = dict(
        node="NODE3",
        chassis="NeoX-03",
        is_neox=True,
        returncode=0,
        duration_seconds=1.0,
        command=["python", "-m", "pytest"],
        log_path="NODE3.log",
        summary_line="40 passed, 34 skipped in 93.77s",
        report_paths={},
        omitted_options=[],
    )
    values.update(overrides)
    return run_multi_node.NodeResult(**values)


def test_runner_reads_the_completeness_line():
    lines = ["EMS completeness: Incomplete (70/74 selected tests have a result)", "EMS txt report: x.txt"]

    assert run_multi_node.parse_completeness_line(lines) == "Incomplete (70/74 selected tests have a result)"
    assert run_multi_node.parse_completeness_line(["EMS txt report: x.txt"]) == ""


@pytest.mark.parametrize(
    ("overrides", "status"),
    [
        ({"completeness": "Complete (74/74 selected tests have a result)"}, "Pass"),
        ({"returncode": 1, "completeness": "Complete (74/74 selected tests have a result)"}, "Fail"),
        ({"completeness": "Incomplete (70/74 selected tests have a result)"}, "Incomplete"),
        ({"returncode": 2, "summary_line": "1 passed in 3.00s"}, "Incomplete"),
        # The process was cut off before pytest printed its final line (2026-10-02 09:54 NODE3).
        ({"returncode": 1, "summary_line": ""}, "Incomplete"),
        ({"returncode": 2, "skipped": True, "summary_line": "DUT preflight failed"}, "Blocked"),
    ],
)
def test_runner_node_status(overrides, status):
    assert run_multi_node.node_status(_node_result(**overrides)) == status


def test_summary_renders_incomplete_node(tmp_path):
    plan = run_multi_node.NodePlan(
        node="NODE3", chassis="NeoX-03", is_neox=True, command=["python", "-m", "pytest"], omitted_options=[]
    )
    result = _node_result(completeness="Incomplete (70/74 selected tests have a result)")

    html = run_multi_node.render_html_summary([plan], [result], tmp_path / "summary.json")

    assert "<td>Incomplete</td>" in html
    assert "completeness: Incomplete (70/74 selected tests have a result)" in html
