from __future__ import annotations

import pytest

from models.api import ApiResponse
from services.remote.service import assert_remote_console_success, remote_console_output


def test_olt140x_valid_pon_command_output_with_fail_status_is_not_accepted_as_success():
    response = ApiResponse(
        status_code=200,
        json={
            "retstatus": "Fail",
            "retresult": "",
            "retval": {
                "return": [
                    "show interface pon-8",
                    "AID | Speed/Duplex | State",
                    "pon-8 | 2500M/F | FORWARDING",
                ]
            },
        },
        text="",
        elapsed=0.1,
        request_id="remote-pon-regression",
        method="POST",
        url="/remote/OLT1408AC_168.84",
    )

    assert "pon-8 | 2500M/F | FORWARDING" in remote_console_output(response)
    with pytest.raises(
        AssertionError,
        match="returned expected CLI output, but API retstatus was 'Fail'",
    ):
        assert_remote_console_success(
            response,
            command="show interface pon-8",
            expected_output_tokens=("pon-8", "FORWARDING"),
        )
