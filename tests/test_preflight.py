from __future__ import annotations

from models.api import ApiResponse
from tests.support import preflight
from tests.support.target_sync import TargetSyncResult


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


def test_find_unready_devstatus_rejects_status_other_than_one():
    payload = {
        "retstatus": "Success",
        "retval": {
            "deviceinfo": {
                "DevName": "Taiwan_NeoX-03_169.58",
                "IPAddress": "192.168.169.58",
                "DevStatus": "4",
            }
        },
    }

    assert (
        preflight._find_unready_devstatus(payload)
        == "DevStatus=4 DevName=Taiwan_NeoX-03_169.58 IPAddress=192.168.169.58; expected DevStatus=1"
    )


def test_find_unready_devstatus_accepts_status_one():
    payload = {"retval": {"deviceinfo": {"DevStatus": "1"}}}

    assert preflight._find_unready_devstatus(payload) is None


def test_check_success_fails_device_inventory_when_devstatus_is_not_one():
    response = ApiResponse(
        status_code=200,
        json={"retstatus": "Success", "retval": {"deviceinfo": {"DevStatus": "4", "DevName": "NODE3", "IPAddress": "1.2.3.4"}}},
        text="",
        elapsed=0,
        request_id="test",
        method="GET",
        url="https://ems/device/NODE3",
    )

    class FakeClient:
        def request(self, method, path, *, session):
            return response

    result = preflight._check_success(FakeClient(), "session", "/device/NODE3", "device inventory")

    assert not result.ok
    assert "DevStatus=4" in result.reason
    assert "expected DevStatus=1" in result.reason


def test_requires_ont_inventory_only_for_ont_items():
    assert preflight.requires_ont_inventory(FakeItem("test_ont_config_min_create_readwrite"))
    assert preflight.requires_ont_inventory(FakeItem("test_inventory_read", {"ont"}))
    assert not preflight.requires_ont_inventory(FakeItem("test_ge_config_min_create_readwrite", {"neox_config"}))
    assert not preflight.requires_ont_inventory(FakeItem("test_nni_config_min_create_readwrite", {"neox_config"}))
    assert not preflight.requires_ont_inventory(FakeItem("test_vlan_config_min_create_readwrite", {"neox_config"}))


def test_skip_unready_dut_items_does_not_ont_preflight_before_prepare(monkeypatch):
    item = FakeItem("test_ont_read_endpoints_readwrite", {"ont"})
    called = {"ont": False}

    monkeypatch.setattr(preflight, "run_startup_preflight", lambda node, auth_profile: preflight.DutPreflightResult(True))

    def fail_if_called(node, auth_profile):
        called["ont"] = True
        return preflight.DutPreflightResult(False, "ONT is not prepared yet")

    monkeypatch.setattr(preflight, "run_ont_preflight", fail_if_called)

    preflight.skip_unready_dut_items(FakeConfig(), [item])

    assert not called["ont"]
    assert item.markers == []


def test_check_success_retries_device_inventory_until_devstatus_is_one(monkeypatch):
    responses = [
        ApiResponse(
            status_code=200,
            json={"retstatus": "Success", "retval": {"deviceinfo": {"DevStatus": "4", "DevName": "NODE3", "IPAddress": "1.2.3.4"}}},
            text="",
            elapsed=0,
            request_id="test-1",
            method="GET",
            url="https://ems/device/NODE3",
        ),
        ApiResponse(
            status_code=200,
            json={"retstatus": "Success", "retval": {"deviceinfo": {"DevStatus": "1", "DevName": "NODE3", "IPAddress": "1.2.3.4"}}},
            text="",
            elapsed=0,
            request_id="test-2",
            method="GET",
            url="https://ems/device/NODE3",
        ),
    ]
    sleeps = []

    class FakeClient:
        def request(self, method, path, *, session):
            return responses.pop(0)

    monkeypatch.setattr(preflight.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = preflight._check_success(
        FakeClient(),
        "session",
        "/device/NODE3",
        "device inventory",
        attempts=2,
        interval_seconds=20,
    )

    assert result.ok
    assert sleeps == [20]


def test_startup_preflight_stops_when_target_sync_fails(monkeypatch):
    monkeypatch.setattr(
        preflight,
        "sync_target_data_from_cli",
        lambda node, auth_profile: TargetSyncResult(False, "show lc st failed"),
    )

    def fail_if_called(node, auth_profile):
        raise AssertionError("device preflight should not run after target sync failure")

    monkeypatch.setattr(preflight, "run_device_preflight", fail_if_called)

    result = preflight.run_startup_preflight("NODE1", None)

    assert not result.ok
    assert result.reason == "show lc st failed"
