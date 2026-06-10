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
        "--run-neox-config",
        action="store_true",
        default=False,
        help="Run NeoX configuration tests that may mutate NODE3 device state.",
    )
    parser.addoption(
        "--run-neox-probe",
        action="store_true",
        default=False,
        help="Run exploratory NeoX probe tests outside the official 80-case plan.",
    )
    parser.addoption(
        "--run-neox-ont-error",
        action="store_true",
        default=False,
        help="Run the slow NeoX ONT error matrix EMS1-7133. Requires --run-neox-config.",
    )
    parser.addoption(
        "--run-live-swagger-check",
        action="store_true",
        default=False,
        help="Run read-only live Swagger /v3/api-docs comparison checks.",
    )
    parser.addoption(
        "--neox-swagger-api-docs-url",
        action="store",
        default=os.environ.get(
            "NEOX_SWAGGER_API_DOCS_URL",
            "https://192.168.128.100:9116/netatlasemsapi/v3/api-docs",
        ),
        help="Live NeoX Swagger /v3/api-docs URL used with --run-live-swagger-check.",
    )
    parser.addoption(
        "--neox-config-delay-seconds",
        action="store",
        type=float,
        default=float(os.environ.get("NEOX_CONFIG_DELAY_SECONDS", "0") or 0),
        help="Delay after each NeoX config test case. Can also be set with NEOX_CONFIG_DELAY_SECONDS.",
    )
    parser.addoption(
        "--skip-neox-cli-verify",
        action="store_true",
        default=False,
        help="Run NeoX config REST API workflows without SSH CLI verification.",
    )
    parser.addoption(
        "--neox-profile-delay-seconds",
        action="store",
        type=float,
        default=float(os.environ.get("NEOX_PROFILE_DELAY_SECONDS", "0") or 0),
        help="Delay between NeoX profile test cases. Can also be set with NEOX_PROFILE_DELAY_SECONDS.",
    )
    parser.addoption(
        "--skip-dut-preflight",
        action="store_true",
        default=False,
        help="Do not pre-check DUT readiness before collecting DUT-dependent API tests.",
    )
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
