"""Poll NeoX GE ACL profile state over CLI instead of waiting a fixed time.

CLI baseline on NODE3 (2026-10-20): after `acl-profile mode <mode>` + `y`, after creating an
ACL profile and after switching back to port mode, the new state was already visible on the
first `show` (about 3.4 s including the SSH round trip).
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from clients.ssh_cli import SshCliClient
from config_loader.settings import scaled_wait
from tests.support.neox_cli_verification import neox_cli_credentials


ACL_PROFILE_TIMEOUT_SECONDS = 30.0
ACL_PROFILE_INTERVAL_SECONDS = 1.0
_PROFILE_NAME_RE = re.compile(r"acl profile name:(\S+)")


@dataclass(frozen=True)
class AclPoll:
    output: str
    polls: int
    elapsed_seconds: float


def read_ge_acl_show(env_config, command: str) -> str:
    username, password = neox_cli_credentials(env_config, "GE")
    results = SshCliClient(env_config.dut.ssh_host, username, password).run_commands([command])
    return results[0].output if results else ""


def acl_profile_names(show_output: str) -> list[str]:
    return _PROFILE_NAME_RE.findall(show_output)


def wait_for_ge_acl_state(
    env_config,
    command: str,
    is_ready: Callable[[str], bool],
    description: str,
    *,
    timeout: float = ACL_PROFILE_TIMEOUT_SECONDS,
    interval: float = ACL_PROFILE_INTERVAL_SECONDS,
    reader: Callable[[object, str], str] = read_ge_acl_show,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> AclPoll:
    """Poll `command` until `is_ready(output)`; raise AssertionError with the last output on timeout."""
    started = clock()
    deadline = started + scaled_wait(env_config, timeout)
    polls = 0
    while True:
        polls += 1
        output = reader(env_config, command)
        if is_ready(output):
            return AclPoll(output, polls, round(clock() - started, 3))
        remaining = deadline - clock()
        if remaining <= 0:
            raise AssertionError(
                f"{description} not visible after {polls} polls ({round(clock() - started, 1)} s): {output}"
            )
        sleeper(min(interval, remaining))


def wait_for_ge_acl_profile_mode(env_config, mode: str, **kwargs) -> AclPoll:
    expected_line = f"Acl-profile mode : {mode}"
    return wait_for_ge_acl_state(
        env_config,
        "show acl-profile mode",
        lambda output: expected_line in output,
        f"GE ACL profile mode {mode!r}",
        **kwargs,
    )


def wait_for_ge_acl_profiles(env_config, names: list[str], **kwargs) -> AclPoll:
    return wait_for_ge_acl_state(
        env_config,
        "show acl-profile",
        lambda output: set(names) <= set(acl_profile_names(output)),
        f"GE ACL profiles {names}",
        **kwargs,
    )
