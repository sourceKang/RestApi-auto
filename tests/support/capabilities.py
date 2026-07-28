from __future__ import annotations

from typing import Any


def item_case_name(item: Any) -> str:
    callspec = getattr(item, "callspec", None)
    params = getattr(callspec, "params", {})
    case = params.get("case") if isinstance(params, dict) else None
    return str(getattr(case, "name", ""))


def item_function_name(item: Any) -> str:
    return str(getattr(item, "originalname", None) or getattr(item, "name", ""))


def requires_slot_inventory(item: Any) -> bool:
    return item_case_name(item).startswith("slot_") or item_function_name(item).startswith("test_slot_api_")


def requires_ge_target(item: Any) -> bool:
    function_name = item_function_name(item)
    case_name = item_case_name(item)
    return (
        function_name.startswith("test_ge_")
        or "_ge_service" in function_name
        or "ge_service" in case_name
    )


def capability_skip_reason(item: Any, env_config: Any) -> str | None:
    if (
        requires_slot_inventory(item)
        and not env_config.hardware.supports_slot_inventory(env_config.dut.chassis)
    ):
        return f"Slot inventory is not supported by {env_config.dut.chassis}"
    if requires_ge_target(item) and not (env_config.dut.ge_slot_id and env_config.dut.ge_port_id):
        return f"GE service tests require a configured GE target for {env_config.dut.node_key}"
    return None
