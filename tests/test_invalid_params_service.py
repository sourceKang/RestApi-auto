from __future__ import annotations

from types import SimpleNamespace

import pytest

from models.api import ApiResponse
from services.invalid_params.service import InvalidParamsService


class FakeApiClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        assert self.responses, f"No fake response left for {method} {path}"
        return self.responses.pop(0)


def response(retresult: str):
    return ApiResponse(
        200,
        {"retstatus": "Fail", "retresult": retresult},
        "",
        0,
        "request-id",
        "POST",
        "https://ems/ontservice/SN",
    )


def service_with(responses):
    env = SimpleNamespace(dut=SimpleNamespace(ont_sn="SN"))
    return InvalidParamsService(FakeApiClient(responses), env, profile_service=SimpleNamespace())


def test_post_ont_invalid_polls_until_prior_sn_reservation_is_released(monkeypatch):
    service = service_with(
        [
            response("SN:SN already exists."),
            response("SN:SN already exists."),
            response("ONT Template not found."),
        ]
    )
    cleanup_calls = []
    monkeypatch.setattr(service, "delete_ont_service_if_exists", lambda session_id: cleanup_calls.append(session_id))
    monkeypatch.setattr("services.invalid_params.service.time.sleep", lambda _seconds: None)

    result = service.post_ont_invalid_after_sn_release(
        "session",
        "/ontservice/SN",
        {"ontservice": {}},
        timeout=30,
        initial_interval=1,
    )

    assert result.retresult == "ONT Template not found."
    assert cleanup_calls == ["session"]
    assert [method for method, _, _ in service.api_client.calls] == ["POST", "POST", "POST"]


def test_post_ont_invalid_fails_when_sn_reservation_never_clears(monkeypatch):
    service = service_with([response("SN:SN already exists.")] * 4)
    cleanup_calls = []
    clock = {"now": 0.0}

    monkeypatch.setattr(service, "delete_ont_service_if_exists", lambda session_id: cleanup_calls.append(session_id))
    monkeypatch.setattr("services.invalid_params.service.time.monotonic", lambda: clock["now"])
    monkeypatch.setattr(
        "services.invalid_params.service.time.sleep",
        lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
    )

    with pytest.raises(AssertionError, match="ONT SN remained reserved"):
        service.post_ont_invalid_after_sn_release(
            "session",
            "/ontservice/SN",
            {"ontservice": {}},
            timeout=3,
            initial_interval=1,
            max_interval=1,
        )

    assert cleanup_calls == ["session"]
    assert len(service.api_client.calls) == 4


def test_ont_invalid_matrix_includes_below_above_and_long_integer(monkeypatch):
    service = service_with([])
    captured_payloads = []
    combined_error = (
        "ONT Template not found. dspir: Range 128~10000000 "
        "inactive value is error maximum length is 31"
    )

    monkeypatch.setattr(service, "delete_ont_service_if_exists", lambda _session_id: None)
    monkeypatch.setattr(
        "services.invalid_params.service.ont_service_payload",
        lambda env, name, ont_template=None: {"ontservice": {"data": {}}},
    )

    def reject(_session_id, _path, payload, **_kwargs):
        captured_payloads.append(payload)
        return response(combined_error)

    monkeypatch.setattr(service, "post_ont_invalid_after_sn_release", reject)

    service.verify_ont_service_post_invalid_parameters("session", ont_template="#Temporary")

    dspir_values = [
        payload["ontservice"]["data"]["dspir"]
        for payload in captured_payloads
        if "dspir" in payload["ontservice"]["data"]
    ]
    assert dspir_values == ["127", "10000001", "9" * 66]
