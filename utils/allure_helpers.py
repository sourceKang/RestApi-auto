from __future__ import annotations

import json
from typing import Any

from utils.redaction import redact


def attach_json(name: str, value: Any) -> None:
    try:
        import allure

        allure.attach(
            json.dumps(redact(value), indent=2, ensure_ascii=False, default=str),
            name=name,
            attachment_type=allure.attachment_type.JSON,
        )
    except Exception:
        return

