from __future__ import annotations

import json
import os
from typing import Any

from utils.redaction import redact


FULL_JSON_ENV = "EMS_ATTACH_FULL_JSON"
MAX_DEPTH = 5
MAX_DICT_ITEMS = 40
MAX_LIST_ITEMS = 8
MAX_STRING_LENGTH = 500
MAX_MESSAGE_LENGTH = 1200


def full_json_enabled() -> bool:
    return os.environ.get(FULL_JSON_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def summarize_value(
    value: Any,
    *,
    max_depth: int = MAX_DEPTH,
    max_dict_items: int = MAX_DICT_ITEMS,
    max_list_items: int = MAX_LIST_ITEMS,
    max_string_length: int = MAX_STRING_LENGTH,
) -> Any:
    return _summarize_value(
        value,
        depth=max_depth,
        max_dict_items=max_dict_items,
        max_list_items=max_list_items,
        max_string_length=max_string_length,
    )


def format_value_summary(value: Any, *, max_length: int = MAX_MESSAGE_LENGTH) -> str:
    rendered = _to_json(summarize_value(redact(value), max_depth=4, max_list_items=5, max_string_length=240))
    if len(rendered) <= max_length:
        return rendered
    return f"{rendered[:max_length]}...<truncated {len(rendered) - max_length} chars>"


def format_response_summary(response: Any, *, max_length: int = MAX_MESSAGE_LENGTH) -> str:
    body = getattr(response, "json", None)
    summary = {
        "method": getattr(response, "method", None),
        "url": getattr(response, "url", None),
        "status_code": getattr(response, "status_code", None),
        "retstatus": getattr(response, "retstatus", None),
        "retresult": getattr(response, "retresult", None),
        "body": summarize_value(body, max_depth=4, max_list_items=5, max_string_length=240),
    }
    return format_value_summary(summary, max_length=max_length)


def json_for_attachment(value: Any) -> str:
    data = value if full_json_enabled() else summarize_value(value)
    return _to_json(data, pretty=True)


def _summarize_value(
    value: Any,
    *,
    depth: int,
    max_dict_items: int,
    max_list_items: int,
    max_string_length: int,
) -> Any:
    if depth <= 0:
        if isinstance(value, (dict, list)):
            return _truncated_marker(value)
        return _summarize_scalar(value, max_string_length=max_string_length)
    if isinstance(value, dict):
        summarized: dict[Any, Any] = {}
        items = list(value.items())
        for key, item in items[:max_dict_items]:
            summarized[key] = _summarize_value(
                item,
                depth=depth - 1,
                max_dict_items=max_dict_items,
                max_list_items=max_list_items,
                max_string_length=max_string_length,
            )
        if len(items) > max_dict_items:
            summarized["__truncated_keys__"] = len(items) - max_dict_items
        return summarized
    if isinstance(value, list):
        summarized_list = [
            _summarize_value(
                item,
                depth=depth - 1,
                max_dict_items=max_dict_items,
                max_list_items=max_list_items,
                max_string_length=max_string_length,
            )
            for item in value[:max_list_items]
        ]
        if len(value) > max_list_items:
            summarized_list.append({"__truncated_items__": len(value) - max_list_items})
        return summarized_list
    return _summarize_scalar(value, max_string_length=max_string_length)


def _summarize_scalar(value: Any, *, max_string_length: int) -> Any:
    if isinstance(value, str) and len(value) > max_string_length:
        return f"{value[:max_string_length]}...<truncated {len(value) - max_string_length} chars>"
    return value


def _truncated_marker(value: Any) -> str:
    if isinstance(value, dict):
        return f"<dict truncated; keys={len(value)}>"
    if isinstance(value, list):
        return f"<list truncated; items={len(value)}>"
    return f"<{type(value).__name__} truncated>"


def _to_json(value: Any, *, pretty: bool = False) -> str:
    if pretty:
        return json.dumps(value, ensure_ascii=False, default=str, indent=2)
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
