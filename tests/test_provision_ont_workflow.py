from __future__ import annotations

from types import SimpleNamespace

import pytest

from models.api import ApiResponse
from services.provision.service import ProvisionService


class FakeApiClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        assert self.responses, f"No fake response left for {method} {path}"
        return self.responses.pop(0)


def response(retstatus, *, retresult="", service=None):
    payload = {"retstatus": retstatus, "retresult": retresult}
    if service is not None:
        payload["retval"] = {"ontserviceinfo": service}
    return ApiResponse(200, payload, "", 0, "request-id", "GET", "https://ems/ontservice/SN")


def env_config():
    return SimpleNamespace(
        dut=SimpleNamespace(
            ont_sn="SN",
            ont_template="#Formal",
            ont_password="placeholder",
            ont_description="workflow_ont",
            slot_id="2",
            port_id="16",
            ont_id="1",
        )
    )


def ont_service(template, *, state="Success"):
    return {
        "ontTemplate": template,
        "Desc": "workflow_ont",
        "password": "placeholder",
        "Slot": "2",
        "Port": "16",
        "ONT": "1",
        "sn": "SN",
        "state": state,
        "data": {
            "templateprof": template,
            "description": "workflow_ont",
            "wifi5ssid1": "musk_wifi5",
            "wifi5pass1": "musk1234",
        },
    }


def test_post_refuses_to_delete_service_using_another_template():
    client = FakeApiClient([response("Success", service=ont_service("#Formal"))])
    service = ProvisionService(client, env_config())

    with pytest.raises(AssertionError, match="Refusing to modify"):
        service.verify_ont_service_post("session", ont_template="#Temporary")

    assert [(method, path) for method, path, _ in client.calls] == [
        ("GET", "/ontservice/SN")
    ]


def test_post_creates_service_and_waits_for_service_success(monkeypatch):
    monkeypatch.setattr("services.provision.service.time.sleep", lambda _seconds: None)
    client = FakeApiClient(
        [
            response("Fail", retresult="No data found in the database."),
            response("Success"),
            response("Success", service=ont_service("#Temporary")),
        ]
    )
    service = ProvisionService(client, env_config())

    service.verify_ont_service_post("session", ont_template="#Temporary")

    assert [(method, path) for method, path, _ in client.calls] == [
        ("GET", "/ontservice/SN"),
        ("POST", "/ontservice/SN"),
        ("GET", "/ontservice/SN"),
    ]
