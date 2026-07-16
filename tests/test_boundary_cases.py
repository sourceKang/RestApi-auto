from __future__ import annotations

from cases.boundary_cases import numeric_boundary_negative_cases


def test_numeric_boundary_cases_generate_below_and_above_for_declared_ranges():
    minimum = {
        "Content": {
            "rate": "64",
            "power": "-15.3",
            "fixed": "5",
            "mode": "enable",
            "entries": [{"vlan": 1}],
        }
    }
    maximum = {
        "Content": {
            "rate": "100",
            "power": "6.5",
            "fixed": "5",
            "mode": "disable",
            "entries": [{"vlan": 4094}],
        }
    }

    cases = {case["name"]: case for case in numeric_boundary_negative_cases(minimum, maximum)}

    assert set(cases) == {
        "content_entries_0_vlan_below_minimum",
        "content_entries_0_vlan_above_maximum",
        "content_power_below_minimum",
        "content_power_above_maximum",
        "content_rate_below_minimum",
        "content_rate_above_maximum",
    }
    assert cases["content_rate_below_minimum"]["payload"]["Content"]["rate"] == "63"
    assert cases["content_rate_above_maximum"]["payload"]["Content"]["rate"] == "101"
    assert cases["content_power_below_minimum"]["payload"]["Content"]["power"] == "-15.4"
    assert cases["content_power_above_maximum"]["payload"]["Content"]["power"] == "6.6"
    assert cases["content_entries_0_vlan_below_minimum"]["payload"]["Content"]["entries"][0]["vlan"] == 0
    assert cases["content_entries_0_vlan_above_maximum"]["payload"]["Content"]["entries"][0]["vlan"] == 4095


def test_numeric_boundary_cases_do_not_mutate_source_or_guess_fixed_ranges():
    minimum = {"Content": {"same": "5", "only_min": "1"}}
    maximum = {"Content": {"same": "5", "only_max": "9"}}

    cases = numeric_boundary_negative_cases(minimum, maximum)

    assert cases == []
    assert minimum == {"Content": {"same": "5", "only_min": "1"}}
    assert maximum == {"Content": {"same": "5", "only_max": "9"}}
