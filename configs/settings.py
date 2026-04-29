from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from configs.hardware import HardwareConfig, HardwareConfigError, load_hardware_config
from models.api import SessionRole


DEFAULT_ENV_FILE = Path(r"D:\AScript\PyTest\EMS\web_ems\ENV_WEB.JSON")
EXPECTED_NOACCESS_USER = "RestApiNA"
EXPECTED_READONLY_USER = "RestApiRO"


class ConfigError(RuntimeError):
    """Raised when the EMS environment file cannot support API tests."""


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str


@dataclass(frozen=True)
class DutSample:
    node_key: str
    device_name: str
    device_ip: str
    slot_id: str
    port_id: str
    ge_slot_id: str
    ge_port_id: str
    ont_id: str
    ont_sn: str
    ont_password: str
    ont_template: str
    ont_description: str
    ge_template: str
    ge_port_name: str
    ge_telephone: str


@dataclass(frozen=True)
class EnvironmentConfig:
    source_path: Path
    raw: dict[str, Any]
    hardware: HardwareConfig
    base_url: str
    verify_tls: bool
    timeout: float
    readwrite: Credentials
    readonly: Credentials
    noaccess: Credentials
    dut: DutSample

    def credentials_for(self, role: SessionRole) -> Credentials:
        if role is SessionRole.READWRITE:
            return self.readwrite
        if role is SessionRole.READONLY:
            return self.readonly
        if role is SessionRole.NOACCESS:
            return self.noaccess
        raise ConfigError(f"Unsupported session role: {role}")


def load_environment(path: str | Path | None = None, node: str | None = None) -> EnvironmentConfig:
    env_path = Path(path or os.environ.get("EMS_ENV_FILE", DEFAULT_ENV_FILE))
    data = _load_json_with_known_repairs(env_path)
    _validate_minimum_shape(data, env_path)
    try:
        hardware = load_hardware_config()
    except HardwareConfigError as error:
        raise ConfigError(f"Cannot load hardware YAML configuration: {error}") from error

    ems = data["EMS"]
    users = ems["USER"]
    user4_name = users["USER4"].get("name")
    user5_name = users["USER5"].get("name")
    if user4_name != EXPECTED_NOACCESS_USER:
        raise ConfigError(
            f"EMS.USER.USER4.name must be {EXPECTED_NOACCESS_USER!r}, got {user4_name!r}."
        )
    if user5_name != EXPECTED_READONLY_USER:
        raise ConfigError(
            f"EMS.USER.USER5.name must be {EXPECTED_READONLY_USER!r}, got {user5_name!r}."
        )

    dut = _select_dut_sample(data, node or os.environ.get("EMS_NODE", "NODE3"), hardware)
    selected_node = data.get("ZYXEL_DUT", {}).get(dut.node_key, {})
    if isinstance(selected_node, dict):
        try:
            hardware.validate_node(dut.node_key, selected_node)
        except HardwareConfigError as error:
            raise ConfigError(f"Invalid hardware YAML target for {dut.node_key}: {error}") from error

    return EnvironmentConfig(
        source_path=env_path,
        raw=data,
        hardware=hardware,
        base_url=str(ems["rest_api_url"]).rstrip("/"),
        verify_tls=_env_bool("EMS_VERIFY_TLS", default=False),
        timeout=float(os.environ.get("EMS_API_TIMEOUT", "60")),
        readwrite=Credentials(str(ems["login_username"]), str(ems["login_password"])),
        readonly=Credentials(str(users["USER5"]["name"]), str(users["USER5"]["password"])),
        noaccess=Credentials(str(users["USER4"]["name"]), str(users["USER4"]["password"])),
        dut=dut,
    )


def _load_json_with_known_repairs(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    try:
        return json.loads(text)
    except json.JSONDecodeError as first_error:
        repaired = _repair_known_env_json_issues(text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as second_error:
            raise ConfigError(
                f"Cannot parse environment JSON at {path}. "
                f"Original error: {first_error}. After known repairs: {second_error}."
            ) from second_error


def _repair_known_env_json_issues(text: str) -> str:
    # Some existing ENV_WEB.JSON files contain a geo_position value that lost the
    # closing quote before the trailing comma. Keep the repair deliberately narrow.
    fixed_lines: list[str] = []
    broken_geo_position = re.compile(r'^(\s*"geo_position"\s*:\s*"[^"\r\n]*),(\s*)$')
    for line in text.splitlines():
        match = broken_geo_position.match(line)
        if match:
            fixed_lines.append(f'{match.group(1)}",{match.group(2)}')
        else:
            fixed_lines.append(line)
    return "\n".join(fixed_lines)


def _validate_minimum_shape(data: dict[str, Any], path: Path) -> None:
    required_paths = [
        ("EMS", "rest_api_url"),
        ("EMS", "login_username"),
        ("EMS", "login_password"),
        ("EMS", "USER", "USER4", "name"),
        ("EMS", "USER", "USER4", "password"),
        ("EMS", "USER", "USER5", "name"),
        ("EMS", "USER", "USER5", "password"),
        ("ZYXEL_DUT",),
    ]
    missing: list[str] = []
    for keys in required_paths:
        current: Any = data
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                missing.append(".".join(keys))
                break
            current = current[key]
    if missing:
        raise ConfigError(f"{path} is missing required keys: {', '.join(missing)}")


def _select_dut_sample(data: dict[str, Any], preferred_node: str, hardware: HardwareConfig | None = None) -> DutSample:
    nodes = data["ZYXEL_DUT"]
    candidates = [preferred_node] + [key for key in nodes if key != preferred_node]
    for node_key in candidates:
        node = nodes.get(node_key)
        if not isinstance(node, dict):
            continue
        try:
            card = _target_or_first_pon_card(node_key, node, hardware)
            ge_card = _target_or_first_ge_service_card(node_key, node, hardware)
            ont = _first_ont(node)
            target = hardware.node_target(node_key) if hardware is not None else {}
            ont_target = _target_section(target, "ont")
            ge_target = _target_section(target, "ge_service")
            return DutSample(
                node_key=node_key,
                device_name=str(node["name"]),
                device_ip=str(node["ip"]),
                slot_id=str(_target_value(ont_target, "slot_id", card["slot_id"])),
                port_id=str(_target_value(ont_target, "port_id", card["port_id"])),
                ge_slot_id=str(_target_value(ge_target, "slot_id", ge_card["slot_id"])),
                ge_port_id=str(_target_value(ge_target, "port_id", ge_card["port_id"])),
                ont_id=str(_target_value(ont_target, "ont_id", ont.get("ont_id", "1"))),
                ont_sn=str(_target_value(ont_target, "sn", ont.get("sn_16") or ont.get("sn_12"))).strip(),
                ont_password=str(_target_value(ont_target, "password", ont.get("pw", "DEFAULT"))),
                ont_template=str(_target_value(ont_target, "template", ont.get("template_name", "#RestApi_provision_temp_SFU"))),
                ont_description=str(_target_value(ont_target, "description", ont.get("description", "AUTO_REST_DESCRIPTION"))),
                ge_template=str(_target_value(ge_target, "template", _ge_card_info_value(ge_card, "ge_template_name", ge_card.get("template_name", "#RestApi_getemp_ge1")))),
                ge_port_name=str(_target_value(ge_target, "port_name", _ge_card_info_value(ge_card, "port_name", "AUTO_REST_GE"))),
                ge_telephone=str(_target_value(ge_target, "telephone", _ge_card_info_value(ge_card, "telephone", "000"))),
            )
        except (KeyError, TypeError, ValueError):
            continue
    raise ConfigError("Cannot find a DUT sample with device, port and ONT data.")


def _target_section(target: dict[str, Any], name: str) -> dict[str, Any]:
    section = target.get(name, {})
    return section if isinstance(section, dict) else {}


def _target_value(section: dict[str, Any], field: str, fallback: Any) -> Any:
    value = section.get(field)
    return fallback if value in (None, "") else value


def _ge_card_info_value(card: dict[str, Any], field: str, fallback: Any) -> Any:
    return card.get("PORTINFO", {}).get("info", {}).get(field, fallback)


def _target_or_first_pon_card(node_key: str, node: dict[str, Any], hardware: HardwareConfig | None) -> dict[str, Any]:
    card = _target_card(node_key, node, hardware, "pon_card")
    if card is not None:
        return card
    return _first_pon_card(node)


def _target_or_first_ge_service_card(node_key: str, node: dict[str, Any], hardware: HardwareConfig | None) -> dict[str, Any]:
    card = _target_card(node_key, node, hardware, "ge_service_card")
    if card is not None:
        return card
    return _first_ge_service_card(node)


def _target_card(node_key: str, node: dict[str, Any], hardware: HardwareConfig | None, field: str) -> dict[str, Any] | None:
    if hardware is None:
        return None
    card_token = hardware.node_target(node_key).get(field)
    if not isinstance(card_token, str):
        return None
    resolved = hardware.resolve_card(node, card_token)
    if resolved is None:
        raise ValueError(f"{node_key}.{field} references missing card {card_token!r}")
    return resolved[2]


def _first_pon_card(node: dict[str, Any]) -> dict[str, Any]:
    cards = node.get("CARDINFO", {})
    for preferred_key in ("NXP316", "OLC3816", "OLC3708", "OLC3416B", "OLC3416-42A"):
        card = cards.get(preferred_key)
        if _is_usable_pon_card(preferred_key, card):
            return card
    for key, card in cards.items():
        if _is_usable_pon_card(str(key), card):
            return card
    raise ValueError("No usable PON card")


def _first_ge_service_card(node: dict[str, Any]) -> dict[str, Any]:
    cards = node.get("CARDINFO", {})
    for preferred_key in ("NXA340", "GLC1540", "GLC1440", "GLC1540X", "GLC1440X"):
        card = cards.get(preferred_key)
        if _is_usable_ge_card(preferred_key, card):
            return card
    for key, card in cards.items():
        if _is_usable_ge_card(str(key), card):
            return card
    raise ValueError("No usable GE service card")


def _is_usable_pon_card(key: str, card: Any) -> bool:
    if not isinstance(card, dict):
        return False
    if card.get("slot_id") in (None, "--") or not card.get("port_id"):
        return False
    if _is_usable_ge_card(key, card):
        return False
    return str(card.get("port_type", "")).lower() in {"xpon", "gpon"}


def _is_usable_ge_card(key: str, card: Any) -> bool:
    if not isinstance(card, dict):
        return False
    if card.get("slot_id") in (None, "--") or not card.get("port_id"):
        return False
    name = key.upper()
    card_type = str(card.get("type", "")).upper()
    supported = ("NXA340", "GLC1540", "GLC1440")
    return any(token in name or token in card_type for token in supported)


def _first_ont(node: dict[str, Any]) -> dict[str, Any]:
    ontinfo = node.get("ONTINFO", {})
    for pon_type in ("XPON", "GPON"):
        group = ontinfo.get(pon_type, {})
        if not isinstance(group, dict):
            continue
        for key, ont in group.items():
            if key.startswith("ONT") and isinstance(ont, dict) and (ont.get("sn_16") or ont.get("sn_12")):
                return ont
    raise ValueError("No usable ONT")


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
