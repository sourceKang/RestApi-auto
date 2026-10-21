from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.support import report_writer, reporting_hooks
from tests.test_reporting import _fake_env
from utils import reporting
from utils.cleanup import CleanupRegistry, StrictCleanupError


pytestmark = pytest.mark.offline

PASSED_NODE = "tests/test_neox_config.py::test_ont_config_clear_readwrite"
FAILED_NODE = "tests/test_neox_config.py::test_ont_config_min_create_readwrite"


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState(timestamp="2026-10-21_10-00-00"))
    for nodeid, case_id in ((PASSED_NODE, "EMS1-7130"), (FAILED_NODE, "EMS1-7124")):
        reporting.REPORT_STATE.case_registry[nodeid] = [reporting.CaseRegistration(case_id=case_id, name=nodeid.rsplit("::", 1)[-1])]
    return reporting.REPORT_STATE


def _raise(message):
    def callback():
        raise AssertionError(message)

    return callback


def test_strict_cleanup_failure_raises_strict_cleanup_error_and_other_failures_stay_silent():
    registry = CleanupRegistry()
    registry.add(_raise("normal cleanup failed"))
    registry.add_strict_final(_raise("restore ONT exact baseline did not converge"))

    with pytest.raises(StrictCleanupError, match="restore ONT exact baseline did not converge"):
        registry.run()

    registry = CleanupRegistry()
    registry.add(_raise("normal cleanup failed"))
    registry.run()


def test_several_strict_failures_are_reported_together():
    registry = CleanupRegistry()
    registry.add_strict_final(_raise("first"))
    registry.add_strict_final(_raise("second"))

    with pytest.raises(StrictCleanupError, match=r"2 strict cleanup callbacks failed: .*first.*second|2 strict cleanup callbacks failed: .*second.*first"):
        registry.run()


def test_strict_teardown_error_blocks_a_passed_case_but_keeps_a_failed_one(state):
    reporting.record_result(PASSED_NODE, "passed", 1.0)
    reporting.record_result(FAILED_NODE, "failed", 2.0)

    reporting.record_teardown_error(PASSED_NODE, "StrictCleanupError: baseline did not converge", strict=True)
    reporting.record_teardown_error(FAILED_NODE, "StrictCleanupError: baseline did not converge", strict=True)

    assert [result.outcome for result in state.results] == ["blocked", "failed"]
    assert len(state.teardown_errors) == 2


def test_other_teardown_error_is_listed_without_changing_the_result(state):
    reporting.record_result(PASSED_NODE, "passed", 1.0)

    reporting.record_teardown_error(PASSED_NODE, "RemoteDisconnected: logout", strict=False)

    assert state.results[0].outcome == "passed"
    lines = report_writer._teardown_error_lines()
    assert lines[0] == "Teardown Errors: 1 (strict cleanup 0, case Blocked unless it already failed; other 1, listed only)"
    assert lines[1] == f"Teardown Error #1: EMS1-7130 {PASSED_NODE} | other teardown | RemoteDisconnected: logout"


def test_txt_report_writes_blocked_result_summary_and_teardown_details(state):
    reporting.record_result(PASSED_NODE, "passed", 1.0)
    reporting.record_result(FAILED_NODE, "failed", 2.0)
    reporting.record_teardown_error(PASSED_NODE, "StrictCleanupError: GET /ont/sn HTTP 500", strict=True)

    rendered = report_writer._render_txt_report(_fake_env())

    assert "Summary: 0 Pass / 1 Fail / 1 Blocked\n" in rendered
    assert "[EMS1-7130][test_ont_config_clear_readwrite] Result Blocked (1s)" in rendered
    assert f"Teardown Error #1: EMS1-7130 {PASSED_NODE} | strict cleanup | StrictCleanupError: GET /ont/sn HTTP 500" in rendered


def test_summary_line_keeps_the_old_format_without_blocked_cases(state):
    reporting.record_result(PASSED_NODE, "passed", 1.0)

    rendered = report_writer._render_txt_report(_fake_env())

    assert "Summary: 1 Pass / 0 Fail\n" in rendered
    assert "Teardown Errors" not in rendered


def test_long_teardown_message_is_truncated_in_the_header(state):
    reporting.record_teardown_error(PASSED_NODE, "x" * 900, strict=True)

    line = report_writer._teardown_error_lines()[1]

    assert line.endswith("x" * report_writer.MAX_TEARDOWN_MESSAGE_CHARS + "... (full text in Allure)")


@pytest.mark.parametrize(
    ("outcomes", "expected"),
    [
        (["passed", "blocked"], "blocked"),
        (["blocked", "failed"], "failed"),
        (["skipped", "blocked"], "blocked"),
        (["passed", "skipped"], "skipped"),
    ],
)
def test_case_outcomes_combine_with_fail_over_blocked_over_skip(outcomes, expected):
    assert report_writer._combine_outcomes(outcomes) == expected


def test_html_report_shows_blocked_card_pill_and_status(state):
    reporting.record_result(PASSED_NODE, "passed", 1.0)
    reporting.record_teardown_error(PASSED_NODE, "StrictCleanupError: restore failed", strict=True)

    rendered = report_writer._render_html_report(_fake_env())

    assert '<strong class="status status-blocked">BLOCKED</strong>' in rendered
    assert '<span class="pill pill-blocked">Blocked</span>' in rendered
    assert "<h2>Blocked Cases (strict cleanup failed)</h2>" in rendered


def _teardown_report(error):
    with pytest.raises(type(error)) as excinfo:
        raise error
    text = f"E   {type(error).__name__}: {error}"
    report = SimpleNamespace(
        when="teardown", failed=True, longrepr=text, longreprtext=text, nodeid=PASSED_NODE, user_properties=[]
    )
    hook = reporting_hooks.pytest_runtest_makereport(item=SimpleNamespace(config=None), call=SimpleNamespace(excinfo=excinfo))
    next(hook)
    with pytest.raises(StopIteration):
        hook.send(SimpleNamespace(get_result=lambda: report))
    return report


@pytest.mark.parametrize(
    ("error", "strict", "outcome"),
    [
        (StrictCleanupError("restore ONT exact baseline did not converge"), True, "blocked"),
        (ConnectionError("RemoteDisconnected during logout"), False, "passed"),
    ],
)
def test_hooks_mark_strict_teardown_failures_blocked(monkeypatch, state, error, strict, outcome):
    monkeypatch.setattr(reporting_hooks, "_known_secret_values", lambda config: ())
    reporting.record_result(PASSED_NODE, "passed", 1.0)

    report = _teardown_report(error)
    reporting_hooks.pytest_runtest_logreport(report)

    assert dict(report.user_properties)[reporting_hooks.TEARDOWN_STRICT_PROPERTY] is strict
    assert state.results[0].outcome == outcome
    assert state.teardown_errors[0].message == f"{type(error).__name__}: {error}"


def test_teardown_message_masks_known_secrets_when_redaction_is_on(monkeypatch, state):
    monkeypatch.setenv("EMS_REPORT_REDACT", "1")
    monkeypatch.setattr(reporting_hooks, "_known_secret_values", lambda config: ("Secret123!",))

    report = _teardown_report(StrictCleanupError("login with Secret123! failed"))

    assert "Secret123!" not in dict(report.user_properties)[reporting_hooks.TEARDOWN_MESSAGE_PROPERTY]


def test_integrated_report_lists_blocked_cases_next_to_failures(tmp_path):
    from utils.integrated_evidence_report import write_integrated_evidence_report

    txt = tmp_path / "run.txt"
    txt.write_text(
        "Summary: 1 Pass / 1 Fail / 1 Blocked\n"
        "[EMS1-1][test_a] Result Pass (0.10s)\n"
        "[EMS1-2][test_b] Result Fail (0.20s)\n"
        "[EMS1-3][test_c] Result Blocked (0.30s)\n",
        encoding="utf-8",
    )
    allure_dir = tmp_path / "allure"
    allure_dir.mkdir()

    rendered = write_integrated_evidence_report(
        txt_report=txt, legacy_html=tmp_path / "run.html", allure_dir=allure_dir, output=tmp_path / "out.html"
    ).read_text(encoding="utf-8")

    assert "<h2>1 Failure, 1 Blocked in txt Report</h2>" in rendered
    assert rendered.count('">open detail</a>') == 2
    assert '<span class="badge partial">Blocked</span>' in rendered
