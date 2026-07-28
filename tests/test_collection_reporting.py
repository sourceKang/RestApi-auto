from __future__ import annotations

from types import SimpleNamespace

from tests.support.collection import (
    _apply_node_capability_skips,
    _deselect_internal_tests_from_full_suite,
    _register_neox_case,
    _register_parametrized_case,
    _skip_neox_config_for_non_neox_chassis,
    _skip_neox_config_without_cli_dependency,
    ont_workflow_phase_for_name,
)
from utils import reporting


def test_full_suite_deselects_internal_tests_and_keeps_formal_cases():
    deselected = []

    class Hook:
        @staticmethod
        def pytest_deselected(items):
            deselected.extend(items)

    config = SimpleNamespace(
        getoption=lambda name: name == "--run-full-testcases",
        hook=Hook(),
    )
    internal = SimpleNamespace(keywords={})
    inventory = SimpleNamespace(keywords={"inventory", "readwrite"})
    openapi = SimpleNamespace(keywords={"openapi"})
    items = [internal, inventory, openapi]

    _deselect_internal_tests_from_full_suite(config, items)

    assert items == [inventory, openapi]
    assert deselected == [internal]


def test_regular_collection_keeps_internal_tests():
    config = SimpleNamespace(getoption=lambda name: False)
    internal = SimpleNamespace(keywords={})
    items = [internal]

    _deselect_internal_tests_from_full_suite(config, items)

    assert items == [internal]


def test_formal_only_collection_deselects_internal_tests_without_enabling_full_suite():
    deselected = []

    class Hook:
        @staticmethod
        def pytest_deselected(items):
            deselected.extend(items)

    config = SimpleNamespace(
        getoption=lambda name: name == "--formal-testcases-only",
        hook=Hook(),
    )
    internal = SimpleNamespace(keywords={})
    inventory = SimpleNamespace(keywords={"inventory", "readwrite"})
    items = [internal, inventory]

    _deselect_internal_tests_from_full_suite(config, items)

    assert items == [inventory]
    assert deselected == [internal]


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


def test_collection_skips_neox_config_when_cli_dependency_is_missing(monkeypatch):
    monkeypatch.setattr("tests.support.collection.importlib.util.find_spec", lambda name: None)
    config = SimpleNamespace(getoption=lambda name: False)
    item = SimpleNamespace(keywords={"neox_config"}, markers=[], add_marker=lambda marker: item.markers.append(marker))

    _skip_neox_config_without_cli_dependency(config, [item])

    assert len(item.markers) == 1
    assert "paramiko" in item.markers[0].mark.kwargs["reason"]


def test_collection_allows_rest_only_neox_config_without_cli_dependency(monkeypatch):
    monkeypatch.setattr("tests.support.collection.importlib.util.find_spec", lambda name: None)

    def getoption(name):
        return name == "--skip-neox-cli-verify"

    config = SimpleNamespace(getoption=getoption)
    item = SimpleNamespace(keywords={"neox_config"}, markers=[], add_marker=lambda marker: item.markers.append(marker))

    _skip_neox_config_without_cli_dependency(config, [item])

    assert item.markers == []


def test_collection_skips_neox_config_for_non_neox_chassis():
    config = SimpleNamespace(getoption=lambda name: "NODE1" if name == "--ems-node" else False)
    item = SimpleNamespace(keywords={"neox_config"}, markers=[], add_marker=lambda marker: item.markers.append(marker))

    skipped = _skip_neox_config_for_non_neox_chassis(config, [item])

    assert skipped
    assert len(item.markers) == 1
    assert "selected NODE1 uses IES4204" in item.markers[0].mark.kwargs["reason"]


def test_collection_allows_neox_config_for_neox_chassis():
    config = SimpleNamespace(getoption=lambda name: "NODE3" if name == "--ems-node" else False)
    item = SimpleNamespace(keywords={"neox_config"}, markers=[], add_marker=lambda marker: item.markers.append(marker))

    skipped = _skip_neox_config_for_non_neox_chassis(config, [item])

    assert not skipped
    assert item.markers == []


def test_collection_applies_node_capability_skip(monkeypatch):
    env_config = SimpleNamespace(
        dut=SimpleNamespace(node_key="NODE2", chassis="OLT1408A-C", ge_slot_id=None, ge_port_id=None),
        hardware=SimpleNamespace(supports_slot_inventory=lambda chassis: False),
    )
    monkeypatch.setattr("tests.support.collection.load_environment", lambda **kwargs: env_config)
    config = SimpleNamespace(getoption=lambda name: "NODE2" if name == "--ems-node" else False)
    item = SimpleNamespace(
        name="test_slot_api_invalid_param_should_return_error",
        originalname="test_slot_api_invalid_param_should_return_error",
        callspec=SimpleNamespace(params={}),
        markers=[],
        add_marker=lambda marker: item.markers.append(marker),
    )

    _apply_node_capability_skips(config, [item])

    assert len(item.markers) == 1
    assert "Slot inventory is not supported by OLT1408A-C" in item.markers[0].mark.kwargs["reason"]

def test_ont_workflow_collection_phases_keep_shared_service_lifecycle_ordered():
    phases = [
        ont_workflow_phase_for_name("test_post_ont_service_by_sn", {"provision", "mutating"}),
        ont_workflow_phase_for_name("test_ont_inventory_ready_after_post", {"ont", "readwrite"}),
        ont_workflow_phase_for_name("test_ont_read_endpoints_readwrite", {"ont", "readwrite"}),
        ont_workflow_phase_for_name("test_ont_provision_read_endpoints_readonly", {"provision", "readonly"}),
        ont_workflow_phase_for_name("test_rad_external_readwrite_summary", {"authmatrix"}),
        ont_workflow_phase_for_name("test_put_ont_service_by_sn", {"provision", "mutating"}),
        ont_workflow_phase_for_name("test_patch_ont_service_by_sn", {"provision", "mutating"}),
        ont_workflow_phase_for_name("test_delete_ont_service_by_sn", {"provision", "mutating"}),
        ont_workflow_phase_for_name(
            "test_ont_service_post_various_invalid_parameters_should_return_error",
            {"provision", "mutating"},
        ),
    ]

    assert phases == sorted(phases)
    assert len(set(phases)) == len(phases)

def test_ge_workflow_collection_phases_keep_formal_service_lifecycle_ordered():
    phases = [
        ont_workflow_phase_for_name("test_post_ge_service_by_port", {"provision", "mutating"}),
        ont_workflow_phase_for_name("test_inventory_read_endpoints_readwrite", {"inventory", "readwrite"}),
        ont_workflow_phase_for_name("test_ge_provision_read_endpoints_readonly", {"provision", "readonly"}),
        ont_workflow_phase_for_name("test_rad_external_readwrite_summary", {"authmatrix"}),
        ont_workflow_phase_for_name("test_put_ge_service_by_serviceid", {"provision", "mutating"}),
        ont_workflow_phase_for_name("test_patch_ge_service_by_serviceid", {"provision", "mutating"}),
        ont_workflow_phase_for_name("test_delete_ge_service_by_serviceid", {"provision", "mutating"}),
        ont_workflow_phase_for_name(
            "test_ge_service_post_various_invalid_parameters_should_return_error",
            {"provision", "mutating"},
        ),
    ]

    assert phases == sorted(phases)
    assert len(set(phases)) == len(phases)
