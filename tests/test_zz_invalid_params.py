from __future__ import annotations

import pytest


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_service_post_various_invalid_parameters_should_return_error(invalid_params_service, readwrite_session):
    invalid_params_service.verify_ont_service_post_invalid_parameters(readwrite_session)


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.readwrite
def test_ge_service_post_various_invalid_parameters_should_return_error(invalid_params_service, readwrite_session):
    invalid_params_service.verify_ge_service_post_invalid_parameters(readwrite_session)


@pytest.mark.alarm
@pytest.mark.mutating
@pytest.mark.readwrite
def test_history_alarm_various_invalid_parameters_should_return_error(invalid_params_service, readwrite_session):
    invalid_params_service.verify_history_alarm_invalid_parameters(readwrite_session)


@pytest.mark.inventory
@pytest.mark.readwrite
def test_get_device_name_with_invalid_parameters_should_return_error(invalid_params_service, readwrite_session):
    invalid_params_service.verify_device_name_invalid_parameters(readwrite_session)


@pytest.mark.inventory
@pytest.mark.readwrite
def test_slot_api_with_invalid_parameters_should_return_error(invalid_params_service, readwrite_session):
    invalid_params_service.verify_slot_invalid_parameters(readwrite_session)


@pytest.mark.inventory
@pytest.mark.readwrite
def test_port_api_with_invalid_parameters_should_return_error(invalid_params_service, readwrite_session):
    invalid_params_service.verify_port_invalid_parameters(readwrite_session)


@pytest.mark.ont
@pytest.mark.readwrite
def test_ont_api_with_invalid_parameters_should_return_error(invalid_params_service, readwrite_session):
    invalid_params_service.verify_ont_invalid_parameters(readwrite_session)
