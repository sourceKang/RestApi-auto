from __future__ import annotations

import copy
import json
from uuid import uuid4

from cases.neox_legacy import profile_definition_by_name
from cases.payloads import ge_service_payload, ge_service_modified_payload, ont_service_payload, ont_service_modified_payload
from utils.allure_helpers import allure_step
from utils.assertions import assert_api_failure, assert_api_success
from utils.case_metadata import attach_case_id


AUTH_FAILURE_MESSAGES = ("not authorized", "no access", "permission", "privilege")


class AuthMatrixService:
    def __init__(self, api_client) -> None:
        self.api_client = api_client

    def verify_rad_readwrite_summary(self, env_config, session_id: str) -> None:
        attach_case_id("EMS1-7056", "rad_external_readwrite_summary", summary_group="RAD-RW")

        with allure_step("Verify RAD readwrite account can read representative inventory, provision and alarm endpoints"):
            device_response = self.api_client.request("GET", "/device", session=session_id)
            assert_api_success(device_response)

            ont_response = self.api_client.request("GET", f"/ont/sn/{env_config.dut.ont_sn}", session=session_id)
            assert_api_success(ont_response)

            ontservice_response = self.api_client.request("GET", f"/ontservice/{env_config.dut.ont_sn}", session=session_id)
            assert_api_success(ontservice_response)

            geservice_response = self.api_client.request("GET", ge_service_port_path(env_config), session=session_id)
            assert_api_success(geservice_response)

            active_alarm_response = self.api_client.request(
                "GET",
                "/activealarm",
                session=session_id,
                params=alarm_filter(env_config),
            )
            assert_read_or_no_data(active_alarm_response)

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

    def verify_rad_readonly_summary(self, env_config, session_id: str, observer_session_id: str) -> None:
        attach_case_id("EMS1-7107", "rad_external_readonly_summary", summary_group="RAD-RO")

        with allure_step("Verify RAD readonly account can read allowed inventory, provision and alarm endpoints"):
            device_response = self.api_client.request("GET", "/device", session=session_id)
            assert_api_success(device_response)

            ont_response = self.api_client.request("GET", f"/ont/sn/{env_config.dut.ont_sn}", session=session_id)
            assert_api_success(ont_response)

            ontservice_response = self.api_client.request("GET", f"/ontservice/{env_config.dut.ont_sn}", session=session_id)
            assert_api_success(ontservice_response)

            geservice_response = self.api_client.request("GET", ge_service_port_path(env_config), session=session_id)
            assert_api_success(geservice_response)

            active_alarm_response = self.api_client.request(
                "GET",
                "/activealarm",
                session=session_id,
                params=alarm_filter(env_config),
            )
            assert_read_or_no_data(active_alarm_response)

        ge_mutation_path = ge_service_mutation_path(self.api_client, observer_session_id, env_config)
        definition = ephemeral_igmp_profile_definition()
        with allure_step("Verify RAD readonly POST rejection does not create a profile"):
            profile_create = self.api_client.request(
                "POST",
                profile_path(definition),
                session=session_id,
                json={"Content": definition["post_profile_info"]},
            )
            assert_api_failure(profile_create, accepted_messages=AUTH_FAILURE_MESSAGES)
            assert_profile_absent(self.api_client, observer_session_id, definition)

        with allure_step("Verify RAD readonly account is rejected by representative provision and remote mutating endpoints"):
            ontservice_create = self.api_client.request(
                "POST",
                f"/ontservice/{env_config.dut.ont_sn}",
                session=session_id,
                json=ont_service_payload(env_config, "RAD_AUTH_MATRIX"),
            )
            assert_api_failure(ontservice_create, accepted_messages=AUTH_FAILURE_MESSAGES)

            ontservice_update = self.api_client.request(
                "PUT",
                f"/ontservice/{env_config.dut.ont_sn}",
                session=session_id,
                json=ont_service_modified_payload(env_config, "RAD_AUTH_MATRIX"),
            )
            assert_api_failure(ontservice_update, accepted_messages=AUTH_FAILURE_MESSAGES)

            ontservice_delete = self.api_client.request("DELETE", f"/ontservice/{env_config.dut.ont_sn}", session=session_id)
            assert_api_failure(ontservice_delete, accepted_messages=AUTH_FAILURE_MESSAGES)

            geservice_create = self.api_client.request(
                "POST",
                ge_service_port_path(env_config),
                session=session_id,
                json=ge_service_payload(env_config, "RAD_AUTH_MATRIX"),
            )
            assert_api_failure(geservice_create, accepted_messages=AUTH_FAILURE_MESSAGES)

            geservice_update = self.api_client.request(
                "PUT",
                ge_mutation_path,
                session=session_id,
                json=ge_service_modified_payload(env_config, "RAD_AUTH_MATRIX"),
            )
            assert_api_failure(geservice_update, accepted_messages=AUTH_FAILURE_MESSAGES)

            geservice_delete = self.api_client.request("DELETE", ge_mutation_path, session=session_id)
            assert_api_failure(geservice_delete, accepted_messages=AUTH_FAILURE_MESSAGES)

            remote_response = self.api_client.request(
                "POST",
                f"/remote/{env_config.dut.device_name}",
                session=session_id,
                json={"command": ["show version"]},
            )
            assert_api_failure(remote_response, accepted_messages=AUTH_FAILURE_MESSAGES)

        protected_definition = ephemeral_igmp_profile_definition()
        try:
            with allure_step("Verify RAD readonly PATCH and DELETE rejections leave an existing profile unchanged"):
                create_profile(self.api_client, observer_session_id, protected_definition)
                before = get_profile_json(self.api_client, observer_session_id, protected_definition)

                profile_update = self.api_client.request(
                    "PATCH",
                    profile_path(protected_definition),
                    session=session_id,
                    json={"Content": protected_definition["patch_profile_info"]},
                )
                assert_api_failure(profile_update, accepted_messages=AUTH_FAILURE_MESSAGES)
                assert_profile_json_unchanged(self.api_client, observer_session_id, protected_definition, before)

                profile_delete = self.api_client.request("DELETE", profile_path(protected_definition), session=session_id)
                assert_api_failure(profile_delete, accepted_messages=AUTH_FAILURE_MESSAGES)
                assert_profile_json_unchanged(self.api_client, observer_session_id, protected_definition, before)
        finally:
            self.delete_profile_if_present(observer_session_id, protected_definition)

    def verify_rad_noaccess_summary(self, env_config, session_id: str, observer_session_id: str) -> None:
        attach_case_id("EMS1-7108", "rad_external_noaccess_summary", summary_group="RAD-NA")

        definition = ephemeral_igmp_profile_definition()
        with allure_step("Verify RAD noaccess account is rejected by representative read endpoints"):
            device_response = self.api_client.request("GET", "/device", session=session_id)
            assert_api_failure(device_response, accepted_messages=AUTH_FAILURE_MESSAGES)

            ont_response = self.api_client.request("GET", f"/ont/sn/{env_config.dut.ont_sn}", session=session_id)
            assert_api_failure(ont_response, accepted_messages=AUTH_FAILURE_MESSAGES)

            ontservice_response = self.api_client.request("GET", f"/ontservice/{env_config.dut.ont_sn}", session=session_id)
            assert_api_failure(ontservice_response, accepted_messages=AUTH_FAILURE_MESSAGES)

            geservice_response = self.api_client.request("GET", ge_service_port_path(env_config), session=session_id)
            assert_api_failure(geservice_response, accepted_messages=AUTH_FAILURE_MESSAGES)

            active_alarm_response = self.api_client.request(
                "GET",
                "/activealarm",
                session=session_id,
                params=alarm_filter(env_config),
            )
            assert_api_failure(active_alarm_response, accepted_messages=AUTH_FAILURE_MESSAGES)

            history_alarm_response = self.api_client.request(
                "GET",
                "/historyalarm",
                session=session_id,
                params=alarm_filter(env_config),
            )
            assert_api_failure(history_alarm_response, accepted_messages=AUTH_FAILURE_MESSAGES)

        ge_mutation_path = ge_service_mutation_path(self.api_client, observer_session_id, env_config)
        with allure_step("Verify RAD noaccess POST rejection does not create a profile"):
            profile_create = self.api_client.request(
                "POST",
                profile_path(definition),
                session=session_id,
                json={"Content": definition["post_profile_info"]},
            )
            assert_api_failure(profile_create, accepted_messages=AUTH_FAILURE_MESSAGES)
            assert_profile_absent(self.api_client, observer_session_id, definition)

        with allure_step("Verify RAD noaccess account is rejected by representative provision and remote mutating endpoints"):
            ontservice_create = self.api_client.request(
                "POST",
                f"/ontservice/{env_config.dut.ont_sn}",
                session=session_id,
                json=ont_service_payload(env_config, "RAD_AUTH_MATRIX"),
            )
            assert_api_failure(ontservice_create, accepted_messages=AUTH_FAILURE_MESSAGES)

            ontservice_update = self.api_client.request(
                "PUT",
                f"/ontservice/{env_config.dut.ont_sn}",
                session=session_id,
                json=ont_service_modified_payload(env_config, "RAD_AUTH_MATRIX"),
            )
            assert_api_failure(ontservice_update, accepted_messages=AUTH_FAILURE_MESSAGES)

            ontservice_delete = self.api_client.request("DELETE", f"/ontservice/{env_config.dut.ont_sn}", session=session_id)
            assert_api_failure(ontservice_delete, accepted_messages=AUTH_FAILURE_MESSAGES)

            geservice_create = self.api_client.request(
                "POST",
                ge_service_port_path(env_config),
                session=session_id,
                json=ge_service_payload(env_config, "RAD_AUTH_MATRIX"),
            )
            assert_api_failure(geservice_create, accepted_messages=AUTH_FAILURE_MESSAGES)

            geservice_update = self.api_client.request(
                "PUT",
                ge_mutation_path,
                session=session_id,
                json=ge_service_modified_payload(env_config, "RAD_AUTH_MATRIX"),
            )
            assert_api_failure(geservice_update, accepted_messages=AUTH_FAILURE_MESSAGES)

            geservice_delete = self.api_client.request("DELETE", ge_mutation_path, session=session_id)
            assert_api_failure(geservice_delete, accepted_messages=AUTH_FAILURE_MESSAGES)

            remote_response = self.api_client.request(
                "POST",
                f"/remote/{env_config.dut.device_name}",
                session=session_id,
                json={"command": ["show version"]},
            )
            assert_api_failure(remote_response, accepted_messages=AUTH_FAILURE_MESSAGES)

        protected_definition = ephemeral_igmp_profile_definition()
        try:
            with allure_step("Verify RAD noaccess GET, PATCH and DELETE rejections leave an existing profile unchanged"):
                create_profile(self.api_client, observer_session_id, protected_definition)
                before = get_profile_json(self.api_client, observer_session_id, protected_definition)

                profile_read = self.api_client.request("GET", profile_path(protected_definition), session=session_id)
                assert_api_failure(profile_read, accepted_messages=AUTH_FAILURE_MESSAGES)

                profile_update = self.api_client.request(
                    "PATCH",
                    profile_path(protected_definition),
                    session=session_id,
                    json={"Content": protected_definition["patch_profile_info"]},
                )
                assert_api_failure(profile_update, accepted_messages=AUTH_FAILURE_MESSAGES)
                assert_profile_json_unchanged(self.api_client, observer_session_id, protected_definition, before)

                profile_delete = self.api_client.request("DELETE", profile_path(protected_definition), session=session_id)
                assert_api_failure(profile_delete, accepted_messages=AUTH_FAILURE_MESSAGES)
                assert_profile_json_unchanged(self.api_client, observer_session_id, protected_definition, before)
        finally:
            self.delete_profile_if_present(observer_session_id, protected_definition)

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


def create_profile(api_client, session_id: str, definition) -> None:
    create = api_client.request(
        "POST",
        profile_path(definition),
        session=session_id,
        json={"Content": definition["post_profile_info"]},
    )
    assert_api_success(create)


def get_profile_json(api_client, session_id: str, definition):
    response = api_client.request("GET", profile_path(definition), session=session_id)
    assert_api_success(response)
    return response.json


def assert_profile_absent(api_client, session_id: str, definition) -> None:
    response = api_client.request("GET", profile_path(definition), session=session_id)
    assert response.retstatus == "Fail", f"Rejected profile create still produced readable profile: {response.json!r}"


def assert_profile_json_unchanged(api_client, session_id: str, definition, before) -> None:
    after = get_profile_json(api_client, session_id, definition)
    assert after == before, "Rejected profile mutation changed the profile visible to a readwrite observer."


def ge_service_port_path(env_config) -> str:
    dut = env_config.dut
    return f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}"


def ge_service_mutation_path(api_client, session_id: str, env_config) -> str:
    response = api_client.request("GET", ge_service_port_path(env_config), session=session_id)
    assert_api_success(response)
    service_id = ge_service_id(response.json)
    assert service_id, f"GE service response does not expose service id: {response.json!r}"
    return f"/geservice/{service_id}"


def ge_service_id(payload):
    if not isinstance(payload, dict):
        return None
    retval = payload.get("retval", {})
    if not isinstance(retval, dict):
        return None
    service = retval.get("geserviceinfo", retval)
    if isinstance(service, dict):
        return service.get("GeServiceID") or service.get("geserviceid") or service.get("serviceid")
    return None


def alarm_filter(env_config) -> dict[str, str]:
    return {"alarmfilter": json.dumps({"KeyWord": [env_config.dut.device_ip, "Login Success"]})}


def assert_read_or_no_data(response) -> None:
    if response.retstatus == "Fail" and "No data found" in response.retresult:
        return
    assert_api_success(response)
