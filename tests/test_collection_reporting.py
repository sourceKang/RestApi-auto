from __future__ import annotations

from types import SimpleNamespace

from tests.support.collection import _register_neox_case, _register_parametrized_case
from utils import reporting


def test_collection_registers_parametrized_endpoint_case_for_txt_report(monkeypatch):
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState())
    item = SimpleNamespace(
        nodeid="tests/test_inventory.py::test_inventory_read_endpoints_readwrite[device_list]",
        callspec=SimpleNamespace(
            params={
                "case": SimpleNamespace(
                    case_id="EMS1-6643",
                    name="device_list",
                )
            }
        ),
    )

    _register_parametrized_case(item)

    assert reporting.REPORT_STATE.case_registry[item.nodeid] == [
        reporting.CaseRegistration(case_id="EMS1-6643", name="device_list")
    ]


def test_collection_ignores_items_without_endpoint_case(monkeypatch):
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState())
    item = SimpleNamespace(
        nodeid="tests/test_config.py::test_environment_has_expected_rest_api_users",
        callspec=SimpleNamespace(params={}),
    )

    _register_parametrized_case(item)

    assert reporting.REPORT_STATE.case_registry == {}


def test_collection_registers_direct_neox_readwrite_case_for_txt_report(monkeypatch):
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState())
    item = SimpleNamespace(
        name="test_ge_config_clear_readwrite",
        nodeid="tests/test_neox_config.py::test_ge_config_clear_readwrite",
    )

    _register_neox_case(item)

    assert reporting.REPORT_STATE.case_registry[item.nodeid] == [
        reporting.CaseRegistration(case_id="EMS1-7118", name="test_ge_config_clear_readwrite")
    ]


def test_collection_registers_parametrized_neox_profile_case_for_txt_report(monkeypatch):
    monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState())
    item = SimpleNamespace(
        name="test_neox_profile_min_create_readwrite[RateLimitProfile]",
        nodeid=(
            "tests/test_neox_profile.py::"
            "test_neox_profile_min_create_readwrite[RateLimitProfile]"
        ),
        callspec=SimpleNamespace(
            params={
                "profile_type": "RateLimitProfile",
            }
        ),
    )

    _register_neox_case(item)

    assert reporting.REPORT_STATE.case_registry[item.nodeid] == [
        reporting.CaseRegistration(
            case_id="EMS1-7187",
            name="test_neox_profile_min_create_readwrite[RateLimitProfile]",
        )
    ]
