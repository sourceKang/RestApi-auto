from __future__ import annotations

from typing import Any


def neox_profile_expected_tokens(
    profile_type: str,
    payload: dict[str, Any],
    profile_name: str,
    fallback_tokens: list[str],
) -> list[str]:
    content = payload.get("Content", {})
    tokens = [profile_name]
    if profile_type == "IGMPGroupPrivilegeProfile":
        tokens.extend(content_values(content, ("grpbandwidth", "startip", "endip", "prvitype")))
    elif profile_type == "ONTAclProfile":
        tokens.extend(ont_acl_profile_tokens(content))
    elif profile_type == "ONTAlarmProfile":
        tokens.extend(ont_alarm_profile_tokens(content))
    elif profile_type == "ONTBandwidthProfile":
        tokens.extend(content_values(content, ("sir", "air", "pir")))
    elif profile_type == "ONTMulticastProfile":
        tokens.extend(
            content_values(content, ("univid", "groupprofile", "igmp", "mode", "txtagvid", "txtagpbit", "maxgroup", "maxmsg"))
        )
    elif profile_type == "ONTONTProfile":
        tokens.extend(content_values(content, ("fwlevel", "telnetport")))
    elif profile_type == "ONTSecurityProfile":
        tokens.extend(content_values(content, ("spoofingdisable", "fdb")))
    elif profile_type == "ONTServiceProfile":
        tokens.extend(ont_service_profile_tokens(content))
    elif profile_type == "ONTTemplateProfile":
        tokens.extend(ont_template_profile_tokens(content))
    elif profile_type == "ONTUNIProfile":
        tokens.extend(ont_uni_profile_tokens(content))
    elif profile_type == "ONTVoipCommonProfile":
        tokens.extend(content_values(content, content.keys()))
    elif profile_type == "ONTVoipDialPlanProfile":
        tokens.extend(content_values(content, ("max", "critical", "partial", "format", "identifier")))
    elif profile_type == "ONTVoipSipProfile":
        tokens.extend(content_values(content, content.keys()))
    elif profile_type == "RateLimitProfile":
        tokens.extend(rate_limit_profile_tokens(content))
    elif profile_type == "ShapingProfile":
        tokens.extend(content_values(content, sorted(content)))
    elif profile_type == "WeightProfile":
        tokens.extend(content_values(content, sorted(content)))
    else:
        tokens.extend(fallback_tokens)
    return unique_tokens(tokens)


def neox_profile_cli_field_mismatches(profile_type: str, payload: dict[str, Any], cli_output: str) -> list[str]:
    if profile_type != "ONTAclProfile":
        return []

    actual_fields = parse_profile_cli_table(cli_output)
    expected_fields = ont_acl_profile_cli_fields(payload.get("Content", {}))
    mismatches = []
    for field, expected in expected_fields.items():
        actual = actual_fields.get(field)
        if actual != expected:
            mismatches.append(f"{field}: expected {expected!r}, actual {actual!r}")
    return mismatches


def parse_profile_cli_table(cli_output: str) -> dict[str, str]:
    fields = {}
    for line in cli_output.splitlines():
        if "|" not in line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 3:
            continue
        field = parts[-2]
        value = parts[-1]
        if not field or field == "Parameter":
            continue
        fields[field] = value
    return fields


def ont_acl_profile_cli_fields(content: dict[str, Any]) -> dict[str, str]:
    fields = {}
    direct_fields = {
        "protocol": "IP protocol",
        "srcport": "Source L4 port",
        "destport": "Destination L4 port",
        "srcip": "Source IP address",
        "destip": "Destination IP address",
        "srcmac": "Source MAC address",
        "destmac": "Destination MAC address",
    }
    for payload_key, cli_field in direct_fields.items():
        if payload_key in content:
            fields[cli_field] = str(content[payload_key])

    if "srcmask" in content and "srcip" in content:
        fields["Source IP mask"] = str(content["srcmask"])
    if "destmask" in content and "destip" in content:
        fields["Destination IP mask"] = str(content["destmask"])
    if "policy" in content:
        fields["Policy"] = str(content["policy"]).title()
    if "interface" in content:
        fields["Interface"] = acl_interface_token(str(content["interface"]))
    if "enable" in content:
        fields["Enable"] = yes_no_token(content["enable"])
    if "counter" in content:
        fields["Drop counter"] = yes_no_token(content["counter"])
    if "logging" in content:
        fields["Drop logging"] = yes_no_token(content["logging"])
    return fields


def content_values(content: dict[str, Any], keys: Any) -> list[str]:
    values = []
    for key in keys:
        if key in content:
            values.append(content[key])
            continue
        for content_key, value in content.items():
            if str(content_key).startswith(str(key)):
                values.append(value)
    return [str(value) for value in values if value not in (None, "")]


def ont_acl_profile_tokens(content: dict[str, Any]) -> list[str]:
    tokens = content_values(
        content,
        ("protocol", "srcport", "destport", "srcmask", "destmask", "srcip", "destip", "srcmac", "destmac"),
    )
    if content.get("policy"):
        tokens.append(str(content["policy"]).title())
    if content.get("interface"):
        tokens.append(acl_interface_token(str(content["interface"])))
    for field in ("enable", "logging", "counter"):
        if field in content:
            tokens.append(yes_no_token(content[field]))
    return tokens


def acl_interface_token(value: str) -> str:
    return {
        "both": "LAN&WAN (Both)",
        "lan": "LAN",
        "wan": "WAN",
    }.get(value, value)


def yes_no_token(value: Any) -> str:
    return "Yes" if str(value).casefold() in {"enable", "enabled", "active", "yes", "y", "1"} else "No"


def ont_alarm_profile_tokens(content: dict[str, Any]) -> list[str]:
    tokens = [
        format_fixed_decimal(content.get("lowvolt"), 2),
        format_fixed_decimal(content.get("upvol"), 2),
        str(content.get("lowcurr", "")),
        str(content.get("upcurr", "")),
        str(content.get("lowtemp", "")),
        str(content.get("uptemp", "")),
        str(content.get("lowtxpower", "")),
        str(content.get("uptxpower", "")),
        format_fixed_decimal(content.get("lowrxpower"), 1),
        format_fixed_decimal(content.get("uprxpower"), 1),
    ]
    return [token for token in tokens if token]


def format_fixed_decimal(value: Any, places: int) -> str:
    if value in (None, ""):
        return ""
    return f"{float(value):.{places}f}"


def ont_service_profile_tokens(content: dict[str, Any]) -> list[str]:
    tokens = content_values(content, ("vlan", "pbit", "mode"))
    if content.get("lan"):
        tokens.append(f"port_lan: {content['lan']}")
    if content.get("xlan"):
        tokens.append(f"port_xlan: {content['xlan']}")
    return tokens


def ont_template_profile_tokens(content: dict[str, Any]) -> list[str]:
    return content_values(
        content,
        (
            "dsop",
            "enc_algorithm",
            "alarmprof",
            "secprof",
            "ontprof",
            "mprof",
        ),
    )


def ont_uni_profile_tokens(content: dict[str, Any]) -> list[str]:
    tokens = []
    for key, value in content.items():
        if value in (None, ""):
            continue
        if str(key).endswith("vlan") or "vlan" in str(key) or str(key).endswith("uniport"):
            tokens.append(str(value))
    return tokens


def rate_limit_profile_tokens(content: dict[str, Any]) -> list[str]:
    tokens = []
    for active_key in ("ingressactive", "egressactive"):
        if active_key in content:
            tokens.append(active_token(content[active_key]))
    tokens.extend(content_values(content, ("cirrate", "cbsrate", "eirrate", "ebsrate", "egressrate", "burstrate")))
    return tokens


def active_token(value: Any) -> str:
    return "Y" if str(value).casefold() in {"active", "enable", "enabled", "yes", "y", "1"} else "N"


def unique_tokens(tokens: list[str]) -> list[str]:
    seen = set()
    unique = []
    for token in tokens:
        if token in (None, ""):
            continue
        text = str(token)
        if text not in seen:
            seen.add(text)
            unique.append(text)
    return unique
