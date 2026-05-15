from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NeoXCase:
    case_id: str
    name: str


DIRECT_NEOX_READWRITE_CASES: dict[str, NeoXCase] = {
    "test_ge_config_clear_readwrite": NeoXCase("NEOX-RW-GE-CLEAR", "test_ge_config_clear_readwrite"),
    "test_ge_config_min_create_readwrite": NeoXCase("NEOX-RW-GE-CREATE-MIN", "test_ge_config_min_create_readwrite"),
    "test_ge_config_max_create_readwrite": NeoXCase("NEOX-RW-GE-CREATE-MAX", "test_ge_config_max_create_readwrite"),
    "test_ge_config_error_readwrite": NeoXCase("NEOX-RW-GE-ERROR", "test_ge_config_error_readwrite"),
    "test_ge_config_set_readwrite": NeoXCase("NEOX-RW-GE-SET-CLI", "test_ge_config_set_readwrite"),
    "test_nni_config_clear_readwrite": NeoXCase("NEOX-RW-NNI-CLEAR", "test_nni_config_clear_readwrite"),
    "test_nni_config_min_create_readwrite": NeoXCase("NEOX-RW-NNI-CREATE-MIN", "test_nni_config_min_create_readwrite"),
    "test_nni_config_max_create_readwrite": NeoXCase("NEOX-RW-NNI-CREATE-MAX", "test_nni_config_max_create_readwrite"),
    "test_nni_config_error_readwrite": NeoXCase("NEOX-RW-NNI-ERROR", "test_nni_config_error_readwrite"),
    "test_vlan_config_clear_readwrite": NeoXCase("NEOX-RW-VLAN-CLEAR", "test_vlan_config_clear_readwrite"),
    "test_vlan_config_min_create_readwrite": NeoXCase("NEOX-RW-VLAN-CREATE-MIN", "test_vlan_config_min_create_readwrite"),
    "test_vlan_config_max_create_readwrite": NeoXCase("NEOX-RW-VLAN-CREATE-MAX", "test_vlan_config_max_create_readwrite"),
    "test_vlan_config_error_readwrite": NeoXCase("NEOX-RW-VLAN-ERROR", "test_vlan_config_error_readwrite"),
    "test_ont_config_clear_readwrite": NeoXCase("NEOX-RW-ONT-CLEAR", "test_ont_config_clear_readwrite"),
    "test_ont_config_min_create_readwrite": NeoXCase("NEOX-RW-ONT-CREATE-MIN", "test_ont_config_min_create_readwrite"),
    "test_ont_config_max_create_readwrite": NeoXCase("NEOX-RW-ONT-CREATE-MAX", "test_ont_config_max_create_readwrite"),
    "test_ont_config_error_readwrite": NeoXCase("NEOX-RW-ONT-ERROR", "test_ont_config_error_readwrite"),
    "test_ge_acl_retry_probe_set_readwrite": NeoXCase("NEOX-RW-GE-PROBE-ACL-RETRY", "test_ge_acl_retry_probe_set_readwrite"),
    "test_ge_enable_probe_set_readwrite": NeoXCase("NEOX-RW-GE-PROBE-ENABLE", "test_ge_enable_probe_set_readwrite"),
    "test_ge_full_parameter_probe_set_readwrite": NeoXCase("NEOX-RW-GE-PROBE-FULL", "test_ge_full_parameter_probe_set_readwrite"),
    "test_ge_incremental_probe_set_readwrite": NeoXCase("NEOX-RW-GE-PROBE-INCREMENTAL", "test_ge_incremental_probe_set_readwrite"),
    "test_ge_negative_payload_probe_set_readwrite": NeoXCase("NEOX-RW-GE-PROBE-NEGATIVE", "test_ge_negative_payload_probe_set_readwrite"),
    "test_ge_paired_retry_probe_set_readwrite": NeoXCase("NEOX-RW-GE-PROBE-PAIRED-RETRY", "test_ge_paired_retry_probe_set_readwrite"),
    "test_ge_pdf_derived_probe_set_readwrite": NeoXCase("NEOX-RW-GE-PROBE-PDF-DERIVED", "test_ge_pdf_derived_probe_set_readwrite"),
}


PROFILE_OPERATION_CASE_PREFIXES: dict[str, tuple[str, str]] = {
    "test_neox_profile_clear_readwrite": ("NEOX-RW-PROFILE-CLEAR", "test_neox_profile_clear_readwrite"),
    "test_neox_profile_min_create_readwrite": ("NEOX-RW-PROFILE-CREATE-MIN", "test_neox_profile_min_create_readwrite"),
    "test_neox_profile_max_create_readwrite": ("NEOX-RW-PROFILE-CREATE-MAX", "test_neox_profile_max_create_readwrite"),
    "test_neox_profile_error_readwrite": ("NEOX-RW-PROFILE-ERROR", "test_neox_profile_error_readwrite"),
}


PROFILE_CONFIG_CASE_PREFIXES: dict[str, tuple[str, str]] = {
    "test_neox_basic_profile_clear_readwrite": ("NEOX-RW-PROFILE-BASIC-CLEAR", "test_neox_basic_profile_clear_readwrite"),
    "test_neox_basic_profile_max_create_readwrite": ("NEOX-RW-PROFILE-BASIC-CREATE-MAX", "test_neox_basic_profile_max_create_readwrite"),
    "test_neox_qos_profile_minmax_create_readwrite": ("NEOX-RW-PROFILE-QOS-CREATE", "test_neox_qos_profile_minmax_create_readwrite"),
    "test_neox_qos_profile_minmax_clear_readwrite": ("NEOX-RW-PROFILE-QOS-CLEAR", "test_neox_qos_profile_minmax_clear_readwrite"),
}


def neox_case_for_item(item: Any) -> NeoXCase | None:
    function_name = _function_name(item)
    direct = DIRECT_NEOX_READWRITE_CASES.get(function_name)
    if direct:
        return direct

    callspec = getattr(item, "callspec", None)
    params = getattr(callspec, "params", {})
    if not isinstance(params, dict):
        return None

    if function_name in PROFILE_OPERATION_CASE_PREFIXES:
        profile_type = params.get("profile_type")
        if not profile_type:
            return None
        prefix, name = PROFILE_OPERATION_CASE_PREFIXES[function_name]
        return NeoXCase(f"{prefix}-{_case_id_part(profile_type)}", f"{name}[{profile_type}]")

    if function_name in PROFILE_CONFIG_CASE_PREFIXES:
        case = params.get("case")
        if not isinstance(case, dict):
            return None
        profile_type = case.get("profile_type")
        if not profile_type:
            return None
        prefix, name = PROFILE_CONFIG_CASE_PREFIXES[function_name]
        parts = [prefix, _case_id_part(profile_type)]
        boundary = case.get("boundary")
        if boundary:
            parts.append(_case_id_part(boundary))
        profile_name = case.get("profile_name")
        if profile_name:
            parts.append(_case_id_part(profile_name))
        return NeoXCase("-".join(parts), f"{name}[{_profile_case_name(case)}]")

    return None


def _function_name(item: Any) -> str:
    original = getattr(item, "originalname", None)
    if original:
        return str(original)
    return str(getattr(item, "name", "")).split("[", 1)[0]


def _profile_case_name(case: dict[str, Any]) -> str:
    values = [str(case["profile_type"])]
    if case.get("boundary"):
        values.append(str(case["boundary"]))
    if case.get("profile_name"):
        values.append(str(case["profile_name"]))
    return "::".join(values)


def _case_id_part(value: Any) -> str:
    text = str(value).strip()
    chars = [char.upper() if char.isalnum() else "-" for char in text]
    slug = "".join(chars).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "UNKNOWN"
