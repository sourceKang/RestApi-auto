from __future__ import annotations

import copy
from uuid import uuid4

import pytest

from cases.neox_legacy import profile_definition_by_name
from cases.payloads import ont_service_payload
from utils.allure_helpers import allure_step
from utils.assertions import assert_api_failure, assert_api_success
from utils.case_metadata import attach_case_id


AUTH_FAILURE_MESSAGES = ("not authorized", "no access", "permission", "privilege")


@pytest.mark.authmatrix
@pytest.mark.readwrite
def test_rad_external_readwrite_summary(api_client, rad_env_config, rad_readwrite_session):
    attach_case_id("RAD-RW", "rad_external_readwrite_summary", summary_group="RAD-RW")

    with allure_step("Verify RAD readwrite account can read core inventory endpoints"):
        device_response = api_client.request("GET", "/device", session=rad_readwrite_session)
        assert_api_success(device_response)

        ont_response = api_client.request("GET", f"/ont/sn/{rad_env_config.dut.ont_sn}", session=rad_readwrite_session)
        assert_api_success(ont_response)

    definition = _ephemeral_igmp_profile_definition()
    try:
        with allure_step("Verify RAD readwrite account can create, patch, get and delete a representative profile"):
            create = api_client.request(
                "POST",
                _profile_path(definition),
                session=rad_readwrite_session,
                json={"Content": definition["post_profile_info"]},
            )
            assert_api_success(create)

            get_created = api_client.request("GET", _profile_path(definition), session=rad_readwrite_session)
            assert_api_success(get_created)

            patch = api_client.request(
                "PATCH",
                _profile_path(definition),
                session=rad_readwrite_session,
                json={"Content": definition["patch_profile_info"]},
            )
            assert_api_success(patch)

            get_patched = api_client.request("GET", _profile_path(definition), session=rad_readwrite_session)
            assert_api_success(get_patched)

            delete = api_client.request("DELETE", _profile_path(definition), session=rad_readwrite_session)
            assert_api_success(delete)
    finally:
        _delete_profile_if_present(api_client, rad_readwrite_session, definition)


@pytest.mark.authmatrix
@pytest.mark.readonly
def test_rad_external_readonly_summary(api_client, rad_env_config, rad_readonly_session):
    attach_case_id("RAD-RO", "rad_external_readonly_summary", summary_group="RAD-RO")

    with allure_step("Verify RAD readonly account can read allowed endpoints"):
        device_response = api_client.request("GET", "/device", session=rad_readonly_session)
        assert_api_success(device_response)

        ont_response = api_client.request("GET", f"/ont/sn/{rad_env_config.dut.ont_sn}", session=rad_readonly_session)
        assert_api_success(ont_response)

    definition = _ephemeral_igmp_profile_definition()
    with allure_step("Verify RAD readonly account is rejected by representative mutating endpoints"):
        profile_create = api_client.request(
            "POST",
            _profile_path(definition),
            session=rad_readonly_session,
            json={"Content": definition["post_profile_info"]},
        )
        assert_api_failure(profile_create, accepted_messages=AUTH_FAILURE_MESSAGES)

        ontservice_create = api_client.request(
            "POST",
            f"/ontservice/{rad_env_config.dut.ont_sn}",
            session=rad_readonly_session,
            json=ont_service_payload(rad_env_config, "RAD_AUTH_MATRIX"),
        )
        assert_api_failure(ontservice_create, accepted_messages=AUTH_FAILURE_MESSAGES)

        remote_response = api_client.request(
            "POST",
            f"/remote/{rad_env_config.dut.device_name}",
            session=rad_readonly_session,
            json={"command": ["show version"]},
        )
        assert_api_failure(remote_response, accepted_messages=AUTH_FAILURE_MESSAGES)


@pytest.mark.authmatrix
@pytest.mark.noaccess
def test_rad_external_noaccess_summary(api_client, rad_env_config, rad_noaccess_session):
    attach_case_id("RAD-NA", "rad_external_noaccess_summary", summary_group="RAD-NA")

    definition = _ephemeral_igmp_profile_definition()
    with allure_step("Verify RAD noaccess account is rejected by representative read and write endpoints"):
        device_response = api_client.request("GET", "/device", session=rad_noaccess_session)
        assert_api_failure(device_response, accepted_messages=AUTH_FAILURE_MESSAGES)

        ont_response = api_client.request("GET", f"/ont/sn/{rad_env_config.dut.ont_sn}", session=rad_noaccess_session)
        assert_api_failure(ont_response, accepted_messages=AUTH_FAILURE_MESSAGES)

        profile_create = api_client.request(
            "POST",
            _profile_path(definition),
            session=rad_noaccess_session,
            json={"Content": definition["post_profile_info"]},
        )
        assert_api_failure(profile_create, accepted_messages=AUTH_FAILURE_MESSAGES)

        remote_response = api_client.request(
            "POST",
            f"/remote/{rad_env_config.dut.device_name}",
            session=rad_noaccess_session,
            json={"command": ["show version"]},
        )
        assert_api_failure(remote_response, accepted_messages=AUTH_FAILURE_MESSAGES)


def _ephemeral_igmp_profile_definition():
    base = profile_definition_by_name("#RestApi_igmpgrouppriv")
    assert base is not None, "Missing converted legacy profile definition for #RestApi_igmpgrouppriv"
    definition = copy.deepcopy(base)
    definition["profilename"] = f"#RAD_AUTH_{uuid4().hex[:10]}"
    return definition


def _profile_path(definition):
    return f"/profile/{definition['profiletype']}/{definition['profilename']}"


def _delete_profile_if_present(api_client, session_id, definition):
    existing = api_client.request("GET", _profile_path(definition), session=session_id)
    if existing.retstatus == "Success":
        api_client.request("DELETE", _profile_path(definition), session=session_id)
