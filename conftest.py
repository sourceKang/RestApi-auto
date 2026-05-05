from __future__ import annotations

import os

import pytest

from clients import EmsApiClient
from configs import load_environment
from models.api import SessionRole
from utils.assertions import assert_api_success
from utils.cleanup import CleanupRegistry
from utils.diagnostics import format_response_summary
from utils.reporting import ensure_report_dirs, record_result, register_node_case, register_permission_role, write_reports


RAD_AUTH_MATRIX_CASES = {
    "test_rad_external_readwrite_summary": ("RAD-RW", "rad_external_readwrite_summary"),
    "test_rad_external_readonly_summary": ("RAD-RO", "rad_external_readonly_summary"),
    "test_rad_external_noaccess_summary": ("RAD-NA", "rad_external_noaccess_summary"),
}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--ems-node",
        action="store",
        default=None,
        help="Select DUT node key from configs/test_targets.yaml, for example NODE1 or NODE3. Overrides EMS_NODE.",
    )
    parser.addoption(
        "--auth-profile",
        action="store",
        default=None,
        help="Select auth profile from configs/auth_accounts.yaml, for example default or rad_external.",
    )
    parser.addoption(
        "--auth-matrix",
        action="store_true",
        default=False,
        help="Also run lightweight RAD external account summary checks in the same pytest session.",
    )
    parser.addoption("--run-remote", action="store_true", default=False, help="Run remote console tests.")
    parser.addoption("--run-alarm-delete", action="store_true", default=False, help="Run history alarm delete tests.")
    parser.addoption(
        "--archive-allure",
        action="store_true",
        default=False,
        help="Archive raw Allure results into reports/<EMS version>/allure-results_<timestamp>.",
    )
    parser.addoption(
        "--generate-allure-html",
        action="store_true",
        default=False,
        help="Generate an Allure HTML report at session finish. Implies --archive-allure.",
    )


def pytest_configure(config: pytest.Config) -> None:
    ensure_report_dirs(config)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    run_auth_matrix = config.getoption("--auth-matrix")
    if not config.getoption("--run-remote"):
        skip_remote = pytest.mark.skip(reason="remote console tests require --run-remote")
        for item in items:
            if "remoteconsole" in item.keywords:
                item.add_marker(skip_remote)
    if not config.getoption("--run-alarm-delete"):
        skip_alarm_delete = pytest.mark.skip(reason="history alarm delete tests require --run-alarm-delete")
        for item in items:
            if "alarm_delete" in item.keywords:
                item.add_marker(skip_alarm_delete)
    if not run_auth_matrix:
        skip_auth_matrix = pytest.mark.skip(reason="RAD external summary tests require --auth-matrix")
        for item in items:
            if "authmatrix" in item.keywords:
                item.add_marker(skip_auth_matrix)
    for item in items:
        if "authmatrix" in item.keywords:
            if run_auth_matrix:
                case = RAD_AUTH_MATRIX_CASES.get(item.name)
                if case is not None:
                    register_node_case(item.nodeid, case[0], case[1])
            continue
        role = None
        if "readonly" in item.keywords:
            role = "readonly"
        elif "noaccess" in item.keywords:
            role = "noaccess"
        register_permission_role(item.nodeid, role)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.when == "call":
        record_result(report.nodeid, report.outcome, report.duration)
        return
    if report.when != "setup" or report.outcome not in {"failed", "skipped"}:
        return
    record_result(report.nodeid, report.outcome, report.duration)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    try:
        env_config = load_environment(
            node=session.config.getoption("--ems-node"),
            auth_profile=session.config.getoption("--auth-profile"),
        )
        txt_path, allure_results, allure_html = write_reports(session.config, env_config)
        terminal = session.config.pluginmanager.get_plugin("terminalreporter")
        if terminal:
            terminal.write_line(f"EMS txt report: {txt_path}")
            terminal.write_line(f"EMS allure results: {allure_results}")
            if allure_html:
                terminal.write_line(f"EMS allure report: {allure_html}")
            elif _option_or_env(session.config, "generate_allure_html", "EMS_GENERATE_ALLURE_HTML"):
                terminal.write_line("EMS allure report: allure CLI not found or generation failed.")
            else:
                terminal.write_line("EMS allure report: skipped; use --generate-allure-html when needed.")
    except Exception as error:
        terminal = session.config.pluginmanager.get_plugin("terminalreporter")
        if terminal:
            terminal.write_line(f"EMS report generation failed: {error}")


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
def env_config(request):
    return load_environment(
        node=request.config.getoption("--ems-node"),
        auth_profile=request.config.getoption("--auth-profile"),
    )


@pytest.fixture(scope="session")
def rad_env_config(request):
    return load_environment(
        node=request.config.getoption("--ems-node"),
        auth_profile="rad_external",
    )


@pytest.fixture(scope="session")
def api_client(env_config):
    return EmsApiClient(env_config)


@pytest.fixture
def cleanup_registry():
    registry = CleanupRegistry()
    try:
        yield registry
    finally:
        registry.run()


@pytest.fixture
def readwrite_session(api_client, env_config):
    response = api_client.login(env_config.credentials_for(SessionRole.READWRITE))
    assert_api_success(response)
    session_id = api_client.session_id_from(response)
    assert session_id, f"Login succeeded but no sessionid was returned: {format_response_summary(response)}"
    try:
        yield session_id
    finally:
        api_client.logout(session_id)


@pytest.fixture
def readonly_session(api_client, env_config):
    response = api_client.login(env_config.credentials_for(SessionRole.READONLY))
    assert_api_success(response)
    session_id = api_client.session_id_from(response)
    assert session_id, f"Login succeeded but no sessionid was returned: {format_response_summary(response)}"
    try:
        yield session_id
    finally:
        api_client.logout(session_id)


@pytest.fixture
def noaccess_session(api_client, env_config):
    response = api_client.login(env_config.credentials_for(SessionRole.NOACCESS))
    assert_api_success(response)
    session_id = api_client.session_id_from(response)
    assert session_id, f"Login succeeded but no sessionid was returned: {format_response_summary(response)}"
    try:
        yield session_id
    finally:
        api_client.logout(session_id)


@pytest.fixture
def rad_readwrite_session(api_client, rad_env_config):
    response = api_client.login(rad_env_config.readwrite)
    assert_api_success(response)
    session_id = api_client.session_id_from(response)
    assert session_id, f"Login succeeded but no sessionid was returned: {format_response_summary(response)}"
    try:
        yield session_id
    finally:
        api_client.logout(session_id)


@pytest.fixture
def rad_readonly_session(api_client, rad_env_config):
    response = api_client.login(rad_env_config.readonly)
    assert_api_success(response)
    session_id = api_client.session_id_from(response)
    assert session_id, f"Login succeeded but no sessionid was returned: {format_response_summary(response)}"
    try:
        yield session_id
    finally:
        api_client.logout(session_id)


@pytest.fixture
def rad_noaccess_session(api_client, rad_env_config):
    response = api_client.login(rad_env_config.noaccess)
    assert_api_success(response)
    session_id = api_client.session_id_from(response)
    assert session_id, f"Login succeeded but no sessionid was returned: {format_response_summary(response)}"
    try:
        yield session_id
    finally:
        api_client.logout(session_id)


def _option_or_env(config: pytest.Config, option_name: str, env_name: str) -> bool:
    return bool(config.getoption(option_name)) or os.environ.get(env_name, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
