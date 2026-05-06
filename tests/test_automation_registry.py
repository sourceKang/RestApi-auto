from __future__ import annotations

from automation.registry import legacy
from cases.endpoint_cases import MUTATING_ENDPOINTS, READ_ENDPOINTS


def test_automated_registry_contains_all_endpoint_case_ids():
    endpoint_ids = {
        case.case_id
        for case in [*READ_ENDPOINTS, *MUTATING_ENDPOINTS]
        if case.case_id
    }

    assert endpoint_ids <= legacy.automated_case_ids()


def test_legacy_report_order_and_names_match_converted_legacy_registry():
    names = legacy.legacy_case_name_by_id()
    order = legacy.legacy_case_order()

    assert names["EMS1-6640"] == "test_get_sessionid"
    assert names["EMS1-6643"] == "test_get_device_all"
    assert order["EMS1-6640"] < order["EMS1-6643"] < order["EMS1-6666"]


def test_summary_case_ids_are_registered_as_fixed_contracts():
    assert legacy.permission_summary_specs() == (
        ("PERM-RO", "readonly", "readonly_permission_summary"),
        ("PERM-NA", "noaccess", "noaccess_permission_summary"),
    )
    assert {"RAD-RW", "RAD-RO", "RAD-NA"} <= legacy.automated_case_ids()
