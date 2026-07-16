from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config_loader.auth import AuthConfigError, ResolvedAccount, load_auth_config
from config_loader.hardware import HardwareConfig, HardwareConfigError, load_hardware_config
from config_loader.simple_yaml import SimpleYamlError, load_simple_yaml
from models.api import SessionRole


CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"
DEFAULT_EMS_FILE = CONFIG_DIR / "ems.yaml"



class ConfigError(RuntimeError):
    """Raised when the YAML configuration cannot support API tests."""


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str = field(repr=False)


@dataclass(frozen=True)
class DutSample:
    node_key: str
    device_name: str
    device_ip: str
    chassis: str
    slot_id: str
    port_id: str
    ge_slot_id: str
    ge_port_id: str
    ont_id: str
    ont_sn: str
    ont_password: str = field(repr=False)
    ont_template: str
    ont_description: str
    ge_template: str
    ge_port_name: str
    ge_telephone: str


@dataclass(frozen=True)
class EnvironmentConfig:
    source_path: Path
    hardware: HardwareConfig = field(repr=False)
    auth_profile: str
    base_url: str
    ems_version: str
    verify_tls: bool
    timeout: float
    readwrite: Credentials = field(repr=False)
    readonly: Credentials = field(repr=False)
    noaccess: Credentials = field(repr=False)
    readwrite_account: ResolvedAccount = field(repr=False)
    readonly_account: ResolvedAccount = field(repr=False)
    noaccess_account: ResolvedAccount = field(repr=False)
    dut: DutSample
    node_target: dict[str, Any] = field(repr=False)

    def credentials_for(self, role: SessionRole) -> Credentials:
        if role is SessionRole.READWRITE:
            return self.readwrite
        if role is SessionRole.READONLY:
            return self.readonly
        if role is SessionRole.NOACCESS:
            return self.noaccess
        raise ConfigError(f"Unsupported session role: {role}")


def load_environment(path: str | Path | None = None, node: str | None = None, auth_profile: str | None = None) -> EnvironmentConfig:
    try:
        hardware = load_hardware_config()
    except HardwareConfigError as error:
        raise ConfigError(f"Cannot load hardware YAML configuration: {error}") from error
    try:
        auth = load_auth_config()
    except AuthConfigError as error:
        raise ConfigError(f"Cannot load auth YAML configuration: {error}") from error
    ems = _load_ems_yaml(path)

    env_node = os.environ.get("EMS_NODE")
    selected_node_key = node or env_node or "NODE3"
    allow_node_fallback = node is None and not env_node

    selected_auth_profile = auth_profile or os.environ.get("EMS_AUTH_PROFILE", "default")
    try:
        resolved_accounts = auth.resolve_profile(selected_auth_profile)
    except AuthConfigError as error:
        raise ConfigError(f"Cannot resolve auth profile {selected_auth_profile!r}: {error}") from error

    dut = _select_dut_sample(hardware, selected_node_key, allow_fallback=allow_node_fallback)
    selected_node = hardware.node_target(dut.node_key)
    try:
        hardware.validate_node(dut.node_key, selected_node)
    except HardwareConfigError as error:
        raise ConfigError(f"Invalid hardware YAML target for {dut.node_key}: {error}") from error

    return EnvironmentConfig(
        source_path=Path(path) if path else DEFAULT_EMS_FILE,
        hardware=hardware,
        auth_profile=selected_auth_profile,
        base_url=str(ems["rest_api_url"]).rstrip("/"),
        ems_version=str(ems["version"]),
        verify_tls=_env_bool("EMS_VERIFY_TLS", default=bool(ems.get("verify_tls", False))),
        timeout=float(os.environ.get("EMS_API_TIMEOUT", str(ems.get("timeout", 60)))),
        readwrite=Credentials(resolved_accounts["readwrite"].username, resolved_accounts["readwrite"].password),
        readonly=Credentials(resolved_accounts["readonly"].username, resolved_accounts["readonly"].password),
        noaccess=Credentials(resolved_accounts["noaccess"].username, resolved_accounts["noaccess"].password),
        readwrite_account=resolved_accounts["readwrite"],
        readonly_account=resolved_accounts["readonly"],
        noaccess_account=resolved_accounts["noaccess"],
        dut=dut,
        node_target=selected_node,
    )


def _load_ems_yaml(path: str | Path | None = None) -> dict[str, Any]:
    ems_path = Path(path or os.environ.get("EMS_YAML_FILE", DEFAULT_EMS_FILE))
    try:
        raw = load_simple_yaml(ems_path)
    except SimpleYamlError as error:
        raise ConfigError(f"Cannot load EMS YAML configuration: {error}") from error
    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise ConfigError(f"{ems_path} must declare version: 1")
    ems = raw.get("ems")
    if not isinstance(ems, dict):
        raise ConfigError(f"{ems_path} must contain ems: mapping")
    for field in ("rest_api_url", "version"):
        if not ems.get(field):
            raise ConfigError(f"{ems_path} must define ems.{field}")
    return ems


def _target_cards(target: dict[str, Any]) -> dict[str, Any]:
    cards = target.get("cards", {})
    return cards if isinstance(cards, dict) else {}


def _select_dut_sample(hardware: HardwareConfig, preferred_node: str, *, allow_fallback: bool = True) -> DutSample:
    nodes = hardware.targets["nodes"]
    candidates = [preferred_node]
    if allow_fallback:
        candidates += [key for key in nodes if key != preferred_node]
    failures: list[str] = []
    for node_key in candidates:
        node = hardware.node_target(node_key)
        if not isinstance(node, dict) or not node:
            failures.append(f"{node_key} is not defined in test_targets.yaml")
            continue
        try:
            target = node
            ont_target = _target_section(target, "ont")
            if not ont_target.get("sn"):
                raise ValueError("no ONT test target")
            ge_target = _target_section(target, "ge_service")
            card = _target_or_first_pon_card(node_key, node, hardware)
            ge_card = _target_or_first_ge_service_card(node_key, node, hardware) if _has_ge_service_target(target) else None
            ont_port = _target_or_first_port(card, ont_target.get("port_id"))
            ge_port = _target_or_first_port(ge_card, ge_target.get("port_id")) if ge_card is not None else {}
            return DutSample(
                node_key=node_key,
                device_name=str(target["device_name"]),
                device_ip=str(target["device_ip"]),
                chassis=str(target["chassis"]),
                slot_id=str(_target_value(ont_target, "slot_id", card["slot_id"])),
                port_id=str(_target_value(ont_target, "port_id", ont_port["port_id"])),
                ge_slot_id=str(_target_value(ge_target, "slot_id", ge_card.get("slot_id", "") if ge_card else "")),
                ge_port_id=str(_target_value(ge_target, "port_id", ge_port.get("port_id", ""))),
                ont_id=str(_target_value(ont_target, "ont_id", "1")),
                ont_sn=str(_target_value(ont_target, "sn", "")).strip(),
                ont_password=str(_target_value(ont_target, "password", "DEFAULT")),
                ont_template=str(_target_value(ont_target, "template", "#RestApi_provision_temp_SFU")),
                ont_description=str(_target_value(ont_target, "description", "AUTO_REST_DESCRIPTION")),
                ge_template=str(_target_value(ge_target, "template", _port_info_value(ge_port, "ge_template", _ge_card_info_value(ge_card, "ge_template_name", ge_card.get("template_name", "#RestApi_getemp_ge1")) if ge_card else ""))),
                ge_port_name=str(_target_value(ge_target, "port_name", _port_info_value(ge_port, "port_name", _ge_card_info_value(ge_card, "port_name", "AUTO_REST_GE") if ge_card else ""))),
                ge_telephone=str(_target_value(ge_target, "telephone", _port_info_value(ge_port, "telephone", _ge_card_info_value(ge_card, "telephone", "000") if ge_card else ""))),
            )
        except (KeyError, TypeError, ValueError) as error:
            failures.append(f"{node_key} has {error}")
            continue
    if not allow_fallback:
        detail = failures[0] if failures else f"{preferred_node} cannot be used as DUT sample"
        raise ConfigError(detail)
    raise ConfigError("Cannot find a DUT sample with device, port and ONT data.")


def _target_section(target: dict[str, Any], name: str) -> dict[str, Any]:
    section = target.get(name, {})
    return section if isinstance(section, dict) else {}


def _has_ge_service_target(target: dict[str, Any]) -> bool:
    return bool(target.get("ge_service_card") or _target_section(target, "ge_service"))


def _target_value(section: dict[str, Any], field: str, fallback: Any) -> Any:
    value = section.get(field)
    return fallback if value in (None, "") else value


def _ge_card_info_value(card: dict[str, Any], field: str, fallback: Any) -> Any:
    return card.get("PORTINFO", {}).get("info", {}).get(field, fallback)


def _port_info_value(port: dict[str, Any], field: str, fallback: Any) -> Any:
    return port.get(field, fallback)


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


def _target_card(node_key: str, node: dict[str, Any], hardware: HardwareConfig, field: str) -> dict[str, Any] | None:
    target = hardware.node_target(node_key)
    section_name = "ont" if field == "pon_card" else "ge_service"
    section = _target_section(target, section_name)
    card_token = section.get("card") or target.get(field)
    if not _target_cards(node) and _target_ports(node):
        if field == "pon_card" and section.get("port_id"):
            return _node_port_target(node, section)
        if field == "ge_service_card" and section.get("port_id"):
            return _node_port_target(node, section)
    if not isinstance(card_token, str):
        return None
    resolved = hardware.resolve_card(node, card_token)
    if resolved is None:
        raise ValueError(f"{node_key}.{field} references missing card {card_token!r}")
    return resolved[2]


def _first_pon_card(node: dict[str, Any]) -> dict[str, Any]:
    if not _target_cards(node) and _target_ports(node):
        return _node_port_target(node, {})
    cards = _target_cards(node)
    for preferred_key in ("NXP316", "OLC3816", "OLC3708", "OLC3416B", "OLC3416-42A"):
        card = cards.get(preferred_key)
        if _is_usable_pon_card(preferred_key, card):
            return card
    for key, card in cards.items():
        if _is_usable_pon_card(str(key), card):
            return card
    raise ValueError("No usable PON card")


def _first_ge_service_card(node: dict[str, Any]) -> dict[str, Any]:
    if not _target_cards(node) and _target_ports(node):
        return _node_port_target(node, {})
    cards = _target_cards(node)
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
    port = _first_port(card)
    if card.get("slot_id") in (None, "--") or not port.get("port_id"):
        return False
    if _is_usable_ge_card(key, card):
        return False
    return str(port.get("port_type", card.get("port_type", ""))).lower() in {"xpon", "gpon"}


def _is_usable_ge_card(key: str, card: Any) -> bool:
    if not isinstance(card, dict):
        return False
    port = _first_port(card)
    if card.get("slot_id") in (None, "--") or not port.get("port_id"):
        return False
    name = key.upper()
    card_type = str(card.get("type", "")).upper()
    supported = ("NXA340", "GLC1540", "GLC1440")
    return any(token in name or token in card_type for token in supported)


def _target_or_first_port(card: dict[str, Any], preferred_port_id: Any = None) -> dict[str, Any]:
    ports = card.get("ports")
    if isinstance(ports, dict) and ports:
        if preferred_port_id not in (None, ""):
            for port in ports.values():
                if isinstance(port, dict) and str(port.get("port_id", "")) == str(preferred_port_id):
                    return port
        for port in ports.values():
            if isinstance(port, dict):
                return port
    if card.get("port_id") not in (None, ""):
        return {
            "port_id": card.get("port_id"),
            "port_type": card.get("port_type"),
            "port_speed": card.get("port_speed"),
        }
    raise ValueError("No usable port on selected card")


def _first_port(card: dict[str, Any]) -> dict[str, Any]:
    try:
        return _target_or_first_port(card)
    except ValueError:
        return {}


def _target_ports(target: dict[str, Any]) -> dict[str, Any]:
    ports = target.get("ports", {})
    return ports if isinstance(ports, dict) else {}


def _node_port_target(node: dict[str, Any], section: dict[str, Any]) -> dict[str, Any]:
    ports = _target_ports(node)
    port = {}
    preferred_port_id = section.get("port_id")
    if preferred_port_id not in (None, ""):
        for candidate in ports.values():
            if isinstance(candidate, dict) and str(candidate.get("port_id", "")) == str(preferred_port_id):
                port = candidate
                break
    if not port:
        port = next((candidate for candidate in ports.values() if isinstance(candidate, dict)), {})
    if not port:
        raise ValueError("No usable node-level port")
    slot_id = section.get("slot_id", port.get("slot_id", node.get("slot_id", "0")))
    return {
        "slot_id": slot_id,
        "type": node.get("type", node.get("chassis", "")),
        "fw_version": node.get("fw_version", ""),
        "ports": {"selected": port},
    }


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
