from __future__ import annotations

import pytest

from tests.support.collection import RAD_AUTH_MATRIX_CASES
from clients.runtime import build_run_context
from clients.session import SessionManager
from tests.support.service_bundle import ServiceBundle, build_service_bundle
from clients import EmsApiClient
from config_loader import load_environment
from models.api import SessionRole
from utils.cleanup import CleanupRegistry


@pytest.fixture(autouse=True)
def allure_node_context(env_config, request):
    try:
        import allure

        chassis = env_config.dut.chassis
        parent_suite = f"{env_config.dut.node_key} - {env_config.dut.device_name}"
        allure.dynamic.parent_suite(parent_suite)
        allure.dynamic.suite(chassis)
        allure.dynamic.label("ems_node", env_config.dut.node_key)
        allure.dynamic.label("dut_name", env_config.dut.device_name)
        allure.dynamic.label("dut_ip", env_config.dut.device_ip)
        allure.dynamic.label("dut_chassis", chassis)
        allure.dynamic.label("auth_profile", env_config.auth_profile)
        allure.dynamic.label("rw_account", env_config.readwrite_account.account_name)
        allure.dynamic.label("ro_account", env_config.readonly_account.account_name)
        allure.dynamic.label("na_account", env_config.noaccess_account.account_name)
        if "authmatrix" in request.node.keywords:
            case = RAD_AUTH_MATRIX_CASES.get(request.node.name)
            if case is not None:
                allure.dynamic.label("summary_group", case[0])
        elif "readonly" in request.node.keywords:
            allure.dynamic.label("summary_group", "PERM-RO")
        elif "noaccess" in request.node.keywords:
            allure.dynamic.label("summary_group", "PERM-NA")
    except Exception:
        pass


@pytest.fixture(scope="session")
def run_context(request):
    return build_run_context(request.config)


@pytest.fixture(scope="session")
def env_config(run_context):
    return run_context.env


@pytest.fixture(scope="session")
def rad_env_config(request):
    return load_environment(
        node=request.config.getoption("--ems-node"),
        auth_profile="rad_external",
    )


@pytest.fixture(scope="session")
def api_client(env_config):
    return EmsApiClient(env_config)


@pytest.fixture(scope="session")
def session_manager(api_client, env_config):
    return SessionManager(api_client, env_config)


@pytest.fixture(scope="session")
def services(api_client, env_config) -> ServiceBundle:
    return build_service_bundle(api_client, env_config)


@pytest.fixture(scope="session")
def inventory_service(services):
    return services.inventory


@pytest.fixture(scope="session")
def neox_config_service(services):
    return services.neox_config


@pytest.fixture(scope="session")
def invalid_params_service(services):
    return services.invalid_params


@pytest.fixture(scope="session")
def alarm_service(services):
    return services.alarm


@pytest.fixture(scope="session")
def auth_matrix_service(services):
    return services.auth_matrix


@pytest.fixture(scope="session")
def provision_service(services):
    return services.provision


@pytest.fixture(scope="session")
def profile_service(services):
    return services.profile


@pytest.fixture(scope="session")
def remote_service(services):
    return services.remote


@pytest.fixture(scope="session")
def user_session_service(services):
    return services.user_session


@pytest.fixture
def cleanup_registry():
    registry = CleanupRegistry()
    try:
        yield registry
    finally:
        registry.run()


@pytest.fixture
def readwrite_session(session_manager):
    with session_manager.role_session(SessionRole.READWRITE) as session_id:
        yield session_id


@pytest.fixture
def readonly_session(session_manager):
    with session_manager.role_session(SessionRole.READONLY) as session_id:
        yield session_id


@pytest.fixture
def noaccess_session(session_manager):
    with session_manager.role_session(SessionRole.NOACCESS) as session_id:
        yield session_id


@pytest.fixture
def rad_session_manager(api_client, rad_env_config):
    return SessionManager(api_client, rad_env_config)


@pytest.fixture
def rad_readwrite_session(rad_session_manager, rad_env_config):
    with rad_session_manager.credentials_session(rad_env_config.readwrite) as session_id:
        yield session_id


@pytest.fixture
def rad_readonly_session(rad_session_manager, rad_env_config):
    with rad_session_manager.credentials_session(rad_env_config.readonly) as session_id:
        yield session_id


@pytest.fixture
def rad_noaccess_session(rad_session_manager, rad_env_config):
    with rad_session_manager.credentials_session(rad_env_config.noaccess) as session_id:
        yield session_id
