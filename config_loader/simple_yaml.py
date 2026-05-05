from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


class SimpleYamlError(RuntimeError):
    pass


def load_simple_yaml(path: Path) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = _strip_comment(raw_line).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent % 2:
            raise SimpleYamlError(f"{path}:{lineno}: indentation must use multiples of two spaces")
        text = line.strip()
        if ":" not in text:
            raise SimpleYamlError(f"{path}:{lineno}: expected 'key: value'")

        key, raw_value = text.split(":", 1)
        key = key.strip()
        if not key:
            raise SimpleYamlError(f"{path}:{lineno}: empty key")

        while indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        value_text = raw_value.strip()
        if value_text:
            parent[key] = _parse_scalar(value_text, path, lineno)
            continue

        child: dict[str, Any] = {}
        parent[key] = child
        stack.append((indent, child))

    return root


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_double:
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if char == "#" and not in_single and not in_double:
            return line[:index]
    return line


def _parse_scalar(value: str, path: Path, lineno: int) -> Any:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    if value.startswith("[") or value.startswith("{"):
        try:
            return ast.literal_eval(value)
        except (SyntaxError, ValueError) as error:
            raise SimpleYamlError(f"{path}:{lineno}: invalid inline collection: {value}") from error
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        try:
            return ast.literal_eval(value)
        except (SyntaxError, ValueError) as error:
            raise SimpleYamlError(f"{path}:{lineno}: invalid quoted string: {value}") from error
    try:
        return int(value)
    except ValueError:
        return value
