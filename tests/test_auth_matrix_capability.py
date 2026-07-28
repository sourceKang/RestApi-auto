from __future__ import annotations

from types import SimpleNamespace

from models.api import ApiResponse
from services.auth_matrix.service import AuthMatrixService, has_ge_target
from tests.test_auth_matrix import auth_matrix_seed_data


class _SuccessApiClient:
    def __init__(self):
        self.requests = []

    def request(self, method, path, **kwargs):
        self.requests.append((method, path, kwargs.get("session")))
        return ApiResponse(
            status_code=200,
            json={"retstatus": "Success", "retresult": "", "retval": {}},
            text="",
            elapsed=0.0,
            request_id="unit",
            method=method,
            url=f"https://ems.invalid{path}",
        )


def _env(*, ge_target: bool):
    return SimpleNamespace(
        dut=SimpleNamespace(
            node_key="NODE2",
            device_ip="192.0.2.2",
            ont_sn="UNIT_TEST_SN",
            ge_slot_id="1" if ge_target else "",
            ge_port_id="39" if ge_target else "",
        )
    )


def test_auth_matrix_seed_does_not_request_ge_fixture_without_target():
    requested = []
    request = SimpleNamespace(getfixturevalue=lambda name: requested.append(name))
    fixture = auth_matrix_seed_data.__wrapped__(request, _env(ge_target=False), "#ONT")

    assert next(fixture) == {"ont_template": "#ONT", "ge_template": None}
    assert requested == []


def test_auth_matrix_seed_requests_ge_fixture_when_target_exists():
    request = SimpleNamespace(getfixturevalue=lambda name: "#GE" if name == "prepared_ge_service" else None)
    fixture = auth_matrix_seed_data.__wrapped__(request, _env(ge_target=True), "#ONT")

    assert next(fixture) == {"ont_template": "#ONT", "ge_template": "#GE"}


def test_rad_readwrite_without_ge_target_omits_ge_service_requests():
    client = _SuccessApiClient()
    env = _env(ge_target=False)

    AuthMatrixService(client).verify_rad_readwrite_summary(env, "rad-rw")

    assert not has_ge_target(env)
    assert all(not path.startswith("/geservice") for _method, path, _session in client.requests)
    assert any(path.startswith("/ontservice/") for _method, path, _session in client.requests)
