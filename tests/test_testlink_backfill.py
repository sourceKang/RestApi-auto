from __future__ import annotations

from tools.testlink_backfill import build_backfill_cases


def test_ems1_6640_backfill_matches_absolute_session_lifetime_flow():
    case = next(case for case in build_backfill_cases() if case.external_id == "EMS1-6640")

    assert len(case.steps) == 1
    assert "readwrite session only" in case.steps[0].actions
    assert "every 60 seconds through minute 10" in case.steps[0].actions
    assert "Log in again with readwrite credentials" in case.steps[0].actions
    assert "Minutes 1 through 9 return success" in case.steps[0].expected_results
    assert "At minute 10" in case.steps[0].expected_results
    assert "`Fail` / `Not authorized.`" in case.steps[0].expected_results
    assert "`GET /device` returns success" in case.steps[0].expected_results
