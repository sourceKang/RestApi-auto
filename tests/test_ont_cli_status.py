from __future__ import annotations

from types import SimpleNamespace

from tests.support import ont_cli_status
from tests.support.ont_cli_status import (
    OntCliStatus,
    ont_cli_status_commands,
    parse_ont_cli_status,
    wait_for_ont_cli_config_absent,
    wait_for_ont_cli_config_tokens,
    wait_for_ont_cli_is,
    wait_for_ont_cli_state,
)


def test_ont_cli_client_selects_explicit_backend_only():
    legacy_env = SimpleNamespace(
        dut=SimpleNamespace(ssh_backend="openssh_legacy", ssh_host="192.0.2.1")
    )
    paramiko_env = SimpleNamespace(
        dut=SimpleNamespace(ssh_backend="paramiko", ssh_host="192.0.2.2")
    )

    legacy_client = ont_cli_status.ont_cli_client(legacy_env, "admin", "secret")
    paramiko_client = ont_cli_status.ont_cli_client(paramiko_env, "admin", "secret")

    assert legacy_client.__class__.__name__ == "LegacyOpenSshCliClient"
    assert paramiko_client.__class__.__name__ == "SshCliClient"


def test_ont_cli_status_commands_use_olt_ug_aid_for_olt1408a_c():
    olt_env = SimpleNamespace(
        dut=SimpleNamespace(chassis="OLT1408A-C", slot_id="0", port_id="8", ont_id="1")
    )
    neox_env = SimpleNamespace(
        dut=SimpleNamespace(chassis="NeoX-03", slot_id="3", port_id="16", ont_id="1")
    )

    assert ont_cli_status_commands(olt_env) == (
        "show remote ont ont-8-1",
        "show remote ont unreg",
    )
    assert ont_cli_status_commands(neox_env) == (
        "show interface remote xont 3-16-1 status",
        "show interface xpon 3-16 unreg",
    )


def test_empty_ont_password_does_not_corrupt_cli_output():
    output = "ONT 1 status IS"

    assert ont_cli_status._redact_cli_output(output, "") == output
    assert ont_cli_status._redact_cli_output(output, "status") == "ONT 1 <redacted> IS"


def test_parse_ont_cli_status_reads_is_from_remote_xont_status():
    status = parse_ont_cli_status(
        "2-16-1  ZYXE8CADDDC3  IS  PM7300-T0",
        "",
        "5A5958458CADDDC3",
    )

    assert status.state == "IS"
    assert status.source == "remote-xont-status"


def test_parse_ont_cli_status_maps_verbose_oos_states_from_device_output():
    cases = {
        "Status | OOS( NOT REGISTERED) (27s)": "OOS-NR",
        "Status | OOS( LOSS OF SIGNAL) (14s)": "OOS-LS",
    }

    for output, expected in cases.items():
        status = parse_ont_cli_status(output, "", "5A5958458CADDDC3")
        assert status.state == expected
        assert status.source == "remote-xont-status"


def test_parse_ont_cli_status_reads_status_delayed_into_second_command_output():
    status = parse_ont_cli_status(
        "",
        "show interface remote xont 2-16-1 status\nStatus | IS (5s)",
        "5A5958458CADDDC3",
    )

    assert status.state == "IS"
    assert status.source == "remote-xont-status"


def test_parse_ont_cli_status_reads_specific_yaml_sn_from_unregistered_table():
    status = parse_ont_cli_status(
        "Error: no such data",
        "2-16 | UnReg  ZYXE8CADDDC3  Active",
        "5A5958458CADDDC3",
    )

    assert status.state == "UnReg"
    assert status.source == "xpon-unreg"


def test_parse_ont_cli_status_does_not_treat_another_unregistered_sn_as_target():
    status = parse_ont_cli_status(
        "Error: no such data",
        "2-16 | UnReg  ZYXE00000000  Active",
        "5A5958458CADDDC3",
    )

    assert status.state == "Unknown"


def test_wait_for_ont_cli_is_accepts_transition_from_unregistered_to_is():
    statuses = iter(
        [
            OntCliStatus("UnReg", "xpon-unreg", {}),
            OntCliStatus("IS", "remote-xont-status", {}),
        ]
    )

    result = wait_for_ont_cli_is(
        SimpleNamespace(),
        status_reader=lambda env: next(statuses),
        timeout=1,
        interval=0,
    )

    assert result.state == "IS"


def test_wait_for_ont_cli_state_accepts_transition_from_is_to_unregistered():
    statuses = iter(
        [
            OntCliStatus("IS", "remote-xont-status", {}),
            OntCliStatus("UnReg", "xpon-unreg", {}),
        ]
    )

    result = wait_for_ont_cli_state(
        SimpleNamespace(),
        "UnReg",
        status_reader=lambda env: next(statuses),
        timeout=1,
        interval=0,
    )

    assert result.state == "UnReg"


def test_wait_for_ont_cli_config_absent_accepts_transition_after_remote_xont_is_removed():
    outputs = iter(
        [
            "interface remote xont 3-16-1; description TEST",
            "interface xpon 3-16; no inactive",
        ]
    )
    env = SimpleNamespace(dut=SimpleNamespace(node_key="NODE3", device_name="NeoX-03"))

    result = wait_for_ont_cli_config_absent(
        env,
        "3-16-1",
        config_reader=lambda _: next(outputs),
        timeout=1,
        interval=0,
    )

    assert "interface remote xont 3-16-1" not in result


def test_wait_for_ont_cli_config_absent_rejects_persistent_remote_xont_config():
    env = SimpleNamespace(dut=SimpleNamespace(node_key="NODE3", device_name="NeoX-03"))

    try:
        wait_for_ont_cli_config_absent(
            env,
            "3-16-1",
            config_reader=lambda _: "interface remote xont 3-16-1",
            timeout=0,
            interval=0,
        )
    except AssertionError as error:
        assert "was not cleared" in str(error)
    else:
        raise AssertionError("Persistent remote xont config must fail the clear barrier")


def test_wait_for_ont_cli_config_tokens_requires_consecutive_exact_baseline_samples(monkeypatch):
    outputs = iter(
        [
            "description REST_API_NEOX_ONT\ntemplate #RestApi_provision_temp_SFU",
            "description REST_API_NEOX_ONT",
            "description CHANGED",
            "description REST_API_NEOX_ONT",
            "description REST_API_NEOX_ONT",
        ]
    )
    env = SimpleNamespace(dut=SimpleNamespace(node_key="NODE3", device_name="NeoX-03"))
    monkeypatch.setattr(ont_cli_status.time, "sleep", lambda _: None)

    result = wait_for_ont_cli_config_tokens(
        env,
        expected_tokens=("description REST_API_NEOX_ONT",),
        absent_tokens=("template #RestApi_provision_temp_SFU",),
        consecutive_successes=2,
        config_reader=lambda _: next(outputs),
        timeout=1,
        interval=0,
    )

    assert "REST_API_NEOX_ONT" in result


def test_wait_for_ont_cli_config_tokens_rejects_persistent_template_residual():
    env = SimpleNamespace(dut=SimpleNamespace(node_key="NODE3", device_name="NeoX-03"))

    try:
        wait_for_ont_cli_config_tokens(
            env,
            expected_tokens=("description REST_API_NEOX_ONT",),
            absent_tokens=("template #RestApi_provision_temp_SFU",),
            config_reader=lambda _: (
                "description REST_API_NEOX_ONT\n"
                "template #RestApi_provision_temp_SFU"
            ),
            timeout=0,
            interval=0,
        )
    except AssertionError as error:
        assert "unexpected" in str(error)
    else:
        raise AssertionError("Persistent template residual must fail the stable baseline barrier")


def test_ssh_credentials_prefer_explicit_dut_environment(monkeypatch):
    monkeypatch.setenv("DUT_SSH_USERNAME", "cli-user")
    monkeypatch.setenv("DUT_SSH_PASSWORD", "cli-password")
    env_config = SimpleNamespace(auth_profile="ems_local_rw2")

    assert ont_cli_status.ssh_credentials(env_config) == ("cli-user", "cli-password")


def test_ssh_credentials_use_dut_target_config(monkeypatch):
    monkeypatch.delenv("DUT_SSH_USERNAME", raising=False)
    monkeypatch.delenv("DUT_SSH_PASSWORD", raising=False)
    monkeypatch.delenv("NEOX_SSH_USERNAME", raising=False)
    monkeypatch.delenv("NEOX_SSH_PASSWORD", raising=False)
    env_config = SimpleNamespace(
        auth_profile="default",
        dut=SimpleNamespace(
            node_key="NODE2",
            ssh_username="admin",
            ssh_password="device-secret",
        ),
    )

    assert ont_cli_status.ssh_credentials(env_config) == ("admin", "device-secret")

def test_ssh_credentials_use_default_profile_for_nondefault_rest_auth(monkeypatch):
    monkeypatch.delenv("DUT_SSH_USERNAME", raising=False)
    monkeypatch.delenv("DUT_SSH_PASSWORD", raising=False)
    monkeypatch.delenv("NEOX_SSH_USERNAME", raising=False)
    monkeypatch.delenv("NEOX_SSH_PASSWORD", raising=False)
    loaded = SimpleNamespace(readwrite=SimpleNamespace(username="default-cli", password="secret"))
    monkeypatch.setattr(ont_cli_status, "load_environment", lambda **kwargs: loaded)
    env_config = SimpleNamespace(
        auth_profile="ems_local_rw2",
        dut=SimpleNamespace(node_key="NODE3"),
    )

    assert ont_cli_status.ssh_credentials(env_config) == ("default-cli", "secret")
