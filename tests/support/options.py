from __future__ import annotations

import os

import pytest

from config_loader.neox_parallel import (  # re-exported for pytest glue and existing imports
    neox_parallel_auth_profile_for_worker,
    validate_neox_parallel_settings,
    xdist_worker_count,
)


FULL_TESTCASE_INCLUDED_OPTIONS = {
    "--auth-matrix",
    "--run-remote",
    "--run-alarm-delete",
    "--run-neox-config",
    "--run-neox-ont-error",
    "--run-live-swagger-check",
}

SESSION_CACHE_MODES = ("off", "on")


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
        help="Select auth profile from configs/auth_accounts.yaml, for example default or ems_local_rw2.",
    )
    parser.addoption(
        "--session-cache-mode",
        action="store",
        choices=SESSION_CACHE_MODES,
        default=os.environ.get("EMS_SESSION_CACHE_MODE", "on").strip().lower(),
        help=(
            "Control process-local role session reuse. off preserves per-test login/logout; "
            "on reuses sessions and proactively refreshes them before the 600-second lifetime."
        ),
    )
    parser.addoption(
        "--auth-matrix",
        action="store_true",
        default=False,
        help="Also run lightweight RAD external account summary checks in the same pytest session.",
    )
    parser.addoption(
        "--run-full-testcases",
        action="store_true",
        default=False,
        help=(
            "Run the official full testcase suite by enabling auth matrix, remote console, "
            "alarm delete, NeoX config, NeoX ONT error, and live Swagger checks."
        ),
    )
    parser.addoption(
        "--formal-testcases-only",
        action="store_true",
        default=False,
        help="Collect formal DUT/API testcases without enabling optional destructive or mutating suites.",
    )
    parser.addoption("--run-remote", action="store_true", default=False, help="Run remote console tests.")
    parser.addoption("--run-alarm-delete", action="store_true", default=False, help="Run history alarm delete tests.")
    parser.addoption(
        "--keep-ont-service-for-manual-check",
        action="store_true",
        default=False,
        help="Keep the temporary ONT service/profile graph after the run for explicit manual inspection.",
    )
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
        default=os.environ.get("NEOX_SWAGGER_API_DOCS_URL"),
        help=(
            "Live NeoX Swagger /v3/api-docs URL used with --run-live-swagger-check. "
            "Defaults to <rest_api_url>/v3/api-docs of the selected EMS target."
        ),
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
        "--neox-parallel-mode",
        action="store",
        choices=("off", "conservative", "resource"),
        default=os.environ.get("NEOX_PARALLEL_MODE", "off"),
        help=(
            "NeoX xdist grouping mode. off keeps current serial behavior; conservative groups all NeoX "
            "config/profile cases together; resource groups GE/NNI/VLAN/ONT/profile resources separately."
        ),
    )
    parser.addoption(
        "--neox-parallel-auth-profiles",
        action="store",
        default=os.environ.get("NEOX_PARALLEL_AUTH_PROFILES", ""),
        help=(
            "Comma-separated auth profile names assigned to xdist workers when --neox-parallel-mode is not off. "
            "Example: default,ems_local_rw2 assigns gw0=default and gw1=ems_local_rw2."
        ),
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
    parser.addoption(
        "--skip-integrated-evidence-report",
        action="store_true",
        default=False,
        help="Skip the merged HTML evidence report generated from txt report and raw Allure attachments.",
    )


def neox_parallel_worker_auth_profile(config: pytest.Config) -> str | None:
    return neox_parallel_auth_profile_for_worker(
        selected_auth_profile=config.getoption("--auth-profile"),
        parallel_mode=str(config.getoption("--neox-parallel-mode") or "off"),
        auth_profiles=str(config.getoption("--neox-parallel-auth-profiles") or ""),
        worker_id=os.environ.get("PYTEST_XDIST_WORKER"),
    )


def session_cache_enabled(config: pytest.Config) -> bool:
    return str(config.getoption("--session-cache-mode") or "on").strip().lower() == "on"


def option_or_env(config: pytest.Config, option_name: str, env_name: str) -> bool:
    return bool(config.getoption(option_name)) or os.environ.get(env_name, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def option_or_full_testcases(config: pytest.Config, option_name: str) -> bool:
    if option_name in FULL_TESTCASE_INCLUDED_OPTIONS and config.getoption("--run-full-testcases"):
        return True
    return bool(config.getoption(option_name))
