from __future__ import annotations

from cases.payloads import remote_console_payload
from models.api import ApiResponse
from utils.assertions import assert_api_failure, assert_api_success
from utils.case_metadata import attach_case_id
from utils.names import unique_name


def remote_console_output(response: ApiResponse) -> str:
    if not isinstance(response.json, dict):
        return ""
    retval = response.json.get("retval")
    if not isinstance(retval, dict):
        return ""
    output = retval.get("return")
    if isinstance(output, list):
        return "\n".join(str(line) for line in output)
    return str(output or "")


def assert_remote_console_success(
    response: ApiResponse,
    *,
    command: str,
    expected_output_tokens: tuple[str, ...] = (),
) -> None:
    output = remote_console_output(response)
    if response.retstatus != "Success" and expected_output_tokens and all(
        token.casefold() in output.casefold() for token in expected_output_tokens
    ):
        raise AssertionError(
            f"Remote console executed {command!r} and returned expected CLI output, "
            f"but API retstatus was {response.retstatus!r}"
        )
    assert_api_success(response)

class RemoteService:
    def __init__(self, api_client, env_config) -> None:
        self.api_client = api_client
        self.env_config = env_config

    def verify_read_command(self, session_id: str) -> None:
        attach_case_id("EMS1-6652", "test_post_remote_console")
        name = unique_name("remote_console")
        response = self.api_client.request(
            "POST",
            f"/remote/{self.env_config.dut.device_name}",
            session=session_id,
            json=remote_console_payload(self.env_config, name),
        )
        assert_remote_console_success(response, command="show version", expected_output_tokens=("version",))

    def verify_noaccess_rejected(self, session_id: str) -> None:
        attach_case_id("EMS1-7022", "test_post_remote_console_invalid_param_should_return_error")
        name = unique_name("remote_console_noaccess")
        response = self.api_client.request(
            "POST",
            f"/remote/{self.env_config.dut.device_name}",
            session=session_id,
            json=remote_console_payload(self.env_config, name),
        )
        assert_api_failure(response, accepted_messages=("not authorized", "no access", "permission", "privilege"))
