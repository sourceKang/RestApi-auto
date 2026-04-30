from __future__ import annotations

from configs import load_environment
from configs.hardware import load_hardware_config
from utils.reporting import _card_version_lines, _target_summary_lines


def test_hardware_yaml_loads_and_validates_known_nodes():
    hardware = load_hardware_config()
    for node_key in ("NODE1", "NODE3"):
        env = load_environment(node=node_key)
        node = env.raw["ZYXEL_DUT"][node_key]
        hardware.validate_node(node_key, node)


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
