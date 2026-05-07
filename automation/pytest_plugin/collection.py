from __future__ import annotations

import pytest

from automation.registry.legacy import RAD_SUMMARY_CASES
from automation.pytest_plugin.preflight import skip_unready_dut_items
from utils.reporting import register_node_case, register_permission_role


RAD_AUTH_MATRIX_CASES = {
    "test_rad_external_readwrite_summary": ("EMS1-7056", "rad_external_readwrite_summary"),
    "test_rad_external_readonly_summary": ("EMS1-7107", "rad_external_readonly_summary"),
    "test_rad_external_noaccess_summary": ("EMS1-7108", "rad_external_noaccess_summary"),
}

for case in RAD_SUMMARY_CASES:
    RAD_AUTH_MATRIX_CASES.setdefault(f"test_{case.name}", (case.case_id, case.name))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    run_auth_matrix = config.getoption("--auth-matrix")
    skip_unready_dut_items(config, items)
    if not config.getoption("--run-remote"):
        skip_remote = pytest.mark.skip(reason="remote console tests require --run-remote")
        for item in items:
            if "remoteconsole" in item.keywords:
                item.add_marker(skip_remote)
    if not config.getoption("--run-alarm-delete"):
        skip_alarm_delete = pytest.mark.skip(reason="history alarm delete tests require --run-alarm-delete")
        for item in items:
            if "alarm_delete" in item.keywords:
                item.add_marker(skip_alarm_delete)
    if not run_auth_matrix:
        skip_auth_matrix = pytest.mark.skip(reason="RAD external summary tests require --auth-matrix")
        for item in items:
            if "authmatrix" in item.keywords:
                item.add_marker(skip_auth_matrix)
    for item in items:
        if "authmatrix" in item.keywords:
            if run_auth_matrix:
                case = RAD_AUTH_MATRIX_CASES.get(item.name)
                if case is not None:
                    register_node_case(item.nodeid, case[0], case[1])
            continue
        role = None
        if "readonly" in item.keywords:
            role = "readonly"
        elif "noaccess" in item.keywords:
            role = "noaccess"
        register_permission_role(item.nodeid, role)
