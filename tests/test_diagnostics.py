from __future__ import annotations

from utils.diagnostics import summarize_value


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
