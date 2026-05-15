from __future__ import annotations

import pytest

from services.neox_config.service import NEOX_PROFILE_READWRITE_TYPES, NEOX_PROFILE_TYPES, neox_profile_minmax_payload
from utils.assertions import assert_api_failure, assert_api_success


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.neox_profile,
    pytest.mark.destructive,
]


@pytest.mark.mutating
@pytest.mark.readonly
@pytest.mark.parametrize("profile_type", NEOX_PROFILE_TYPES)
def test_neox_profile_create_delete_rejects_readonly(neox_config_service, readonly_session, profile_type):
    neox_config_service.verify_neox_profile_rejected(readonly_session, profile_type)


@pytest.mark.mutating
@pytest.mark.noaccess
@pytest.mark.parametrize("profile_type", NEOX_PROFILE_TYPES)
def test_neox_profile_create_delete_rejects_noaccess(neox_config_service, noaccess_session, profile_type):
    neox_config_service.verify_neox_profile_rejected(noaccess_session, profile_type)


@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("profile_type", NEOX_PROFILE_READWRITE_TYPES, ids=NEOX_PROFILE_READWRITE_TYPES)
def test_neox_profile_min_create_readwrite(
    neox_config_service,
    api_client,
    readwrite_session,
    cleanup_registry,
    profile_type,
):
    neox_config_service.verify_node3_target()
    neox_config_service.ensure_neox_profile_dependencies(readwrite_session, cleanup_registry, profile_type)
    path = neox_config_service.neox_profile_path(profile_type)
    payload = neox_profile_minmax_payload(profile_type, "min")
    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))
    api_client.request("DELETE", path, session=readwrite_session)
    response = api_client.request("POST", path, session=readwrite_session, json=payload)
    assert_api_success(response)


@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("profile_type", NEOX_PROFILE_READWRITE_TYPES, ids=NEOX_PROFILE_READWRITE_TYPES)
def test_neox_profile_max_create_readwrite(
    neox_config_service,
    api_client,
    readwrite_session,
    cleanup_registry,
    profile_type,
):
    neox_config_service.verify_node3_target()
    neox_config_service.ensure_neox_profile_dependencies(readwrite_session, cleanup_registry, profile_type)
    path = neox_config_service.neox_profile_path(profile_type)
    payload = neox_profile_minmax_payload(profile_type, "max")
    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))
    api_client.request("DELETE", path, session=readwrite_session)
    response = api_client.request("POST", path, session=readwrite_session, json=payload)
    assert_api_success(response)


@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("profile_type", NEOX_PROFILE_READWRITE_TYPES, ids=NEOX_PROFILE_READWRITE_TYPES)
def test_neox_profile_clear_readwrite(
    neox_config_service,
    api_client,
    readwrite_session,
    cleanup_registry,
    profile_type,
):
    neox_config_service.verify_node3_target()
    neox_config_service.ensure_neox_profile_dependencies(readwrite_session, cleanup_registry, profile_type)
    path = neox_config_service.neox_profile_path(profile_type)
    payload = neox_config_service.neox_profile_payload(profile_type)
    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))
    api_client.request("DELETE", path, session=readwrite_session)
    response = api_client.request("POST", path, session=readwrite_session, json=payload)
    assert_api_success(response)
    response = api_client.request("DELETE", path, session=readwrite_session)
    assert_api_success(response)


@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("profile_type", NEOX_PROFILE_READWRITE_TYPES, ids=NEOX_PROFILE_READWRITE_TYPES)
def test_neox_profile_error_readwrite(
    neox_config_service,
    api_client,
    readwrite_session,
    profile_type,
):
    neox_config_service.verify_node3_target()
    path = neox_config_service.neox_profile_path(profile_type)
    response = api_client.request("POST", path, session=readwrite_session, json={"Content": {"__invalid_field__": "invalid"}})
    assert_api_failure(response, accepted_messages=("invalid field",))
