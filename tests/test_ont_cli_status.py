from __future__ import annotations

from types import SimpleNamespace

from tests.support import ont_cli_status
from tests.support.ont_cli_status import OntCliStatus, parse_ont_cli_status, wait_for_ont_cli_is


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

def test_ssh_credentials_prefer_explicit_dut_environment(monkeypatch):
    monkeypatch.setenv("DUT_SSH_USERNAME", "cli-user")
    monkeypatch.setenv("DUT_SSH_PASSWORD", "cli-password")
    env_config = SimpleNamespace(auth_profile="ems_local_rw2")

    assert ont_cli_status.ssh_credentials(env_config) == ("cli-user", "cli-password")


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
