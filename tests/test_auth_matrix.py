from __future__ import annotations

import pytest

from utils.cleanup import CleanupRegistry


@pytest.fixture(scope="module")
def auth_matrix_seed_data(services, session_manager):
    registry = CleanupRegistry()
    with session_manager.credentials_session(services.provision.env_config.readwrite) as session_id:
        services.inventory.ensure_ont_inventory_ready(session_id)
        services.provision.ensure_ge_seed_data(session_id, registry)
        yield


@pytest.mark.authmatrix
@pytest.mark.readwrite
def test_rad_external_readwrite_summary(services, rad_env_config, rad_readwrite_session, auth_matrix_seed_data):
    services.auth_matrix.verify_rad_readwrite_summary(rad_env_config, rad_readwrite_session)


@pytest.mark.authmatrix
@pytest.mark.readonly
def test_rad_external_readonly_summary(
    services,
    rad_env_config,
    rad_readonly_session,
    rad_readwrite_session,
    auth_matrix_seed_data,
):
    services.auth_matrix.verify_rad_readonly_summary(rad_env_config, rad_readonly_session, rad_readwrite_session)


@pytest.mark.authmatrix
@pytest.mark.noaccess
def test_rad_external_noaccess_summary(
    services,
    rad_env_config,
    rad_noaccess_session,
    rad_readwrite_session,
    auth_matrix_seed_data,
):
    services.auth_matrix.verify_rad_noaccess_summary(rad_env_config, rad_noaccess_session, rad_readwrite_session)
