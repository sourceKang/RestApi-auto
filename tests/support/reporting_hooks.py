from __future__ import annotations

import threading
import time

import pytest

from clients.ssh_cli import close_ssh_session_pools
from tests.support.options import option_or_env
from config_loader import load_environment
from utils.reporting import ensure_report_dirs, ensure_worker_report_dirs, record_result, write_reports


_HEARTBEAT_STOP: threading.Event | None = None
_HEARTBEAT_THREAD: threading.Thread | None = None


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    if is_xdist_worker(config):
        ensure_worker_report_dirs(config)
        return
    ensure_report_dirs(config)


def pytest_sessionstart(session: pytest.Session) -> None:
    if is_xdist_worker(session.config):
        return
    if _neox_xdist_heartbeat_enabled(session.config):
        _start_neox_xdist_heartbeat(session.config)

def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.when == "call":
        record_result(report.nodeid, report.outcome, report.duration)
        return
    if report.when != "setup" or report.outcome not in {"failed", "skipped"}:
        return
    record_result(report.nodeid, report.outcome, report.duration)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    _stop_neox_xdist_heartbeat()
    close_ssh_session_pools()
    if is_xdist_worker(session.config):
        return
    try:
        env_config = load_environment(
            node=session.config.getoption("--ems-node"),
            auth_profile=session.config.getoption("--auth-profile"),
        )
        txt_path, html_summary, allure_results, allure_html, integrated_html = write_reports(session.config, env_config)
        terminal = session.config.pluginmanager.get_plugin("terminalreporter")
        if terminal:
            if integrated_html:
                terminal.write_line(f"EMS HTML report: {integrated_html}")
                terminal.write_line(f"EMS html summary (legacy): {html_summary}")
            else:
                terminal.write_line(f"EMS HTML report: {html_summary}")
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


def is_xdist_worker(config: pytest.Config) -> bool:
    return hasattr(config, "workerinput")


def _neox_xdist_heartbeat_enabled(config: pytest.Config) -> bool:
    return str(config.getoption("--neox-parallel-mode", default="off") or "off").lower() != "off"


def _start_neox_xdist_heartbeat(config: pytest.Config) -> None:
    global _HEARTBEAT_STOP, _HEARTBEAT_THREAD
    if _HEARTBEAT_THREAD and _HEARTBEAT_THREAD.is_alive():
        return
    stop_event = threading.Event()
    _HEARTBEAT_STOP = stop_event
    terminal = config.pluginmanager.get_plugin("terminalreporter")

    def write_line(message: str) -> None:
        if terminal:
            terminal.write_line(message)

    write_line("[neox-xdist-heartbeat] enabled")

    def emit_heartbeat() -> None:
        started = time.monotonic()
        while not stop_event.wait(5):
            elapsed = int(time.monotonic() - started)
            write_line(f"[neox-xdist-heartbeat] still running after {elapsed}s")

    _HEARTBEAT_THREAD = threading.Thread(target=emit_heartbeat, name="neox-xdist-heartbeat", daemon=True)
    _HEARTBEAT_THREAD.start()


def _stop_neox_xdist_heartbeat() -> None:
    global _HEARTBEAT_STOP, _HEARTBEAT_THREAD
    if _HEARTBEAT_STOP is not None:
        _HEARTBEAT_STOP.set()
    if _HEARTBEAT_THREAD is not None:
        _HEARTBEAT_THREAD.join(timeout=1)
    _HEARTBEAT_STOP = None
    _HEARTBEAT_THREAD = None