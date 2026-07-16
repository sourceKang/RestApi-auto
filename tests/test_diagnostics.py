from __future__ import annotations

from utils.diagnostics import format_value_summary, json_for_attachment, summarize_value


def test_summarize_value_keeps_scalar_values_at_depth_limit():
    value = {
        "body": {
            "retstatus": "Success",
            "retval": {
                "slotinfolist": [
                    {
                        "SubmapName": "Default",
                        "SlotID": "2",
                        "index": 1,
                    }
                ]
            },
        }
    }

    summarized = summarize_value(value, max_depth=5)

    slot = summarized["body"]["retval"]["slotinfolist"][0]
    assert slot["SubmapName"] == "Default"
    assert slot["SlotID"] == "2"
    assert slot["index"] == 1


def test_summarize_value_truncates_nested_containers_at_depth_limit():
    value = {"body": {"retval": {"items": [{"nested": {"too": {"deep": "value"}}}]}}}

    summarized = summarize_value(value, max_depth=5)

    assert summarized["body"]["retval"]["items"][0]["nested"] == "<dict truncated; keys=1>"


def test_json_for_attachment_is_pretty_printed():
    rendered = json_for_attachment({"status_code": 200, "body": {"retstatus": "Success"}})

    assert rendered.startswith("{\n")
    assert '  "status_code": 200' in rendered
    assert '    "retstatus": "Success"' in rendered


def test_format_value_summary_stays_compact_for_assertion_messages():
    rendered = format_value_summary({"status_code": 200, "body": {"retstatus": "Success"}})

    assert "\n" not in rendered


def test_format_value_summary_redacts_sensitive_fields():
    rendered = format_value_summary(
        {"password": "secret-password", "nested": {"token": "secret-token"}}
    )

    assert "secret-password" not in rendered
    assert "secret-token" not in rendered
    assert rendered.count("***REDACTED***") == 2