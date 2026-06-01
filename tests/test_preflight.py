from __future__ import annotations

from tests.support import preflight


class FakeItem:
    def __init__(self, name: str, keywords: set[str] | None = None) -> None:
        self.name = name
        self.keywords = keywords or set()
        self.markers = []

    def add_marker(self, marker) -> None:
        self.markers.append(marker)


class FakeConfig:
    def getoption(self, name: str):
        return {
            "--skip-dut-preflight": False,
            "--ems-node": "NODE3",
            "--auth-profile": None,
        }.get(name)


def test_find_down_reason_detects_device_down_message():
    payload = {
        "retstatus": "Success",
        "retval": {
            "ontserviceinfo": {
                "result": "Device 192.168.169.57 is down.",
                "state": "Fail",
            }
        },
    }

    assert preflight._find_down_reason(payload) == "result=Device 192.168.169.57 is down."


def test_find_down_reason_detects_failed_service_state():
    payload = {"retval": {"geserviceinfo": {"state": "Fail"}}}

    assert preflight._find_down_reason(payload) == "state=Fail"


def test_find_down_reason_ignores_healthy_payload():
    payload = {"retval": {"device": {"OperationStatus": "Up", "state": "Success"}}}

    assert preflight._find_down_reason(payload) is None


def test_requires_ont_inventory_only_for_ont_items():
    assert preflight.requires_ont_inventory(FakeItem("test_ont_config_min_create_readwrite"))
    assert preflight.requires_ont_inventory(FakeItem("test_inventory_read", {"ont"}))
    assert not preflight.requires_ont_inventory(FakeItem("test_ge_config_min_create_readwrite", {"neox_config"}))
    assert not preflight.requires_ont_inventory(FakeItem("test_nni_config_min_create_readwrite", {"neox_config"}))
    assert not preflight.requires_ont_inventory(FakeItem("test_vlan_config_min_create_readwrite", {"neox_config"}))


def test_skip_unready_dut_items_does_not_ont_preflight_before_prepare(monkeypatch):
    item = FakeItem("test_ont_read_endpoints_readwrite", {"ont"})
    called = {"ont": False}

    monkeypatch.setattr(preflight, "run_device_preflight", lambda node, auth_profile: preflight.DutPreflightResult(True))

    def fail_if_called(node, auth_profile):
        called["ont"] = True
        return preflight.DutPreflightResult(False, "ONT is not prepared yet")

    monkeypatch.setattr(preflight, "run_ont_preflight", fail_if_called)

    preflight.skip_unready_dut_items(FakeConfig(), [item])

    assert not called["ont"]
    assert item.markers == []
