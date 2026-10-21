from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from tests.support import ont_baseline
from utils import reporting


pytestmark = pytest.mark.offline

PAYLOAD = {"Content": {"ontdescription": "REST_API_NEOX_ONT", "templatename": ""}}


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class Harness:
    """Fake EMS: each polling chunk spends its whole timeout unless it converges after `polls_to_converge`."""

    def __init__(self, monkeypatch, *, polls_to_converge=None, fail_immediately=False):
        self.clock = FakeClock()
        self.posts = 0
        self.sessions = []
        self.chunks = []
        self.attachments = []
        self.total_polls = 0

        def fake_rest(api_client, path, session_id, tokens, **kwargs):
            assert kwargs["scale_timeout"] is False
            assert (kwargs["interval"], kwargs["max_interval"], kwargs["consecutive_successes"]) == (15, 15, 4)
            self.chunks.append((session_id, kwargs["timeout"]))
            if fail_immediately:
                raise AssertionError("REST polling lost authorization")
            polls_in_chunk = int(kwargs["timeout"] // 15) + 1
            if polls_to_converge is not None and self.total_polls + polls_in_chunk >= polls_to_converge:
                used = polls_to_converge - self.total_polls
                self.total_polls = polls_to_converge
                kwargs["stats"]["polls"] += used
                self.clock.now += (used - 1) * 15
                return None
            self.total_polls += polls_in_chunk
            kwargs["stats"]["polls"] += polls_in_chunk
            self.clock.now += kwargs["timeout"]
            raise AssertionError("REST response was not stable for 4 consecutive samples")

        monkeypatch.setattr(ont_baseline, "wait_for_rest_tokens", fake_rest)
        monkeypatch.setattr(ont_baseline, "assert_api_success", lambda response: None)
        monkeypatch.setattr(ont_baseline, "attach_json", lambda name, body: self.attachments.append((name, body)))
        monkeypatch.setattr(reporting, "REPORT_STATE", reporting.ReportState(timestamp="2026-10-21_12-00-00"))

    def request(self, method, path, *, session, json=None):
        assert method == "POST" and json == PAYLOAD
        self.posts += 1
        return SimpleNamespace(retstatus="Success")

    @contextmanager
    def session(self):
        self.sessions.append(f"s{len(self.sessions) + 1}")
        yield self.sessions[-1]

    def run(self, wait_scale=1.0):
        return ont_baseline.converge_ont_baseline(
            self,
            SimpleNamespace(wait_scale=wait_scale),
            self.session,
            "/config/ont",
            PAYLOAD,
            "/ont/sn/SN-1",
            ["SN-1"],
            cli_expected_tokens=("description REST_API_NEOX_ONT",),
            cli_absent_tokens=("template x",),
            verify_cli=False,
            label="ONT clear strict baseline convergence",
            clock=self.clock,
        )


def test_slow_restore_keeps_polling_in_fresh_sessions_without_reposting(monkeypatch):
    harness = Harness(monkeypatch, polls_to_converge=26)

    result = harness.run()

    assert result.converged and harness.posts == 1
    assert [timeout for _, timeout in harness.chunks] == [300, 300]
    assert harness.sessions == ["s1", "s2", "s3"]  # POST, then one login per polling chunk
    assert result.polls == 26 and result.slow
    note = reporting.REPORT_STATE.report_notes["ONT Baseline Restore (ONT clear strict baseline convergence)"]
    assert note.startswith("SLOW ") and "(26 polls, over threshold 12)" in note


def test_restore_within_twelve_polls_is_not_marked_slow(monkeypatch):
    harness = Harness(monkeypatch, polls_to_converge=12)

    result = harness.run()

    assert result.converged and not result.slow
    assert reporting.REPORT_STATE.report_notes == {}
    name, body = harness.attachments[-1]
    assert name == "ONT clear strict baseline convergence"
    assert (body["polls"], body["slow"], body["window_seconds"], body["converged"]) == (12, False, 600, True)


def test_window_is_600_seconds_times_wait_scale_and_then_fails(monkeypatch):
    harness = Harness(monkeypatch)

    result = harness.run(wait_scale=1.5)

    assert not result.converged and harness.posts == 1
    assert [timeout for _, timeout in harness.chunks] == [300, 300, 300]
    assert harness.clock.now == 900
    assert result.errors[0].startswith("REST baseline convergence: REST response was not stable")


def test_immediate_error_stops_instead_of_looping_until_the_deadline(monkeypatch):
    harness = Harness(monkeypatch, fail_immediately=True)

    result = harness.run()

    assert len(harness.chunks) == 1
    assert result.errors == ["REST baseline convergence: REST polling lost authorization"]
