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


def test_neox_profile_error_matrix_includes_generated_numeric_boundaries(monkeypatch):
    import tests.test_neox_profile as neox_profile_module

    class BoundaryService:
        def neox_profile_boundary_payload(self, profile_type, boundary):
            assert profile_type == "RateLimitProfile"
            value = "64" if boundary == "min" else "100"
            return {"Content": {"rate": value}}

    monkeypatch.setattr(
        neox_profile_module,
        "neox_profile_negative_cases_config",
        lambda profile_type: [{"name": "declared_invalid_field", "payload": {"Content": {"bad": "x"}}}],
    )

    cases = neox_profile_module.neox_profile_negative_cases(BoundaryService(), "RateLimitProfile")

    assert [case["name"] for case in cases] == [
        "declared_invalid_field",
        "content_rate_below_minimum",
        "content_rate_above_maximum",
    ]


def test_igmp_bandwidth_config_uses_ug_range_and_keeps_19_as_accepted_data():
    from services.neox_config.service import (
        neox_profile_accepted_cases_config,
        neox_profile_minmax_payload,
        neox_profile_negative_cases_config,
    )

    minimum = neox_profile_minmax_payload("IGMPGroupPrivilegeProfile", "min")
    accepted = neox_profile_accepted_cases_config("IGMPGroupPrivilegeProfile")
    standalone = [
        case
        for case in neox_profile_negative_cases_config("IGMPGroupPrivilegeProfile")
        if case.get("standalone")
    ]

    assert minimum["Content"]["grpbandwidth1"] == "0"
    assert minimum["Content"]["grpbandwidth10"] == "0"
    assert accepted == [
        {
            "name": "grpbandwidth1_normal_19",
            "payload": {
                "Content": {
                    "igmpactive1": "enable",
                    "grpbandwidth1": "19",
                    "startip1": "224.0.1.1",
                    "endip1": "224.0.1.10",
                    "prvitype1": "permit",
                }
            },
        }
    ]
    assert [(case["field"], case["payload"]["Content"]["grpbandwidth1"]) for case in standalone] == [
        ("Content.grpbandwidth1", "-1")
    ]


def test_neox_profile_error_matrix_excludes_standalone_boundary_duplicate(monkeypatch):
    import tests.test_neox_profile as neox_profile_module

    class BoundaryService:
        def neox_profile_boundary_payload(self, profile_type, boundary):
            assert profile_type == "IGMPGroupPrivilegeProfile"
            value = "0" if boundary == "min" else "100"
            return {"Content": {"grpbandwidth1": value}}

    monkeypatch.setattr(
        neox_profile_module,
        "neox_profile_negative_cases_config",
        lambda profile_type: [
            {"name": "declared_invalid_field", "payload": {"Content": {"bad": "x"}}},
            {
                "name": "standalone_below_minimum",
                "standalone": True,
                "field": "Content.grpbandwidth1",
                "boundary": {"kind": "below_minimum"},
                "payload": {"Content": {"grpbandwidth1": "-1"}},
            },
        ],
    )

    cases = neox_profile_module.neox_profile_negative_cases(BoundaryService(), "IGMPGroupPrivilegeProfile")

    assert [case["name"] for case in cases] == [
        "declared_invalid_field",
        "content_grpbandwidth1_above_maximum",
    ]


def test_weight_config_uses_cli_ground_truth_range_zero_to_fifty():
    from services.neox_config.service import neox_profile_minmax_payload

    minimum = neox_profile_minmax_payload("WeightProfile", "min")
    maximum = neox_profile_minmax_payload("WeightProfile", "max")
    cases = {case["name"]: case for case in numeric_boundary_negative_cases(minimum, maximum)}

    assert set(minimum["Content"].values()) == {"0"}
    assert set(maximum["Content"].values()) == {"50"}
    assert len(cases) == 16
    assert cases["content_weight0_below_minimum"]["payload"]["Content"]["weight0"] == "-1"
    assert cases["content_weight0_above_maximum"]["payload"]["Content"]["weight0"] == "51"


def test_neox_profile_error_matrix_confirms_rejected_post_leaves_no_residual(monkeypatch):
    import tests.test_neox_profile as neox_profile_module

    class FakeResponse:
        def __init__(self, retstatus, retresult):
            self.status_code = 200
            self.retstatus = retstatus
            self.retresult = retresult
            self.json = {"retstatus": retstatus, "retresult": retresult}
            self.text = str(self.json)
            self.method = "GET"
            self.url = "/profile/RateLimitProfile/Test"

    class FakeApiClient:
        def __init__(self):
            self.calls = []

        def request(self, method, path, *, session):
            self.calls.append((method, path, session))
            return FakeResponse("Fail", "No data found.")

    class FakeService:
        @staticmethod
        def neox_profile_path(profile_type):
            return f"/profile/{profile_type}/Test"

        @staticmethod
        def neox_profile_name(profile_type):
            return "Test"

    class CleanupRegistry:
        @staticmethod
        def add(callback):
            assert callable(callback)

    api_client = FakeApiClient()
    attachments = []
    rejected = FakeResponse("Fail", "Invalid parameter.")
    monkeypatch.setattr(
        neox_profile_module,
        "neox_profile_negative_cases",
        lambda service, profile_type: [{"name": "below_minimum", "payload": {"Content": {"rate": "63"}}}],
    )
    monkeypatch.setattr(neox_profile_module, "delete_profile_if_exists", lambda *args: None)
    monkeypatch.setattr(neox_profile_module, "post_neox_profile", lambda *args, **kwargs: rejected)
    monkeypatch.setattr(neox_profile_module, "assert_neox_profile_error_response", lambda *args: None)
    monkeypatch.setattr(neox_profile_module, "write_neox_profile_error_report", lambda *args: "report.json")
    monkeypatch.setattr(neox_profile_module, "attach_json", lambda name, payload: attachments.append((name, payload)))

    neox_profile_module.verify_neox_profile_error_cases(
        FakeService(),
        api_client,
        object(),
        "session",
        CleanupRegistry(),
        "RateLimitProfile",
    )

    assert api_client.calls == [("GET", "/profile/RateLimitProfile/Test", "session")]
    assert attachments[0][1]["observations"][0]["residual"]["retstatus"] == "Fail"
