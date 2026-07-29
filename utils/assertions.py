from __future__ import annotations

from collections.abc import Iterable

from models.api import ApiResponse
from utils.diagnostics import format_response_summary


AUTHORIZED_FAILURE_MESSAGES = (
    "not authorized",
    "invalid session",
    "invalid username",
    "invalid password",
    "no access",
    "permission",
    "privilege",
)


def assert_api_success(response: ApiResponse) -> None:
    assert response.status_code < 500, _format_response(response)
    assert isinstance(response.json, dict), _format_response(response)
    assert response.json.get("retstatus") == "Success", _format_response(response)


def assert_api_failure(response: ApiResponse, accepted_messages: Iterable[str] = AUTHORIZED_FAILURE_MESSAGES) -> None:
    assert isinstance(response.json, dict), _format_response(response)
    if "retstatus" not in response.json and response.status_code >= 400:
        result = str(response.json).lower()
        assert any(message.lower() in result for message in accepted_messages) or response.status_code in {
            400,
            401,
            403,
            404,
        }, _format_response(response)
        return
    assert response.json.get("retstatus") == "Fail", _format_response(response)
    result = str(response.json.get("retresult", "")).lower()
    assert any(message.lower() in result for message in accepted_messages), _format_response(response)


def assert_api_failure_exact(response: ApiResponse, *, expected_retresult: str) -> None:
    assert isinstance(response.json, dict), _format_response(response)
    assert response.json.get("retstatus") == "Fail", _format_response(response)
    assert response.json.get("retresult") == expected_retresult, _format_response(response)


def assert_contains_required_keys(response: ApiResponse, *keys: str) -> None:
    assert_api_success(response)
    for key in keys:
        assert key in response.json, f"Missing key {key!r}: {_format_response(response)}"


def _format_response(response: ApiResponse) -> str:
    return (
        f"{response.method} {response.url} failed expectation. "
        f"HTTP={response.status_code}, body={format_response_summary(response)}"
    )
