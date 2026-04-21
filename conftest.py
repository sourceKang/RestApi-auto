from __future__ import annotations

import pytest

from clients import EmsApiClient
from configs import load_environment
from models.api import SessionRole
from utils.assertions import assert_api_success
from utils.cleanup import CleanupRegistry
from utils.reporting import ensure_report_dirs, record_result, write_reports


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--run-remote", action="store_true", default=False, help="Run remote console tests.")
    parser.addoption("--run-alarm-delete", action="store_true", default=False, help="Run history alarm delete tests.")


def pytest_configure(config: pytest.Config) -> None:
    ensure_report_dirs(config)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
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
        env_config = load_environment()
        txt_path, allure_results, allure_html = write_reports(session.config, env_config)
        terminal = session.config.pluginmanager.get_plugin("terminalreporter")
        if terminal:
            terminal.write_line(f"EMS txt report: {txt_path}")
            terminal.write_line(f"EMS allure results: {allure_results}")
            if allure_html:
                terminal.write_line(f"EMS allure report: {allure_html}")
            else:
                terminal.write_line("EMS allure report: allure CLI not found; raw allure results were archived.")
    except Exception as error:
        terminal = session.config.pluginmanager.get_plugin("terminalreporter")
        if terminal:
            terminal.write_line(f"EMS report generation failed: {error}")


@pytest.fixture(scope="session")
def env_config():
    return load_environment()


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
    assert session_id, f"Login succeeded but no sessionid was returned: {response.json!r}"
    try:
        yield session_id
    finally:
        api_client.logout(session_id)


@pytest.fixture
def readonly_session(api_client, env_config):
    response = api_client.login(env_config.credentials_for(SessionRole.READONLY))
    assert_api_success(response)
    session_id = api_client.session_id_from(response)
    assert session_id, f"Login succeeded but no sessionid was returned: {response.json!r}"
    try:
        yield session_id
    finally:
        api_client.logout(session_id)


@pytest.fixture
def noaccess_session(api_client, env_config):
    response = api_client.login(env_config.credentials_for(SessionRole.NOACCESS))
    assert_api_success(response)
    session_id = api_client.session_id_from(response)
    assert session_id, f"Login succeeded but no sessionid was returned: {response.json!r}"
    try:
        yield session_id
    finally:
        api_client.logout(session_id)
