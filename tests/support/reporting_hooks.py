from __future__ import annotations

import pytest

from tests.support.options import option_or_env
from config_loader import load_environment
from utils.reporting import ensure_report_dirs, record_result, write_reports


def pytest_configure(config: pytest.Config) -> None:
    ensure_report_dirs(config)


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
            elif option_or_env(session.config, "generate_allure_html", "EMS_GENERATE_ALLURE_HTML"):
                terminal.write_line("EMS allure report: allure CLI not found or generation failed.")
            else:
                terminal.write_line("EMS allure report: skipped; use --generate-allure-html when needed.")
    except Exception as error:
        terminal = session.config.pluginmanager.get_plugin("terminalreporter")
        if terminal:
            terminal.write_line(f"EMS report generation failed: {error}")
