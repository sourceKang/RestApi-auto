from __future__ import annotations

import copy
from uuid import uuid4

from cases.neox_legacy import profile_definition_by_name
from cases.payloads import ont_service_payload
from utils.allure_helpers import allure_step
from utils.assertions import assert_api_failure, assert_api_success
from utils.case_metadata import attach_case_id


AUTH_FAILURE_MESSAGES = ("not authorized", "no access", "permission", "privilege")


class AuthMatrixService:
    def __init__(self, api_client) -> None:
        self.api_client = api_client

    def verify_rad_readwrite_summary(self, env_config, session_id: str) -> None:
        attach_case_id("RAD-RW", "rad_external_readwrite_summary", summary_group="RAD-RW")

        with allure_step("Verify RAD readwrite account can read core inventory endpoints"):
            device_response = self.api_client.request("GET", "/device", session=session_id)
            assert_api_success(device_response)

            ont_response = self.api_client.request("GET", f"/ont/sn/{env_config.dut.ont_sn}", session=session_id)
            assert_api_success(ont_response)

        definition = ephemeral_igmp_profile_definition()
        try:
            with allure_step("Verify RAD readwrite account can create, patch, get and delete a representative profile"):
                create = self.api_client.request(
                    "POST",
                    profile_path(definition),
                    session=session_id,
                    json={"Content": definition["post_profile_info"]},
                )
                assert_api_success(create)

                get_created = self.api_client.request("GET", profile_path(definition), session=session_id)
                assert_api_success(get_created)

                patch = self.api_client.request(
                    "PATCH",
                    profile_path(definition),
                    session=session_id,
                    json={"Content": definition["patch_profile_info"]},
                )
                assert_api_success(patch)

                get_patched = self.api_client.request("GET", profile_path(definition), session=session_id)
                assert_api_success(get_patched)

                delete = self.api_client.request("DELETE", profile_path(definition), session=session_id)
                assert_api_success(delete)
        finally:
            self.delete_profile_if_present(session_id, definition)

    def verify_rad_readonly_summary(self, env_config, session_id: str) -> None:
        attach_case_id("RAD-RO", "rad_external_readonly_summary", summary_group="RAD-RO")

        with allure_step("Verify RAD readonly account can read allowed endpoints"):
            device_response = self.api_client.request("GET", "/device", session=session_id)
            assert_api_success(device_response)

            ont_response = self.api_client.request("GET", f"/ont/sn/{env_config.dut.ont_sn}", session=session_id)
            assert_api_success(ont_response)

        definition = ephemeral_igmp_profile_definition()
        with allure_step("Verify RAD readonly account is rejected by representative mutating endpoints"):
            profile_create = self.api_client.request(
                "POST",
                profile_path(definition),
                session=session_id,
                json={"Content": definition["post_profile_info"]},
            )
            assert_api_failure(profile_create, accepted_messages=AUTH_FAILURE_MESSAGES)

            ontservice_create = self.api_client.request(
                "POST",
                f"/ontservice/{env_config.dut.ont_sn}",
                session=session_id,
                json=ont_service_payload(env_config, "RAD_AUTH_MATRIX"),
            )
            assert_api_failure(ontservice_create, accepted_messages=AUTH_FAILURE_MESSAGES)

            remote_response = self.api_client.request(
                "POST",
                f"/remote/{env_config.dut.device_name}",
                session=session_id,
                json={"command": ["show version"]},
            )
            assert_api_failure(remote_response, accepted_messages=AUTH_FAILURE_MESSAGES)

    def verify_rad_noaccess_summary(self, env_config, session_id: str) -> None:
        attach_case_id("RAD-NA", "rad_external_noaccess_summary", summary_group="RAD-NA")

        definition = ephemeral_igmp_profile_definition()
        with allure_step("Verify RAD noaccess account is rejected by representative read and write endpoints"):
            device_response = self.api_client.request("GET", "/device", session=session_id)
            assert_api_failure(device_response, accepted_messages=AUTH_FAILURE_MESSAGES)

            ont_response = self.api_client.request("GET", f"/ont/sn/{env_config.dut.ont_sn}", session=session_id)
            assert_api_failure(ont_response, accepted_messages=AUTH_FAILURE_MESSAGES)

            profile_create = self.api_client.request(
                "POST",
                profile_path(definition),
                session=session_id,
                json={"Content": definition["post_profile_info"]},
            )
            assert_api_failure(profile_create, accepted_messages=AUTH_FAILURE_MESSAGES)

            remote_response = self.api_client.request(
                "POST",
                f"/remote/{env_config.dut.device_name}",
                session=session_id,
                json={"command": ["show version"]},
            )
            assert_api_failure(remote_response, accepted_messages=AUTH_FAILURE_MESSAGES)

    def delete_profile_if_present(self, session_id: str, definition) -> None:
        existing = self.api_client.request("GET", profile_path(definition), session=session_id)
        if existing.retstatus == "Success":
            self.api_client.request("DELETE", profile_path(definition), session=session_id)


def ephemeral_igmp_profile_definition():
    base = profile_definition_by_name("#RestApi_igmpgrouppriv")
    assert base is not None, "Missing converted legacy profile definition for #RestApi_igmpgrouppriv"
    definition = copy.deepcopy(base)
    definition["profilename"] = f"#RAD_AUTH_{uuid4().hex[:10]}"
    return definition


def profile_path(definition):
    return f"/profile/{definition['profiletype']}/{definition['profilename']}"
