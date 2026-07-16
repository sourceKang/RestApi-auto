from __future__ import annotations

import time

import pytest

from tests.support.collection import RAD_AUTH_MATRIX_CASES
from clients.runtime import build_run_context
from clients.session import SessionManager
from tests.support.service_bundle import ServiceBundle, build_service_bundle
from tests.support.options import neox_parallel_worker_auth_profile
from tests.support.ge_cli_config import wait_for_ge_cli_config
from tests.support.ge_workflow import GeServiceWorkflowState
from tests.support.ont_cli_status import read_ont_cli_status, wait_for_ont_cli_is
from tests.support.ont_workflow import OntServiceWorkflowState
from clients import EmsApiClient
from config_loader import load_environment
from models.api import SessionRole
from services.profile import TemporaryGeTemplate, TemporaryOntTemplate
from utils.cleanup import CleanupRegistry
from utils.allure_helpers import attach_json
from utils.case_metadata import format_case_title
from utils.reporting import REPORT_STATE


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
        for key, value in request.node.user_properties:
            if key == "neox_parallel_group" and value:
                allure.dynamic.label("neox_parallel_group", str(value))
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
        registrations = REPORT_STATE.case_registry.get(request.node.nodeid, [])
        if registrations:
            for registration in registrations:
                allure.dynamic.label("case_id", registration.case_id)
                allure.dynamic.testcase(registration.case_id, registration.case_id)
            name = registrations[0].name
            allure.dynamic.label("case_name", name)
            allure.dynamic.title(format_case_title([registration.case_id for registration in registrations], name))
    except Exception:
        pass


@pytest.fixture(autouse=True)
def neox_config_case_delay(env_config, request):
    yield
    if "neox_config" not in request.node.keywords:
        return
    delay_seconds = request.config.getoption("--neox-config-delay-seconds")
    if delay_seconds < 0:
        pytest.fail("--neox-config-delay-seconds must be greater than or equal to 0")
    if delay_seconds <= 0:
        return

    started = time.monotonic()
    time.sleep(float(delay_seconds))
    attach_json(
        "NeoX config inter-case delay",
        {
            "node": env_config.dut.node_key,
            "device_ip": env_config.dut.device_ip,
            "case": request.node.nodeid,
            "requested_seconds": float(delay_seconds),
            "actual_seconds": round(time.monotonic() - started, 3),
        },
    )


@pytest.fixture(scope="session")
def run_context(request):
    return build_run_context(request.config, auth_profile_override=neox_parallel_worker_auth_profile(request.config))


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
def ont_service_workflow_state() -> OntServiceWorkflowState:
    return OntServiceWorkflowState()


@pytest.fixture(scope="session")
def ge_service_workflow_state() -> GeServiceWorkflowState:
    return GeServiceWorkflowState()


@pytest.fixture(scope="session")
def temporary_ge_template(services, session_manager, env_config):
    with session_manager.credentials_session(env_config.readwrite) as session_id:
        graph = services.profile.create_temporary_profile_graph(
            session_id,
            env_config.dut.ge_template,
            env_config.ems_version,
            env_config.dut.node_key,
        )
    profile_name = TemporaryGeTemplate(graph)
    try:
        yield profile_name
    finally:
        with session_manager.credentials_session(env_config.readwrite) as session_id:
            services.provision.delete_ge_service_if_uses_template(session_id, profile_name)
            for definition in reversed(graph.definitions):
                services.profile.delete_temporary_profile(
                    session_id,
                    definition,
                    timeout=90,
                    interval=5,
                )


@pytest.fixture(scope="session")
def temporary_ont_template(services, session_manager, env_config, request):
    with session_manager.credentials_session(env_config.readwrite) as session_id:
        graph = services.profile.create_temporary_profile_graph(
            session_id,
            env_config.dut.ont_template,
            env_config.ems_version,
            env_config.dut.node_key,
        )
    profile_name = TemporaryOntTemplate(graph)

    try:
        yield profile_name
    finally:
        if request.config.getoption("--keep-ont-service-for-manual-check"):
            attach_json(
                "ONT service retained for manual inspection",
                {
                    "node": env_config.dut.node_key,
                    "sn": env_config.dut.ont_sn,
                    "template": str(profile_name),
                },
            )
            return
        with session_manager.credentials_session(env_config.readwrite) as session_id:
            services.provision.delete_ont_service_if_uses_template(session_id, profile_name)
            for definition in reversed(graph.definitions):
                services.profile.delete_temporary_profile(
                    session_id,
                    definition,
                    timeout=90,
                    interval=5,
                )


def prepare_ont_inventory_with_session_rotation(
    services,
    session_manager,
    env_config,
    ont_template_factory,
    *,
    cli_status_reader=read_ont_cli_status,
    cli_is_waiter=wait_for_ont_cli_is,
    workflow_state: OntServiceWorkflowState | None = None,
) -> str:
    with session_manager.credentials_session(env_config.readwrite) as session_id:
        existing = services.inventory.get_ont_service(session_id)

    cli_status = cli_status_reader(env_config)
    if existing.retstatus == "Success":
        existing_template = services.inventory.ont_service_template(existing)
        if workflow_state is not None and workflow_state.post_succeeded:
            if existing_template != workflow_state.template:
                raise AssertionError(
                    "EMS1-6666 created an ONT service with an unexpected template: "
                    f"expected={workflow_state.template}, actual={existing_template}"
                )
            if cli_status.state != "IS":
                cli_is_waiter(
                    env_config,
                    status_reader=cli_status_reader,
                    timeout=180,
                    interval=15,
                )
        elif cli_status.state != "IS":
            raise AssertionError(
                "ONT service already exists, but CLI is not IS; refusing to modify the existing service. "
                f"CLI state={cli_status.state}, source={cli_status.source}, template={existing_template}"
            )
        selected_template = existing_template
    else:
        if workflow_state is not None and workflow_state.post_succeeded:
            raise AssertionError(
                "EMS1-6666 POST reached Success, but the ONT service disappeared before inventory verification."
            )
        if not services.inventory.ont_service_is_missing(existing):
            raise AssertionError(
                "Cannot determine whether ONT service exists: "
                f"{existing.retstatus} {existing.retresult}"
            )
        if cli_status.state == "IS":
            raise AssertionError(
                "CLI reports IS but GET ONT service returned no data; refusing to create a duplicate service."
            )
        if cli_status.state != "UnReg":
            raise AssertionError(
                "ONT service is absent, but CLI is not UnReg; refusing automatic provisioning. "
                f"CLI state={cli_status.state}, source={cli_status.source}"
            )

        selected_template = ont_template_factory()
        with session_manager.credentials_session(env_config.readwrite) as session_id:
            services.inventory.upsert_ont_service(session_id, selected_template)
            ready = services.inventory.wait_for_ont_service_state(
                session_id,
                {"Success"},
                timeout=120,
                interval=15,
                initial_delay=30,
                raise_on_timeout=False,
            )

        if ready is None:
            with session_manager.credentials_session(env_config.readwrite) as session_id:
                services.provision.delete_ont_service_if_uses_template(
                    session_id,
                    str(selected_template),
                    timeout=90,
                    interval=5,
                )
                services.inventory.upsert_ont_service(session_id, selected_template)
                services.inventory.wait_for_ont_service_state(
                    session_id,
                    {"Success"},
                    timeout=300,
                    interval=15,
                    initial_delay=15,
                )

        cli_is_waiter(
            env_config,
            status_reader=cli_status_reader,
            timeout=180,
            interval=15,
        )

    with session_manager.credentials_session(env_config.readwrite) as session_id:
        services.inventory.wait_for_ont_inventory(
            session_id=session_id,
            ont_template=str(selected_template),
            timeout=240,
            interval=15,
            consecutive_successes=2,
            raise_on_timeout=True,
        )
    if workflow_state is not None:
        workflow_state.mark_inventory_ready(str(selected_template))
    return str(selected_template)


@pytest.fixture(scope="session")
def prepared_ont_inventory(services, session_manager, env_config, request, ont_service_workflow_state):
    if ont_service_workflow_state.post_failure:
        pytest.skip(
            "Blocked because EMS1-6666 POST failed: "
            f"{ont_service_workflow_state.post_failure}"
        )
    if ont_service_workflow_state.readiness_failure:
        pytest.skip(
            "Blocked because ONT workflow readiness failed: "
            f"{ont_service_workflow_state.readiness_failure}"
        )
    if ont_service_workflow_state.inventory_ready and ont_service_workflow_state.template:
        return ont_service_workflow_state.template
    try:
        return prepare_ont_inventory_with_session_rotation(
            services,
            session_manager,
            env_config,
            lambda: request.getfixturevalue("temporary_ont_template"),
            workflow_state=ont_service_workflow_state,
        )
    except AssertionError as error:
        ont_service_workflow_state.fail_readiness(error)
        pytest.fail(f"ONT inventory setup failed: {error}")


@pytest.fixture(scope="session")
def prepared_ge_service(
    services,
    session_manager,
    env_config,
    request,
    ge_service_workflow_state,
):
    if ge_service_workflow_state.post_failure:
        pytest.skip(f"Blocked because EMS1-6661 POST failed: {ge_service_workflow_state.post_failure}")
    if ge_service_workflow_state.cli_failure:
        pytest.skip(f"Blocked because GE CLI verification failed: {ge_service_workflow_state.cli_failure}")
    if ge_service_workflow_state.post_succeeded and ge_service_workflow_state.cli_verified:
        return ge_service_workflow_state.template

    template = request.getfixturevalue("temporary_ge_template")
    ge_service_workflow_state.begin_post(str(template))
    try:
        with session_manager.credentials_session(env_config.readwrite) as session_id:
            services.provision.verify_ge_service_post(session_id, ge_template=template)
        ge_service_workflow_state.complete_post()
        wait_for_ge_cli_config(env_config, template.definition, timeout=120, interval=10)
        ge_service_workflow_state.complete_cli()
    except Exception as error:
        if not ge_service_workflow_state.post_succeeded:
            ge_service_workflow_state.fail_post(error)
        else:
            ge_service_workflow_state.fail_cli(error)
        pytest.fail(f"GE service setup failed: {error}")
    return str(template)


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
