from __future__ import annotations

import pytest

from tests.support.preflight import DutPreflightResult
from tools import run_multi_node


def test_parse_nodes_accepts_comma_separated_values():
    assert run_multi_node.parse_nodes("NODE1, NODE3,,NODE6") == ["NODE1", "NODE3", "NODE6"]


def test_build_node_plan_omits_neox_only_full_options_for_non_neox_node():
    plan = run_multi_node.build_node_plan(
        node="NODE1",
        pytest_args=["tests/test_inventory.py", "-q"],
        run_full_testcases=True,
        python_executable="python",
    )

    assert plan.chassis == "IES4204"
    assert not plan.is_neox
    assert "--run-full-testcases" not in plan.command
    assert "--run-neox-config" not in plan.command
    assert "--run-neox-ont-error" not in plan.command
    assert "--auth-matrix" in plan.command
    assert "--run-remote" in plan.command
    assert "--run-alarm-delete" in plan.command
    assert "--run-live-swagger-check" in plan.command
    assert "tests/test_inventory.py" in plan.command
    assert plan.omitted_options == ["--run-neox-config", "--run-neox-ont-error"]


def test_build_node_plan_keeps_full_option_for_neox_node():
    plan = run_multi_node.build_node_plan(
        node="NODE3",
        pytest_args=["tests/test_neox_config.py", "-q"],
        run_full_testcases=True,
        python_executable="python",
    )

    assert plan.chassis == "NeoX-03"
    assert plan.is_neox
    assert "--run-full-testcases" in plan.command
    assert "tests/test_neox_config.py" in plan.command
    assert plan.omitted_options == []


def test_build_node_plan_rejects_unsafe_per_node_xdist():
    with pytest.raises(ValueError, match="only supported for NeoX"):
        run_multi_node.build_node_plan(
            node="NODE1",
            pytest_args=["tests/test_inventory.py", "-n", "2"],
            run_full_testcases=False,
            python_executable="python",
        )

    with pytest.raises(ValueError, match="--dist loadgroup"):
        run_multi_node.build_node_plan(
            node="NODE3",
            pytest_args=[
                "tests/test_neox_config.py",
                "-n",
                "2",
                "--neox-parallel-mode",
                "resource",
                "--neox-parallel-auth-profiles",
                "default,ems_local_rw2",
            ],
            run_full_testcases=False,
            python_executable="python",
        )


def test_build_node_plan_accepts_grouped_neox_xdist_with_distinct_profiles():
    plan = run_multi_node.build_node_plan(
        node="NODE3",
        pytest_args=[
            "tests/test_neox_config.py",
            "-n2",
            "--dist=loadgroup",
            "--neox-parallel-mode=resource",
            "--neox-parallel-auth-profiles=default,ems_local_rw2",
        ],
        run_full_testcases=False,
        python_executable="python",
    )

    assert "-n2" in plan.command


def test_sanitize_pytest_args_drops_node_and_neox_options_for_non_neox_node():
    sanitized, omitted = run_multi_node.sanitize_pytest_args(
        ["--ems-node", "NODE3", "--run-neox-config", "--run-neox-ont-error", "-q"],
        is_neox=False,
    )

    assert sanitized == ["-q"]
    assert omitted == ["--ems-node", "--run-neox-config", "--run-neox-ont-error"]


def test_parse_report_paths_collects_pytest_report_artifacts():
    lines = [
        "EMS HTML report: D:\\RestApi auto\\reports\\demo_integrated.html",
        "EMS html summary (legacy): D:\\RestApi auto\\reports\\demo.html",
        "EMS txt report: D:\\RestApi auto\\reports\\demo.txt",
        "EMS allure results: D:\\RestApi auto\\reports\\allure-results_demo",
        "EMS allure report: skipped; use --generate-allure-html when needed.",
    ]

    paths = run_multi_node.parse_report_paths(lines)

    assert paths == {
        "integrated_html": "D:\\RestApi auto\\reports\\demo_integrated.html",
        "html_summary": "D:\\RestApi auto\\reports\\demo.html",
        "txt_report": "D:\\RestApi auto\\reports\\demo.txt",
        "allure_results": "D:\\RestApi auto\\reports\\allure-results_demo",
    }


def test_parse_pytest_summary_line_returns_last_terminal_summary():
    lines = [
        "some output",
        "============================= 22 passed in 1.72s =============================",
    ]

    assert run_multi_node.parse_pytest_summary_line(lines) == "22 passed in 1.72s"


def test_build_node_plan_tracks_auth_profile_for_runner_preflight():
    plan = run_multi_node.build_node_plan(
        node="NODE3",
        pytest_args=["--auth-profile", "ems_local_rw2"],
        run_full_testcases=False,
        python_executable="python",
    )

    assert plan.auth_profile == "ems_local_rw2"


def test_run_node_plan_skips_pytest_when_runner_preflight_fails(monkeypatch, tmp_path):
    plan = run_multi_node.NodePlan(
        node="NODE1",
        chassis="IES4204",
        is_neox=False,
        command=["python", "-m", "pytest"],
        omitted_options=[],
    )
    monkeypatch.setattr(
        run_multi_node,
        "run_startup_preflight",
        lambda node, auth_profile: DutPreflightResult(False, "DevStatus=4"),
    )

    class FailIfCalled:
        def __init__(self, *args, **kwargs):
            raise AssertionError("pytest should not be invoked when preflight fails")

    monkeypatch.setattr(run_multi_node.subprocess, "Popen", FailIfCalled)

    result = run_multi_node.run_node_plan(plan, tmp_path)

    assert result.returncode == 0
    assert result.skipped
    assert "DevStatus=4" in result.skip_reason
    assert "DevStatus=4" in (tmp_path / "NODE1.log").read_text(encoding="utf-8")


def test_run_node_plan_adds_skip_dut_preflight_after_runner_preflight(monkeypatch, tmp_path):
    plan = run_multi_node.NodePlan(
        node="NODE3",
        chassis="NeoX-03",
        is_neox=True,
        command=["python", "-m", "pytest", "tests/test_inventory.py"],
        omitted_options=[],
    )
    captured = {}
    monkeypatch.setattr(
        run_multi_node,
        "run_startup_preflight",
        lambda node, auth_profile: DutPreflightResult(True),
    )

    class FakeProcess:
        stdout = ["============================= 1 passed in 0.01s =============================\n"]

        def __init__(self, command, **kwargs):
            captured["command"] = command

        def wait(self):
            return 0

    monkeypatch.setattr(run_multi_node.subprocess, "Popen", FakeProcess)

    result = run_multi_node.run_node_plan(plan, tmp_path)

    assert "--skip-dut-preflight" in captured["command"]
    assert "--alluredir" in captured["command"]
    assert captured["command"][-1].endswith("NODE3_allure-current")
    assert "--skip-dut-preflight" in result.command
    assert "--alluredir" in result.command
    assert result.summary_line == "1 passed in 0.01s"


def test_build_node_plan_injects_auth_profile_override():
    plan = run_multi_node.build_node_plan(
        node="NODE1",
        pytest_args=["tests/test_inventory.py", "-q"],
        run_full_testcases=False,
        python_executable="python",
        auth_profile_override="ems_local_rw2",
    )

    assert plan.auth_profile == "ems_local_rw2"
    assert plan.command[:6] == ["python", "-m", "pytest", "--ems-node", "NODE1", "--auth-profile"]
    assert plan.command[6] == "ems_local_rw2"


def test_auth_profile_for_node_round_robins_profiles():
    profiles = ["default", "ems_local_rw2"]

    assert run_multi_node.auth_profile_for_node(profiles, 0) == "default"
    assert run_multi_node.auth_profile_for_node(profiles, 1) == "ems_local_rw2"
    assert run_multi_node.auth_profile_for_node(profiles, 2) == "default"


def test_run_node_plans_parallel_preserves_plan_order(monkeypatch, tmp_path):
    plans = [
        run_multi_node.NodePlan(
            node="NODE1",
            chassis="IES4204",
            is_neox=False,
            command=["python", "-m", "pytest"],
            omitted_options=[],
        ),
        run_multi_node.NodePlan(
            node="NODE3",
            chassis="NeoX-03",
            is_neox=True,
            command=["python", "-m", "pytest"],
            omitted_options=[],
        ),
    ]
    calls = []

    def fake_run_node_plan(plan, report_dir, *, preflight=True):
        calls.append((plan.node, preflight))
        return run_multi_node.NodeResult(
            node=plan.node,
            chassis=plan.chassis,
            is_neox=plan.is_neox,
            returncode=0,
            duration_seconds=0.1,
            command=plan.command,
            log_path=str(tmp_path / f"{plan.node}.log"),
            summary_line="1 passed in 0.01s",
            report_paths={},
            omitted_options=[],
        )

    monkeypatch.setattr(run_multi_node, "run_node_plan", fake_run_node_plan)

    results = run_multi_node.run_node_plans(plans, tmp_path, preflight=True, jobs=2)

    assert [result.node for result in results] == ["NODE1", "NODE3"]
    assert sorted(calls) == [("NODE1", True), ("NODE3", True)]

def test_run_node_plan_prints_preflight_progress(monkeypatch, tmp_path, capsys):
    plan = run_multi_node.NodePlan(
        node="NODE3",
        chassis="NeoX-03",
        is_neox=True,
        command=["python", "-m", "pytest"],
        omitted_options=[],
        auth_profile="ems_local_rw2",
    )
    monkeypatch.setattr(
        run_multi_node,
        "run_startup_preflight",
        lambda node, auth_profile: DutPreflightResult(True),
    )

    class FakeProcess:
        stdout = ["============================= 1 passed in 0.01s =============================\n"]

        def __init__(self, command, **kwargs):
            pass

        def wait(self):
            return 0

    monkeypatch.setattr(run_multi_node.subprocess, "Popen", FakeProcess)

    run_multi_node.run_node_plan(plan, tmp_path)

    output = capsys.readouterr().out
    assert "[NODE3] preflight started (auth_profile=ems_local_rw2)" in output
    assert "[NODE3] preflight passed in" in output
    assert "[NODE3] pytest started; log=" in output


def test_run_node_plan_prints_preflight_failure(monkeypatch, tmp_path, capsys):
    plan = run_multi_node.NodePlan(
        node="NODE1",
        chassis="IES4204",
        is_neox=False,
        command=["python", "-m", "pytest"],
        omitted_options=[],
    )
    monkeypatch.setattr(
        run_multi_node,
        "run_startup_preflight",
        lambda node, auth_profile: DutPreflightResult(False, "DevStatus=4"),
    )

    class FailIfCalled:
        def __init__(self, *args, **kwargs):
            raise AssertionError("pytest should not be invoked when preflight fails")

    monkeypatch.setattr(run_multi_node.subprocess, "Popen", FailIfCalled)

    result = run_multi_node.run_node_plan(plan, tmp_path)

    output = capsys.readouterr().out
    assert result.skipped
    assert "[NODE1] preflight started" in output
    assert "[NODE1] preflight failed in" in output
    assert "DevStatus=4" in output
    assert "[NODE1] skipped: DUT preflight failed: DevStatus=4" in output
