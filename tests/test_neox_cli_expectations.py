from __future__ import annotations

from services.neox_config.cli_expectations import clear_ignored_line_prefixes, normalize_cli_output


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
