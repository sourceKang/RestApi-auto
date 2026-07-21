from models.api import ApiResponse
from tests.test_neox_config import restore_ont_config_baseline, wait_for_rest_tokens


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FakeApiClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, path, *, session, json=None):
        self.calls.append((method, path, session, json))
        if len(self.responses) > 1:
            return self.responses.pop(0)
        return self.responses[0]


def response(status_code, retstatus, retresult="", retval=None):
    payload = {"retstatus": retstatus, "retresult": retresult}
    if retval is not None:
        payload["retval"] = retval
    return ApiResponse(status_code, payload, "", 0, "id", "GET", "url")


def test_wait_for_rest_tokens_recovers_from_transient_500_and_no_data():
    clock = FakeClock()
    client = FakeApiClient(
        [
            response(500, "Fail", "Internal Server Error"),
            response(200, "Fail", "No data found in the database."),
            response(200, "Success", retval={"ont": ["ONT-1", "SN-1", "READY"]}),
        ]
    )

    result = wait_for_rest_tokens(
        client,
        "/ont/sn/SN-1",
        "session",
        ["ONT-1", "SN-1", "READY"],
        timeout=30,
        interval=1,
        max_interval=4,
        sleeper=clock.sleep,
        clock=clock.monotonic,
    )

    assert result.retstatus == "Success"
    assert len(client.calls) == 3
    assert clock.sleeps == [1, 2]


def test_wait_for_rest_tokens_fails_after_total_timeout_for_persistent_no_data():
    clock = FakeClock()
    client = FakeApiClient([response(200, "Fail", "No data found in the database.")])

    try:
        wait_for_rest_tokens(
            client,
            "/ont/sn/SN-1",
            "session",
            ["SN-1"],
            timeout=3,
            interval=1,
            max_interval=2,
            sleeper=clock.sleep,
            clock=clock.monotonic,
        )
    except AssertionError as error:
        assert "No data found" in str(error)
    else:
        raise AssertionError("Persistent no-data response must fail after the total timeout")

    assert clock.sleeps == [1, 2]


def test_restore_ont_config_baseline_posts_original_payload_without_delete_and_waits_for_cli(monkeypatch):
    clock = []
    client = FakeApiClient([response(200, "Success")])
    monkeypatch.setattr(
        "tests.test_neox_config.wait_for_ont_cli_is",
        lambda env, timeout, interval: clock.append((env, timeout, interval)),
    )
    env = object()
    payload = {"Content": {"description": "baseline"}}

    result = restore_ont_config_baseline(
        client,
        env,
        "/config/ont",
        "session",
        payload,
        verify_cli=True,
    )

    assert result.retstatus == "Success"
    assert [(method, path) for method, path, _, _ in client.calls] == [
        ("POST", "/config/ont"),
    ]
    assert client.calls[0][3] == payload
    assert clock == [(env, 180, 15)]
