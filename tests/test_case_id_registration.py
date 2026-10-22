from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.support import report_writer
from tests.support.collection import _register_marked_cases, _register_parametrized_case
from tests.test_reporting import _fake_env
from utils import reporting


pytestmark = pytest.mark.offline

ROOT = Path(__file__).resolve().parents[1]

# Formal tests that are not TestLink cases, or whose ids are all owned by other tests.
ITEMS_WITHOUT_CASE_ID = {
    "tests/test_inventory.py::test_ont_inventory_ready_after_post",
    "tests/test_openapi_yaml.py::test_neox_swagger_nni_summary_matches_openapi_baseline",
    "tests/test_openapi_yaml.py::test_live_neox_swagger_nni_schema_matches_baseline",
}

LIST_PLUGIN = '''
def pytest_collection_finish(session):
    from utils import reporting

    for item in session.items:
        if item.nodeid not in reporting.REPORT_STATE.case_registry:
            print("NO_CASE_ID " + item.nodeid)
'''


def _marked_item(nodeid: str, *cases: tuple[str, str]):
    markers = [SimpleNamespace(args=case) for case in cases]
    return SimpleNamespace(nodeid=nodeid, iter_markers=lambda name: markers if name == "testlink_case" else [])


def test_marked_case_is_registered_at_collection(monkeypatch):
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState())
    item = _marked_item(
        "tests/test_alarm.py::test_alarm_lifecycle_remote_console_to_history_delete",
        ("EMS1-6654", "test_get_active_alarm_by_id"),
        ("EMS1-6659", "test_delete_active_alarm_by_id"),
    )

    _register_marked_cases(item)

    assert reporting.REPORT_STATE.case_registry[item.nodeid] == [
        reporting.CaseRegistration(case_id="EMS1-6654", name="test_get_active_alarm_by_id"),
        reporting.CaseRegistration(case_id="EMS1-6659", name="test_delete_active_alarm_by_id"),
    ]


def test_parametrized_catalog_case_dict_is_registered(monkeypatch):
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState())
    item = SimpleNamespace(
        nodeid="tests/test_profiles.py::test_profile_post_cases[EMS1-6788]",
        callspec=SimpleNamespace(params={"case": {"case_ids": ["EMS1-6788"], "name": "test_post_profile_by_x"}}),
    )

    _register_parametrized_case(item)

    assert reporting.REPORT_STATE.case_registry[item.nodeid] == [
        reporting.CaseRegistration(case_id="EMS1-6788", name="test_post_profile_by_x")
    ]


def test_skipped_main_test_is_not_reported_as_pass_by_permission_variants(monkeypatch):
    # b12 NODE1 (2026-09-08): the readwrite PUT was skipped in setup before its service
    # registered EMS1-6667, so only the passing readonly/noaccess rejections were reported.
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState(timestamp="2026-10-22_12-00-00"))
    main = "tests/test_provision.py::test_put_ont_service_by_sn"
    _register_marked_cases(_marked_item(main, ("EMS1-6667", "test_put_ont_service_by_sn")))
    reporting.record_result(main, "skipped", 0.0)
    for role in ("readonly", "noaccess"):
        nodeid = f"tests/test_provision.py::test_mutating_endpoints_reject_{role}[modify_ont_service]"
        reporting.register_permission_role(nodeid, role)
        reporting.register_node_case(nodeid, "EMS1-6667", "modify_ont_service")
        reporting.record_result(nodeid, "passed", 0.05)

    rendered = report_writer._render_txt_report(_fake_env())
    case_lines = [line for line in rendered.splitlines() if line.startswith("[EMS1-6667]")]

    assert len(case_lines) == 1
    assert "Result Skip" in case_lines[0]


def test_formal_items_have_case_id_at_collection(tmp_path):
    (tmp_path / "case_id_list.py").write_text(LIST_PLUGIN, encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(tmp_path), str(ROOT)]))
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
            "case_id_list",
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

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    missing = {line.split(" ", 1)[1].strip() for line in output.splitlines() if line.startswith("NO_CASE_ID ")}
    assert missing == ITEMS_WITHOUT_CASE_ID
