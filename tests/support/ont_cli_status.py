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


def wait_for_ont_cli_is(
    env_config,
    *,
    status_reader: Callable = read_ont_cli_status,
    timeout: int = 120,
    interval: int = 15,
) -> OntCliStatus:
    deadline = time.monotonic() + timeout
    last = None
    while True:
        last = status_reader(env_config)
        if last.state == "IS":
            return last
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(interval, remaining))
    raise AssertionError(
        "ONT did not become IS according to CLI. "
        f"Last state={last.state if last else 'Unknown'}, source={last.source if last else 'none'}"
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
