from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.offline

ROOT = Path(__file__).resolve().parents[1]
GUARD_MESSAGE = "DUT preflight must not run for this selection"

# Loaded with `-p preflight_guard`; replaces the preflight before collection so the
# child pytest fails loudly instead of connecting to EMS or the DUT.
GUARD_PLUGIN = f'''
import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_collection(session):
    from tests.support import preflight

    def fail(*args, **kwargs):
        raise RuntimeError("{GUARD_MESSAGE}")

    preflight.run_startup_preflight = fail
'''


def _collect(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    (tmp_path / "preflight_guard.py").write_text(GUARD_PLUGIN, encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(tmp_path), str(ROOT)]))
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            # test_session.py holds DUT-dependent `session` items; the other file is offline.
            "tests/test_session.py",
            "tests/test_session_cache_options.py",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "preflight_guard",
            # Keep the child's Allure output out of reports/.allure-results-current.
            f"--alluredir={tmp_path / 'allure'}",
            *args,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


def test_offline_selection_does_not_run_dut_preflight(tmp_path):
    result = _collect(tmp_path, "-m", "offline")

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert GUARD_MESSAGE not in output


def test_dut_selection_still_runs_dut_preflight(tmp_path):
    # Control: proves the guard is active, so the offline case above is not vacuous.
    result = _collect(tmp_path)

    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert GUARD_MESSAGE in output
