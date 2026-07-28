from __future__ import annotations

import pytest

from tests.support.ge_cli_config import (
    GeCliConfigResult,
    canonical_running_config,
    capture_ge_service_timeout_cli_diagnostic,
    compare_ge_cli_config,
    ge_cli_commands,
    monitor_ge_patch_transition,
    wait_for_ge_cli_config,
)


def test_timeout_cli_diagnostic_does_not_run_for_unrelated_failure(monkeypatch):
    monkeypatch.setattr(
        "tests.support.ge_cli_config.SshCliSession",
        lambda *_args, **_kwargs: pytest.fail("SSH must not run for a non-timeout failure"),
    )

    captured = capture_ge_service_timeout_cli_diagnostic(_env_config(), AssertionError("different failure"))

    assert captured is False


def test_timeout_cli_diagnostic_runs_one_read_only_command_and_attaches(monkeypatch):
    calls = []
    attachments = []

    class DiagnosticSession:
        def __init__(self, host, username, password, *, timeout):
            calls.append(("init", host, username, password, timeout))

        def connect(self):
            calls.append(("connect",))

        def run_command(self, command, **kwargs):
            calls.append(("run", command, kwargs))
            return "interface ge 1-39", 0.25, False

        def close(self, *, logout=True):
            calls.append(("close", logout))
            return 0.1

    monkeypatch.setattr("tests.support.ge_cli_config.SshCliSession", DiagnosticSession)
    monkeypatch.setattr("tests.support.ge_cli_config.ssh_credentials", lambda _env: ("user", "pass"))
    monkeypatch.setattr(
        "tests.support.ge_cli_config.attach_json",
        lambda name, payload: attachments.append((name, payload)),
    )

    captured = capture_ge_service_timeout_cli_diagnostic(
        _env_config(),
        AssertionError("GE service did not reach states Success within 120 seconds"),
    )

    assert captured is True
    assert calls[0] == ("init", "192.0.2.10", "user", "pass", 5)
    assert calls[2] == (
        "run",
        "show running-config interface ge 1-39",
        {"first_wait": 0.5, "idle_wait": 0.3, "max_wait": 5},
    )
    assert calls[-1] == ("close", True)
    assert attachments[0][1]["captured"] is True
    assert attachments[0][1]["output"] == "interface ge 1-39"


def test_ge_cli_commands_follow_ies4204_user_guide_forms():
    assert ge_cli_commands("1", "39") == [
        "show running-config interface ge 1-39",
        "show interface ge 1-39 config",
        "show interface ge 1-39 status",
        "show interface ge 1-39 pvid",
        "show interface ge 1-39 mtu",
        "show interface ge 1-39 vlan",
        "show interface ge 1-39 vlan outer-tpid",
        "show interface ge 1-39 qos",
        "show interface ge 1-39 igmp-mld",
    ]


def test_ge_cli_comparison_checks_profile_port_name_and_telephone():
    commands = ge_cli_commands("1", "39")
    output = {
        commands[0]: (
            'interface ge 1-39\n speed 1g-full\n name "1g_Hsinchu"\n'
            ' tel "011+886+7+2737"\n mtu 512\n pvid 1 pbit 0\n qos algorithm sp'
        ),
        commands[1]: "speed: 1g-full\nPort-Name: 1g_Hsinchu\nPort-Telephone-No.: 011+886+7+2737",
        commands[2]: "link: up",
        commands[3]: "Port Pvid Pbit\n1-39 1 0",
        commands[4]: "1-39 MTU: 512 bytes",
        commands[5]: "vlan 101 forbidden",
        commands[6]: "outer-tpid: enable",
        commands[7]: "queue algorithm: sp",
        commands[8]: "igmp-mld: disable",
    }
    content = {
        "getmplateprofile_portspeed": "1g-full",
        "getmplateprofile_portmtu": "512",
        "getmplateprofile_pvid": "1",
        "getmplateprofile_pbit": "0",
        "getmplateprofile_qosalgorithm": "sp",
        "vlanvidarray": [{"vlanid": "101", "mode": "Forbidden"}],
    }

    result = compare_ge_cli_config(
        output,
        content,
        telephone="011+886+7+2737",
        port_name="1g_Hsinchu",
    )

    assert result.matches
    assert result.mismatches == ()
    assert result.unverified_fields == ("vlanvidarray",)


def test_ge_cli_comparison_accepts_unquoted_name_and_rejects_wrong_port_name():
    commands = ge_cli_commands("1", "39")
    output = {command: "ok" for command in commands}
    output[commands[0]] = "interface ge 1-39\nname 1g_Hsinchu\ntel 0000\nexit"

    accepted = compare_ge_cli_config(output, {}, telephone="0000", port_name="1g_Hsinchu")
    rejected = compare_ge_cli_config(output, {}, telephone="0000", port_name="other_name")

    assert accepted.matches
    assert not rejected.matches
    assert any("name expected 'other_name'" in mismatch for mismatch in rejected.mismatches)


def test_ge_cli_comparison_blocks_downstream_when_required_value_differs():
    commands = ge_cli_commands("1", "39")
    output = {command: "ok" for command in commands}
    output[commands[4]] = "mtu: 9200"

    result = compare_ge_cli_config(
        output,
        {"getmplateprofile_portmtu": "512"},
        telephone=None,
        port_name=None,
    )

    assert not result.matches
    assert any("mtu expected '512'" in mismatch for mismatch in result.mismatches)


def test_ge_cli_comparison_retries_when_running_config_is_empty():
    commands = ge_cli_commands("1", "39")
    output = {command: "ok" for command in commands}
    output[commands[0]] = ""

    result = compare_ge_cli_config(output, {}, telephone=None, port_name=None)

    assert not result.matches
    assert "GE running-config output is empty" in result.mismatches


def test_canonical_running_config_ignores_command_prompt_and_order():
    first = "MSC1240QA# show running-config interface ge 1-39\nCurrent configuration:\ninterface ge 1-39\nname X\ntel Y\nexit\nIES#"
    second = "interface ge 1-39\ntel Y\nname X\nexit\nIES#"

    assert canonical_running_config(first) == canonical_running_config(second)


def test_wait_for_ge_cli_config_requires_consecutive_stable_running_config(monkeypatch):
    command = "show running-config interface ge 1-39"
    outputs = iter(
        [
            "interface ge 1-39\nname first\nexit",
            "interface ge 1-39\nname final\nexit",
            "interface ge 1-39\nname final\nexit",
        ]
    )
    calls = []

    def reader(*_args, **_kwargs):
        calls.append(True)
        return GeCliConfigResult(True, (), {command: next(outputs)}, ())

    monkeypatch.setattr("tests.support.ge_cli_config.time.sleep", lambda _seconds: None)

    result = wait_for_ge_cli_config(
        _env_config(),
        {"post_profile_info": {}},
        reader=reader,
        timeout=10,
        interval=0,
        consecutive_stable_successes=2,
    )

    assert len(calls) == 3
    assert "name final" in result.output_by_command[command]


class FakeSshSession:
    outputs: list[str] = []

    def __init__(self, *_args, **_kwargs):
        self._outputs = list(self.outputs)

    def connect(self):
        return None

    def run_command(self, _command, **_kwargs):
        assert self._outputs
        return self._outputs.pop(0), 0.01, False

    def close(self, *, logout=True):
        return 0.0


def test_patch_monitor_attaches_pre_patch_config_diff(monkeypatch):
    baseline = 'interface ge 1-39\nname "modify_1g_Hsinchu"\ntel "00000123"\nspeed 1g-full\nexit'
    changed = 'interface ge 1-39\nname "modify_1g_Hsinchu"\ntel "00000123"\nspeed auto\nexit'
    FakeSshSession.outputs = [changed]
    attachments = []
    monkeypatch.setattr("tests.support.ge_cli_config.SshCliSession", FakeSshSession)
    monkeypatch.setattr("tests.support.ge_cli_config.ssh_credentials", lambda _env: ("user", "pass"))
    monkeypatch.setattr("tests.support.ge_cli_config.attach_json", lambda name, payload: attachments.append((name, payload)))

    with pytest.raises(AssertionError, match="CLI config changed after PUT baseline"):
        monitor_ge_patch_transition(
            _env_config(),
            baseline_running_config=baseline,
            port_name="modify_1g_Hsinchu",
            telephone="00000123",
            patch_action=lambda: None,
            state_reader=lambda: {"state": "Success"},
        )

    evidence = attachments[-1][1]
    assert "speed 1g-full" in evidence["running_config_snapshots"]["baseline_only"]
    assert "speed auto" in evidence["running_config_snapshots"]["pre_patch_only"]



def test_patch_monitor_accepts_cli_clear_and_restore_when_reprovision_is_not_observed(monkeypatch):
    baseline = 'interface ge 1-39\nname "modify_1g_Hsinchu"\ntel "00000123"\nspeed 1g-full\nexit'
    cleared = "interface ge 1-39\nspeed auto\nexit"
    FakeSshSession.outputs = [baseline, cleared, baseline]
    monkeypatch.setattr("tests.support.ge_cli_config.SshCliSession", FakeSshSession)
    monkeypatch.setattr("tests.support.ge_cli_config.ssh_credentials", lambda _env: ("user", "pass"))
    monkeypatch.setattr("tests.support.ge_cli_config.time.sleep", lambda _seconds: None)
    states = iter([{"state": "Success"}, {"state": "Success"}])
    patched = []

    result = monitor_ge_patch_transition(
        _env_config(),
        baseline_running_config=baseline,
        port_name="modify_1g_Hsinchu",
        telephone="00000123",
        patch_action=lambda: patched.append(True),
        state_reader=lambda: next(states),
        timeout=10,
        interval=0,
        success_evidence_grace=2,
    )

    assert patched == [True]
    assert not result.observed_reprovision
    assert result.observed_cli_cleared
    assert result.observed_cli_restored
    assert result.final_service["state"] == "Success"


def test_patch_monitor_accepts_reprovision_then_success_without_cli_clear(monkeypatch):
    baseline = 'interface ge 1-39\nname "modify_1g_Hsinchu"\ntel "00000123"\nexit'
    FakeSshSession.outputs = [baseline, baseline, baseline]
    monkeypatch.setattr("tests.support.ge_cli_config.SshCliSession", FakeSshSession)
    monkeypatch.setattr("tests.support.ge_cli_config.ssh_credentials", lambda _env: ("user", "pass"))
    monkeypatch.setattr("tests.support.ge_cli_config.time.sleep", lambda _seconds: None)
    states = iter([{"state": "Reprovision"}, {"state": "Success"}])

    result = monitor_ge_patch_transition(
        _env_config(),
        baseline_running_config=baseline,
        port_name="modify_1g_Hsinchu",
        telephone="00000123",
        patch_action=lambda: None,
        state_reader=lambda: next(states),
        timeout=10,
        interval=0,
        success_evidence_grace=2,
    )

    assert result.observed_reprovision
    assert not result.observed_cli_cleared
    assert result.final_service["state"] == "Success"


def test_patch_monitor_retries_empty_pre_patch_cli_output(monkeypatch):
    baseline = 'interface ge 1-39\nname "modify_1g_Hsinchu"\ntel "00000123"\nexit'
    FakeSshSession.outputs = ["", baseline, baseline, baseline]
    monkeypatch.setattr("tests.support.ge_cli_config.SshCliSession", FakeSshSession)
    monkeypatch.setattr("tests.support.ge_cli_config.ssh_credentials", lambda _env: ("user", "pass"))
    monkeypatch.setattr("tests.support.ge_cli_config.time.sleep", lambda _seconds: None)
    states = iter([{"state": "Reprovision"}, {"state": "Success"}])

    result = monitor_ge_patch_transition(
        _env_config(),
        baseline_running_config=baseline,
        port_name="modify_1g_Hsinchu",
        telephone="00000123",
        patch_action=lambda: None,
        state_reader=lambda: next(states),
        timeout=10,
        interval=0,
        success_evidence_grace=2,
    )

    assert result.observed_reprovision
    assert result.final_service["state"] == "Success"



def test_patch_monitor_rejects_success_without_reprovision_or_cli_transition(monkeypatch):
    baseline = 'interface ge 1-39\nname "modify_1g_Hsinchu"\ntel "00000123"\nexit'
    FakeSshSession.outputs = [baseline, baseline]
    monkeypatch.setattr("tests.support.ge_cli_config.SshCliSession", FakeSshSession)
    monkeypatch.setattr("tests.support.ge_cli_config.ssh_credentials", lambda _env: ("user", "pass"))

    with pytest.raises(AssertionError, match="neither Reprovision state nor CLI clear/restore"):
        monitor_ge_patch_transition(
            _env_config(),
            baseline_running_config=baseline,
            port_name="modify_1g_Hsinchu",
            telephone="00000123",
            patch_action=lambda: None,
            state_reader=lambda: {"state": "Success"},
            timeout=10,
            interval=0,
            success_evidence_grace=0,
        )


def _env_config():
    dut = type(
        "Dut",
        (),
        {
            "node_key": "NODE1",
            "device_name": "device",
            "device_ip": "192.0.2.10",
            "ssh_host": "192.0.2.10",
            "ge_slot_id": "1",
            "ge_port_id": "39",
        },
    )()
    return type("Env", (), {"dut": dut})()
