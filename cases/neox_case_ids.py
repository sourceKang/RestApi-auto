from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NeoXCase:
    case_id: str
    name: str


DIRECT_NEOX_READWRITE_CASES: dict[str, NeoXCase] = {
    "test_ge_config_clear_readwrite": NeoXCase("EMS1-7118", "test_ge_config_clear_readwrite"),
    "test_ge_config_min_create_readwrite": NeoXCase("EMS1-7119", "test_ge_config_min_create_readwrite"),
    "test_ge_config_max_create_readwrite": NeoXCase("EMS1-7120", "test_ge_config_max_create_readwrite"),
    "test_ge_config_max_variant_readwrite": NeoXCase("EMS1-7120", "test_ge_config_max_variant_readwrite"),
    "test_ge_config_error_readwrite": NeoXCase("EMS1-7121", "test_ge_config_error_readwrite"),
    "test_nni_config_clear_readwrite": NeoXCase("EMS1-7122", "test_nni_config_clear_readwrite"),
    "test_nni_config_min_create_readwrite": NeoXCase("EMS1-7123", "test_nni_config_min_create_readwrite"),
    "test_nni_config_max_create_readwrite": NeoXCase("EMS1-7124", "test_nni_config_max_create_readwrite"),
    "test_nni_config_error_readwrite": NeoXCase("EMS1-7125", "test_nni_config_error_readwrite"),
    "test_vlan_config_clear_readwrite": NeoXCase("EMS1-7126", "test_vlan_config_clear_readwrite"),
    "test_vlan_config_min_create_readwrite": NeoXCase("EMS1-7127", "test_vlan_config_min_create_readwrite"),
    "test_vlan_config_max_create_readwrite": NeoXCase("EMS1-7128", "test_vlan_config_max_create_readwrite"),
    "test_vlan_config_error_readwrite": NeoXCase("EMS1-7129", "test_vlan_config_error_readwrite"),
    "test_ont_config_clear_readwrite": NeoXCase("EMS1-7130", "test_ont_config_clear_readwrite"),
    "test_ont_config_min_create_readwrite": NeoXCase("EMS1-7131", "test_ont_config_min_create_readwrite"),
    "test_ont_config_max_create_readwrite": NeoXCase("EMS1-7132", "test_ont_config_max_create_readwrite"),
    "test_ont_config_error_readwrite": NeoXCase("EMS1-7133", "test_ont_config_error_readwrite"),
    "test_ont_config_apply_provision_template_sfu_readwrite": NeoXCase(
        "EMS1-7223", "test_ont_config_apply_provision_template_sfu_readwrite"
    ),
}


PROFILE_TYPES: tuple[str, ...] = (
    "IGMPGroupPrivilegeProfile",
    "ONTAclProfile",
    "ONTAlarmProfile",
    "ONTBandwidthProfile",
    "ONTMulticastProfile",
    "ONTONTProfile",
    "ONTSecurityProfile",
    "ONTServiceProfile",
    "ONTTemplateProfile",
    "ONTUNIProfile",
    "ONTVoipCommonProfile",
    "ONTVoipDialPlanProfile",
    "ONTVoipSipProfile",
    "RateLimitProfile",
    "ShapingProfile",
    "WeightProfile",
)


PROFILE_OPERATION_OFFSETS: dict[str, tuple[int, str]] = {
    "test_neox_profile_clear_readwrite": (0, "test_neox_profile_clear_readwrite"),
    "test_neox_profile_min_create_readwrite": (1, "test_neox_profile_min_create_readwrite"),
    "test_neox_profile_max_create_readwrite": (2, "test_neox_profile_max_create_readwrite"),
    "test_neox_profile_error_readwrite": (3, "test_neox_profile_error_readwrite"),
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

    if function_name in PROFILE_OPERATION_OFFSETS:
        profile_type = params.get("profile_type")
        if not profile_type:
            return None
        try:
            profile_index = PROFILE_TYPES.index(str(profile_type))
        except ValueError:
            return None
        offset, name = PROFILE_OPERATION_OFFSETS[function_name]
        case_id = f"EMS1-{7134 + profile_index * 4 + offset}"
        return NeoXCase(case_id, f"{name}[{profile_type}]")

    return None


def _function_name(item: Any) -> str:
    original = getattr(item, "originalname", None)
    if original:
        return str(original)
    return str(getattr(item, "name", "")).split("[", 1)[0]


def _case_id_part(value: Any) -> str:
    text = str(value).strip()
    chars = [char.upper() if char.isalnum() else "-" for char in text]
    slug = "".join(chars).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "UNKNOWN"
