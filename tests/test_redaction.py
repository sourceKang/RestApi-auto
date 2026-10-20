from __future__ import annotations

import pytest

from utils.redaction import redact, redact_text


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
