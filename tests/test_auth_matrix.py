from __future__ import annotations

import pytest

from utils.cleanup import CleanupRegistry


@pytest.fixture(scope="module")
def auth_matrix_seed_data(provision_service, session_manager):
    registry = CleanupRegistry()
    with session_manager.credentials_session(provision_service.env_config.readwrite) as session_id:
        provision_service.ensure_seed_data(session_id, registry)
        yield


@pytest.mark.authmatrix
@pytest.mark.readwrite
def test_rad_external_readwrite_summary(auth_matrix_service, rad_env_config, rad_readwrite_session, auth_matrix_seed_data):
    auth_matrix_service.verify_rad_readwrite_summary(rad_env_config, rad_readwrite_session)


@pytest.mark.authmatrix
@pytest.mark.readonly
def test_rad_external_readonly_summary(
    auth_matrix_service,
    rad_env_config,
    rad_readonly_session,
    rad_readwrite_session,
    auth_matrix_seed_data,
):
    auth_matrix_service.verify_rad_readonly_summary(rad_env_config, rad_readonly_session, rad_readwrite_session)


@pytest.mark.authmatrix
@pytest.mark.noaccess
def test_rad_external_noaccess_summary(
    auth_matrix_service,
    rad_env_config,
    rad_noaccess_session,
    rad_readwrite_session,
    auth_matrix_seed_data,
):
    auth_matrix_service.verify_rad_noaccess_summary(rad_env_config, rad_noaccess_session, rad_readwrite_session)
