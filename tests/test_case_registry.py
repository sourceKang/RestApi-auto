from __future__ import annotations

from cases import registry as cases
from cases.endpoint_cases import MUTATING_ENDPOINTS, READ_ENDPOINTS


def test_automated_registry_contains_all_endpoint_case_ids():
    endpoint_ids = {
        case.case_id
        for case in [*READ_ENDPOINTS, *MUTATING_ENDPOINTS]
        if case.case_id
    }

    assert endpoint_ids <= cases.automated_case_ids()


def test_report_order_and_names_match_case_catalog():
    names = cases.case_name_by_id()
    order = cases.case_order()

    assert names["EMS1-6640"] == "test_get_sessionid"
    assert names["EMS1-6643"] == "test_get_device_all"
    assert order["EMS1-6640"] < order["EMS1-6643"] < order["EMS1-6666"]


def test_summary_case_ids_are_registered_as_fixed_contracts():
    assert cases.permission_summary_specs() == (
        ("EMS1-7109", "readonly", "readonly_permission_summary"),
        ("EMS1-7110", "noaccess", "noaccess_permission_summary"),
    )
    assert {"EMS1-7056", "EMS1-7107", "EMS1-7108"} <= cases.automated_case_ids()


def test_openapi_yaml_case_id_is_registered():
    assert "EMS1-7116" in cases.automated_case_ids()
    assert "EMS1-7210" in cases.automated_case_ids()
