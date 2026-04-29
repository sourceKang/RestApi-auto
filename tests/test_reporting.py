from __future__ import annotations

from types import SimpleNamespace

from utils import reporting


def _fake_env():
    dut = SimpleNamespace(
        node_key="NODE1",
        device_name="DemoNode",
        device_ip="192.0.2.10",
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
            "ont": {"slot_id": "2"},
            "ge_service": {"slot_id": "1"},
        },
    )
    raw = {
        "EMS": {"version": "demo"},
        "ZYXEL_DUT": {
            "NODE1": {
                "chassis": "IES4204",
                "CARDINFO": {"MSC": {"fw_version": "V2.03", "port_type": "network"}},
            }
        },
    }
    return SimpleNamespace(base_url="https://example.invalid", raw=raw, dut=dut, hardware=hardware)


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
    assert any("[PERM-RO][readonly_permission_summary] Result Fail" in line for line in case_lines)
    assert any("[PERM-NA][noaccess_permission_summary] Result Pass" in line for line in case_lines)
    assert len(case_lines) == 5


def test_permission_summary_treats_skip_as_non_blocking_when_other_cases_pass(monkeypatch):
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState(timestamp="2026-04-29_12-00-00"))

    reporting.register_permission_role("tests/test_inventory.py::test_inventory_read_endpoints_readonly[port_list]", "readonly")
    reporting.record_result("tests/test_inventory.py::test_inventory_read_endpoints_readonly[port_list]", "skipped", 0.05)

    reporting.register_permission_role("tests/test_inventory.py::test_inventory_read_endpoints_readonly[device_list]", "readonly")
    reporting.record_result("tests/test_inventory.py::test_inventory_read_endpoints_readonly[device_list]", "passed", 0.07)

    rendered = reporting._render_txt_report(_fake_env())
    case_lines = [line for line in rendered.splitlines() if line.startswith("[")]

    assert any("[PERM-RO][readonly_permission_summary] Result Pass" in line for line in case_lines)
