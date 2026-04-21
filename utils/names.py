from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


def unique_name(case_name: str, prefix: str = "AUTO_REST") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    suffix = uuid4().hex[:8]
    safe_case = "".join(ch if ch.isalnum() else "_" for ch in case_name).strip("_")
    return f"{prefix}_{stamp}_{safe_case}_{suffix}"

