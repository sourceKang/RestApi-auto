from __future__ import annotations

from tests.support import preflight


class FakeItem:
    def __init__(self, name: str, keywords: set[str] | None = None) -> None:
        self.name = name
        self.keywords = keywords or set()


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
