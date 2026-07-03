from __future__ import annotations

import importlib.util
import os
import re

import pytest

from cases.neox_case_ids import neox_case_for_item
from cases.registry import RAD_SUMMARY_CASES
from tests.support.options import option_or_full_testcases
from tests.support.preflight import skip_unready_dut_items
from utils.reporting import register_node_case, register_permission_role


RAD_AUTH_MATRIX_CASES = {
    "test_rad_external_readwrite_summary": ("EMS1-7056", "rad_external_readwrite_summary"),
    "test_rad_external_readonly_summary": ("EMS1-7107", "rad_external_readonly_summary"),
    "test_rad_external_noaccess_summary": ("EMS1-7108", "rad_external_noaccess_summary"),
}

for case in RAD_SUMMARY_CASES:
    RAD_AUTH_MATRIX_CASES.setdefault(f"test_{case.name}", (case.case_id, case.name))


NEOX_PARALLEL_NODE_CONFIG_SUFFIX = "node_config"
NEOX_PARALLEL_DEVICE_SCOPE_SUFFIX = "device_scoped"
NEOX_PARALLEL_EMS_SCOPE_GROUP = "ems_global_exclusive"
NEOX_PARALLEL_RESOURCE_GROUPS = {
    "ge": "ge_port",
    "nni": "nni_port",
    "vlan": "vlan",
    "ont": "ont_1",
    "profile": "profile_ns",
}
NEOX_DEVICE_SCOPED_CASES = {
    "test_ge_config_max_variant_readwrite",
    "test_ont_config_error_readwrite",
}
NEOX_EMS_SCOPED_CASES: set[str] = set()

@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    run_auth_matrix = option_or_full_testcases(config, "--auth-matrix")
    skip_unready_dut_items(config, items)
    if not option_or_full_testcases(config, "--run-remote"):
        skip_remote = pytest.mark.skip(reason="remote console tests require --run-remote")
        for item in items:
            if "remoteconsole" in item.keywords:
                item.add_marker(skip_remote)
    if not option_or_full_testcases(config, "--run-alarm-delete"):
        skip_alarm_delete = pytest.mark.skip(reason="history alarm delete tests require --run-alarm-delete")
        for item in items:
            if "alarm_delete" in item.keywords:
                item.add_marker(skip_alarm_delete)
    if not option_or_full_testcases(config, "--run-neox-config"):
        skip_neox_config = pytest.mark.skip(reason="NeoX configuration tests require --run-neox-config")
        for item in items:
            if "neox_config" in item.keywords:
                item.add_marker(skip_neox_config)
    else:
        _skip_neox_config_without_cli_dependency(config, items)
    if not config.getoption("--run-neox-probe"):
        deselected = [item for item in items if "neox_probe" in item.keywords]
        if deselected:
            items[:] = [item for item in items if "neox_probe" not in item.keywords]
            config.hook.pytest_deselected(items=deselected)
    if not run_auth_matrix:
        skip_auth_matrix = pytest.mark.skip(reason="RAD external summary tests require --auth-matrix")
        for item in items:
            if "authmatrix" in item.keywords:
                item.add_marker(skip_auth_matrix)
    _apply_neox_parallel_groups(config, items)
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
        _register_parametrized_case(item)
        _register_neox_case(item)
        register_permission_role(item.nodeid, role)


def _apply_neox_parallel_groups(config: pytest.Config, items: list[pytest.Item]) -> None:
    mode = str(config.getoption("--neox-parallel-mode") or "off")
    if mode == "off":
        return
    node_key = neox_parallel_node_key(config)
    cli_verify = not bool(config.getoption("--skip-neox-cli-verify"))
    for item in items:
        group = neox_parallel_group_for_item(item, mode, node_key=node_key, cli_verify=cli_verify)
        if not group:
            continue
        scope = neox_parallel_scope_for_name(_function_name(item), set(str(keyword) for keyword in item.keywords))
        if scope:
            item.add_marker(pytest.mark.neox_parallel_scope(scope))
            item.user_properties.append(("neox_parallel_scope", scope))
        item.add_marker(pytest.mark.neox_parallel_group(group))
        item.add_marker(pytest.mark.xdist_group(group))
        item.user_properties.append(("neox_parallel_group", group))


def neox_parallel_group_for_item(
    item: pytest.Item,
    mode: str,
    *,
    node_key: str | None = None,
    cli_verify: bool = True,
) -> str | None:
    keywords = set(str(keyword) for keyword in item.keywords)
    return neox_parallel_group_for_name(_function_name(item), keywords, mode, node_key=node_key, cli_verify=cli_verify)


def neox_parallel_group_for_name(
    function_name: str,
    keywords: set[str],
    mode: str,
    *,
    node_key: str | None = "NODE3",
    cli_verify: bool = False,
) -> str | None:
    if mode == "off" or "neox_config" not in keywords:
        return None
    node_prefix = neox_parallel_group_prefix(node_key)
    if mode == "conservative":
        return neox_parallel_group_name(node_prefix, NEOX_PARALLEL_NODE_CONFIG_SUFFIX)
    if mode != "resource":
        raise ValueError(f"Unsupported NeoX parallel mode: {mode}")

    scope = neox_parallel_scope_for_name(function_name, keywords)
    if scope == "ems":
        return NEOX_PARALLEL_EMS_SCOPE_GROUP
    if scope == "device":
        return neox_parallel_group_name(node_prefix, NEOX_PARALLEL_NODE_CONFIG_SUFFIX)

    if cli_verify and "mutating" in keywords:
        return neox_parallel_group_name(node_prefix, NEOX_PARALLEL_NODE_CONFIG_SUFFIX)
    if "neox_profile" in keywords or function_name.startswith("test_neox_profile_"):
        return neox_parallel_group_name(node_prefix, NEOX_PARALLEL_RESOURCE_GROUPS["profile"])
    for prefix, resource in (
        ("test_ge_config_", NEOX_PARALLEL_RESOURCE_GROUPS["ge"]),
        ("test_nni_config_", NEOX_PARALLEL_RESOURCE_GROUPS["nni"]),
        ("test_vlan_config_", NEOX_PARALLEL_RESOURCE_GROUPS["vlan"]),
        ("test_ont_config_", NEOX_PARALLEL_RESOURCE_GROUPS["ont"]),
    ):
        if function_name.startswith(prefix):
            return neox_parallel_group_name(node_prefix, resource)
    return neox_parallel_group_name(node_prefix, NEOX_PARALLEL_NODE_CONFIG_SUFFIX)


def neox_parallel_scope_for_name(function_name: str, keywords: set[str]) -> str | None:
    if "ems_scoped" in keywords or function_name in NEOX_EMS_SCOPED_CASES:
        return "ems"
    if "device_scoped" in keywords or function_name in NEOX_DEVICE_SCOPED_CASES:
        return "device"
    return None


def neox_parallel_node_key(config: pytest.Config) -> str:
    return str(config.getoption("--ems-node") or os.environ.get("EMS_NODE") or "node")


def neox_parallel_group_prefix(node_key: str | None) -> str:
    return safe_group_part(str(node_key or "node"))


def neox_parallel_group_name(node_prefix: str, resource_suffix: str) -> str:
    return f"{node_prefix}_{safe_group_part(resource_suffix)}"


def safe_group_part(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return cleaned or "node"

def _function_name(item: pytest.Item) -> str:
    original = getattr(item, "originalname", None)
    if original:
        return str(original)
    return str(getattr(item, "name", "")).split("[", 1)[0]


def _skip_neox_config_without_cli_dependency(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--skip-neox-cli-verify"):
        return
    if importlib.util.find_spec("paramiko") is not None:
        return

    skip_missing_paramiko = pytest.mark.skip(
        reason=(
            "NeoX config CLI verification requires paramiko; run with the project .venv, "
            "install requirements.txt, or use --skip-neox-cli-verify for REST-only execution."
        )
    )
    for item in items:
        if "neox_config" in item.keywords:
            item.add_marker(skip_missing_paramiko)


def _register_parametrized_case(item: pytest.Item) -> None:
    callspec = getattr(item, "callspec", None)
    params = getattr(callspec, "params", {})
    case = params.get("case") if isinstance(params, dict) else None
    if case is None:
        return
    register_node_case(
        item.nodeid,
        getattr(case, "case_id", None),
        str(getattr(case, "name", "")),
    )


def _register_neox_case(item: pytest.Item) -> None:
    case = neox_case_for_item(item)
    if case is None:
        return
    register_node_case(item.nodeid, case.case_id, case.name)
