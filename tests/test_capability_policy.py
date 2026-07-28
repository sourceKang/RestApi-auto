from __future__ import annotations

from types import SimpleNamespace

from tests.support.capabilities import capability_skip_reason


def _item(function_name: str, case_name: str = ""):
    case = SimpleNamespace(name=case_name) if case_name else None
    return SimpleNamespace(
        name=function_name,
        originalname=function_name,
        callspec=SimpleNamespace(params={"case": case} if case else {}),
    )


def _env(*, slot_inventory: bool, ge_target: bool):
    return SimpleNamespace(
        dut=SimpleNamespace(
            node_key="NODE2",
            chassis="OLT1408A-C",
            ge_slot_id="1" if ge_target else "",
            ge_port_id="39" if ge_target else "",
        ),
        hardware=SimpleNamespace(supports_slot_inventory=lambda _chassis: slot_inventory),
    )


def test_slot_capability_policy_covers_endpoint_cases_and_direct_invalid_case():
    env = _env(slot_inventory=False, ge_target=False)

    assert capability_skip_reason(_item("test_inventory", "slot_by_id"), env) == (
        "Slot inventory is not supported by OLT1408A-C"
    )
    assert capability_skip_reason(
        _item("test_slot_api_with_invalid_parameters_should_return_error"),
        env,
    ) == "Slot inventory is not supported by OLT1408A-C"


def test_ge_capability_policy_covers_direct_and_parameterized_cases():
    env = _env(slot_inventory=True, ge_target=False)

    assert capability_skip_reason(_item("test_post_ge_service_by_port"), env) == (
        "GE service tests require a configured GE target for NODE2"
    )
    assert capability_skip_reason(_item("test_provision", "ge_service_by_port"), env) == (
        "GE service tests require a configured GE target for NODE2"
    )


def test_capability_policy_allows_supported_cases():
    env = _env(slot_inventory=True, ge_target=True)

    assert capability_skip_reason(_item("test_inventory", "slot_by_id"), env) is None
    assert capability_skip_reason(_item("test_post_ge_service_by_port"), env) is None
    assert capability_skip_reason(_item("test_ont_read_endpoints", "ont_by_id"), env) is None
