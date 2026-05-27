from __future__ import annotations

from tests.support.connectivity import PingResult, ping_attachment


def test_ping_attachment_uses_line_arrays_for_readability():
    result = PingResult(
        target="192.0.2.1",
        checkpoint="after_cli_verify",
        command=["ping", "-n", "2", "192.0.2.1"],
        returncode=0,
        stdout="line 1\nline 2\n",
        stderr="",
        duration_seconds=0.1,
    )

    attachment = ping_attachment(result)

    assert attachment["command_text"] == "ping -n 2 192.0.2.1"
    assert attachment["stdout_lines"] == ["line 1", "line 2"]
    assert attachment["stderr_lines"] == []
    assert "stdout" not in attachment
    assert "stderr" not in attachment
