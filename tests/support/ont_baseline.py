"""Converge the NeoX ONT back to its baseline after a test changed it.

The baseline is POSTed once, then REST is polled in one window (600 s x wait_scale, fixed 15 s
interval, 4 consecutive matching samples); the baseline is not re-POSTed. The window is split
into chunks that each log in again, because an EMS session expires after 600 s. A restore that
needs more than ONT_BASELINE_SLOW_POLLS REST polls is marked SLOW in the report header; the
case result only changes when the whole window runs out (the .100 RedHat EMS is slow while the
ONT re-registers, which used to fail the old 120 s + 180 s attempts).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any

from config_loader.settings import scaled_wait
from tests.support.ont_cli_status import wait_for_ont_cli_config_tokens, wait_for_ont_cli_is
from tests.support.rest_polling import wait_for_rest_tokens
from utils.allure_helpers import attach_json
from utils.assertions import assert_api_success
from utils.reporting import record_report_note


ONT_BASELINE_STABLE_SAMPLES = 4
ONT_BASELINE_TIMEOUT_SECONDS = 600
ONT_BASELINE_INTERVAL_SECONDS = 15
ONT_BASELINE_SLOW_POLLS = 12
ONT_BASELINE_SESSION_CHUNK_SECONDS = 300  # real seconds per login, inside the 600 s session lifetime
ONT_BASELINE_CLI_TIMEOUT_SECONDS = 180
ONT_BASELINE_IMMEDIATE_RETRIES = 2  # fresh sessions after an error that did not use the chunk time


@dataclass
class OntBaselineConvergence:
    polls: int
    elapsed_seconds: float
    slow: bool
    errors: list[str] = field(default_factory=list)

    @property
    def converged(self) -> bool:
        return not self.errors


def converge_ont_baseline(
    api_client,
    env_config,
    session_scope: Callable[[], AbstractContextManager[str]],
    config_path: str,
    restore_payload: dict[str, Any],
    read_path: str,
    expected_rest_tokens: list[str],
    *,
    cli_expected_tokens: tuple[str, ...],
    cli_absent_tokens: tuple[str, ...],
    verify_cli: bool,
    label: str,
    clock: Callable[[], float] = time.monotonic,
) -> OntBaselineConvergence:
    """POST the baseline once and wait for REST (and CLI) to show it; never raises for non-convergence."""
    content = restore_payload.get("Content", {})
    expected_description = str(content.get("ontdescription") or "")
    expected_template = str(content.get("templatename") or "")

    def rest_baseline_matches(response) -> bool:
        payload = response.json if isinstance(response.json, dict) else {}
        ont_info = (payload.get("retval") or {}).get("ontinfo") or {}
        actual_description = str(ont_info.get("description") or "")
        actual_template = str(ont_info.get("templateName") or ont_info.get("ontTemplate") or "")
        return actual_description == expected_description and actual_template == expected_template

    errors: list[str] = []
    stats = {"polls": 0}
    started = clock()
    rest_elapsed = 0.0
    window = scaled_wait(env_config, ONT_BASELINE_TIMEOUT_SECONDS)
    try:
        with session_scope() as session_id:
            assert_api_success(api_client.request("POST", config_path, session=session_id, json=restore_payload))
    except Exception as error:
        errors.append(f"POST baseline: {error}")

    if not errors:
        deadline = started + window
        immediate_retries = 0
        while True:
            chunk = max(0.0, min(deadline - clock(), ONT_BASELINE_SESSION_CHUNK_SECONDS))
            chunk_started = clock()
            try:
                with session_scope() as session_id:
                    wait_for_rest_tokens(
                        api_client,
                        read_path,
                        session_id,
                        expected_rest_tokens,
                        timeout=chunk,
                        scale_timeout=False,
                        interval=ONT_BASELINE_INTERVAL_SECONDS,
                        max_interval=ONT_BASELINE_INTERVAL_SECONDS,
                        response_validator=rest_baseline_matches,
                        consecutive_successes=ONT_BASELINE_STABLE_SAMPLES,
                        stats=stats,
                    )
                break
            except Exception as error:
                # A chunk that used its whole time moves on to a fresh session. An immediate error
                # (login failure, lost authorization, transport error) gets a few fresh-session
                # retries so one EMS hiccup does not fail the restore, without looping until the deadline.
                if clock() >= deadline:
                    errors.append(f"REST baseline convergence: {error}")
                    break
                if clock() < chunk_started + chunk:
                    immediate_retries += 1
                    if immediate_retries > ONT_BASELINE_IMMEDIATE_RETRIES:
                        errors.append(
                            f"REST baseline convergence: {error} "
                            f"(after {ONT_BASELINE_IMMEDIATE_RETRIES} fresh-session retries)"
                        )
                        break
        rest_elapsed = clock() - started

    if verify_cli:
        try:
            wait_for_ont_cli_is(env_config, timeout=ONT_BASELINE_CLI_TIMEOUT_SECONDS, interval=ONT_BASELINE_INTERVAL_SECONDS)
            wait_for_ont_cli_config_tokens(
                env_config,
                expected_tokens=cli_expected_tokens,
                absent_tokens=cli_absent_tokens,
                consecutive_successes=ONT_BASELINE_STABLE_SAMPLES,
                timeout=ONT_BASELINE_CLI_TIMEOUT_SECONDS,
                interval=ONT_BASELINE_INTERVAL_SECONDS,
            )
        except Exception as error:
            errors.append(f"CLI baseline convergence: {error}")

    # SLOW and the attachment describe the REST convergence only; CLI checks are not counted.
    elapsed = round(rest_elapsed, 1)
    result = OntBaselineConvergence(
        polls=stats["polls"], elapsed_seconds=elapsed, slow=stats["polls"] > ONT_BASELINE_SLOW_POLLS, errors=errors
    )
    attach_json(
        label,
        {
            "config_path": config_path,
            "read_path": read_path,
            "expected_description": expected_description,
            "expected_template_name": expected_template,
            "window_seconds": window,
            "interval_seconds": ONT_BASELINE_INTERVAL_SECONDS,
            "stable_samples": ONT_BASELINE_STABLE_SAMPLES,
            "polls": result.polls,
            "elapsed_seconds": elapsed,
            "slow_after_polls": ONT_BASELINE_SLOW_POLLS,
            "slow": result.slow,
            "converged": result.converged,
            "errors": errors,
        },
    )
    if result.slow:
        record_report_note(
            f"ONT Baseline Restore ({label})",
            f"SLOW {elapsed:.0f}s ({result.polls} polls, over threshold {ONT_BASELINE_SLOW_POLLS})",
        )
    return result
