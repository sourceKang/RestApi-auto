from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from models.api import ApiResponse
from tests.support import reporting_hooks
from utils.diagnostics import masked_response_body
from utils.redaction import REPORT_REDACT_ENV, redact, redact_text, report_mask_values, report_text, report_value


pytestmark = pytest.mark.offline

SECRET = "OntPw-1234"


def test_redact_masks_registid_in_neox_ont_payload():
    payload = {"ontlist": [{"sn": "ZYXE00000001", "registid": SECRET}]}

    redacted = redact(payload)

    assert redacted == {"ontlist": [{"sn": "ZYXE00000001", "registid": "***REDACTED***"}]}
    assert payload["ontlist"][0]["registid"] == SECRET


@pytest.mark.parametrize(
    "text",
    [
        f'{{"registid": "{SECRET}"}}',
        f"registid={SECRET}",
        f"ont 1/1/1 registration-id {SECRET}",
        f"  Registration-ID   {SECRET}\n",
    ],
)
def test_redact_text_masks_ont_password_forms(text):
    masked = redact_text(text)

    assert SECRET not in masked
    assert "***REDACTED***" in masked


def test_redact_masks_strings_inside_cli_report_entries():
    entry = {
        "output_lines": ["ont 1/1/1", f" registration-id {SECRET}"],
        "expected_tokens": [f"registration-id {SECRET}", "sn ZYXE00000001"],
    }

    redacted = redact(entry)

    assert SECRET not in repr(redacted)
    assert redacted["expected_tokens"][1] == "sn ZYXE00000001"


def test_redact_keeps_non_secret_values():
    value = {"name": "ONTUNIProfile", "count": 3, "enabled": True, "note": "registration id pending"}

    assert redact(value) == value


def test_report_helpers_keep_original_values_by_default(monkeypatch):
    monkeypatch.delenv(REPORT_REDACT_ENV, raising=False)
    payload = {"password": SECRET, "sessionid": "s-1", "devKey": "dk-1", "registid": SECRET}
    response = ApiResponse(200, payload, "", 0, "id", "GET", "https://ems/ont/sn/X")

    assert report_value(payload) == payload
    assert report_text(f"token=t-1 registration-id {SECRET}") == f"token=t-1 registration-id {SECRET}"
    assert report_mask_values(f"connect(password={SECRET!r})", [SECRET]) == f"connect(password={SECRET!r})"
    assert SECRET in masked_response_body(response) and "dk-1" in masked_response_body(response)


def test_report_helpers_mask_when_switch_is_on(monkeypatch):
    monkeypatch.setenv(REPORT_REDACT_ENV, "1")
    payload = {"password": SECRET, "sessionid": "s-1", "registid": SECRET}

    assert report_value(payload) == {key: "***REDACTED***" for key in payload}
    assert SECRET not in report_text(f"registration-id {SECRET}")
    assert SECRET not in report_mask_values(f"connect(password={SECRET!r})", [SECRET])


@pytest.mark.parametrize(("option", "expected"), [(True, "1"), (False, None)])
def test_redact_reports_option_sets_the_switch(monkeypatch, tmp_path, option, expected):
    monkeypatch.delenv(REPORT_REDACT_ENV, raising=False)
    config = SimpleNamespace(
        getoption=lambda name, default=None: option if name == "--redact-reports" else default,
        workerinput={},  # xdist worker path: only prepares the configured Allure directory
        rootpath=tmp_path,
        option=SimpleNamespace(allure_report_dir=str(tmp_path / "allure")),
    )

    reporting_hooks.pytest_configure(config)

    assert os.environ.get(REPORT_REDACT_ENV) == expected
    monkeypatch.delenv(REPORT_REDACT_ENV, raising=False)
