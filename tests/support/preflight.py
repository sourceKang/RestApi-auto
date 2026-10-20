from __future__ import annotations

import pytest

# DutPreflightResult and run_startup_preflight are looked up here at call time, so tests
# can replace tests.support.preflight.run_startup_preflight.
from services.preflight import DutPreflightResult, run_startup_preflight
from tests.support.options import neox_parallel_worker_auth_profile


DUT_DEPENDENT_MARKERS = {
    "alarm",
    "authmatrix",
    "inventory",
    "mutating",
    "noaccess",
    "ont",
    "profile",
    "provision",
    "readonly",
    "readwrite",
    "remoteconsole",
    "session",
}


def skip_unready_dut_items(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--skip-dut-preflight"):
        return

    dut_items = [item for item in items if is_dut_dependent(item)]
    if not dut_items:
        return

    result = run_startup_preflight(
        node=config.getoption("--ems-node"),
        auth_profile=neox_parallel_worker_auth_profile(config),
    )
    if not result.ok:
        skip_dut = pytest.mark.skip(reason=f"DUT preflight failed: {result.reason}")
        for item in dut_items:
            item.add_marker(skip_dut)
        return

    # ONT availability is prepared by the ONT inventory fixture. Checking it
    # during collection would skip the prepare flow before it has a chance to run.


def is_dut_dependent(item: pytest.Item) -> bool:
    return any(marker in item.keywords for marker in DUT_DEPENDENT_MARKERS)


def requires_ont_inventory(item: pytest.Item) -> bool:
    if "ont" in item.keywords:
        return True
    function_name = _function_name(item)
    return function_name.startswith("test_ont_config_")


def _function_name(item: pytest.Item) -> str:
    original = getattr(item, "originalname", None)
    if original:
        return str(original)
    return str(getattr(item, "name", "")).split("[", 1)[0]
