"""Fail-fast environment check for this REST API automation project.

Run this before pytest on a new machine. It answers one question only:
"is this machine able to run the suite, and if not, exactly what is missing?"

    python tools\check_environment.py
    python tools\check_environment.py --node NODE3 --auth-profile default
    python tools\check_environment.py --node NODE3 --no-network

Checks, in order:

    1. Python version and interpreter
    2. Required packages from requirements.txt
    3. Config files present, parseable, and free of placeholder values
    4. Auth profile resolves to real usernames and passwords
    5. DUT target resolves (slot / port / ONT / GE)
    6. OpenAPI YAML root availability (informational)
    7. Allure Commandline and Java (informational)
    8. Network: EMS REST endpoint reachable, DUT ping, DUT SSH port open

Exit code 0 when nothing is BLOCKING. Informational gaps report WARN and do
not change the exit code, because they only disable optional features.
"""

from __future__ import annotations

import argparse
import importlib.util
import platform
import re
import shutil
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MINIMUM_PYTHON = (3, 11)
CONFIG_DIR = PROJECT_ROOT / "configs"

# Values that mean "this file was never filled in for this machine".
PLACEHOLDER_PATTERN = re.compile(
    r"CHANGE_ME|REPLACE_WITH|example_readwrite|example_readonly|example_noaccess",
    re.IGNORECASE,
)

REQUIRED_MODULES = {
    "pytest": "pytest",
    "requests": "requests",
    "urllib3": "urllib3",
    "yaml": "PyYAML",
    "paramiko": "paramiko",
    "allure_pytest": "allure-pytest",
    "xdist": "pytest-xdist",
}

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


@dataclass
class Result:
    status: str
    title: str
    detail: str = ""
    hint: str = ""


class Report:
    def __init__(self) -> None:
        self.results: list[Result] = []

    def add(self, result: Result) -> Result:
        self.results.append(result)
        _print_result(result)
        return result

    @property
    def blocking(self) -> list[Result]:
        return [item for item in self.results if item.status == FAIL]

    @property
    def warnings(self) -> list[Result]:
        return [item for item in self.results if item.status == WARN]


def main() -> int:
    args = _parse_args()
    report = Report()

    _section("1. Python runtime")
    check_python(report)

    _section("2. Python packages")
    check_packages(report)

    _section("3. Configuration files")
    env_config = check_configuration(report, node=args.node, auth_profile=args.auth_profile)

    _section("4. OpenAPI YAML source")
    check_openapi_root(report)

    _section("5. Allure report tooling")
    check_allure_tooling(report)

    if args.no_network:
        _section("6. Network reachability")
        report.add(Result(WARN, "Network checks skipped", "--no-network was given."))
    else:
        _section("6. Network reachability")
        check_network(report, env_config, ping_timeout_ms=args.ping_timeout_ms)

    return _summarize(report)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check that this machine can run the REST API automation suite.",
    )
    parser.add_argument("--node", default=None, help="DUT node key to validate, for example NODE3.")
    parser.add_argument("--auth-profile", default=None, help="Auth profile to validate, for example default.")
    parser.add_argument("--no-network", action="store_true", help="Skip EMS/DUT reachability checks.")
    parser.add_argument("--ping-timeout-ms", type=int, default=2000, help="Per-ping timeout in milliseconds.")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# 1. Python runtime
# ---------------------------------------------------------------------------


def check_python(report: Report) -> None:
    version = sys.version_info
    text = f"{version.major}.{version.minor}.{version.micro} ({platform.python_implementation()})"
    if version[:2] >= MINIMUM_PYTHON:
        report.add(Result(PASS, "Python version", text))
    else:
        report.add(
            Result(
                FAIL,
                "Python version",
                f"{text} is older than {MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]}",
                "utils/cleanup.py uses ExceptionGroup, which needs Python 3.11 or newer.",
            )
        )

    report.add(Result(PASS, "Interpreter", sys.executable))

    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if in_venv:
        report.add(Result(PASS, "Virtual environment", sys.prefix))
    else:
        report.add(
            Result(
                WARN,
                "Virtual environment",
                "Running against the system interpreter.",
                r"Create one with: python -m venv .venv",
            )
        )


# ---------------------------------------------------------------------------
# 2. Packages
# ---------------------------------------------------------------------------


def check_packages(report: Report) -> None:
    missing: list[str] = []
    for module_name, distribution in REQUIRED_MODULES.items():
        if importlib.util.find_spec(module_name) is None:
            missing.append(distribution)
    if missing:
        report.add(
            Result(
                FAIL,
                "Required packages",
                "Missing: " + ", ".join(sorted(missing)),
                r"Install with: python -m pip install -r requirements.txt",
            )
        )
    else:
        report.add(Result(PASS, "Required packages", ", ".join(sorted(REQUIRED_MODULES.values()))))


# ---------------------------------------------------------------------------
# 3. Configuration
# ---------------------------------------------------------------------------


def check_configuration(report: Report, node: str | None, auth_profile: str | None) -> Any | None:
    tracked_files = {
        "ems.yaml": True,
        "auth_accounts.yaml": True,
        "hardware_matrix.yaml": True,
        "test_targets.yaml": True,
    }
    for name in tracked_files:
        path = CONFIG_DIR / name
        if path.exists():
            report.add(Result(PASS, f"configs/{name}", "present"))
        else:
            report.add(Result(FAIL, f"configs/{name}", "missing", "The repository checkout is incomplete."))

    for name in ("auth_accounts.local.yaml", "test_targets.local.yaml"):
        path = CONFIG_DIR / name
        example = CONFIG_DIR / f"{name}.example"
        if path.exists():
            report.add(Result(PASS, f"configs/{name}", "present (machine-local values in use)"))
        else:
            report.add(
                Result(
                    WARN,
                    f"configs/{name}",
                    "not present; the sanitized tracked file will be used",
                    f"Copy {example.name} to {name} and fill in the real lab values."
                    if example.exists()
                    else "Create it from the tracked file and fill in the real lab values.",
                )
            )

    _check_placeholders(report)

    return _check_resolved_environment(report, node=node, auth_profile=auth_profile)


def _check_placeholders(report: Report) -> None:
    """Report placeholder values that are actually reachable at run time."""

    for name in ("auth_accounts", "test_targets"):
        local = CONFIG_DIR / f"{name}.local.yaml"
        tracked = CONFIG_DIR / f"{name}.yaml"
        effective = local if local.exists() else tracked
        if not effective.exists():
            continue
        try:
            text = effective.read_text(encoding="utf-8")
        except OSError as error:
            report.add(Result(FAIL, f"Read configs/{effective.name}", str(error)))
            continue
        hits = sorted({match.group(0) for match in PLACEHOLDER_PATTERN.finditer(text)})
        if hits:
            report.add(
                Result(
                    WARN,
                    f"Placeholders in configs/{effective.name}",
                    ", ".join(hits),
                    "Placeholders resolve only if the matching environment variables are set. "
                    "The auth profile check below shows whether they actually resolved.",
                )
            )
        else:
            report.add(Result(PASS, f"configs/{effective.name}", "no placeholder values"))


def _check_resolved_environment(report: Report, node: str | None, auth_profile: str | None) -> Any | None:
    try:
        from config_loader.settings import ConfigError, load_environment
    except Exception as error:  # pragma: no cover - import failure is already fatal
        report.add(Result(FAIL, "Import config_loader", str(error)))
        return None

    try:
        env_config = load_environment(node=node, auth_profile=auth_profile)
    except ConfigError as error:
        report.add(
            Result(
                FAIL,
                "Resolve environment",
                str(error),
                "Check configs/test_targets*.yaml and configs/auth_accounts*.yaml for this machine.",
            )
        )
        return None
    except Exception as error:
        report.add(Result(FAIL, "Resolve environment", f"{type(error).__name__}: {error}"))
        return None

    report.add(
        Result(
            PASS,
            "Resolve environment",
            f"node={env_config.dut.node_key} chassis={env_config.dut.chassis} "
            f"profile={env_config.auth_profile} ems={env_config.base_url}",
        )
    )
    report.add(
        Result(
            PASS,
            "DUT target",
            f"ip={env_config.dut.device_ip} ont=slot {env_config.dut.slot_id}/port {env_config.dut.port_id}/"
            f"ont {env_config.dut.ont_id} ge=slot {env_config.dut.ge_slot_id}/port {env_config.dut.ge_port_id}",
        )
    )

    _check_credentials(report, env_config)
    return env_config


def _check_credentials(report: Report, env_config: Any) -> None:
    roles = (
        ("readwrite", env_config.readwrite),
        ("readonly", env_config.readonly),
        ("noaccess", env_config.noaccess),
    )
    unresolved: list[str] = []
    for role, credentials in roles:
        if not credentials.username or PLACEHOLDER_PATTERN.search(credentials.username):
            unresolved.append(f"{role}.username")
        if not credentials.password or PLACEHOLDER_PATTERN.search(credentials.password):
            unresolved.append(f"{role}.password")

    if unresolved:
        report.add(
            Result(
                FAIL,
                "EMS accounts",
                "Still placeholder or empty: " + ", ".join(unresolved),
                "Fill configs/auth_accounts.local.yaml, or export the matching EMS_AUTH_* variables. "
                "EMS login will fail and every DUT test will be skipped by the preflight.",
            )
        )
    else:
        usernames = ", ".join(f"{role}={credentials.username}" for role, credentials in roles)
        report.add(Result(PASS, "EMS accounts", usernames))

    ssh_username = env_config.dut.ssh_username
    ssh_password = env_config.dut.ssh_password
    if not ssh_username or not ssh_password or PLACEHOLDER_PATTERN.search(ssh_password or ""):
        report.add(
            Result(
                WARN,
                "DUT SSH credentials",
                "Still placeholder or empty.",
                "CLI verification and the target sync preflight need real SSH values in "
                "configs/test_targets.local.yaml, or DUT_SSH_* environment variables.",
            )
        )
    else:
        report.add(Result(PASS, "DUT SSH credentials", f"user={ssh_username} host={env_config.dut.ssh_host}"))


# ---------------------------------------------------------------------------
# 4. OpenAPI source
# ---------------------------------------------------------------------------


def check_openapi_root(report: Report) -> None:
    # Load the module by file path so this check keeps working even when the
    # rest of the cases package cannot import yet.
    module_path = PROJECT_ROOT / "cases" / "openapi_contract.py"
    if not module_path.exists():
        report.add(Result(FAIL, "cases/openapi_contract.py", "missing", "The repository checkout is incomplete."))
        return
    try:
        spec = importlib.util.spec_from_file_location("_check_openapi_contract", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        openapi_root: Callable[[], Path] = module.openapi_root
        openapi_root_available: Callable[[], bool] = module.openapi_root_available
        root_env = module.OPENAPI_ROOT_ENV
    except Exception as error:
        report.add(Result(WARN, "OpenAPI contract module", f"{type(error).__name__}: {error}"))
        return

    root = openapi_root()
    if openapi_root_available():
        report.add(Result(PASS, "OpenAPI YAML root", str(root)))
    else:
        report.add(
            Result(
                WARN,
                "OpenAPI YAML root",
                f"{root} does not exist on this machine.",
                "The OpenAPI YAML files ship with the EMS firmware and are not in this repository. "
                f"Set ems.openapi_root in configs/ems.yaml or the {root_env} variable. "
                "Without it the OpenAPI YAML guard skips instead of running.",
            )
        )


# ---------------------------------------------------------------------------
# 5. Allure tooling
# ---------------------------------------------------------------------------


def check_allure_tooling(report: Report) -> None:
    allure = shutil.which("allure")
    local_wrapper = PROJECT_ROOT / ".codex-tools" / "bin" / "allure.cmd"
    if allure:
        report.add(Result(PASS, "Allure Commandline", allure))
    elif local_wrapper.exists():
        report.add(Result(PASS, "Allure Commandline", str(local_wrapper)))
    else:
        report.add(
            Result(
                WARN,
                "Allure Commandline",
                "not found",
                "--generate-allure-html silently produces no HTML without it. "
                "Install with: npm.cmd install -g allure-commandline (or choco/scoop). "
                "Raw Allure results from allure-pytest still work.",
            )
        )

    java = shutil.which("java")
    if java:
        report.add(Result(PASS, "Java runtime", java))
    else:
        report.add(
            Result(
                WARN,
                "Java runtime",
                "not found",
                "Allure Commandline needs Java to generate the HTML report.",
            )
        )


# ---------------------------------------------------------------------------
# 6. Network
# ---------------------------------------------------------------------------


def check_network(report: Report, env_config: Any | None, ping_timeout_ms: int) -> None:
    if env_config is None:
        report.add(Result(WARN, "Network checks skipped", "The environment could not be resolved."))
        return

    _check_ems_endpoint(report, env_config)
    _check_ping(report, env_config.dut.device_ip, "DUT ping", ping_timeout_ms)
    _check_tcp_port(report, env_config.dut.ssh_host, 22, "DUT SSH port 22")


def _check_ems_endpoint(report: Report, env_config: Any) -> None:
    url = env_config.base_url
    host, port = _split_host_port(url)
    if host and not _tcp_open(host, port, timeout=5.0):
        report.add(
            Result(
                FAIL,
                "EMS REST endpoint",
                f"Cannot open TCP {host}:{port}",
                "Check VPN, routing and firewall. Every API test fails without this.",
            )
        )
        return

    context = ssl.create_default_context()
    if not env_config.verify_tls:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    probe = f"{url}/v3/api-docs"
    try:
        with urllib.request.urlopen(probe, timeout=10, context=context) as response:
            code = response.getcode()
        report.add(Result(PASS, "EMS REST endpoint", f"{probe} -> HTTP {code}"))
    except urllib.error.HTTPError as error:
        # An HTTP error still proves the EMS answered.
        report.add(Result(PASS, "EMS REST endpoint", f"{probe} -> HTTP {error.code} (service responded)"))
    except Exception as error:
        report.add(
            Result(
                WARN,
                "EMS REST endpoint",
                f"TCP {host}:{port} is open but {probe} failed: {type(error).__name__}: {error}",
                "The port is reachable, so this is usually a TLS or path detail rather than a routing problem.",
            )
        )


def _check_ping(report: Report, target: str, title: str, timeout_ms: int) -> None:
    if not target:
        report.add(Result(WARN, title, "No address configured."))
        return
    if platform.system().casefold() == "windows":
        command = ["ping", "-n", "2", "-w", str(timeout_ms), target]
    else:
        command = ["ping", "-c", "2", "-W", str(max(1, timeout_ms // 1000)), target]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
    except FileNotFoundError:
        report.add(Result(WARN, title, "ping command not available on this machine."))
        return
    except subprocess.TimeoutExpired:
        report.add(Result(FAIL, title, f"{target} timed out."))
        return

    if completed.returncode == 0:
        report.add(Result(PASS, title, target))
    else:
        report.add(
            Result(
                FAIL,
                title,
                f"{target} did not answer (exit {completed.returncode}).",
                "tests/support/connectivity.py fails the test when this ping fails.",
            )
        )


def _check_tcp_port(report: Report, host: str, port: int, title: str) -> None:
    if not host:
        report.add(Result(WARN, title, "No host configured."))
        return
    if _tcp_open(host, port, timeout=5.0):
        report.add(Result(PASS, title, f"{host}:{port} open"))
    else:
        report.add(
            Result(
                WARN,
                title,
                f"{host}:{port} not reachable",
                "CLI verification and the target sync preflight need SSH. "
                "REST-only runs can use --skip-neox-cli-verify.",
            )
        )


def _tcp_open(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _split_host_port(url: str) -> tuple[str, int]:
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    host = parts.hostname or ""
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return host, port


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _section(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def _print_result(result: Result) -> None:
    print(f"  [{result.status}] {result.title}: {result.detail}" if result.detail else f"  [{result.status}] {result.title}")
    if result.hint and result.status != PASS:
        for line in _wrap(result.hint):
            print(f"         {line}")


def _wrap(text: str, width: int = 96) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _summarize(report: Report) -> int:
    print()
    print("=" * 72)
    blocking = report.blocking
    warnings = report.warnings
    if blocking:
        print(f"BLOCKING: {len(blocking)} check(s) must be fixed before running pytest.")
        for result in blocking:
            print(f"  - {result.title}: {result.detail}")
    else:
        print("No blocking problems. This machine can run pytest.")
    if warnings:
        print(f"Optional gaps: {len(warnings)} warning(s). Some features are unavailable but the suite runs.")
        for result in warnings:
            print(f"  - {result.title}: {result.detail}")
    print("=" * 72)
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
