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


class _RemoteApiClient(_SuccessApiClient):
    def __init__(self, remote_retval):
        super().__init__()
        self.remote_retval = remote_retval

    def request(self, method, path, **kwargs):
        response = super().request(method, path, **kwargs)
        if path.startswith("/remote/"):
            self.remote_payload = kwargs.get("json")
            return ApiResponse(
                status_code=200,
                json={"retstatus": "Success", "retresult": "", "retval": self.remote_retval},
                text="",
                elapsed=0.0,
                request_id="unit",
                method=method,
                url=f"https://ems.invalid{path}",
            )
        return response


def _env_with_device():
    env = _env(ge_target=False)
    env.dut.device_name = "UNIT_DEVICE"
    return env


def test_rad_readwrite_skips_remote_console_unless_enabled():
    client = _RemoteApiClient({"return": ["Firmware version V1.02"]})

    AuthMatrixService(client).verify_rad_readwrite_summary(_env_with_device(), "rad-rw")

    assert all(not path.startswith("/remote/") for _method, path, _session in client.requests)


def test_rad_readwrite_runs_read_only_remote_console_when_enabled():
    client = _RemoteApiClient({"return": ["Firmware version V1.02"]})

    AuthMatrixService(client).verify_rad_readwrite_summary(_env_with_device(), "rad-rw", include_remote=True)

    assert ("POST", "/remote/UNIT_DEVICE", "rad-rw") in client.requests
    assert client.remote_payload == {"command": ["show version"]}


def test_rad_readwrite_remote_console_requires_command_output():
    client = _RemoteApiClient({"return": []})

    try:
        AuthMatrixService(client).verify_rad_readwrite_summary(_env_with_device(), "rad-rw", include_remote=True)
    except AssertionError as error:
        assert "version" in str(error)
    else:
        raise AssertionError("Remote console without CLI output must fail")
