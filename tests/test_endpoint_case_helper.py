from __future__ import annotations

from types import SimpleNamespace

from cases.endpoint_cases import READ_ENDPOINTS
from models.api import EndpointCase
from services.endpoint_case import request_endpoint_case


class RecordingClient:
    def __init__(self):
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return {"ok": True}


class Env:
    value = "target"


def test_inventory_port_paths_fallback_to_ont_target_without_ge_target():
    cases = {case.name: case for case in READ_ENDPOINTS}
    env = SimpleNamespace(
        dut=SimpleNamespace(
            device_name="NODE2",
            slot_id="0",
            port_id="8",
            ge_slot_id="",
            ge_port_id="",
        )
    )

    assert cases["port_by_slot"].build_path(env) == "/port/NODE2/0"
    assert cases["port_by_id"].build_path(env) == "/port/NODE2/0/8"


def test_request_endpoint_case_builds_path_params_and_session():
    client = RecordingClient()
    case = EndpointCase(
        "read_case",
        "GET",
        "inventory",
        lambda env: f"/device/{env.value}",
        params_factory=lambda env, name: {"filter": env.value, "name": name},
    )

    response = request_endpoint_case(client, Env(), "session-1", case, step="GET read_case")

    assert response == {"ok": True}
    method, path, kwargs = client.calls[0]
    assert method == "GET"
    assert path == "/device/target"
    assert kwargs["session"] == "session-1"
    assert kwargs["params"]["filter"] == "target"
    assert "_read_case_" in kwargs["params"]["name"]
    assert "json" not in kwargs


def test_request_endpoint_case_builds_payload_for_mutation():
    client = RecordingClient()
    case = EndpointCase(
        "mutating_case",
        "POST",
        "provision",
        "/ontservice/abc",
        payload_factory=lambda env, name: {"name": name, "value": env.value},
    )

    request_endpoint_case(client, Env(), "session-2", case, step="POST mutating_case", payload=True)

    method, path, kwargs = client.calls[0]
    assert method == "POST"
    assert path == "/ontservice/abc"
    assert kwargs["session"] == "session-2"
    assert kwargs["params"] is None
    assert "_mutating_case_" in kwargs["json"]["name"]
    assert kwargs["json"]["value"] == "target"
