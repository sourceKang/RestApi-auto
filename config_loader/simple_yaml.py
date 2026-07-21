from __future__ import annotations

import ast
import os
from pathlib import Path
import re
from typing import Any


class SimpleYamlError(RuntimeError):
    pass


DEFAULT_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
ENV_REFERENCE_PATTERN = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}$")
ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_simple_yaml(path: Path) -> dict[str, Any]:
    load_local_env()
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
            return _expand_env_reference(ast.literal_eval(value), path, lineno)
        except (SyntaxError, ValueError) as error:
            raise SimpleYamlError(f"{path}:{lineno}: invalid quoted string: {value}") from error
    try:
        return int(value)
    except ValueError:
        return _expand_env_reference(value, path, lineno)


def load_local_env(path: Path | None = None) -> None:
    env_path = path or Path(os.environ.get("EMS_ENV_FILE", DEFAULT_ENV_FILE))
    if not env_path.exists():
        return

    for lineno, raw_line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise SimpleYamlError(f"{env_path}:{lineno}: expected KEY=VALUE")
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not ENV_KEY_PATTERN.fullmatch(key):
            raise SimpleYamlError(f"{env_path}:{lineno}: invalid environment variable name {key!r}")
        os.environ.setdefault(key, _parse_env_value(raw_value.strip(), env_path, lineno))


def _parse_env_value(value: str, path: Path, lineno: int) -> str:
    if not value:
        return ""
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError) as error:
            raise SimpleYamlError(f"{path}:{lineno}: invalid quoted environment value") from error
        if not isinstance(parsed, str):
            raise SimpleYamlError(f"{path}:{lineno}: environment value must resolve to a string")
        return parsed
    return value


def _expand_env_reference(value: Any, path: Path, lineno: int) -> Any:
    if not isinstance(value, str):
        return value
    match = ENV_REFERENCE_PATTERN.fullmatch(value)
    if not match:
        return value
    name, fallback = match.groups()
    resolved = os.environ.get(name)
    if resolved is not None:
        return resolved
    if fallback is not None:
        return fallback
    raise SimpleYamlError(f"{path}:{lineno}: required environment variable {name} is not set")
