from __future__ import annotations

from cases.payloads import remote_console_payload
from utils.assertions import assert_api_failure, assert_api_success
from utils.case_metadata import attach_case_id
from utils.names import unique_name


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
        assert_api_success(response)

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
