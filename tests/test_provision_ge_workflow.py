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
        payload["retval"] = {"geserviceinfo": service}
    return ApiResponse(200, payload, "", 0, "request-id", "GET", "https://ems/geservice/device/1/39")


def env_config():
    return SimpleNamespace(
        dut=SimpleNamespace(
            device_name="device",
            device_ip="192.0.2.10",
            ge_slot_id="1",
            ge_port_id="39",
            ge_template="#Formal",
            ge_telephone="011+886+7+2737",
            ge_port_name="1g_Hsinchu",
        )
    )


def ge_service(
    template,
    *,
    state="Success",
    service_id="88",
    telephone="011+886+7+2737",
    port_name="1g_Hsinchu",
):
    return {
        "GeServiceID": service_id,
        "DevName": "device",
        "SlotID": "1",
        "PortID": "39",
        "geTemplate": template,
        "Tel": telephone,
        "PortName": port_name,
        "state": state,
        "data": "{}",
        "result": "--",
    }


def test_post_deletes_any_existing_port_service_then_creates_isolated_service(monkeypatch):
    monkeypatch.setattr("services.provision.service.time.sleep", lambda _seconds: None)
    client = FakeApiClient(
        [
            response("Success", service=ge_service("#Formal")),
            response("Success"),
            response("Fail", retresult="No data found in the database."),
            response("Success"),
            response("Success", service=ge_service("#Temporary")),
            response("Success", service=ge_service("#Temporary")),
        ]
    )

    ProvisionService(client, env_config()).verify_ge_service_post("session", ge_template="#Temporary")

    assert [(method, path) for method, path, _ in client.calls] == [
        ("GET", "/geservice/device/1/39"),
        ("DELETE", "/geservice/88"),
        ("GET", "/geservice/device/1/39"),
        ("POST", "/geservice/device/1/39"),
        ("GET", "/geservice/device/1/39"),
        ("GET", "/geservice/device/1/39"),
    ]


def test_put_refuses_to_modify_service_using_another_template():
    client = FakeApiClient([response("Success", service=ge_service("#Formal"))])

    with pytest.raises(AssertionError, match="Refusing to modify"):
        ProvisionService(client, env_config()).verify_ge_service_put("session", ge_template="#Temporary")

    assert [(method, path) for method, path, _ in client.calls] == [
        ("GET", "/geservice/device/1/39")
    ]


def test_temporary_ge_cleanup_ignores_service_using_another_template():
    client = FakeApiClient([response("Success", service=ge_service("#Formal"))])

    ProvisionService(client, env_config()).delete_ge_service_if_uses_template("session", "#Temporary")

    assert [(method, path) for method, path, _ in client.calls] == [
        ("GET", "/geservice/device/1/39")
    ]


def test_patch_uses_transition_monitor_and_requires_final_success():
    modified = ge_service(
        "#Temporary",
        telephone="011+886+7+27370123",
        port_name="modify_1g_Hsinchu",
    )
    client = FakeApiClient(
        [
            response("Success", service=modified),
            response("Success"),
            response("Success", service=modified),
        ]
    )
    monitor_calls = []

    def transition_monitor(patch_action, state_reader):
        monitor_calls.append("monitor")
        patch_action()
        return state_reader()

    payload = ProvisionService(client, env_config()).verify_ge_service_patch(
        "session",
        ge_template="#Temporary",
        transition_monitor=transition_monitor,
    )

    assert monitor_calls == ["monitor"]
    assert payload["geservice"]["PortName"] == "modify_1g_Hsinchu"
    assert [(method, path) for method, path, _ in client.calls] == [
        ("GET", "/geservice/device/1/39"),
        ("PATCH", "/geservice/88"),
        ("GET", "/geservice/device/1/39"),
    ]


def test_patch_transition_reader_tolerates_transient_missing_service():
    modified = ge_service(
        "#Temporary",
        telephone="011+886+7+27370123",
        port_name="modify_1g_Hsinchu",
    )
    client = FakeApiClient(
        [
            response("Success", service=modified),
            response("Success"),
            response("Fail", retresult="Slot or Port not found."),
            response("Success", service=modified),
        ]
    )
    observed_states = []

    def transition_monitor(patch_action, state_reader):
        patch_action()
        observed_states.append(state_reader()["state"])
        restored = state_reader()
        observed_states.append(restored["state"])
        return restored

    ProvisionService(client, env_config()).verify_ge_service_patch(
        "session",
        ge_template="#Temporary",
        transition_monitor=transition_monitor,
    )

    assert observed_states == ["Missing", "Success"]


def test_delete_ge_service_verifies_repeated_delete_missing_response(monkeypatch):
    client = FakeApiClient(
        [
            response("Success", service=ge_service("#Temporary")),
            response("Success"),
            response("Fail", retresult="No data found in the database."),
            response("Fail", retresult="The GE service does not exist."),
            response("Fail", retresult="No data found in the database."),
        ]
    )
    service = ProvisionService(client, env_config())
    monkeypatch.setattr(service, "wait_for_ge_service_removed", lambda *args, **kwargs: None)

    service.verify_ge_service_delete("session", ge_template="#Temporary")

    assert [(method, path) for method, path, _ in client.calls] == [
        ("GET", "/geservice/device/1/39"),
        ("DELETE", "/geservice/88"),
        ("GET", "/geservice/device/1/39"),
        ("DELETE", "/geservice/88"),
        ("GET", "/geservice/device/1/39"),
    ]


def test_delete_ge_service_accepts_idempotent_success_if_resource_remains_absent(monkeypatch):
    client = FakeApiClient(
        [
            response("Success", service=ge_service("#Temporary")),
            response("Success"),
            response("Fail", retresult="No data found in the database."),
            response("Success"),
            response("Fail", retresult="No data found in the database."),
        ]
    )
    service = ProvisionService(client, env_config())
    monkeypatch.setattr(service, "wait_for_ge_service_removed", lambda *args, **kwargs: None)

    service.verify_ge_service_delete("session", ge_template="#Temporary")

    assert [(method, path) for method, path, _ in client.calls][-2:] == [
        ("DELETE", "/geservice/88"),
        ("GET", "/geservice/device/1/39"),
    ]


def test_existing_ge_post_payload_uses_maximum_port_name_length():
    from cases.payloads import ge_service_payload

    payload = ge_service_payload(env_config(), "X" * 80, ge_template="#Temporary")

    assert payload["geservice"]["PortName"] == "X" * 31
