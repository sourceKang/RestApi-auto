from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


# registid carries the ONT password in NeoX ONT config payloads.
SENSITIVE_KEYS = {"password", "passwd", "sessionid", "token", "authorization", "registid"}
_SENSITIVE_TEXT_RE = re.compile(
    r"(?i)(\b(?:%s|devkey)\b[\"']?\s*[:=]\s*[\"']?)([^\s\"',}&]+)" % "|".join(sorted(SENSITIVE_KEYS))
)
# NeoX CLI writes the same ONT password as `registration-id <value>`.
_CLI_SECRET_RE = re.compile(r"(?i)(\bregistration-id\s+)(\S+)")


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
    if isinstance(value, str):
        # Free text such as CLI output or an error message can embed secrets too.
        return redact_text(value)
    return value


def redact_text(text: str) -> str:
    """Mask key=value / "key": "value" pairs and CLI `registration-id <value>` inside free text."""
    text = _SENSITIVE_TEXT_RE.sub(lambda match: f"{match.group(1)}***REDACTED***", text)
    return _CLI_SECRET_RE.sub(lambda match: f"{match.group(1)}***REDACTED***", text)


def mask_values(text: str, secrets: Iterable[str]) -> str:
    """Mask known secret values wherever they appear, e.g. in a traceback's argument reprs."""
    for secret in sorted({secret for secret in secrets if secret}, key=len, reverse=True):
        text = text.replace(secret, "***REDACTED***")
    return text

