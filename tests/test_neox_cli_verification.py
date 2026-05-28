from __future__ import annotations

from tests.support.neox_cli_verification import _cli_report_entry


def test_cli_report_entry_uses_output_lines_for_allure_readability():
    entry = _cli_report_entry(
        "show running-config interface ge 1-39\nCurrent configuration:\ninterface ge 1-39\nexit\nNXC400#",
        ["enable", "speed auto"],
        [],
    )

    assert "output" not in entry
    assert entry["output_lines"] == [
        "show running-config interface ge 1-39",
        "Current configuration:",
        "interface ge 1-39",
        "exit",
        "NXC400#",
    ]
    assert entry["expected_tokens"] == ["enable", "speed auto"]


def test_cli_report_entry_moves_multiline_expected_values_to_lines():
    entry = _cli_report_entry(
        "after",
        ["show vlan 1314\nVLAN Name: REST_API"],
        ["running-config differs after REST clear"],
    )

    assert entry["expected_tokens"] == []
    assert entry["expected_output_lines"] == [["show vlan 1314", "VLAN Name: REST_API"]]
    assert entry["missing_tokens"] == ["running-config differs after REST clear"]
