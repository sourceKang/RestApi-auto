from __future__ import annotations

import json
import time

from config_loader.settings import scaled_wait
from utils.assertions import assert_api_success
from utils.diagnostics import masked_response_body


def wait_for_rest_tokens(
    api_client,
    path: str,
    session_id: str,
    expected_tokens: list[str],
    *,
    timeout: float = 300,
    interval: float = 10,
    max_interval: float = 30,
    response_validator=None,
    consecutive_successes: int = 1,
    sleeper=time.sleep,
    clock=time.monotonic,
):
    if consecutive_successes < 1:
        raise ValueError("consecutive_successes must be at least 1")
    timeout = scaled_wait(getattr(api_client, "env", None), timeout)
    deadline = clock() + timeout
    last_response = None
    last_missing = expected_tokens
    delay = max(0.0, interval)
    stable_hits = 0
    while clock() <= deadline:
        last_response = api_client.request("GET", path, session=session_id)
        if last_response.retstatus == "Fail" and "not authorized" in last_response.retresult.casefold():
            raise AssertionError(
                f"REST polling lost authorization for {path}; obtain a fresh session before retrying"
            )
        if last_response.retstatus == "Success":
            body = json.dumps(last_response.json, ensure_ascii=False)
            last_missing = [token for token in expected_tokens if token not in body]
            response_matches = response_validator is None or response_validator(last_response)
            if not last_missing and response_matches:
                stable_hits += 1
                if stable_hits >= consecutive_successes:
                    return last_response
            else:
                stable_hits = 0
        else:
            stable_hits = 0

        remaining = deadline - clock()
        if remaining <= 0:
            break
        sleep_for = min(delay, remaining)
        sleeper(sleep_for)
        delay = min(max_interval, max(delay * 2, 1.0))

    assert last_response is not None
    if last_response.retstatus != "Success":
        assert_api_success(last_response)
    masked_body = masked_response_body(last_response)
    assert not last_missing, f"Missing expected REST response tokens {last_missing}: {masked_body}"
    assert response_validator is None or response_validator(last_response), (
        "REST response did not match the required exact baseline fields: " + masked_body
    )
    assert stable_hits >= consecutive_successes, (
        f"REST response was not stable for {consecutive_successes} consecutive samples; "
        f"last stable count={stable_hits}: {masked_body}"
    )
    return last_response
