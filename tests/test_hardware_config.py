from __future__ import annotations

from configs import load_environment
from configs.hardware import load_hardware_config
from utils.reporting import _card_version_lines, _target_summary_lines


def test_hardware_yaml_loads_and_validates_known_nodes():
    hardware = load_hardware_config()
    for node_key in hardware.targets["nodes"]:
        env = load_environment(node=node_key)
        node = env.node_target
        hardware.validate_node(node_key, node)


def test_each_yaml_hardware_target_has_port_inventory():
    hardware = load_hardware_config()
    for node_key, node in hardware.targets["nodes"].items():
        cards = node.get("cards", {})
        node_ports = node.get("ports", {})
        assert cards or node_ports, f"{node_key} must define card inventory or node-level ports"
        if node_ports:
            assert not cards, f"{node_key} must not mix card inventory with node-level ports"
            for port_name, port in node_ports.items():
                assert port.get("slot_id") is not None, f"{node_key}.{port_name} missing slot_id"
                assert port.get("port_id"), f"{node_key}.{port_name} missing port_id"
                assert port.get("port_type"), f"{node_key}.{port_name} missing port_type"
                assert port.get("port_speed"), f"{node_key}.{port_name} missing port_speed"
            continue
        for card_name, card in cards.items():
            assert card.get("fw_version"), f"{node_key}.{card_name} missing fw_version"
            assert card.get("slot_id") is not None, f"{node_key}.{card_name} missing slot_id"
            assert card.get("type"), f"{node_key}.{card_name} missing type"
            ports = card.get("ports", {})
            assert ports, f"{node_key}.{card_name} must define ports"
            for port_name, port in ports.items():
                assert port.get("port_id"), f"{node_key}.{card_name}.{port_name} missing port_id"
                assert port.get("port_type"), f"{node_key}.{card_name}.{port_name} missing port_type"
                assert port.get("port_speed"), f"{node_key}.{card_name}.{port_name} missing port_speed"


def test_each_yaml_model_matches_supported_device_matrix():
    hardware = load_hardware_config()
    supported = hardware.matrix["supported_devices"]
    aliases = hardware.matrix.get("model_aliases", {})
    for node_key, node in hardware.targets["nodes"].items():
        if node.get("ports"):
            _assert_supported_model(
                supported,
                aliases,
                node_key,
                str(node.get("type", node.get("chassis", ""))),
                str(node.get("fw_version", "")),
            )
        for card_name, card in node.get("cards", {}).items():
            _assert_supported_model(
                supported,
                aliases,
                f"{node_key}.{card_name}",
                str(card.get("type", "")),
                str(card.get("fw_version", "")),
            )


def test_feature_targets_only_use_supported_devices():
    hardware = load_hardware_config()
    aliases = hardware.matrix.get("model_aliases", {})
    features = hardware.matrix["feature_support"]
    ont_models = set(features["ont_models"])
    ge_models = set(features["ge_port_models"])
    for node_key, node in hardware.targets["nodes"].items():
        if isinstance(node.get("ont"), dict):
            ont_model = _target_model(hardware, node, node["ont"], "pon_card")
            assert _canonical_model(ont_model, aliases) in ont_models, f"{node_key}.ont uses unsupported {ont_model}"
        if isinstance(node.get("ge_service"), dict):
            ge_model = _target_model(hardware, node, node["ge_service"], "ge_service_card")
            assert _canonical_model(ge_model, aliases) in ge_models, f"{node_key}.ge_service uses unsupported {ge_model}"
        if node.get("ports"):
            assert "ont" not in node, f"{node_key} is port-only and must not define ONT target unless model is supported"
            assert "ge_service" not in node, f"{node_key} is port-only and must not define GE target unless model is supported"


def _target_model(hardware, node, section, fallback_card_field):
    card_token = section.get("card") or node.get(fallback_card_field)
    if card_token:
        resolved = hardware.resolve_card(node, str(card_token))
        if resolved is not None:
            return str(resolved[2].get("type", resolved[0]))
    return str(section.get("type") or node.get("type") or node.get("chassis") or "")


def _canonical_model(value, aliases):
    return aliases.get(value, value)


def _assert_supported_model(supported, aliases, label, model, actual_version):
    canonical_model = aliases.get(model, model)
    assert canonical_model in supported, f"{label} model {model!r} is not listed in supported_devices"
    expected_version = str(supported[canonical_model]["version"])
    assert actual_version == expected_version, (
        f"{label} firmware {actual_version!r} does not match configured test version "
        f"{expected_version!r} for {canonical_model}"
    )


def test_node1_report_cards_are_yaml_targeted():
    env = load_environment(node="NODE1")
    lines = _card_version_lines(env)
    assert [line.split(":", 1)[0] for line in lines] == ["MSC1240QB", "GLC1440X", "OLC3816"]
    assert env.dut.device_name == "California_IES4204_169.57"
    assert env.dut.device_ip == "192.168.169.57"
    assert env.dut.chassis == "IES4204"
    assert env.dut.slot_id == "2"
    assert env.dut.port_id == "16"
    assert env.dut.ge_slot_id == "1"
    assert env.dut.ge_port_id == "39"
    assert env.dut.ont_sn == "5A5958458CADDDC3"
    assert env.dut.ont_template == "#RestApi_provision_temp_SFU"
    assert env.dut.ge_template == "#RestApi_getemp_ge1"
    assert "Test Target Source: YAML" in _target_summary_lines(env)


def test_node3_report_cards_are_yaml_targeted():
    env = load_environment(node="NODE3")
    lines = _card_version_lines(env)
    assert [line.split(":", 1)[0] for line in lines] == ["NXC400", "NXP316", "NXA340"]
    assert env.dut.device_name == "北京_NeoX-03_169.58"
    assert env.dut.device_ip == "192.168.169.58"
    assert env.dut.chassis == "NeoX-03"
