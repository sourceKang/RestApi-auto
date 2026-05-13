from __future__ import annotations

import pytest

from services.neox_config.service import NEOX_PROFILE_READWRITE_TYPES, NEOX_PROFILE_TYPES


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
@pytest.mark.parametrize("profile_type", NEOX_PROFILE_READWRITE_TYPES)
def test_neox_profile_create_and_delete_readwrite(
    neox_config_service,
    readwrite_session,
    cleanup_registry,
    profile_type,
):
    neox_config_service.verify_neox_profile_create_and_delete(readwrite_session, cleanup_registry, profile_type)
