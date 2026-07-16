from __future__ import annotations

import copy
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterator


PathPart = str | int
ValuePath = tuple[PathPart, ...]

_NUMERIC_TEXT = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?$")


def numeric_boundary_negative_cases(
    minimum_payload: dict[str, Any],
    maximum_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build N(min)-1 and N(max)+1 cases from declared min/max payloads.

    Only numeric leaves present in both payloads with a strictly increasing
    range are used. This avoids guessing a range for fixed values or fields
    that are only present in one boundary payload.
    """

    minimum_values = dict(_numeric_leaves(minimum_payload))
    maximum_values = dict(_numeric_leaves(maximum_payload))
    cases: list[dict[str, Any]] = []

    for path in sorted(minimum_values.keys() & maximum_values.keys(), key=_display_path):
        minimum_number, minimum_source = minimum_values[path]
        maximum_number, maximum_source = maximum_values[path]
        if minimum_number >= maximum_number:
            continue

        step = _boundary_step(minimum_number, maximum_number)
        cases.append(
            _boundary_case(
                minimum_payload,
                path,
                minimum_number - step,
                minimum_source,
                kind="below_minimum",
                declared_minimum=minimum_number,
                declared_maximum=maximum_number,
            )
        )
        cases.append(
            _boundary_case(
                maximum_payload,
                path,
                maximum_number + step,
                maximum_source,
                kind="above_maximum",
                declared_minimum=minimum_number,
                declared_maximum=maximum_number,
            )
        )

    return cases


def _numeric_leaves(value: Any, path: ValuePath = ()) -> Iterator[tuple[ValuePath, tuple[Decimal, Any]]]:
    if isinstance(value, dict):
        for key in sorted(value):
            yield from _numeric_leaves(value[key], (*path, str(key)))
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _numeric_leaves(item, (*path, index))
        return

    number = _as_decimal(value)
    if number is not None:
        yield path, (number, value)


def _as_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str) and _NUMERIC_TEXT.fullmatch(value):
        try:
            return Decimal(value)
        except InvalidOperation:
            return None
    return None


def _boundary_step(minimum: Decimal, maximum: Decimal) -> Decimal:
    exponent = min(minimum.as_tuple().exponent, maximum.as_tuple().exponent, 0)
    return Decimal(1).scaleb(exponent)


def _boundary_case(
    base_payload: dict[str, Any],
    path: ValuePath,
    value: Decimal,
    source_value: Any,
    *,
    kind: str,
    declared_minimum: Decimal,
    declared_maximum: Decimal,
) -> dict[str, Any]:
    payload = copy.deepcopy(base_payload)
    _set_path(payload, path, _coerce_boundary_value(value, source_value))
    return {
        "name": f"{_case_name(path)}_{kind}",
        "field": _display_path(path),
        "error_layer": "device_cli",
        "payload": payload,
        "expected_retstatus": "Fail",
        "generated_from": "declared_numeric_minmax",
        "boundary": {
            "kind": kind,
            "declared_minimum": _decimal_text(declared_minimum),
            "declared_maximum": _decimal_text(declared_maximum),
        },
    }


def _set_path(payload: Any, path: ValuePath, value: Any) -> None:
    target = payload
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value


def _coerce_boundary_value(value: Decimal, source_value: Any) -> Any:
    if isinstance(source_value, int) and not isinstance(source_value, bool):
        return int(value)
    if isinstance(source_value, float):
        return float(value)
    return _decimal_text(value)


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _display_path(path: ValuePath) -> str:
    parts: list[str] = []
    for part in path:
        if isinstance(part, int):
            parts[-1] = f"{parts[-1]}[{part}]"
        else:
            parts.append(part)
    return ".".join(parts)


def _case_name(path: ValuePath) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _display_path(path).casefold()).strip("_")
