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