from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from utils.diagnostics import json_for_attachment
from utils.redaction import redact


def attach_json(name: str, value: Any) -> None:
    try:
        import allure

        allure.attach(
            json_for_attachment(redact(value)),
            name=name,
            attachment_type=allure.attachment_type.JSON,
        )
    except Exception:
        return


@contextmanager
def allure_step(title: str):
    try:
        import allure
    except Exception:
        yield
    else:
        with allure.step(title):
            yield
