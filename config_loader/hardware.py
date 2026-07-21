from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from config_loader.simple_yaml import SimpleYamlError, load_simple_yaml


CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"
DEFAULT_HARDWARE_MATRIX_FILE = CONFIG_DIR / "hardware_matrix.yaml"
DEFAULT_TEST_TARGETS_FILE = CONFIG_DIR / "test_targets.yaml"


class HardwareConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class HardwareConfig:
    matrix_path: Path
    targets_path: Path
    matrix: dict[str, Any]
    targets: dict[str, Any]

    def node_target(self, node_key: str) -> dict[str, Any]:
        nodes = self.targets.get("nodes", {})
        target = nodes.get(node_key, {})
        if self.targets.get("version") == 2:
            return _normalize_topology_node(target, self.targets.get("defaults", {}))
        return target if isinstance(target, dict) else {}

    def chassis_rules(self, chassis: str) -> dict[str, Any]:
        rules = self.matrix.get("chassis", {}).get(chassis, {})
        return rules if isinstance(rules, dict) else {}

    def report_card_names(self, node_key: str, node_data: dict[str, Any]) -> list[str]:
        configured = self.report_card_entries(node_key, node_data)
        if configured:
            return [label for label, _key, _card in configured]

        chassis = str(node_data.get("chassis", ""))
        rules = self.chassis_rules(chassis)
        ordered = rules.get("report_card_order")
        if isinstance(ordered, list) and ordered:
            entries = [entry for name in ordered if (entry := self.resolve_card(node_data, str(name))) is not None]
            if entries:
                return [label for label, _key, _card in entries]
        return []

    def controller_card_name(self, node_key: str, node_data: dict[str, Any]) -> str | None:
        target = self.node_target(node_key)
        configured = target.get("controller_card")
        if isinstance(configured, str):
            resolved = self.resolve_card(node_data, configured)
            if resolved is not None:
                return resolved[0]

        for label, _key, card in self.report_card_entries(node_key, node_data):
            if isinstance(card, dict) and str(card.get("port_type", "")).lower() == "network":
                return label
        return None

    def report_card_entries(self, node_key: str, node_data: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
        if _node_is_port_only(node_data):
            return []
        target = self.node_target(node_key)
        configured = target.get("report_cards")
        if isinstance(configured, list) and configured:
            entries = [entry for token in configured if (entry := self.resolve_card(node_data, str(token))) is not None]
            if entries:
                return entries
        return []

    def resolve_card(self, node_data: dict[str, Any], token: str) -> tuple[str, str, dict[str, Any]] | None:
        cards = _node_cards(node_data)
        if not isinstance(cards, dict):
            return None
        if token in cards and isinstance(cards[token], dict):
            return token, token, cards[token]

        normalized_token = _normalize_card_token(token)
        for key, card in cards.items():
            if not isinstance(card, dict):
                continue
            card_type = str(card.get("type", ""))
            if _normalize_card_token(card_type) == normalized_token:
                return token, str(key), card
        return None

    def validate_node(self, node_key: str, node_data: dict[str, Any]) -> None:
        target = self.node_target(node_key)
        if not target:
            return
        node_data = target

        chassis = str(node_data.get("chassis", ""))
        rules = self.chassis_rules(chassis)
        if not rules:
            raise HardwareConfigError(f"{node_key} uses chassis {chassis!r}, but it is not defined in hardware_matrix.yaml")

        cards = _node_cards(node_data)
        ports = _node_ports(node_data)
        if not isinstance(cards, dict):
            raise HardwareConfigError(f"{node_key}.cards must be a mapping")
        if not cards and not ports:
            raise HardwareConfigError(f"{node_key} must define cards or node-level ports")

        for field in ("report_cards",):
            value = target.get(field, [])
            if not isinstance(value, list):
                raise HardwareConfigError(f"{node_key}.{field} must be a list")
            missing = [name for name in value if cards and self.resolve_card(node_data, str(name)) is None]
            if missing:
                raise HardwareConfigError(f"{node_key}.{field} references cards not present in YAML card inventory: {missing}")

        for field in ("controller_card", "pon_card", "ge_service_card"):
            value = target.get(field)
            if cards and value is not None and self.resolve_card(node_data, str(value)) is None:
                raise HardwareConfigError(
                    f"{node_key}.{field} references card {value!r}, but it is not present in YAML card inventory"
                )

        self._validate_report_card_limits(node_key, chassis, target)
        self._validate_target_capabilities(node_key, chassis, target)
        self._validate_feature_targets(node_key, target)
        self._validate_test_target_sections(node_key, target)

    def _validate_report_card_limits(self, node_key: str, chassis: str, target: dict[str, Any]) -> None:
        rules = self.chassis_rules(chassis)
        report_cards = target.get("report_cards") or []
        if _node_is_port_only(target):
            report_cards = []
        controllers = set(_as_string_list(rules.get("controller_cards")))
        line_cards = set(_as_string_list(rules.get("line_cards")))

        controller_count = sum(1 for name in report_cards if name in controllers)
        line_count = sum(1 for name in report_cards if name in line_cards)
        max_controllers = rules.get("max_controller_cards")
        max_lines = rules.get("max_line_cards")
        if isinstance(max_controllers, int) and controller_count > max_controllers:
            raise HardwareConfigError(
                f"{node_key} reports {controller_count} controller cards for {chassis}, max is {max_controllers}"
            )
        if isinstance(max_lines, int) and line_count > max_lines:
            raise HardwareConfigError(f"{node_key} reports {line_count} line cards for {chassis}, max is {max_lines}")

    def _validate_target_capabilities(self, node_key: str, chassis: str, target: dict[str, Any]) -> None:
        rules = self.chassis_rules(chassis)
        checks = (
            ("controller_card", "controller_cards"),
            ("pon_card", "line_cards"),
            ("ge_service_card", "ge_service_cards"),
        )
        for target_field, rule_field in checks:
            value = target.get(target_field)
            allowed = _as_string_list(rules.get(rule_field))
            if value is not None and allowed and value not in allowed:
                raise HardwareConfigError(
                    f"{node_key}.{target_field} uses {value!r}, but {chassis}.{rule_field} allows {allowed}"
                )

    def _validate_test_target_sections(self, node_key: str, target: dict[str, Any]) -> None:
        for field in ("device_name", "device_ip", "chassis"):
            value = target.get(field)
            if value is not None and not isinstance(value, (str, int)):
                raise HardwareConfigError(f"{node_key}.{field} must be a string or integer")

        ont = target.get("ont", {})
        if ont is not None and not isinstance(ont, dict):
            raise HardwareConfigError(f"{node_key}.ont must be a mapping")
        ge_service = target.get("ge_service", {})
        if ge_service is not None and not isinstance(ge_service, dict):
            raise HardwareConfigError(f"{node_key}.ge_service must be a mapping")

        for section_name, section, fields in (
            ("ont", ont or {}, ("slot_id", "port_id", "ont_id", "sn", "password", "description", "template")),
            ("ge_service", ge_service or {}, ("slot_id", "port_id", "template", "port_name", "telephone")),
        ):
            for field in fields:
                value = section.get(field)
                if value is not None and not isinstance(value, (str, int)):
                    raise HardwareConfigError(f"{node_key}.{section_name}.{field} must be a string or integer")

    def _validate_feature_targets(self, node_key: str, target: dict[str, Any]) -> None:
        aliases = self.matrix.get("model_aliases", {})
        features = self.matrix.get("feature_support", {})
        ont_models = set(_as_string_list(features.get("ont_models")))
        ge_models = set(_as_string_list(features.get("ge_port_models")))

        ont = target.get("ont")
        if isinstance(ont, dict):
            ont_model = self._target_feature_model(target, ont, "pon_card")
            if _canonical_model(ont_model, aliases) not in ont_models:
                raise HardwareConfigError(f"{node_key}.ont targets unsupported ONT device {ont_model!r}")

        ge_service = target.get("ge_service")
        if isinstance(ge_service, dict):
            ge_model = self._target_feature_model(target, ge_service, "ge_service_card")
            if _canonical_model(ge_model, aliases) not in ge_models:
                raise HardwareConfigError(f"{node_key}.ge_service targets unsupported GE Port device {ge_model!r}")

    def _target_feature_model(self, target: dict[str, Any], section: dict[str, Any], fallback_card_field: str) -> str:
        cards = _node_cards(target)
        card_token = section.get("card") or target.get(fallback_card_field)
        if isinstance(cards, dict) and card_token:
            resolved = self.resolve_card(target, str(card_token))
            if resolved is not None:
                return str(resolved[2].get("type", resolved[0]))
        return str(section.get("type") or target.get("type") or target.get("chassis") or "")


def load_hardware_config(
    matrix_path: str | Path | None = None,
    targets_path: str | Path | None = None,
) -> HardwareConfig:
    matrix_file = Path(matrix_path or DEFAULT_HARDWARE_MATRIX_FILE)
    targets_file = Path(targets_path) if targets_path is not None else _default_test_targets_file()
    try:
        matrix = load_simple_yaml(matrix_file)
        targets = load_simple_yaml(targets_file)
    except SimpleYamlError as error:
        raise HardwareConfigError(str(error)) from error

    _validate_top_level(matrix_file, matrix, "chassis", allowed_versions={1})
    _validate_top_level(targets_file, targets, "nodes", allowed_versions={1, 2})
    return HardwareConfig(matrix_path=matrix_file, targets_path=targets_file, matrix=matrix, targets=targets)


def _default_test_targets_file() -> Path:
    override = os.environ.get("EMS_TEST_TARGETS_FILE")
    if override:
        return Path(override)
    return DEFAULT_TEST_TARGETS_FILE


def _validate_top_level(path: Path, data: dict[str, Any], required_key: str, allowed_versions: set[int]) -> None:
    if not isinstance(data, dict):
        raise HardwareConfigError(f"{path} must contain a mapping")
    if data.get("version") not in allowed_versions:
        allowed = ", ".join(str(version) for version in sorted(allowed_versions))
        raise HardwareConfigError(f"{path} must declare version: {allowed}")
    if required_key not in data or not isinstance(data[required_key], dict):
        raise HardwareConfigError(f"{path} must contain {required_key}: mapping")


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _normalize_card_token(value: str) -> str:
    return value.strip().upper()


def _canonical_model(value: str, aliases: Any) -> str:
    model = value.strip()
    return aliases.get(model, model) if isinstance(aliases, dict) else model


def _node_cards(node_data: dict[str, Any]) -> Any:
    return node_data.get("cards", {})


def _node_ports(node_data: dict[str, Any]) -> Any:
    return node_data.get("ports", {})


def _node_is_port_only(node_data: dict[str, Any]) -> bool:
    return not _node_cards(node_data) and bool(_node_ports(node_data))


def _normalize_topology_node(node_data: Any, defaults: Any = None) -> dict[str, Any]:
    if not isinstance(node_data, dict):
        return {}
    slots = node_data.get("slots")
    if not isinstance(slots, dict):
        return node_data

    normalized = {
        key: value
        for key, value in node_data.items()
        if key not in {"slots", "test_targets"} and not isinstance(value, dict)
    }
    cards: dict[str, Any] = {}
    slot_to_card_key: dict[str, str] = {}

    for raw_slot_id, raw_slot in slots.items():
        if not isinstance(raw_slot, dict):
            continue
        slot_id = str(raw_slot.get("slot_id", raw_slot_id))
        label = str(raw_slot.get("card") or raw_slot.get("model") or f"slot_{slot_id}")
        card_key = _unique_card_key(label, cards, slot_id)
        slot_to_card_key[slot_id] = card_key

        card = {
            "fw_version": raw_slot.get("fw_version", ""),
            "hw_version": raw_slot.get("hw_version", ""),
            "slot_id": slot_id,
            "type": str(raw_slot.get("model") or raw_slot.get("type") or label),
            "ports": _normalize_topology_ports(raw_slot.get("ports", {})),
        }
        if raw_slot.get("role") is not None:
            card["role"] = raw_slot["role"]
        cards[card_key] = card

    normalized["cards"] = cards

    targets = node_data.get("test_targets", {})
    targets = targets if isinstance(targets, dict) else {}
    normalized["report_cards"] = _normalize_report_cards(targets, slot_to_card_key)

    controller = _first_slot_by_role(slots, slot_to_card_key, "controller")
    if controller is not None:
        normalized["controller_card"] = controller

    ont = _normalize_topology_ont(slots, slot_to_card_key, targets.get("ont"), _section_defaults(defaults, "ont"))
    if ont:
        normalized["pon_card"] = ont["card"]
        normalized["ont"] = ont

    ge_service = _normalize_topology_ge_service(
        slots,
        slot_to_card_key,
        targets.get("ge_service"),
        _section_defaults(defaults, "ge_service"),
    )
    if ge_service:
        normalized["ge_service_card"] = ge_service["card"]
        normalized["ge_service"] = ge_service

    nni = _normalize_topology_nni(slots, slot_to_card_key, targets.get("nni"))
    if nni:
        normalized["nni_card"] = nni["card"]
        normalized["nni"] = nni

    return normalized


def _normalize_topology_ports(raw_ports: Any) -> dict[str, Any]:
    ports: dict[str, Any] = {}
    if not isinstance(raw_ports, dict):
        return ports
    for raw_port_id, raw_port in raw_ports.items():
        if not isinstance(raw_port, dict):
            continue
        port_id = str(raw_port.get("port_id", raw_port_id))
        port = {
            "port_id": port_id,
            "port_type": str(raw_port.get("port_type", raw_port.get("type", ""))),
            "port_speed": str(raw_port.get("port_speed", raw_port.get("speed", ""))),
        }
        ge_service = raw_port.get("ge_service")
        if isinstance(ge_service, dict):
            _copy_if_present(port, "ge_template", ge_service, "template")
            _copy_if_present(port, "port_name", ge_service, "port_name")
            _copy_if_present(port, "telephone", ge_service, "telephone")
        ports[f"port_{port_id}"] = port
    return ports


def _normalize_report_cards(targets: dict[str, Any], slot_to_card_key: dict[str, str]) -> list[str]:
    report_slots = targets.get("report_slots")
    if isinstance(report_slots, list):
        return [slot_to_card_key[str(slot)] for slot in report_slots if str(slot) in slot_to_card_key]
    return list(slot_to_card_key.values())


def _normalize_topology_ont(
    slots: dict[str, Any],
    slot_to_card_key: dict[str, str],
    selector: Any,
    defaults: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(selector, dict):
        return {}
    slot_id = str(selector.get("slot", ""))
    port_id = str(selector.get("port", ""))
    ont_id = str(selector.get("ont", "1"))
    raw_port = _topology_port(slots, slot_id, port_id)
    onts = raw_port.get("onts") if isinstance(raw_port, dict) else None
    raw_ont = onts.get(ont_id, {}) if isinstance(onts, dict) else {}
    if not isinstance(raw_ont, dict) or slot_id not in slot_to_card_key or not port_id:
        return {}

    ont = {"card": slot_to_card_key[slot_id], "port_id": port_id, "ont_id": ont_id}
    for field in ("sn", "password", "description", "template", "model", "fw_image", "service_mode"):
        _copy_if_present(ont, field, defaults, field)
        _copy_if_present(ont, field, raw_ont, field)
    return ont


def _normalize_topology_ge_service(
    slots: dict[str, Any],
    slot_to_card_key: dict[str, str],
    selector: Any,
    defaults: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(selector, dict):
        return {}
    slot_id = str(selector.get("slot", ""))
    port_id = str(selector.get("port", ""))
    raw_port = _topology_port(slots, slot_id, port_id)
    raw_ge = raw_port.get("ge_service") if isinstance(raw_port, dict) else None
    if not isinstance(raw_ge, dict) or slot_id not in slot_to_card_key or not port_id:
        return {}

    ge_service = {"card": slot_to_card_key[slot_id], "port_id": port_id}
    for field in ("template", "port_name", "telephone"):
        _copy_if_present(ge_service, field, defaults, field)
        _copy_if_present(ge_service, field, raw_ge, field)
    return ge_service


def _normalize_topology_nni(
    slots: dict[str, Any],
    slot_to_card_key: dict[str, str],
    selector: Any,
) -> dict[str, Any]:
    if not isinstance(selector, dict):
        return {}
    slot_id = str(selector.get("slot", ""))
    port_id = str(selector.get("port", ""))
    raw_port = _topology_port(slots, slot_id, port_id)
    if not isinstance(raw_port, dict) or slot_id not in slot_to_card_key or not port_id:
        return {}
    return {
        "card": slot_to_card_key[slot_id],
        "slot_id": slot_id,
        "port_id": port_id,
        "port_type": str(raw_port.get("port_type", raw_port.get("type", ""))),
        "port_speed": str(raw_port.get("port_speed", raw_port.get("speed", ""))),
    }


def _section_defaults(defaults: Any, section: str) -> dict[str, Any]:
    if not isinstance(defaults, dict):
        return {}
    value = defaults.get(section, {})
    return value if isinstance(value, dict) else {}


def _topology_port(slots: dict[str, Any], slot_id: str, port_id: str) -> dict[str, Any]:
    slot = slots.get(slot_id, {})
    ports = slot.get("ports", {}) if isinstance(slot, dict) else {}
    port = ports.get(port_id, {}) if isinstance(ports, dict) else {}
    return port if isinstance(port, dict) else {}


def _first_slot_by_role(slots: dict[str, Any], slot_to_card_key: dict[str, str], role: str) -> str | None:
    for raw_slot_id, raw_slot in slots.items():
        slot_id = str(raw_slot.get("slot_id", raw_slot_id)) if isinstance(raw_slot, dict) else str(raw_slot_id)
        if isinstance(raw_slot, dict) and raw_slot.get("role") == role and slot_id in slot_to_card_key:
            return slot_to_card_key[slot_id]
    return None


def _unique_card_key(label: str, cards: dict[str, Any], slot_id: str) -> str:
    if label not in cards:
        return label
    return f"{label}_slot_{slot_id}"


def _copy_if_present(target: dict[str, Any], target_key: str, source: dict[str, Any], source_key: str) -> None:
    if source.get(source_key) not in (None, ""):
        target[target_key] = source[source_key]
