from __future__ import annotations

from services.neox_config.cli_expectations import clear_ignored_line_prefixes, normalize_cli_output, vlan_cli_expectation
from services.neox_config.profile_expectations import neox_profile_cli_field_mismatches


def test_nni_clear_normalization_ignores_non_clearable_lines():
    baseline = """
show running-config interface nni 12
Current configuration:
interface nni 12
enable
flow-control enable
speed detect
mode uplink
exit
NXC400#
"""
    after_clear = """
show running-config interface nni 12
Current configuration:
interface nni 12
enable
flow-control disable
speed auto
mode uplink
exit
NXC400#
"""

    ignored = clear_ignored_line_prefixes("nni")

    assert ignored == ("flow-control ", "speed ")
    assert normalize_cli_output(after_clear, ignored) == normalize_cli_output(baseline, ignored)


def test_non_nni_clear_normalization_keeps_all_lines():
    ignored = clear_ignored_line_prefixes("ge")

    assert ignored == ()
    assert normalize_cli_output("flow-control enable", ignored) == "flow-control enable"


def test_clear_normalization_ignores_prompt_echo_shape():
    with_prompt = """
NeoX_168.85# show running-config interface xpon 8-1
Current configuration:
interface xpon 8-1
exit
NeoX_168.85#
"""
    without_prompt = """
show running-config interface xpon 8-1
Current configuration:
interface xpon 8-1
exit
"""

    assert normalize_cli_output(with_prompt) == normalize_cli_output(without_prompt)


def test_clear_normalization_ignores_remote_xont_dynamic_fields():
    baseline = """
8-16-2   |                    Edith_SFU_X   0 m -16.23     IS            1d 1h 40m 12s      V542ABYY3Z0      ZYXE/PM7300-T0
|                   ZYXE8CACE174                                                 V V542ABYY4Z0                                       D41AD1009EC8
"""
    after_clear = """
8-16-2   |                    Edith_SFU_X   0 m -16.35     IS            1d 1h 40m 48s      V542ABYY3Z0      ZYXE/PM7300-T0
|                   ZYXE8CACE174                                                 V V542ABYY4Z0                                       D41AD1009EC8
"""

    assert normalize_cli_output(after_clear) == normalize_cli_output(baseline)


def test_clear_normalization_ignores_remote_xont_elapsed_without_day_hour():
    baseline = """
8-16-2   |                    Edith_SFU_X   4 m -16.35     IS                   35m 4s    V V542ABYY3Z0      ZYXE/PM7300-T0
|                   ZYXE8CACE174                                                   V542ABYY4Z0                                       D41AD1009EC8
"""
    after_clear = """
8-16-2   |                    Edith_SFU_X   4 m -16.33     IS                  35m 40s    V V542ABYY3Z0      ZYXE/PM7300-T0
|                   ZYXE8CACE174                                                   V542ABYY4Z0                                       D41AD1009EC8
"""

    assert normalize_cli_output(after_clear) == normalize_cli_output(baseline)


def test_vlan_cli_expectation_accepts_vlan_id_range():
    payload = {
        "vlanname": "REST_API_VLAN_MAX",
        "fixedport": "2~11",
        "untaggedport": "1~4",
        "forbiddenport": "5~8",
        "tpid": "qinq-tpid",
    }
    output = """
VLAN Name: REST_API_VLAN_MAX
TPID: QinQ
4090 . U U U X X X X T T T .
4091 . U U U X X X X T T T .
4092 . U U U X X X X T T T .
4093 . U U U X X X X T T T .
4094 . U U U X X X X T T T .
"""

    expectation = vlan_cli_expectation("4090~4094", payload, output)

    assert expectation.missing == []

def test_ont_acl_profile_cli_field_mismatches_catch_reused_yes_no_tokens():
    payload = {
        "Content": {
            "enable": "no",
            "policy": "trust",
            "interface": "both",
            "counter": "enable",
            "logging": "enable",
            "protocol": "255",
            "srcport": "65535",
            "destport": "65535",
            "srcip": "210.109.190.100",
            "srcmask": "32",
            "destip": "210.109.190.86",
            "destmask": "32",
            "srcmac": "FE:DC:BA:98:76:54",
            "destmac": "01:23:45:67:89:AB",
        }
    }
    cli_output = """
RestApi_NeoX_ONTAcl      | Enable                  | Yes
                         | Policy                  | Trust
                         | Interface               | LAN&WAN (Both)
                         | Drop counter            | No
                         | Drop logging            | Yes
                         | IP protocol             | 255
                         | Source L4 port          | 65535
                         | Source IP address       | 210.109.190.100
                         | Source IP mask          | 32
                         | Source MAC address      | FE:DC:BA:98:76:54
                         | Destination L4 port     | 65535
                         | Destination IP address  | 210.109.190.86
                         | Destination IP mask     | 32
                         | Destination MAC address | 01:23:45:67:89:AB
"""

    mismatches = neox_profile_cli_field_mismatches("ONTAclProfile", payload, cli_output)

    assert "Drop counter: expected 'Yes', actual 'No'" in mismatches
    assert "Enable: expected 'No', actual 'Yes'" in mismatches


def test_ont_acl_profile_cli_field_mismatches_accept_updated_min_payload():
    payload = {
        "Content": {
            "enable": " ",
            "policy": "trust",
            "interface": "lan",
            "protocol": "0",
            "srcport": "1",
            "destport": "1",
            "srcip": "1.1.1.10",
            "srcmask": "1",
            "destip": "10.9.19.86",
            "destmask": "1",
            "srcmac": "10:10:10:10:10:01",
            "destmac": "10:10:10:10:10:02",
            "logging": "disable",
            "counter": "disable",
        }
    }
    cli_output = """
RestApi_NeoX_ONTAcl      | Enable                  | No
                         | Policy                  | Trust
                         | Interface               | LAN
                         | Drop counter            | No
                         | Drop logging            | No
                         | IP protocol             | 0
                         | Source L4 port          | 1
                         | Source IP address       | 1.1.1.10
                         | Source IP mask          | 1
                         | Source MAC address      | 10:10:10:10:10:01
                         | Destination L4 port     | 1
                         | Destination IP address  | 10.9.19.86
                         | Destination IP mask     | 1
                         | Destination MAC address | 10:10:10:10:10:02
"""

    assert neox_profile_cli_field_mismatches("ONTAclProfile", payload, cli_output) == []
