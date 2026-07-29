from __future__ import annotations

import pytest




@pytest.fixture(scope="module")
def auth_matrix_seed_data(request, env_config, prepared_ont_inventory):
    ge_template = (
        request.getfixturevalue("prepared_ge_service")
        if env_config.dut.ge_slot_id and env_config.dut.ge_port_id
        else None
    )
    yield {"ont_template": prepared_ont_inventory, "ge_template": ge_template}


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
