"""Offline checks for testing a node that EMS manages by IPv4 or IPv6 (see ADR 0003)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from config_loader.settings import ConfigError, DutSample, _apply_managed_ip_family
from models.api import ApiResponse
from services import preflight as preflight_core
from tools.case_step_diff import IPV4_RE


pytestmark = pytest.mark.offline

V4 = "192.0.2.58"
V6 = "2001:db8:169::58"


def _dut(**overrides) -> DutSample:
    values = dict(
        node_key="NODE3",
        device_name="Taiwan_NeoX-03",
        device_ip=V4,
        ssh_host=V4,
        ssh_backend="paramiko",
        ssh_username="u",
        ssh_password="p",
        chassis="NeoX-03",
        slot_id="3",
        port_id="16",
        ge_slot_id="1",
        ge_port_id="39",
        ont_id="1",
        ont_sn="SN",
        ont_password="pw",
        ont_template="#t",
        ont_description="d",
        ge_template="#g",
        ge_port_name="n",
        ge_telephone="000",
    )
    values.update(overrides)
    return DutSample(**values)


def test_ipv4_is_the_default_and_keeps_device_ip(monkeypatch):
    monkeypatch.delenv("EMS_NODE_IP_FAMILY", raising=False)
    dut = _apply_managed_ip_family(_dut(), {"device_ip": V4, "device_ip_v6": V6})

    assert (dut.device_ip, dut.managed_ip_family, dut.device_ip_v4, dut.device_ip_v6) == (V4, "ipv4", V4, V6)


def test_ipv6_node_points_device_ip_at_v6_and_keeps_ssh_on_v4(monkeypatch):
    monkeypatch.delenv("EMS_NODE_IP_FAMILY", raising=False)
    dut = _apply_managed_ip_family(_dut(), {"device_ip_v6": V6, "managed_ip_family": "ipv6"})

    assert dut.device_ip == V6
    assert dut.device_ip_v4 == V4
    assert dut.ssh_host == V4
    assert dut.managed_ip_family == "ipv6"


def test_env_override_wins_over_the_node_setting(monkeypatch):
    monkeypatch.setenv("EMS_NODE_IP_FAMILY", "ipv4")
    dut = _apply_managed_ip_family(_dut(), {"device_ip_v6": V6, "managed_ip_family": "ipv6"})

    assert (dut.device_ip, dut.managed_ip_family) == (V4, "ipv4")


def test_ipv6_without_an_ipv6_address_is_a_config_error(monkeypatch):
    monkeypatch.delenv("EMS_NODE_IP_FAMILY", raising=False)
    with pytest.raises(ConfigError, match="no device_ip_v6"):
        _apply_managed_ip_family(_dut(), {"managed_ip_family": "ipv6"})


def test_unknown_family_is_a_config_error(monkeypatch):
    monkeypatch.setenv("EMS_NODE_IP_FAMILY", "dual")
    with pytest.raises(ConfigError, match="managed_ip_family 'dual'"):
        _apply_managed_ip_family(_dut(), {})


class _DeviceClient:
    def __init__(self, ip_address):
        self.ip_address = ip_address

    def request(self, method, path, *, session=None, **kwargs):
        device = {"DevName": "Taiwan_NeoX-03", "DevStatus": "1"}
        if self.ip_address is not None:
            device["IPAddress"] = self.ip_address
        body = {"retstatus": "Success", "retval": {"deviceinfo": device}}
        return ApiResponse(200, body, "", 0, "id", method, path)


def _env(dut):
    return SimpleNamespace(dut=dut)


def test_managed_ip_check_passes_when_ems_reports_the_expected_address():
    dut = _apply_managed_ip_family(_dut(), {"device_ip_v6": V6, "managed_ip_family": "ipv6"})
    # EMS may print the IPv6 address in another valid form.
    result = preflight_core._check_managed_ip(_DeviceClient("2001:0db8:0169:0:0:0:0:0058"), "s", _env(dut))

    assert result.ok


def test_managed_ip_check_stops_early_and_names_the_fix_when_ems_uses_ipv6(monkeypatch):
    monkeypatch.delenv("EMS_NODE_IP_FAMILY", raising=False)
    dut = _apply_managed_ip_family(_dut(), {"device_ip_v6": V6})
    result = preflight_core._check_managed_ip(_DeviceClient(V6), "s", _env(dut))

    assert not result.ok
    assert f"IPAddress={V6}" in result.reason
    assert "managed_ip_family: ipv6" in result.reason


def test_managed_ip_check_does_not_judge_a_response_without_an_address():
    result = preflight_core._check_managed_ip(_DeviceClient(None), "s", _env(_dut()))

    assert result.ok


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("GET https://[2001:2:128::8]:9116/x", "GET https://[<ip>]:9116/x"),
        ("ip=2001:2:169:0:a94d:6ac4:a6ee:d44c, status=200", "ip=<ip>, status=200"),
        ("Device 192.168.169.57 is down", "Device <ip> is down"),
        ("2026-11-20 07:40:50.519Z", "2026-11-20 07:40:50.519Z"),
    ],
)
def test_step_comparison_masks_ipv4_and_ipv6_but_not_clock_times(text, expected):
    assert IPV4_RE.sub("<ip>", text) == expected
