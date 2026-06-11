from __future__ import annotations

import pytest

from tests.support import connectivity
from tests.support.connectivity import PingResult, assert_ping_reachable, ping_attachment


def test_ping_attachment_uses_line_arrays_for_readability():
    result = PingResult(
        target="192.0.2.1",
        checkpoint="after_cli_verify",
        command=["ping", "-n", "2", "192.0.2.1"],
        returncode=0,
        stdout="line 1\nline 2\n",
        stderr="",
        duration_seconds=0.1,
    )

    attachment = ping_attachment(result)

    assert attachment["command_text"] == "ping -n 2 192.0.2.1"
    assert attachment["stdout_lines"] == ["line 1", "line 2"]
    assert attachment["stderr_lines"] == []
    assert "stdout" not in attachment
    assert "stderr" not in attachment


def test_assert_ping_reachable_retries_transient_failure(monkeypatch):
    results = [
        PingResult("192.0.2.1", "before_case", ["ping"], 1, "timeout", "", 2.0),
        PingResult("192.0.2.1", "before_case", ["ping"], 0, "reply", "", 0.1),
    ]
    attachments = []

    monkeypatch.setattr(connectivity, "ping_host", lambda *args, **kwargs: results.pop(0))
    monkeypatch.setattr(connectivity, "attach_json", lambda name, body: attachments.append((name, body)))
    monkeypatch.setattr(connectivity.time, "sleep", lambda seconds: None)

    result = assert_ping_reachable("192.0.2.1", "before_case", attempts=3)

    assert result.ok
    assert attachments[0][1]["attempt_count"] == 2
    assert len(attachments[0][1]["attempts"]) == 2


def test_assert_ping_reachable_fails_after_retries(monkeypatch):
    attempts = []
    attachments = []

    def fail_ping(*args, **kwargs):
        attempts.append(1)
        return PingResult("192.0.2.1", "before_case", ["ping"], 1, "timeout", "", 2.0)

    monkeypatch.setattr(connectivity, "ping_host", fail_ping)
    monkeypatch.setattr(connectivity, "attach_json", lambda name, body: attachments.append((name, body)))
    monkeypatch.setattr(connectivity.time, "sleep", lambda seconds: None)

    with pytest.raises(pytest.fail.Exception):
        assert_ping_reachable("192.0.2.1", "before_case", attempts=3)

    assert len(attempts) == 3
    assert attachments[0][1]["attempt_count"] == 3
    assert attachments[1][0] == "Ping failure diagnostics"
