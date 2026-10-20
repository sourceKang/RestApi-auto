from __future__ import annotations

import os
import re
from collections.abc import Iterable
from typing import Any


# Local test reports (Allure attachments, txt/HTML/integrated reports, failure messages, tracebacks)
# keep original values so test data can be looked up later. Set EMS_REPORT_REDACT=1 (or pytest
# --redact-reports) to mask them, e.g. before sharing a report. redact/redact_text/mask_values below
# always mask; use them for anything shared outside (PR text, Redmine, TestLink notes, committed files).
REPORT_REDACT_ENV = "EMS_REPORT_REDACT"

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


def report_redaction_enabled() -> bool:
    return os.environ.get(REPORT_REDACT_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def report_value(value: Any) -> Any:
    """Value for a local report or attachment: original unless EMS_REPORT_REDACT is on."""
    return redact(value) if report_redaction_enabled() else value


def report_text(text: str) -> str:
    """Text for a local report, failure message or console output: original unless EMS_REPORT_REDACT is on."""
    return redact_text(text) if report_redaction_enabled() else text


def report_mask_values(text: str, secrets: Iterable[str]) -> str:
    """Traceback text for a local report: original unless EMS_REPORT_REDACT is on."""
    return mask_values(text, secrets) if report_redaction_enabled() else text

