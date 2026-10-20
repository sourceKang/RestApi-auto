from __future__ import annotations

import ast
from pathlib import Path

import pytest

from models.api import ApiResponse
from tests.support.rest_polling import wait_for_rest_tokens
from utils.diagnostics import masked_response_body


pytestmark = pytest.mark.offline

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("clients", "services", "utils", "cases", "tools", "tests")
SECRET = "OntPw-1234"

# Allure copies exception messages verbatim into statusDetails (test, step and fixture
# teardown), outside the longrepr masking in tests/support/reporting_hooks.py. A raw
# response body in an assert/raise/pytest.fail message therefore reaches the report unmasked.
MASKING_CALLS = {"masked_response_body", "format_response_summary", "format_value_summary", "redact", "redact_text"}
RAW_BODY_NAMES = {"body", "response_text"}


def _call_name(node: ast.Call) -> str:
    func = node.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


def _raw_body_kind(node: ast.AST) -> str | None:
    if isinstance(node, ast.Attribute) and node.attr == "text" and isinstance(node.value, ast.Name) and "resp" in node.value.id:
        return f"{node.value.id}.text"
    if isinstance(node, ast.Call) and _call_name(node) == "dumps" and any(
        isinstance(arg, ast.Attribute) and arg.attr == "json" for arg in node.args
    ):
        return "json.dumps(<response>.json)"
    if isinstance(node, ast.Name) and node.id in RAW_BODY_NAMES and isinstance(node.ctx, ast.Load):
        return node.id
    return None


def _messages(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert) and node.msg is not None:
            yield node.msg
        elif isinstance(node, ast.Raise) and node.exc is not None:
            yield node.exc
        elif isinstance(node, ast.Call) and _call_name(node) == "fail" and isinstance(node.func, ast.Attribute) and getattr(node.func.value, "id", "") == "pytest":
            yield from node.args


def raw_bodies_in_messages(source: bytes, rel: str) -> list[str]:
    found = []
    for message in _messages(ast.parse(source, filename=rel)):
        masked: set[int] = set()
        for node in ast.walk(message):
            if isinstance(node, ast.Call) and _call_name(node) in MASKING_CALLS:
                masked.update(id(child) for child in ast.walk(node))
        for node in ast.walk(message):
            kind = _raw_body_kind(node)
            if kind and id(node) not in masked:
                found.append(f"{rel}:{node.lineno} {kind}")
    return found


def test_failure_messages_do_not_embed_raw_response_bodies():
    found = []
    for package in PACKAGES:
        for path in sorted((ROOT / package).rglob("*.py")):
            if "__pycache__" not in path.parts:
                found.extend(raw_bodies_in_messages(path.read_bytes(), path.relative_to(ROOT).as_posix()))

    assert found == [], "Wrap response bodies in masked_response_body() (utils/diagnostics.py):\n" + "\n".join(found)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('assert ok, f"got {response.text}"\n', ["sample.py:1 response.text"]),
        ('assert ok, "got " + json.dumps(resp.json)\n', ["sample.py:1 json.dumps(<response>.json)"]),
        ('pytest.fail(f"body={body}")\n', ["sample.py:1 body"]),
        ('raise AssertionError(f"{response_text}")\n', ["sample.py:1 response_text"]),
        ('assert ok, f"got {masked_response_body(response)}"\n', []),
        ('assert ok, f"got {format_value_summary(body)}"\n', []),
        ('body = json.dumps(response.json)\nmissing = [t for t in tokens if t not in body]\n', []),
    ],
)
def test_scanner_flags_only_unmasked_bodies(source, expected):
    assert raw_bodies_in_messages(source.encode(), "sample.py") == expected


def _response(payload, text=""):
    return ApiResponse(200, payload, text, 0, "id", "GET", "https://ems/ont/sn/X")


def test_masked_response_body_masks_json_and_text_bodies(monkeypatch):
    monkeypatch.setenv("EMS_REPORT_REDACT", "1")
    json_body = masked_response_body(_response({"retstatus": "Success", "retval": [{"sn": "X", "password": SECRET, "registid": SECRET}]}))
    text_body = masked_response_body(_response(None, f"error: password={SECRET} registration-id {SECRET}"))

    assert SECRET not in json_body and '"sn": "X"' in json_body
    assert SECRET not in text_body and text_body.count("***REDACTED***") == 2


def test_rest_polling_timeout_message_is_masked_but_matching_uses_raw_body(monkeypatch):
    monkeypatch.setenv("EMS_REPORT_REDACT", "1")
    payload = {"retstatus": "Success", "retresult": "", "retval": {"sn": "X", "password": SECRET}}

    class Client:
        def request(self, method, path, *, session):
            return _response(payload)

    clock = {"now": 0.0}

    def sleeper(seconds):
        clock["now"] += seconds

    # The raw body still drives token matching: the secret value itself is found.
    assert wait_for_rest_tokens(Client(), "/ont/sn/X", "s", [SECRET], timeout=10, sleeper=sleeper, clock=lambda: clock["now"])

    with pytest.raises(AssertionError) as error:
        wait_for_rest_tokens(Client(), "/ont/sn/X", "s", ["missing-token"], timeout=10, sleeper=sleeper, clock=lambda: clock["now"])

    assert "missing-token" in str(error.value)
    assert SECRET not in str(error.value)
