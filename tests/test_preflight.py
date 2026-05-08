from __future__ import annotations

from tests.support import preflight


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
