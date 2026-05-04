from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from configs.simple_yaml import SimpleYamlError, load_simple_yaml


DEFAULT_HARDWARE_MATRIX_FILE = Path(__file__).with_name("hardware_matrix.yaml")
DEFAULT_TEST_TARGETS_FILE = Path(__file__).with_name("test_targets.yaml")


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
    targets_file = Path(targets_path or DEFAULT_TEST_TARGETS_FILE)
    try:
        matrix = load_simple_yaml(matrix_file)
        targets = load_simple_yaml(targets_file)
    except SimpleYamlError as error:
        raise HardwareConfigError(str(error)) from error

    _validate_top_level(matrix_file, matrix, "chassis")
    _validate_top_level(targets_file, targets, "nodes")
    return HardwareConfig(matrix_path=matrix_file, targets_path=targets_file, matrix=matrix, targets=targets)


def _validate_top_level(path: Path, data: dict[str, Any], required_key: str) -> None:
    if not isinstance(data, dict):
        raise HardwareConfigError(f"{path} must contain a mapping")
    if data.get("version") != 1:
        raise HardwareConfigError(f"{path} must declare version: 1")
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
