from __future__ import annotations

import pytest




@pytest.fixture(scope="module")
def auth_matrix_seed_data(prepared_ont_inventory, prepared_ge_service):
    yield {"ont_template": prepared_ont_inventory, "ge_template": prepared_ge_service}


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
    services.auth_matrix.verify_rad_readonly_summary(
        rad_env_config,
        rad_readonly_session,
        rad_readwrite_session,
        ont_template=auth_matrix_seed_data["ont_template"],
        ge_template=auth_matrix_seed_data["ge_template"],
    )


@pytest.mark.authmatrix
@pytest.mark.noaccess
def test_rad_external_noaccess_summary(
    services,
    rad_env_config,
    rad_noaccess_session,
    rad_readwrite_session,
    auth_matrix_seed_data,
):
    services.auth_matrix.verify_rad_noaccess_summary(
        rad_env_config,
        rad_noaccess_session,
        rad_readwrite_session,
        ont_template=auth_matrix_seed_data["ont_template"],
        ge_template=auth_matrix_seed_data["ge_template"],
    )
