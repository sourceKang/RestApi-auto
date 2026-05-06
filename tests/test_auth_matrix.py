from __future__ import annotations

import pytest


@pytest.mark.authmatrix
@pytest.mark.readwrite
def test_rad_external_readwrite_summary(auth_matrix_service, rad_env_config, rad_readwrite_session):
    auth_matrix_service.verify_rad_readwrite_summary(rad_env_config, rad_readwrite_session)


@pytest.mark.authmatrix
@pytest.mark.readonly
def test_rad_external_readonly_summary(auth_matrix_service, rad_env_config, rad_readonly_session):
    auth_matrix_service.verify_rad_readonly_summary(rad_env_config, rad_readonly_session)


@pytest.mark.authmatrix
@pytest.mark.noaccess
def test_rad_external_noaccess_summary(auth_matrix_service, rad_env_config, rad_noaccess_session):
    auth_matrix_service.verify_rad_noaccess_summary(rad_env_config, rad_noaccess_session)
