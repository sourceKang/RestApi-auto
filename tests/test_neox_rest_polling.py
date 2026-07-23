from contextlib import contextmanager
from models.api import ApiResponse
from tests.test_neox_config import (
    cleanup_ont_provision_template_scenario,
    restore_ont_config_baseline,
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


def test_restore_ont_config_exact_baseline_uses_fresh_session_and_exact_polling(monkeypatch):
    events = []

    class SessionManager:
        @contextmanager
        def role_session(self, role):
            events.append(("session_open", role))
            try:
                yield "fresh-session"
            finally:
                events.append(("session_close", "fresh-session"))

    monkeypatch.setattr(
        "tests.test_neox_config.restore_ont_config_baseline",
        lambda api_client, env, path, session_id, payload, verify_cli: events.append(
            ("baseline_post", session_id, payload)
        ),
    )
    monkeypatch.setattr(
        "tests.test_neox_config.wait_for_rest_tokens",
        lambda api_client, path, session_id, tokens, **kwargs: events.append(
            ("rest_verify", session_id, tokens, kwargs["consecutive_successes"])
        ),
    )
    monkeypatch.setattr(
        "tests.test_neox_config.wait_for_ont_cli_is",
        lambda *args, **kwargs: events.append(("cli_state", "IS")),
    )
    monkeypatch.setattr(
        "tests.test_neox_config.wait_for_ont_cli_config_tokens",
        lambda *args, **kwargs: events.append(
            (
                "cli_config",
                kwargs["expected_tokens"],
                kwargs["absent_tokens"],
                kwargs["consecutive_successes"],
            )
        ),
    )
    monkeypatch.setattr("tests.test_neox_config.attach_json", lambda *args, **kwargs: None)

    payload = {"Content": {"ontdescription": "baseline", "templatename": ""}}
    restore_ont_config_exact_baseline(
        object(),
        object(),
        SessionManager(),
        "/config/ont",
        payload,
        "/ont/sn/SN-1",
        ["ONT-1", "SN-1", "baseline"],
        "3-16-1",
        verify_cli=True,
        attachment_name="test cleanup",
    )

    assert ("baseline_post", "fresh-session", payload) in events
    assert ("rest_verify", "fresh-session", ["ONT-1", "SN-1", "baseline"], 4) in events
    assert ("cli_config", ("3-16-1", "description baseline"), ("template #RestApi_provision_temp_SFU",), 4) in events
    assert events[0][0] == "session_open"
    assert ("session_close", "fresh-session") in events


def test_provision_template_cleanup_restores_before_rest_and_cli_verification(monkeypatch):
    events = []

    class Provision:
        @staticmethod
        def delete_ont_service_if_uses_template(*args, **kwargs):
            events.append("service_removed")

    class Services:
        provision = Provision()

    class ApiClient:
        @staticmethod
        def request(method, path, *, session):
            events.append("config_delete_requested")
            return type("Response", (), {"retstatus": "Success"})()

    monkeypatch.setattr(
        "tests.test_neox_config.wait_for_ont_cli_config_absent",
        lambda *args, **kwargs: events.append("config_cleared"),
    )
    monkeypatch.setattr(
        "tests.test_neox_config.wait_for_ont_cli_state",
        lambda *args, **kwargs: events.append("ont_unregistered"),
    )
    monkeypatch.setattr(
        "tests.test_neox_config.restore_ont_config_baseline",
        lambda *args, **kwargs: events.append("baseline_restored"),
    )
    monkeypatch.setattr(
        "tests.test_neox_config.wait_for_rest_tokens",
        lambda *args, **kwargs: events.append("rest_verified"),
    )
    monkeypatch.setattr(
        "tests.test_neox_config.wait_for_ont_cli_is",
        lambda *args, **kwargs: events.append("cli_verified"),
    )

    monkeypatch.setattr(
        "tests.test_neox_config.wait_for_ont_cli_config_tokens",
        lambda *args, **kwargs: events.append("cli_config_verified"),
    )
    cleanup_ont_provision_template_scenario(
        ApiClient(),
        object(),
        Services(),
        "session",
        "template",
        "3-16-1",
        "/config/ont",
        {"Content": {"description": "baseline"}},
        "/ont/sn/SN-1",
        ["SN-1", "baseline"],
        verify_cli=True,
    )

    assert events == [
        "service_removed",
        "config_delete_requested",
        "config_cleared",
        "ont_unregistered",
        "baseline_restored",
        "rest_verified",
        "cli_verified",
        "cli_config_verified",
    ]


def test_provision_template_cleanup_reposts_baseline_once_after_nonconvergence(monkeypatch):
    events = []
    rest_attempts = {"count": 0}

    class Provision:
        @staticmethod
        def delete_ont_service_if_uses_template(*args, **kwargs):
            events.append("service_removed")

    class Services:
        provision = Provision()

    class ApiClient:
        @staticmethod
        def request(method, path, *, session):
            events.append("config_delete_requested")
            return type("Response", (), {"retstatus": "Success"})()

    def wait_for_rest(*args, **kwargs):
        rest_attempts["count"] += 1
        events.append(f"rest_attempt_{rest_attempts['count']}")
        if rest_attempts["count"] == 1:
            raise AssertionError("not converged")

    monkeypatch.setattr("tests.test_neox_config.wait_for_ont_cli_config_absent", lambda *args, **kwargs: None)
    monkeypatch.setattr("tests.test_neox_config.wait_for_ont_cli_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "tests.test_neox_config.restore_ont_config_baseline",
        lambda *args, **kwargs: events.append("baseline_posted"),
    )
    monkeypatch.setattr("tests.test_neox_config.wait_for_rest_tokens", wait_for_rest)
    monkeypatch.setattr("tests.test_neox_config.attach_json", lambda *args, **kwargs: None)

    cleanup_ont_provision_template_scenario(
        ApiClient(),
        object(),
        Services(),
        "session",
        "template",
        "3-16-1",
        "/config/ont",
        {"Content": {"description": "baseline"}},
        "/ont/sn/SN-1",
        ["SN-1", "baseline"],
        verify_cli=False,
    )

    assert events == [
        "service_removed",
        "config_delete_requested",
        "baseline_posted",
        "rest_attempt_1",
        "baseline_posted",
        "rest_attempt_2",
    ]


def test_provision_template_cleanup_restores_even_when_service_removal_fails(monkeypatch):
    events = []

    class Provision:
        @staticmethod
        def delete_ont_service_if_uses_template(*args, **kwargs):
            events.append("service_remove_failed")
            raise AssertionError("delete failed")

    class Services:
        provision = Provision()

    class ApiClient:
        @staticmethod
        def request(method, path, *, session):
            events.append("config_delete_requested")
            return type("Response", (), {"retstatus": "Success"})()

    monkeypatch.setattr(
        "tests.test_neox_config.wait_for_ont_cli_config_absent",
        lambda *args, **kwargs: events.append("config_cleared"),
    )
    monkeypatch.setattr(
        "tests.test_neox_config.wait_for_ont_cli_state",
        lambda *args, **kwargs: events.append("ont_unregistered"),
    )
    monkeypatch.setattr(
        "tests.test_neox_config.restore_ont_config_baseline",
        lambda *args, **kwargs: events.append("baseline_restored"),
    )
    monkeypatch.setattr(
        "tests.test_neox_config.wait_for_rest_tokens",
        lambda *args, **kwargs: events.append("rest_verified"),
    )

    try:
        cleanup_ont_provision_template_scenario(
            ApiClient(),
            object(),
            Services(),
            "session",
            "template",
            "3-16-1",
            "/config/ont",
            {"Content": {"description": "baseline"}},
            "/ont/sn/SN-1",
            ["SN-1", "baseline"],
            verify_cli=False,
        )
    except AssertionError as error:
        assert "delete failed" in str(error)
    else:
        raise AssertionError("Cleanup must preserve the service-removal failure")

    assert events == ["service_remove_failed", "config_delete_requested", "config_cleared", "ont_unregistered", "baseline_restored", "rest_verified"]


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


def test_provision_template_cleanup_rotates_fresh_sessions_for_each_rest_phase(monkeypatch):
    events = []

    class Provision:
        @staticmethod
        def delete_ont_service_if_uses_template(session_id, *args, **kwargs):
            events.append(("service_delete", session_id))

    class Services:
        provision = Provision()

    class ApiClient:
        @staticmethod
        def request(method, path, *, session):
            events.append(("config_delete", session))
            return type("Response", (), {"retstatus": "Success"})()

    class SessionManager:
        def __init__(self):
            self.count = 0

        @contextmanager
        def role_session(self, role):
            self.count += 1
            session_id = f"fresh-{self.count}"
            events.append(("session_open", session_id))
            try:
                yield session_id
            finally:
                events.append(("session_close", session_id))

    monkeypatch.setattr("tests.test_neox_config.wait_for_ont_cli_config_absent", lambda *args, **kwargs: None)
    monkeypatch.setattr("tests.test_neox_config.wait_for_ont_cli_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "tests.test_neox_config.restore_ont_config_baseline",
        lambda api_client, env, path, session_id, payload, verify_cli: events.append(
            ("baseline_post", session_id)
        ),
    )
    monkeypatch.setattr(
        "tests.test_neox_config.wait_for_rest_tokens",
        lambda api_client, path, session_id, *args, **kwargs: events.append(
            ("rest_verify", session_id)
        ),
    )
    monkeypatch.setattr("tests.test_neox_config.attach_json", lambda *args, **kwargs: None)

    cleanup_ont_provision_template_scenario(
        ApiClient(),
        object(),
        Services(),
        "expired-session",
        "template",
        "3-16-1",
        "/config/ont",
        {"Content": {"ontdescription": "baseline"}},
        "/ont/sn/SN-1",
        ["SN-1", "baseline"],
        verify_cli=False,
        session_manager=SessionManager(),
    )

    assert ("service_delete", "fresh-1") in events
    assert ("config_delete", "fresh-2") in events
    assert ("baseline_post", "fresh-3") in events
    assert ("rest_verify", "fresh-3") in events
