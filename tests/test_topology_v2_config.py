from __future__ import annotations

from config_loader.hardware import load_hardware_config


def test_default_topology_v2_node1_normalizes_to_runtime_target_shape():
    hardware = load_hardware_config()
    node = hardware.node_target("NODE1")

    hardware.validate_node("NODE1", node)

    assert node["report_cards"] == ["MSC1240QA", "GLC1440X-55", "OLC3816-IA"]
    assert node["controller_card"] == "MSC1240QA"
    assert node["pon_card"] == "OLC3816-IA"
    assert node["ge_service_card"] == "GLC1440X-55"
    assert node["ont"]["port_id"] == "16"
    assert node["ont"]["ont_id"] == "1"
    assert node["ont"]["sn"] == "5A5958458CADDDC3"
    assert node["ge_service"]["port_id"] == "39"
    assert node["ge_service"]["template"] == "#RestApi_getemp_ge1"
    assert node["cards"]["OLC3816-IA"]["ports"]["port_16"]["port_type"] == "xPON"


def test_default_topology_v2_node3_report_cards_are_slot_ordered():
    hardware = load_hardware_config()
    node = hardware.node_target("NODE3")

    hardware.validate_node("NODE3", node)

    assert hardware.report_card_names("NODE3", node) == ["NXC400", "NXP316", "NXA340"]
    assert node["ont"]["card"] == "NXP316"
    assert node["ont"]["ont_id"] == "1"
    assert node["ge_service"]["card"] == "NXA340"
