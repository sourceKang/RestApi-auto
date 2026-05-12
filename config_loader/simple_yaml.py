from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


class SimpleYamlError(RuntimeError):
    pass


def load_simple_yaml(path: Path) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    lines = path.read_text(encoding="utf-8").splitlines()

    index = 0
    while index < len(lines):
        lineno = index + 1
        raw_line = lines[index]
        line = _strip_comment(raw_line).rstrip()
        if not line.strip():
            index += 1
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
        if value_text in {"|", "|-"}:
            block_lines: list[str] = []
            block_indent: int | None = None
            index += 1
            while index < len(lines):
                block_raw = lines[index]
                if not block_raw.strip():
                    block_lines.append("")
                    index += 1
                    continue
                current_indent = len(block_raw) - len(block_raw.lstrip(" "))
                if current_indent <= indent:
                    break
                if block_indent is None:
                    block_indent = current_indent
                block_lines.append(block_raw[block_indent:])
                index += 1
            parent[key] = "\n".join(block_lines)
            continue
        if value_text:
            parent[key] = _parse_scalar(value_text, path, lineno)
            index += 1
            continue

        child: dict[str, Any] = {}
        parent[key] = child
        stack.append((indent, child))
        index += 1

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
