from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Callable

from clients.ssh_cli import SshCliClient
from config_loader import load_environment
from utils.allure_helpers import attach_json


ONT_SERVICE_STATES = ("IS", "OOS-LO", "OOS-SB", "OOS-DG", "OOS-LS", "OOS-NR", "OOS-CD", "OOS-NP", "OOS-PF")
ONT_STATE_PATTERN = re.compile(rf"(?<![A-Z0-9-])({'|'.join(ONT_SERVICE_STATES)})(?![A-Z0-9-])", re.IGNORECASE)
VERBOSE_OOS_STATES = {
    "NOT REGISTERED": "OOS-NR",
    "LOSS OF SIGNAL": "OOS-LS",
}


@dataclass(frozen=True)
class OntCliStatus:
    state: str
    source: str
    output_by_command: dict[str, str]


def read_ont_cli_status(env_config) -> OntCliStatus:
    dut = env_config.dut
    aid = f"{dut.slot_id}-{dut.port_id}-{dut.ont_id}"
    pon = f"{dut.slot_id}-{dut.port_id}"
    commands = [
        f"show interface remote xont {aid} status",
        f"show interface xpon {pon} unreg",
    ]
    ssh_username, ssh_password = ssh_credentials(env_config)
    client = SshCliClient(
        dut.device_ip,
        ssh_username,
        ssh_password,
        timeout=15,
    )
    results = client.run_commands(commands)
    output_by_command = {
        result.command: result.output.replace(dut.ont_password, "<redacted>")
        for result in results
    }
    status = parse_ont_cli_status(
        output_by_command.get(commands[0], ""),
        output_by_command.get(commands[1], ""),
        dut.ont_sn,
    )
    attach_json(
        "ONT CLI status ground truth",
        {
            "node": dut.node_key,
            "device": dut.device_name,
            "aid": aid,
            "state": status.state,
            "source": status.source,
            "commands": output_by_command,
        },
    )
    return OntCliStatus(status.state, status.source, output_by_command)


def read_ont_cli_running_config(env_config) -> str:
    dut = env_config.dut
    pon = f"{dut.slot_id}-{dut.port_id}"
    command = f"show running-config interface xpon {pon}"
    ssh_username, ssh_password = ssh_credentials(env_config)
    client = SshCliClient(
        dut.device_ip,
        ssh_username,
        ssh_password,
        timeout=15,
    )
    result = client.run_commands([command])[0]
    return result.output.replace(dut.ont_password, "<redacted>")


def wait_for_ont_cli_config_absent(
    env_config,
    remote_xont: str,
    *,
    config_reader: Callable = read_ont_cli_running_config,
    timeout: int = 300,
    interval: int = 15,
) -> str:
    expected_absent = f"interface remote xont {remote_xont}"
    deadline = time.monotonic() + timeout
    last_output = ""
    while True:
        last_output = config_reader(env_config)
        if expected_absent.casefold() not in last_output.casefold():
            attach_json(
                "ONT CLI config cleanup ground truth",
                {
                    "node": env_config.dut.node_key,
                    "device": env_config.dut.device_name,
                    "expected_absent": expected_absent,
                    "output": last_output,
                },
            )
            return last_output
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(interval, remaining))
    attach_json(
        "ONT CLI config cleanup timeout",
        {
            "node": env_config.dut.node_key,
            "device": env_config.dut.device_name,
            "expected_absent": expected_absent,
            "output": last_output,
        },
    )
    raise AssertionError(
        f"ONT CLI config was not cleared within {timeout}s; still found {expected_absent!r}"
    )


def wait_for_ont_cli_config_tokens(
    env_config,
    *,
    expected_tokens: tuple[str, ...] = (),
    absent_tokens: tuple[str, ...] = (),
    consecutive_successes: int = 1,
    config_reader: Callable = read_ont_cli_running_config,
    timeout: int = 180,
    interval: int = 15,
) -> str:
    if consecutive_successes < 1:
        raise ValueError("consecutive_successes must be at least 1")

    deadline = time.monotonic() + timeout
    stable_hits = 0
    last_output = ""
    last_missing: list[str] = []
    last_present: list[str] = []

    while True:
        last_output = config_reader(env_config)
        normalized = last_output.casefold()
        last_missing = [token for token in expected_tokens if str(token).casefold() not in normalized]
        last_present = [token for token in absent_tokens if str(token).casefold() in normalized]
        if not last_missing and not last_present:
            stable_hits += 1
            if stable_hits >= consecutive_successes:
                attach_json(
                    "ONT CLI config stable ground truth",
                    {
                        "node": env_config.dut.node_key,
                        "device": env_config.dut.device_name,
                        "expected_tokens": expected_tokens,
                        "absent_tokens": absent_tokens,
                        "consecutive_successes": consecutive_successes,
                        "output": last_output,
                    },
                )
                return last_output
        else:
            stable_hits = 0

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(interval, remaining))

    attach_json(
        "ONT CLI config stable timeout",
        {
            "node": env_config.dut.node_key,
            "device": env_config.dut.device_name,
            "missing_tokens": last_missing,
            "unexpected_tokens": last_present,
            "consecutive_successes": consecutive_successes,
            "stable_hits": stable_hits,
            "output": last_output,
        },
    )
    raise AssertionError(
        "ONT CLI config did not become stable within "
        f"{timeout}s; missing={last_missing!r}, unexpected={last_present!r}, "
        f"stable_hits={stable_hits}/{consecutive_successes}"
    )


def parse_ont_cli_status(status_output: str, unreg_output: str, ont_sn: str) -> OntCliStatus:
    combined_output = f"{status_output}\n{unreg_output}"
    for line in combined_output.splitlines():
        for verbose_state, state in VERBOSE_OOS_STATES.items():
            if re.search(rf"OOS\s*\(\s*{re.escape(verbose_state)}\s*\)", line, re.IGNORECASE):
                return OntCliStatus(state, "remote-xont-status", {})
        match = ONT_STATE_PATTERN.search(line)
        if match:
            return OntCliStatus(match.group(1).upper(), "remote-xont-status", {})

    normalized_unreg = _normalized_cli_text(unreg_output)
    if "UNREG" in normalized_unreg and any(candidate in normalized_unreg for candidate in _serial_candidates(ont_sn)):
        return OntCliStatus("UnReg", "xpon-unreg", {})
    return OntCliStatus("Unknown", "no-matching-cli-entry", {})


def wait_for_ont_cli_state(
    env_config,
    expected_state: str,
    *,
    status_reader: Callable = read_ont_cli_status,
    timeout: int = 120,
    interval: int = 15,
) -> OntCliStatus:
    deadline = time.monotonic() + timeout
    last = None
    while True:
        last = status_reader(env_config)
        if last.state == expected_state:
            return last
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(interval, remaining))
    raise AssertionError(
        f"ONT did not become {expected_state} according to CLI. "
        f"Last state={last.state if last else 'Unknown'}, source={last.source if last else 'none'}"
    )


def wait_for_ont_cli_is(
    env_config,
    *,
    status_reader: Callable = read_ont_cli_status,
    timeout: int = 120,
    interval: int = 15,
) -> OntCliStatus:
    return wait_for_ont_cli_state(
        env_config,
        "IS",
        status_reader=status_reader,
        timeout=timeout,
        interval=interval,
    )


def _serial_candidates(ont_sn: str) -> set[str]:
    normalized = _normalized_cli_text(ont_sn)
    candidates = {normalized}
    if len(normalized) >= 8:
        try:
            vendor = bytes.fromhex(normalized[:8]).decode("ascii")
        except (ValueError, UnicodeDecodeError):
            pass
        else:
            candidates.add(_normalized_cli_text(vendor + normalized[8:]))
    return candidates


def _normalized_cli_text(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def ssh_credentials(env_config) -> tuple[str, str]:
    username = os.environ.get("DUT_SSH_USERNAME") or os.environ.get("NEOX_SSH_USERNAME")
    password = os.environ.get("DUT_SSH_PASSWORD") or os.environ.get("NEOX_SSH_PASSWORD")
    if username and password:
        return username, password
    ssh_env = env_config
    if env_config.auth_profile != "default":
        ssh_env = load_environment(node=env_config.dut.node_key, auth_profile="default")
    return ssh_env.readwrite.username, ssh_env.readwrite.password
