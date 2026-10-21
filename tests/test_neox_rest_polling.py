from contextlib import contextmanager
from models.api import ApiResponse
from tests.test_neox_config import (
    cleanup_ont_provision_template_scenario,
    restore_ont_config_exact_baseline,
    wait_for_rest_tokens,
)


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


def test_wait_for_rest_tokens_requires_exact_validator_and_consecutive_samples():
    clock = FakeClock()
    client = FakeApiClient(
        [
            response(200, "Success", retval={"ontinfo": {"description": "", "history": "baseline"}}),
            response(200, "Success", retval={"ontinfo": {"description": "baseline"}}),
            response(200, "Success", retval={"ontinfo": {"description": "changed"}}),
            response(200, "Success", retval={"ontinfo": {"description": "baseline"}}),
            response(200, "Success", retval={"ontinfo": {"description": "baseline"}}),
        ]
    )

    def exact_description(api_response):
        return api_response.json["retval"]["ontinfo"].get("description") == "baseline"

    result = wait_for_rest_tokens(
        client,
        "/ont/sn/SN-1",
        "session",
        ["baseline"],
        timeout=30,
        interval=1,
        max_interval=1,
        response_validator=exact_description,
        consecutive_successes=2,
        sleeper=clock.sleep,
        clock=clock.monotonic,
    )

    assert result.json["retval"]["ontinfo"]["description"] == "baseline"
    assert len(client.calls) == 5


def test_wait_for_rest_tokens_fails_immediately_when_session_loses_authorization():
    clock = FakeClock()
    client = FakeApiClient([response(200, "Fail", "Not authorized.")])

    try:
        wait_for_rest_tokens(
            client,
            "/ont/sn/SN-1",
            "expired-session",
            ["baseline"],
            timeout=180,
            interval=15,
            sleeper=clock.sleep,
            clock=clock.monotonic,
        )
    except AssertionError as error:
        assert "fresh session" in str(error)
    else:
        raise AssertionError("Authorization loss must fail immediately")

    assert len(client.calls) == 1
    assert clock.sleeps == []


def test_wait_for_rest_tokens_counts_polls_and_can_skip_timeout_scaling():
    clock = FakeClock()
    client = FakeApiClient([response(200, "Fail", "No data found in the database.")])
    client.env = type("Env", (), {"wait_scale": 1.5})()
    stats = {"polls": 2}

    try:
        wait_for_rest_tokens(
            client,
            "/ont/sn/SN-1",
            "session",
            ["SN-1"],
            timeout=30,
            interval=15,
            max_interval=15,
            scale_timeout=False,
            stats=stats,
            sleeper=clock.sleep,
            clock=clock.monotonic,
        )
    except AssertionError:
        pass

    assert clock.sleeps == [15, 15]
    assert stats["polls"] == 2 + 3


class Provision:
    def __init__(self, events, fail=False):
        self.events = events
        self.fail = fail

    def delete_ont_service_if_uses_template(self, session_id, *args, **kwargs):
        self.events.append(("service_delete", session_id))
        if self.fail:
            raise AssertionError("delete failed")


class RecordingApiClient:
    def __init__(self, events):
        self.events = events

    def request(self, method, path, *, session, json=None):
        self.events.append((method.lower(), session))
        return type("Response", (), {"retstatus": "Success"})()


class RotatingSessions:
    def __init__(self, events):
        self.events = events
        self.count = 0

    @contextmanager
    def role_session(self, role):
        self.count += 1
        session_id = f"fresh-{self.count}"
        self.events.append(("session_open", session_id))
        try:
            yield session_id
        finally:
            self.events.append(("session_close", session_id))


def _patch_convergence(monkeypatch, events, *, rest_error=None):
    def fake_rest(api_client, path, session_id, tokens, **kwargs):
        events.append(("rest_verify", session_id, kwargs["consecutive_successes"], kwargs["interval"], kwargs["max_interval"]))
        kwargs["stats"]["polls"] += 1
        if rest_error:
            raise AssertionError(rest_error)

    monkeypatch.setattr("tests.support.ont_baseline.wait_for_rest_tokens", fake_rest)
    monkeypatch.setattr("tests.support.ont_baseline.assert_api_success", lambda response: None)
    monkeypatch.setattr("tests.support.ont_baseline.wait_for_ont_cli_is", lambda *args, **kwargs: events.append(("cli_is",)))
    monkeypatch.setattr(
        "tests.support.ont_baseline.wait_for_ont_cli_config_tokens",
        lambda *args, **kwargs: events.append(("cli_config", kwargs["expected_tokens"], kwargs["absent_tokens"])),
    )
    monkeypatch.setattr("tests.support.ont_baseline.attach_json", lambda *args, **kwargs: None)


def test_restore_ont_config_exact_baseline_posts_once_and_polls_in_fresh_sessions(monkeypatch):
    events = []
    _patch_convergence(monkeypatch, events)
    payload = {"Content": {"ontdescription": "baseline", "templatename": ""}}

    restore_ont_config_exact_baseline(
        RecordingApiClient(events),
        object(),
        RotatingSessions(events),
        "/config/ont",
        payload,
        "/ont/sn/SN-1",
        ["ONT-1", "SN-1", "baseline"],
        "3-16-1",
        verify_cli=True,
        attachment_name="test cleanup",
    )

    assert [event for event in events if event[0] in {"post", "rest_verify"}] == [
        ("post", "fresh-1"),
        ("rest_verify", "fresh-2", 4, 15, 15),
    ]
    assert ("cli_config", ("3-16-1", "description baseline"), ("template #RestApi_provision_temp_SFU",)) in events


def test_restore_ont_config_exact_baseline_raises_when_rest_never_converges(monkeypatch):
    events = []
    _patch_convergence(monkeypatch, events, rest_error="not stable")

    try:
        restore_ont_config_exact_baseline(
            RecordingApiClient(events),
            object(),
            RotatingSessions(events),
            "/config/ont",
            {"Content": {"ontdescription": "baseline"}},
            "/ont/sn/SN-1",
            ["SN-1"],
            "3-16-1",
            verify_cli=False,
            attachment_name="test cleanup",
        )
    except AssertionError as error:
        assert "did not converge" in str(error) and "not stable" in str(error)
    else:
        raise AssertionError("A restore that never converges must fail the strict cleanup")

    assert [event[0] for event in events].count("post") == 1


def test_provision_template_cleanup_clears_then_restores_once_with_fresh_sessions(monkeypatch):
    events = []
    _patch_convergence(monkeypatch, events)
    monkeypatch.setattr("tests.test_neox_config.wait_for_ont_cli_config_absent", lambda *args, **kwargs: events.append(("config_cleared",)))
    monkeypatch.setattr("tests.test_neox_config.wait_for_ont_cli_state", lambda *args, **kwargs: events.append(("ont_unregistered",)))

    cleanup_ont_provision_template_scenario(
        RecordingApiClient(events),
        object(),
        type("Services", (), {"provision": Provision(events)})(),
        "expired-session",
        "template",
        "3-16-1",
        "/config/ont",
        {"Content": {"ontdescription": "baseline"}},
        "/ont/sn/SN-1",
        ["SN-1", "baseline"],
        verify_cli=True,
        session_manager=RotatingSessions(events),
    )

    steps = [event for event in events if event[0] not in {"session_open", "session_close"}]
    assert steps == [
        ("service_delete", "fresh-1"),
        ("delete", "fresh-2"),
        ("config_cleared",),
        ("ont_unregistered",),
        ("post", "fresh-3"),
        ("rest_verify", "fresh-4", 4, 15, 15),
        ("cli_is",),
        ("cli_config", ("description baseline",), ("template template",)),
    ]


def test_provision_template_cleanup_restores_even_when_service_removal_fails(monkeypatch):
    events = []
    _patch_convergence(monkeypatch, events)
    monkeypatch.setattr("tests.test_neox_config.wait_for_ont_cli_config_absent", lambda *args, **kwargs: events.append(("config_cleared",)))
    monkeypatch.setattr("tests.test_neox_config.wait_for_ont_cli_state", lambda *args, **kwargs: events.append(("ont_unregistered",)))

    try:
        cleanup_ont_provision_template_scenario(
            RecordingApiClient(events),
            object(),
            type("Services", (), {"provision": Provision(events, fail=True)})(),
            "session",
            "template",
            "3-16-1",
            "/config/ont",
            {"Content": {"ontdescription": "baseline"}},
            "/ont/sn/SN-1",
            ["SN-1", "baseline"],
            verify_cli=False,
        )
    except AssertionError as error:
        assert "delete failed" in str(error)
    else:
        raise AssertionError("Cleanup must preserve the service-removal failure")

    assert [event[0] for event in events] == ["service_delete", "delete", "config_cleared", "ont_unregistered", "post", "rest_verify"]
