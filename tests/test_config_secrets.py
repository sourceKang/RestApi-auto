from __future__ import annotations

import pytest

from tools.check_config_secrets import scan_text


pytestmark = pytest.mark.offline


@pytest.mark.parametrize(
    "line",
    [
        'password: "${EMS_AUTH_READWRITE_DEFAULT_PASSWORD:-change_me}"',
        "ssh_password: ${DUT_SSH_NODE1_PASSWORD}",
        '    ont_password: "${EMS_ONT_NODE1_PASSWORD:-SET_IN_ENV_OR_LOCAL_YAML}"',
        "devKey: ${EMS_DEVKEY:-example_devkey}",
        "token:",
        "api_key: ''",
    ],
)
def test_placeholder_secret_values_pass(line):
    assert scan_text(line, "configs/sample.yaml") == []


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        ("password: hunter22", "literal value"),
        ('ssh_password: "s3cret!"', "literal value"),
        ("  - devKey: abcdef123456", "literal value"),
        ('password: "${EMS_PASSWORD:-hunter22}"', "environment default is not a placeholder"),
    ],
)
def test_plaintext_secret_values_fail(line, reason):
    [finding] = scan_text(line, "configs/sample.yaml")

    assert finding.reason.startswith(reason)
    assert finding.line == 1


def test_finding_never_contains_the_secret_value():
    [finding] = scan_text("user: a\npassword: hunter22\n", "configs/sample.yaml")

    assert (finding.path, finding.line, finding.key) == ("configs/sample.yaml", 2, "password")
    assert "hunter22" not in repr(finding)
