from __future__ import annotations

import os

import pytest


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


def option_or_env(config: pytest.Config, option_name: str, env_name: str) -> bool:
    return bool(config.getoption(option_name)) or os.environ.get(env_name, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
