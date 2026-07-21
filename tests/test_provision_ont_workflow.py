from __future__ import annotations

from types import SimpleNamespace

import pytest

from models.api import ApiResponse
from services.provision.service import ProvisionService
from tests.support.ont_workflow import OntInventoryPreconditionError, OntServiceWorkflowState


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


def test_delete_ont_service_verifies_repeated_delete_is_rejected(monkeypatch):
    client = FakeApiClient(
        [
            response("Success", service=ont_service("#Temporary")),
            response("Success"),
            response("Fail", retresult="No data found in the database."),
            response("Fail", retresult="Serial number does not exist."),
        ]
    )
    service = ProvisionService(client, env_config())
    monkeypatch.setattr(service, "wait_for_ont_service_removed", lambda *args, **kwargs: None)

    service.verify_ont_service_delete("session", ont_template="#Temporary")

    assert [(method, path) for method, path, _ in client.calls] == [
        ("GET", "/ontservice/SN"),
        ("DELETE", "/ontservice/SN"),
        ("GET", "/ontservice/SN"),
        ("DELETE", "/ontservice/SN"),
    ]


def test_existing_ont_post_payload_uses_maximum_wifi_ssid_length():
    from cases.payloads import ont_service_payload

    payload = ont_service_payload(env_config(), "X" * 80, ont_template="#Temporary")

    assert payload["ontservice"]["data"]["wifi5ssid1"] == "X" * 31


def test_ont_workflow_state_tracks_precondition_separately_from_failure():
    state = OntServiceWorkflowState()

    state.block_readiness_precondition(OntInventoryPreconditionError("CLI-only ONT"))

    assert state.readiness_precondition == "CLI-only ONT"
    assert state.readiness_failure == ""
    assert state.inventory_ready is False

    state.begin_post("#Temporary")

    assert state.readiness_precondition == ""
