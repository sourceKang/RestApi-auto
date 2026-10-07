from __future__ import annotations

from types import SimpleNamespace

from utils import reporting


def _fake_env():
    dut = SimpleNamespace(
        node_key="NODE1",
        device_name="DemoNode",
        device_ip="192.0.2.10",
        chassis="IES4204",
        slot_id="2",
        port_id="16",
        ont_id="1",
        ont_sn="SN1234567890",
        ont_template="#RestApi_ont_template",
        ge_slot_id="1",
        ge_port_id="39",
        ge_template="#RestApi_ge_template",
    )
    hardware = SimpleNamespace(
        controller_card_name=lambda node_key, node: "MSC1240QB",
        report_card_entries=lambda node_key, node: [("MSC1240QB", "MSC", {"fw_version": "V2.03"})],
        node_target=lambda node_key: {
            "chassis": "IES4204",
            "ont": {"slot_id": "2"},
            "ge_service": {"slot_id": "1"},
            "cards": {"MSC": {"fw_version": "V2.03", "port_type": "network"}},
        },
    )
    node_target = hardware.node_target("NODE1")
    readwrite_account = SimpleNamespace(account_name="default", username="admin")
    readonly_account = SimpleNamespace(account_name="default", username="RestApiRO")
    noaccess_account = SimpleNamespace(account_name="default", username="RestApiNA")
    return SimpleNamespace(
        base_url="https://example.invalid",
        ems_version="demo",
        dut=dut,
        hardware=hardware,
        node_target=node_target,
        auth_profile="default",
        readwrite_account=readwrite_account,
        readonly_account=readonly_account,
        noaccess_account=noaccess_account,
    )


def test_txt_report_aggregates_permission_cases_and_suppresses_internal_tests(monkeypatch):
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState(timestamp="2026-04-28_12-00-00"))

    reporting.REPORT_STATE.case_registry["tests/test_inventory.py::test_inventory_read_endpoints_readwrite[device_list]"] = [
        reporting.CaseRegistration(case_id="EMS1-6643", name="device_list")
    ]
    reporting.record_result("tests/test_inventory.py::test_inventory_read_endpoints_readwrite[device_list]", "passed", 0.11)

    reporting.register_permission_role(
        "tests/test_inventory.py::test_inventory_read_endpoints_readonly[device_list]",
        "readonly",
    )
    reporting.REPORT_STATE.case_registry[
        "tests/test_inventory.py::test_inventory_read_endpoints_readonly[device_list]"
    ] = [reporting.CaseRegistration(case_id="EMS1-6643", name="device_list")]
    reporting.record_result(
        "tests/test_inventory.py::test_inventory_read_endpoints_readonly[device_list]",
        "failed",
        0.07,
    )

    reporting.register_permission_role("tests/test_alarm.py::test_alarm_noaccess_is_rejected", "noaccess")
    reporting.REPORT_STATE.case_registry["tests/test_alarm.py::test_alarm_noaccess_is_rejected"] = [
        reporting.CaseRegistration(
            case_id="EMS1-7029",
            name="test_active_alarm_various_invalid_parameters_should_return_error",
        )
    ]
    reporting.record_result("tests/test_alarm.py::test_alarm_noaccess_is_rejected", "passed", 0.21)

    reporting.register_permission_role("tests/test_remote.py::test_remote_console_noaccess_rejected", "noaccess")
    reporting.REPORT_STATE.case_registry["tests/test_remote.py::test_remote_console_noaccess_rejected"] = [
        reporting.CaseRegistration(
            case_id="EMS1-7022",
            name="test_post_remote_console_invalid_param_should_return_error",
        )
    ]
    reporting.record_result("tests/test_remote.py::test_remote_console_noaccess_rejected", "passed", 0.19)

    reporting.record_result("tests/test_hardware_config.py::test_node1_report_cards_are_yaml_targeted", "passed", 0.01)

    rendered = reporting._render_txt_report(_fake_env())
    case_lines = [line for line in rendered.splitlines() if line.startswith("[")]

    assert all("NO_CASE_ID" not in line for line in case_lines)
    assert any("[EMS1-6643][test_get_device_all]" in line and "Result Pass" in line for line in case_lines)
    assert any("[EMS1-7029][test_active_alarm_various_invalid_parameters_should_return_error]" in line for line in case_lines)
    assert any("[EMS1-7022][test_post_remote_console_invalid_param_should_return_error]" in line for line in case_lines)
    assert any("[EMS1-7109][readonly_permission_summary] Result Fail" in line for line in case_lines)
    assert any("[EMS1-7110][noaccess_permission_summary] Result Pass" in line for line in case_lines)
    assert len(case_lines) == 5


def test_permission_summary_treats_skip_as_non_blocking_when_other_cases_pass(monkeypatch):
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState(timestamp="2026-04-29_12-00-00"))

    reporting.register_permission_role("tests/test_inventory.py::test_inventory_read_endpoints_readonly[unsupported_case]", "readonly")
    reporting.record_result("tests/test_inventory.py::test_inventory_read_endpoints_readonly[unsupported_case]", "skipped", 0.05)

    reporting.register_permission_role("tests/test_inventory.py::test_inventory_read_endpoints_readonly[device_list]", "readonly")
    reporting.record_result("tests/test_inventory.py::test_inventory_read_endpoints_readonly[device_list]", "passed", 0.07)

    rendered = reporting._render_txt_report(_fake_env())
    case_lines = [line for line in rendered.splitlines() if line.startswith("[")]

    assert any("[EMS1-7109][readonly_permission_summary] Result Pass" in line for line in case_lines)


def test_permission_summary_breakdown_lists_failed_members(monkeypatch):
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState(timestamp="2026-04-30_12-00-00"))

    reporting.register_permission_role("tests/test_inventory.py::test_inventory_read_endpoints_readonly[device_list]", "readonly")
    reporting.REPORT_STATE.case_registry["tests/test_inventory.py::test_inventory_read_endpoints_readonly[device_list]"] = [
        reporting.CaseRegistration(case_id="EMS1-6643", name="device_list")
    ]
    reporting.record_result("tests/test_inventory.py::test_inventory_read_endpoints_readonly[device_list]", "passed", 0.07)

    reporting.register_permission_role("tests/test_inventory.py::test_inventory_read_endpoints_readonly[ont_by_id]", "readonly")
    reporting.REPORT_STATE.case_registry["tests/test_inventory.py::test_inventory_read_endpoints_readonly[ont_by_id]"] = [
        reporting.CaseRegistration(case_id="EMS1-6678", name="ont_by_id")
    ]
    reporting.record_result("tests/test_inventory.py::test_inventory_read_endpoints_readonly[ont_by_id]", "failed", 0.12)

    breakdown = reporting.permission_summary_breakdown("readonly")

    assert breakdown["case_id"] == "EMS1-7109"
    assert breakdown["outcome"] == "failed"
    assert breakdown["failed"] == 1
    assert len(breakdown["failed_items"]) == 1
    assert breakdown["failed_items"][0]["case_ids"] == ["EMS1-6678"]


def test_html_report_summarizes_results_and_failed_cases(monkeypatch):
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState(timestamp="2026-05-01_12-00-00"))

    reporting.REPORT_STATE.case_registry["tests/test_inventory.py::test_inventory_read_endpoints_readwrite[device_list]"] = [
        reporting.CaseRegistration(case_id="EMS1-6643", name="device_list")
    ]
    reporting.record_result("tests/test_inventory.py::test_inventory_read_endpoints_readwrite[device_list]", "passed", 0.11)

    reporting.REPORT_STATE.case_registry["tests/test_inventory.py::test_inventory_read_endpoints_readwrite[ont_by_id]"] = [
        reporting.CaseRegistration(case_id="EMS1-6678", name="ont_by_id")
    ]
    reporting.record_result("tests/test_inventory.py::test_inventory_read_endpoints_readwrite[ont_by_id]", "failed", 0.12)

    rendered = reporting._render_html_report(_fake_env())

    assert "<title>Web_Ems_Rest_Api_demo_IES4204_MSC1240QB_report_2026-05-01_12-00-00</title>" in rendered
    assert '<strong class="status status-failed">FAIL</strong>' in rendered
    assert "<td>EMS1-6643</td>" in rendered
    assert "<td>EMS1-6678</td>" in rendered
    assert '<span class="pill pill-failed">Fail</span>' in rendered
    assert "?祆活瘝?憭望??" not in rendered


def test_html_report_escapes_metadata_and_case_names(monkeypatch):
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState(timestamp="2026-05-02_12-00-00"))

    reporting.REPORT_STATE.case_registry["tests/test_inventory.py::test_inventory_read_endpoints_readwrite[xss]"] = [
        reporting.CaseRegistration(case_id="EMS1-9999", name="<script>alert(1)</script>")
    ]
    reporting.record_result("tests/test_inventory.py::test_inventory_read_endpoints_readwrite[xss]", "failed", 0.1)

    env = _fake_env()
    env.dut.device_name = "<NODE3>"

    rendered = reporting._render_html_report(env)

    assert "&lt;NODE3&gt;" in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "<script>alert(1)</script>" not in rendered


def test_session_metrics_are_allowlisted_and_rendered_without_sensitive_values(monkeypatch):
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState(timestamp="2026-05-02_13-00-00"))
    reporting.set_session_metrics(
        {
            "mode": "on",
            "login_requests": 2,
            "logout_requests": 1,
            "cache_hits": 7,
            "cache_misses": 1,
            "session_generations": {"readwrite": 1},
            "session_id": "must-not-appear",
            "token": "must-not-appear-either",
        }
    )

    txt = reporting._render_txt_report(_fake_env())
    html = reporting._render_html_report(_fake_env())

    assert "Session Cache Mode: on" in txt
    assert "Session Cache Hits: 7" in txt
    assert "Session Generations: readwrite=1" in txt
    assert "Session Cache Mode" in html
    assert "must-not-appear" not in txt + html


def test_write_reports_generates_integrated_evidence_report_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState(timestamp="2026-05-03_12-00-00"))
    reporting.REPORT_STATE.case_registry["tests/test_inventory.py::test_inventory_read_endpoints_readwrite[device_list]"] = [
        reporting.CaseRegistration(case_id="EMS1-6643", name="test_get_device_all")
    ]
    reporting.record_result("tests/test_inventory.py::test_inventory_read_endpoints_readwrite[device_list]", "passed", 0.11)

    allure_current = tmp_path / "reports" / ".allure-results-current"
    allure_current.mkdir(parents=True)
    (allure_current / "request-attachment.json").write_text('{"method":"GET","url":"https://example.invalid/device"}', encoding="utf-8")
    (allure_current / "response-attachment.json").write_text('{"status_code":200,"body":{"retstatus":"Success"}}', encoding="utf-8")
    (allure_current / "case-result.json").write_text(
        """
{
  "name": "test_get_device_all",
  "status": "passed",
  "start": 1,
  "stop": 12,
  "fullName": "tests.test_inventory#test_inventory_read_endpoints_readwrite",
  "links": [{"type": "tms", "url": "EMS1-6643", "name": "EMS1-6643"}],
  "steps": [{
    "name": "GET /device",
    "status": "passed",
    "start": 2,
    "stop": 10,
    "attachments": [
      {"name": "request abc", "source": "request-attachment.json", "type": "application/json"},
      {"name": "response abc", "source": "response-attachment.json", "type": "application/json"}
    ]
  }]
}
""".strip(),
        encoding="utf-8",
    )
    for index, status in enumerate(("failed", "broken", "skipped"), start=1):
        (allure_current / f"extra{index}-result.json").write_text(
            f'{{"name": "test_extra_{status}", "status": "{status}", "start": 1, "stop": 2}}',
            encoding="utf-8",
        )
    config = SimpleNamespace(
        rootpath=tmp_path,
        option=SimpleNamespace(
            allure_report_dir=str(allure_current),
            archive_allure=False,
            generate_allure_html=False,
            skip_integrated_evidence_report=False,
        ),
    )

    txt_path, html_summary, allure_results, allure_html, integrated_html = reporting.write_reports(config, _fake_env())

    assert txt_path.exists()
    assert html_summary.exists()
    assert allure_html is None
    assert allure_results.name == "allure-results_2026-05-03_12-00-00"
    assert integrated_html is not None
    assert integrated_html.exists()
    summary_rendered = html_summary.read_text(encoding="utf-8")
    assert "Integrated evidence report (open this for case details)" in summary_rendered
    assert "_integrated.html" in summary_rendered
    rendered = integrated_html.read_text(encoding="utf-8")
    assert "Merged case evidence" in rendered
    assert "Photo Issue Comparison" not in rendered
    assert "EMS1-6643 / test_get_device_all" in rendered
    assert "Request / payload" in rendered
    assert "EMS response" in rendered
    assert (
        '<div class="label">Node</div><div class="value">DemoNode</div>'
        '<div class="note">Chassis: IES4204</div>'
    ) in rendered
    assert (
        '<div class="label">pytest raw</div><div class="value">1 / 2 / 1</div>'
        '<div class="note">passed / failed / skipped; failed includes Allure 1 failed + 1 broken</div>'
    ) in rendered
    assert "Node3" not in rendered
    assert "422 / 28 / 5" not in rendered
    assert '<section id="EMS1-6643">' in rendered
    assert "openCaseFromHash" in rendered
    assert "<h2>0 Failures in txt Report</h2>" in rendered


def test_integrated_report_failure_heading_counts_failed_txt_cases(tmp_path):
    from tools.generate_integrated_evidence_report import write_integrated_evidence_report

    txt = tmp_path / "run.txt"
    txt.write_text(
        "Summary: 1 Pass / 2 Fail\n"
        "[EMS1-1][test_a] Result Pass (0.10s)\n"
        "[EMS1-2][test_b] Result Fail (0.20s)\n"
        "[EMS1-3][test_c] Result Fail (0.30s)\n",
        encoding="utf-8",
    )
    allure_dir = tmp_path / "allure"
    allure_dir.mkdir()
    output = tmp_path / "run_integrated.html"

    rendered = write_integrated_evidence_report(
        txt_report=txt, legacy_html=tmp_path / "run.html", allure_dir=allure_dir, output=output
    ).read_text(encoding="utf-8")

    assert "<h2>2 Failures in txt Report</h2>" in rendered
    assert "8 Failures" not in rendered
    assert rendered.count('">open detail</a>') == 2

    txt.write_text("[EMS1-2][test_b] Result Fail (0.20s)\n", encoding="utf-8")
    single = write_integrated_evidence_report(
        txt_report=txt, legacy_html=tmp_path / "run.html", allure_dir=allure_dir, output=output
    ).read_text(encoding="utf-8")
    assert "<h2>1 Failure in txt Report</h2>" in single


def _report_config(tmp_path):
    allure_current = tmp_path / "reports" / ".allure-results-current"
    allure_current.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        rootpath=tmp_path,
        option=SimpleNamespace(
            allure_report_dir=str(allure_current),
            archive_allure=False,
            generate_allure_html=False,
            skip_integrated_evidence_report=False,
        ),
    )


def test_write_reports_skips_sessions_without_testlink_cases(monkeypatch, tmp_path):
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState(timestamp="2026-10-07_12-00-00"))
    config = _report_config(tmp_path)

    # --collect-only: nothing ran at all.
    assert reporting.has_reportable_cases() is False
    assert reporting.write_reports(config, _fake_env()) is None

    # Offline unit tests: results exist but none is registered to a TestLink case.
    reporting.record_result("tests/test_reporting.py::test_something", "passed", 0.01)
    reporting.record_result("tests/test_report_index.py::test_other", "failed", 0.02)
    assert reporting.has_reportable_cases() is False
    assert reporting.write_reports(config, _fake_env()) is None
    assert sorted(path.name for path in (tmp_path / "reports").iterdir()) == [".allure-results-current"]

    reporting.REPORT_STATE.case_registry["tests/test_inventory.py::test_x"] = [
        reporting.CaseRegistration(case_id="EMS1-6643", name="test_get_device_all")
    ]
    reporting.record_result("tests/test_inventory.py::test_x", "passed", 0.11)
    assert reporting.has_reportable_cases() is True
    txt_path, *_ = reporting.write_reports(config, _fake_env())
    assert "[EMS1-6643][test_get_device_all] Result Pass" in txt_path.read_text(encoding="utf-8")


def test_session_finish_reports_skip_instead_of_paths_without_testlink_cases(monkeypatch, tmp_path):
    from tests.support import reporting_hooks

    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState(timestamp="2026-10-07_12-00-00"))
    reporting.record_result("tests/test_reporting.py::test_something", "passed", 0.01)
    monkeypatch.setattr(reporting_hooks, "load_environment", lambda **kwargs: _fake_env())
    monkeypatch.setattr(reporting_hooks, "close_ssh_session_pools", lambda: None)
    lines: list[str] = []
    terminal = SimpleNamespace(write_line=lines.append)
    config = _report_config(tmp_path)
    config.getoption = lambda name, default=None: None
    config.pluginmanager = SimpleNamespace(get_plugin=lambda name: terminal)

    reporting_hooks.pytest_sessionfinish(SimpleNamespace(config=config), 0)

    assert lines == ["EMS report: skipped; no TestLink case results in this session."]
    assert not list((tmp_path / "reports").glob("*/*.txt"))


def test_write_reports_records_ems_target_and_platform(monkeypatch, tmp_path):
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState(timestamp="2026-10-01_12-00-00"))
    reporting.REPORT_STATE.case_registry["tests/test_inventory.py::test_inventory_read_endpoints_readwrite[device_list]"] = [
        reporting.CaseRegistration(case_id="EMS1-6643", name="test_get_device_all")
    ]
    reporting.record_result("tests/test_inventory.py::test_inventory_read_endpoints_readwrite[device_list]", "passed", 0.11)
    allure_current = tmp_path / "reports" / ".allure-results-current"
    allure_current.mkdir(parents=True)
    config = SimpleNamespace(
        rootpath=tmp_path,
        option=SimpleNamespace(
            allure_report_dir=str(allure_current),
            archive_allure=False,
            generate_allure_html=False,
            skip_integrated_evidence_report=False,
        ),
    )
    env = _fake_env()
    env.ems_version = "03.00.11 (AAVV.221) b12"
    env.ems_target = "redhat"
    env.ems_platform = "RedHat 9 (HA)"

    txt_path, html_summary, _, _, integrated_html = reporting.write_reports(config, env)

    assert txt_path.parent.name == "03.00.11 (AAVV.221) b12_redhat"
    txt = txt_path.read_text(encoding="utf-8")
    assert "EMS Version: 03.00.11 (AAVV.221) b12\nEMS Target: redhat\nEMS Platform: RedHat 9 (HA)\n" in txt
    summary = html_summary.read_text(encoding="utf-8")
    assert "<h1>03.00.11 (AAVV.221) b12 (RedHat 9 (HA)) / DemoNode</h1>" in summary
    assert "RedHat 9 (HA)" in integrated_html.read_text(encoding="utf-8")


def test_report_without_ems_target_keeps_version_directory_and_metadata():
    env = _fake_env()

    assert reporting._report_dir_name(env) == "demo"
    assert reporting._ems_server_metadata(env) == []
    assert reporting._ems_heading(env) == "demo"


def test_write_reports_can_skip_integrated_evidence_report(monkeypatch, tmp_path):
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState(timestamp="2026-05-04_12-00-00"))
    reporting.REPORT_STATE.case_registry["tests/test_inventory.py::test_inventory_read_endpoints_readwrite[device_list]"] = [
        reporting.CaseRegistration(case_id="EMS1-6643", name="test_get_device_all")
    ]
    reporting.record_result("tests/test_inventory.py::test_inventory_read_endpoints_readwrite[device_list]", "passed", 0.11)

    allure_current = tmp_path / "reports" / ".allure-results-current"
    allure_current.mkdir(parents=True)
    config = SimpleNamespace(
        rootpath=tmp_path,
        option=SimpleNamespace(
            allure_report_dir=str(allure_current),
            archive_allure=False,
            generate_allure_html=False,
            skip_integrated_evidence_report=True,
        ),
    )

    txt_path, html_summary, *_, integrated_html = reporting.write_reports(config, _fake_env())

    assert txt_path.exists()
    assert html_summary.exists()
    assert integrated_html is None
    assert "Integrated evidence report (open this for case details)" not in html_summary.read_text(encoding="utf-8")
    assert not list((tmp_path / "reports" / "demo").glob("*_integrated.html"))


def test_worker_report_dir_preserves_existing_allure_results(tmp_path):
    allure_current = tmp_path / "reports" / ".allure-results-current"
    allure_current.mkdir(parents=True)
    sentinel = allure_current / "worker-result.json"
    sentinel.write_text('{"status":"passed"}', encoding="utf-8")
    config = SimpleNamespace(
        rootpath=tmp_path,
        option=SimpleNamespace(allure_report_dir=None, clean_alluredir=None),
    )

    reporting.ensure_worker_report_dirs(config)

    assert config.option.allure_report_dir == str(allure_current)
    assert config.option.clean_alluredir is False
    assert sentinel.exists()
