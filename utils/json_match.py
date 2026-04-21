from __future__ import annotations

from typing import Any


def content_as_dict(value: Any) -> Any:
    if isinstance(value, str):
        import json

        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def assert_expected_subset(actual: Any, expected: Any, path: str = "") -> None:
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path or '<root>'}: expected dict, got {type(actual).__name__}"
        for key, expected_value in expected.items():
            assert key in actual, f"{path or '<root>'}: missing key {key!r}"
            next_path = f"{path}.{key}" if path else key
            assert_expected_subset(content_as_dict(actual[key]), expected_value, next_path)
        return
    if isinstance(expected, list):
        assert isinstance(actual, list), f"{path or '<root>'}: expected list, got {type(actual).__name__}"
        for index, expected_item in enumerate(expected):
            if index >= len(actual):
                raise AssertionError(f"{path or '<root>'}: missing list index {index}")
            assert_expected_subset(content_as_dict(actual[index]), expected_item, f"{path}[{index}]")
        return
    assert actual == expected, f"{path or '<root>'}: actual={actual!r}, expected={expected!r}"

