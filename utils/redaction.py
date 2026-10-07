from __future__ import annotations

import re
from typing import Any


SENSITIVE_KEYS = {"password", "passwd", "sessionid", "token", "authorization"}
_SENSITIVE_TEXT_RE = re.compile(
    r"(?i)(\b(?:%s|devkey)\b[\"']?\s*[:=]\s*[\"']?)([^\s\"',}&]+)" % "|".join(sorted(SENSITIVE_KEYS))
)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                redacted[key] = "***REDACTED***"
            else:
                redacted[key] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def redact_text(text: str) -> str:
    """Mask key=value / "key": "value" pairs of sensitive keys inside free text."""
    return _SENSITIVE_TEXT_RE.sub(lambda match: f"{match.group(1)}***REDACTED***", text)

