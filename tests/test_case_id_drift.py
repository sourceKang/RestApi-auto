from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cases.registry import case_name_by_id
from tests.support import report_writer
from tests.test_reporting import _fake_env
from tools.testlink_backfill import build_backfill_cases
from utils import reporting


pytestmark = pytest.mark.offline

ROOT = Path(__file__).resolve().parents[1]
PUT = "tests/test_provision.py::test_put_ont_service_by_sn"
LIFECYCLE = "tests/test_alarm.py::test_alarm_lifecycle_remote_console_to_history_delete"

DUMP_PLUGIN = '''
import json
import os


def pytest_collection_finish(session):
    from utils import reporting

    markers = []
    for item in session.items:
        for marker in item.iter_markers("testlink_case"):
            markers.append(["testlink_case", *marker.args])
        for marker in item.iter_markers("testlink_runtime_case"):
            markers.append(["testlink_runtime_case", *marker.args])
    frozen = reporting.REPORT_STATE.collection_case_ids or {}
    with open(os.environ["CASE_ID_DUMP"], "w", encoding="utf-8") as handle:
        json.dump({"held": sorted({i for ids in frozen.values() for i in ids}), "markers": markers}, handle)
'''


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState(timestamp="2026-10-22_12-00-00"))
    reporting.register_node_case(PUT, "EMS1-6667", "test_put_ont_service_by_sn")
    reporting.freeze_collection_case_ids([PUT, LIFECYCLE], {LIFECYCLE: {"EMS1-6641"}})
    return reporting.REPORT_STATE


def _register_while_running(monkeypatch, nodeid, case_id, name):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", f"{nodeid} (call)")
    reporting.register_case(case_id, name)


def test_runtime_id_missing_from_the_marker_is_reported_once(monkeypatch, state):
    _register_while_running(monkeypatch, PUT, "EMS1-6699", "test_put_ont_service_by_sn")
    _register_while_running(monkeypatch, PUT, "EMS1-6699", "test_put_ont_service_by_sn")

    lines = report_writer._render_txt_report(_fake_env()).splitlines()

    assert state.case_id_drift == [
        reporting.CaseIdDrift(PUT, "EMS1-6699", "test_put_ont_service_by_sn", ("EMS1-6667",))
    ]
    assert "Case ID Drift: 1 (service registered an id the testlink_case marker does not declare)" in lines
    assert f"Case ID Drift #1: {PUT} registered EMS1-6699; collection had EMS1-6667" in lines
    # The id is still registered as before; the drift only adds header lines.
    assert any(item.case_id == "EMS1-6699" for item in state.case_registry[PUT])


@pytest.mark.parametrize(
    ("nodeid", "case_id"),
    [
        (PUT, "EMS1-6667"),  # same id as the marker
        (LIFECYCLE, "EMS1-6641"),  # declared with testlink_runtime_case
        ("tests/test_other.py::test_not_selected", "EMS1-6699"),  # not part of the frozen selection
    ],
)
def test_declared_or_untracked_ids_are_not_drift(monkeypatch, state, nodeid, case_id):
    _register_while_running(monkeypatch, nodeid, case_id, "name")

    assert state.case_id_drift == []
    assert not any(line.startswith("Case ID Drift") for line in report_writer._render_txt_report(_fake_env()).splitlines())


def test_no_drift_is_recorded_before_collection_freezes_ids(monkeypatch):
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState())
    _register_while_running(monkeypatch, PUT, "EMS1-6699", "name")

    assert reporting.REPORT_STATE.case_id_drift == []


def _attach_case_id_literals() -> dict[str, set[str]]:
    literals: dict[str, set[str]] = {}
    sources = [*ROOT.glob("services/**/*.py"), *ROOT.glob("tests/**/*.py")]
    for path in sources:
        if path.name.startswith("test_case_id_"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) == "attach_case_id"):
                continue
            # register_txt=False only labels Allure (permission summaries); the report never sees the id.
            if any(kw.arg == "register_txt" and getattr(kw.value, "value", True) is False for kw in node.keywords):
                continue
            args = [arg.value for arg in node.args[:2] if isinstance(arg, ast.Constant)]
            if len(args) == 2 and isinstance(args[0], str):
                literals.setdefault(args[0], set()).add(args[1])
    return literals


@pytest.fixture(scope="module")
def collected(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("case_id_drift")
    (tmp_path / "case_id_dump.py").write_text(DUMP_PLUGIN, encoding="utf-8")
    dump = tmp_path / "dump.json"
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(tmp_path), str(ROOT)]), CASE_ID_DUMP=str(dump))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--run-full-testcases",
            "--skip-dut-preflight",
            "-p",
            "no:cacheprovider",
            "-p",
            "case_id_dump",
            f"--alluredir={tmp_path / 'allure'}",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(dump.read_text(encoding="utf-8"))


def test_every_service_literal_id_is_held_by_a_collected_test(collected):
    literals = _attach_case_id_literals()

    assert literals, "the scan found no attach_case_id literals"
    assert sorted(set(literals) - set(collected["held"])) == []


def test_marker_ids_are_known_cases_and_match_service_names(collected):
    known = {case.external_id for case in build_backfill_cases()} | set(case_name_by_id())
    literals = _attach_case_id_literals()

    unknown = sorted({marker[1] for marker in collected["markers"]} - known)
    renamed = sorted(
        (case_id, name)
        for kind, case_id, *rest in collected["markers"]
        if kind == "testlink_case"
        for name in rest
        if case_id in literals and name not in literals[case_id]
    )

    assert unknown == []
    assert renamed == []
