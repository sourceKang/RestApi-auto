from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest


pytestmark = pytest.mark.offline

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("models", "config_loader", "utils", "cases", "clients", "services", "tools", "tests")
SLEEP_MODULES = {"time", "asyncio"}

# Rule (docs/engineering-guidelines.md): do not stand in for async EMS/DUT state with a fixed
# sleep. A sleep is accepted without registration only when it is
#   - polling: called inside a loop that can end (non-constant `while`, or return/break/raise)
#     and whose body reads something (a call other than sleep and time.*), or
#   - injection: `sleeper=time.sleep` as a default argument (outside tests/test_*.py).
# Test modules (tests/test_*.py) must not reference sleep at all; helpers live in tests/support.
# Everything else is listed below with its count, reason and removal condition.


@dataclass(frozen=True)
class Known:
    count: int
    kind: str
    reason: str
    remove_when: str


KNOWN_SLEEPS: dict[tuple[str, str], Known] = {
    ("clients/ems_api_client.py", "EmsApiClient._pace"): Known(
        1, "rate-limit-pacing", "ems.min_request_interval spacing between EMS requests", "never; throttling, not state"
    ),
    ("clients/ssh_cli.py", "SshCliClient._read_available"): Known(
        1, "cli-stream-read", "SSH shell has no completion signal; waits for the first output burst", "CLI reads get a prompt-based end marker"
    ),
    ("services/inventory/service.py", "InventoryService.wait_for_ont_service_state"): Known(
        1, "pre-poll-settle", "caller-supplied initial_delay (30 s) before polling; reason undocumented", "regression with initial_delay=0 shows no transient Fail (R-SLP)"
    ),
    ("services/inventory/service.py", "InventoryService.wait_for_ont_inventory"): Known(
        1, "pre-poll-settle", "caller-supplied initial_delay (15 s) before polling; reason undocumented", "regression with initial_delay=0 shows no transient Fail (R-SLP)"
    ),
    ("services/provision/service.py", "ProvisionService.wait_for_ont_service_state"): Known(
        1, "pre-poll-settle", "caller-supplied initial_delay before polling; reason undocumented", "regression with initial_delay=0 shows no transient Fail (R-SLP)"
    ),
    ("services/session/service.py", "UserSessionService._verify_readwrite_absolute_lifetime"): Known(
        1, "time-under-test", "the absolute session lifetime itself is the behavior under test", "never"
    ),
    ("tests/support/pacing.py", "pause_between_cases"): Known(
        1, "rate-limit-pacing", "opt-in --neox-*-delay-seconds cooldown between cases", "never; default 0"
    ),
    ("tests/test_session_manager.py", "FakeApiClient.login"): Known(
        1, "fake-latency", "keeps concurrent cache misses overlapping so single-login is exercised", "a deterministic overlap without timing is found"
    ),
}


@dataclass(frozen=True)
class SleepUse:
    path: str
    line: int
    qualname: str
    kind: str  # polling, injection or fixed


def _sleep_aliases(tree: ast.Module) -> tuple[set[str], set[str]]:
    modules: set[str] = set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in SLEEP_MODULES:
                    modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module in SLEEP_MODULES:
            for alias in node.names:
                if alias.name == "sleep":
                    names.add(alias.asname or alias.name)
    return modules, names


def _is_sleep_ref(node: ast.AST, modules: set[str], names: set[str]) -> bool:
    if isinstance(node, ast.Attribute) and node.attr == "sleep" and isinstance(node.ctx, ast.Load):
        return isinstance(node.value, ast.Name) and node.value.id in modules
    return isinstance(node, ast.Name) and node.id in names and isinstance(node.ctx, ast.Load)


def _is_time_call(call: ast.Call, modules: set[str]) -> bool:
    func = call.func
    return isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in modules


def _loop_reads_state(loop: ast.While | ast.For, modules: set[str], names: set[str]) -> bool:
    can_end = isinstance(loop, ast.While) and not isinstance(loop.test, ast.Constant)
    reads = False
    for node in ast.walk(ast.Module(body=loop.body, type_ignores=[])):
        if isinstance(node, (ast.Return, ast.Break, ast.Raise)):
            can_end = True
        if isinstance(node, ast.Call) and not _is_sleep_ref(node.func, modules, names) and not _is_time_call(node, modules):
            reads = True
    return can_end and reads


def scan_source(source: bytes, rel: str) -> list[SleepUse]:
    tree = ast.parse(source, filename=rel)
    modules, names = _sleep_aliases(tree)
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    defaults = {
        id(value)
        for node in ast.walk(tree)
        if isinstance(node, ast.arguments)
        for value in [*node.defaults, *node.kw_defaults]
        if value is not None
    }
    uses = []
    for node in ast.walk(tree):
        if not _is_sleep_ref(node, modules, names):
            continue
        scope: list[str] = []
        loop = None
        current = parents.get(node)
        while current is not None:
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                if not isinstance(current, ast.Lambda):
                    scope.append(current.name)
            elif loop is None and not scope and isinstance(current, (ast.While, ast.For)):
                loop = current
            current = parents.get(current)
        parent = parents.get(node)
        if id(node) in defaults:
            kind = "injection"
        elif isinstance(parent, ast.Call) and parent.func is node and loop is not None and _loop_reads_state(loop, modules, names):
            kind = "polling"
        else:
            kind = "fixed"
        uses.append(SleepUse(rel, node.lineno, ".".join(reversed(scope)) or "<module>", kind))
    return sorted(uses, key=lambda use: use.line)


def scan_project() -> list[SleepUse]:
    files = [ROOT / "conftest.py"]
    for package in PACKAGES:
        files.extend(path for path in (ROOT / package).rglob("*.py") if "__pycache__" not in path.parts)
    uses = []
    for path in sorted(files):
        uses.extend(scan_source(path.read_bytes(), path.relative_to(ROOT).as_posix()))
    return uses


def _needs_registration(use: SleepUse) -> bool:
    is_test_module = use.path.startswith("tests/test_")
    return is_test_module or use.kind == "fixed"


def test_fixed_sleeps_are_registered_with_exact_counts():
    counts = Counter((use.path, use.qualname) for use in scan_project() if _needs_registration(use))
    unregistered = sorted(f"{path}::{name} x{count}" for (path, name), count in counts.items() if (path, name) not in KNOWN_SLEEPS)
    miscounted = sorted(
        f"{path}::{name} found {counts[(path, name)]}, registered {known.count}"
        for (path, name), known in KNOWN_SLEEPS.items()
        if counts.get((path, name), 0) not in {0, known.count}
    )

    assert unregistered == [], (
        "Fixed sleep outside a polling loop (poll the state instead; see docs/engineering-guidelines.md):\n"
        + "\n".join(unregistered)
    )
    assert miscounted == [], "\n".join(miscounted)


def test_registered_sleeps_still_exist():
    counts = Counter((use.path, use.qualname) for use in scan_project() if _needs_registration(use))
    stale = sorted(f"{path}::{name}" for path, name in KNOWN_SLEEPS if (path, name) not in counts)

    assert stale == [], f"Removed sleeps: delete them from KNOWN_SLEEPS: {stale}"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import time\ndef f(read):\n    while True:\n        if read():\n            return\n        time.sleep(1)\n", ["polling"]),
        ("import time\ndef f(deadline):\n    while time.monotonic() < deadline:\n        time.sleep(5)\n", ["fixed"]),
        ("import time\ndef f(read):\n    read()\n    time.sleep(2)\n", ["fixed"]),
        ("import time\ndef f(read):\n    for _ in range(3):\n        read()\n        time.sleep(1)\n", ["fixed"]),
        ("import time\ndef f(read, sleeper=time.sleep):\n    sleeper(1)\n", ["injection"]),
        ("from time import sleep as pause\ndef f():\n    pause(1)\n", ["fixed"]),
        ("import asyncio\nasync def f():\n    await asyncio.sleep(1)\n", ["fixed"]),
        ("import time\ndef f(monkeypatch):\n    monkeypatch.setattr(time, 'sleep', lambda s: None)\n", []),
    ],
)
def test_scanner_classifies_sleep_forms(source, expected):
    assert [use.kind for use in scan_source(source.encode(), "services/sample.py")] == expected
