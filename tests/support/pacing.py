from __future__ import annotations

import time
from typing import Any

from utils.allure_helpers import attach_json


def pause_between_cases(label: str, seconds: float, details: dict[str, Any]) -> None:
    """Opt-in cooldown between NeoX cases to ease EMS/DUT load; it does not wait for any state."""
    if seconds <= 0:
        return
    started = time.monotonic()
    time.sleep(seconds)
    attach_json(
        label,
        {
            **details,
            "requested_seconds": seconds,
            "actual_seconds": round(time.monotonic() - started, 3),
        },
    )
