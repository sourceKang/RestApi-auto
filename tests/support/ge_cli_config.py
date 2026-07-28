from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Callable

from clients.ssh_cli import SshCliSession
from tests.support.ont_cli_status import ssh_credentials
from utils.allure_helpers import attach_json


@dataclass(frozen=True)
class GeCliConfigResult:
    matches: bool
    mismatches: tuple[str, ...]
    output_by_command: dict[str, str]
    unverified_fields: tuple[str, ...]


@dataclass(frozen=True)
class GePatchTransitionResult:
    observed_reprovision: bool
    observed_cli_cleared: bool
    observed_cli_restored: bool
    final_service: dict
    final_running_config: str
    timeline: tuple[dict, ...]


GE_SERVICE_STATE_TIMEOUT_TEXT = "GE service did not reach states"


def ge_running_config_command(slot_id: str, port_id: str) -> str:
    return f"show running-config interface ge {slot_id}-{port_id}"


def capture_ge_service_timeout_cli_diagnostic(
    env_config,
    error: Exception,
    *,
    attachment_name: str = "GE service timeout CLI diagnostic",
) -> bool:
    if GE_SERVICE_STATE_TIMEOUT_TEXT.lower() not in str(error).lower():
        return False

    dut = env_config.dut
    command = ge_running_config_command(dut.ge_slot_id, dut.ge_port_id)
    payload = {
        "node": dut.node_key,
        "device": dut.device_name,
        "port": f"{dut.ge_slot_id}-{dut.ge_port_id}",
        "trigger": str(error),
        "command": command,
        "captured": False,
    }
    session = None
    try:
        username, password = ssh_credentials(env_config)
        session = SshCliSession(dut.ssh_host, username, password, timeout=5)
        session.connect()
        output, elapsed, confirmed = session.run_command(
            command,
            first_wait=0.5,
            idle_wait=0.3,
            max_wait=5,
        )
        payload.update(
            {
                "captured": True,
                "elapsed_seconds": round(elapsed, 3),
                "confirmation_prompt_seen": confirmed,
                "output": output,
            }
        )
    except Exception as diagnostic_error:
        payload["diagnostic_error"] = f"{type(diagnostic_error).__name__}: {diagnostic_error}"
    finally:
        if session is not None:
            try:
                session.close(logout=True)
            except Exception as close_error:
                payload["close_error"] = f"{type(close_error).__name__}: {close_error}"
        attach_json(attachment_name, payload)
    return True


def ge_cli_commands(slot_id: str, port_id: str) -> list[str]:
    port = f"{slot_id}-{port_id}"
    return [
        ge_running_config_command(slot_id, port_id),
        f"show interface ge {port} config",
        f"show interface ge {port} status",
        f"show interface ge {port} pvid",
        f"show interface ge {port} mtu",
        f"show interface ge {port} vlan",
        f"show interface ge {port} vlan outer-tpid",
        f"show interface ge {port} qos",
        f"show interface ge {port} igmp-mld",
    ]


def read_ge_cli_config(
    env_config,
    profile_definition: dict,
    *,
    telephone: str | None = None,
    port_name: str | None = None,
    attachment_name: str = "GE CLI configuration ground truth",
) -> GeCliConfigResult:
    dut = env_config.dut
    commands = ge_cli_commands(dut.ge_slot_id, dut.ge_port_id)
    username, password = ssh_credentials(env_config)
    session = SshCliSession(dut.ssh_host, username, password, timeout=15)
    output_by_command = {}
    try:
        session.connect()
        for command in commands:
            read_options = {"idle_wait": 1.5, "max_wait": 15} if command == commands[0] else {}
            output, _elapsed, _confirmed = session.run_command(command, **read_options)
            output_by_command[command] = output
    finally:
        session.close(logout=True)
    result = compare_ge_cli_config(
        output_by_command,
        profile_definition.get("post_profile_info", {}),
        telephone=dut.ge_telephone if telephone is None else telephone,
        port_name=dut.ge_port_name if port_name is None else port_name,
    )
    attach_json(
        attachment_name,
        {
            "node": dut.node_key,
            "device": dut.device_name,
            "port": f"{dut.ge_slot_id}-{dut.ge_port_id}",
            "matches": result.matches,
            "mismatches": result.mismatches,
            "unverified_fields": result.unverified_fields,
            "commands": output_by_command,
        },
    )
    return result


def compare_ge_cli_config(
    output_by_command: dict[str, str],
    profile_content: dict,
    telephone: str | None,
    port_name: str | None,
) -> GeCliConfigResult:
    normalized_by_command = {
        command: _normalized_output(output)
        for command, output in output_by_command.items()
    }
    all_output = "\n".join(normalized_by_command.values())
    mismatches = []
    if not output_by_command:
        mismatches.append("No CLI output was returned")
    if _contains_cli_error(all_output):
        mismatches.append("One or more IES4204 show commands returned a CLI error")
    running_outputs = [
        output
        for command, output in output_by_command.items()
        if command.lower().startswith("show running-config interface ge ")
    ]
    if not any(canonical_running_config(output) for output in running_outputs):
        mismatches.append("GE running-config output is empty")

    checks = [
        ("speed", profile_content.get("getmplateprofile_portspeed"), (" config", "running-config")),
        ("mtu", profile_content.get("getmplateprofile_portmtu"), (" mtu", "running-config")),
        ("pvid", profile_content.get("getmplateprofile_pvid"), (" pvid", "running-config")),
        ("pbit", profile_content.get("getmplateprofile_pbit"), (" pvid", "running-config")),
        ("algorithm", profile_content.get("getmplateprofile_qosalgorithm"), (" qos", "running-config")),
        ("name", port_name, (" config", "running-config")),
        ("tel", telephone, (" config", "running-config")),
    ]
    for label, expected, command_hints in checks:
        if expected in (None, ""):
            continue
        selected = "\n".join(
            output
            for command, output in normalized_by_command.items()
            if any(hint in command.lower() for hint in command_hints)
        )
        if not _field_value_present(selected, label, str(expected)):
            mismatches.append(f"{label} expected {expected!r} was not found in its CLI output")

    covered = {
        "getmplateprofile_portspeed",
        "getmplateprofile_portmtu",
        "getmplateprofile_pvid",
        "getmplateprofile_pbit",
        "getmplateprofile_qosalgorithm",
    }
    unverified = tuple(sorted(str(key) for key in profile_content if key not in covered))
    return GeCliConfigResult(not mismatches, tuple(mismatches), dict(output_by_command), unverified)


def wait_for_ge_cli_config(
    env_config,
    profile_definition: dict,
    *,
    telephone: str | None = None,
    port_name: str | None = None,
    attachment_name: str = "GE CLI configuration ground truth",
    reader: Callable = read_ge_cli_config,
    timeout: int = 120,
    interval: int = 10,
    consecutive_stable_successes: int = 1,
) -> GeCliConfigResult:
    if consecutive_stable_successes < 1:
        raise ValueError("consecutive_stable_successes must be at least 1")
    deadline = time.monotonic() + timeout
    last = None
    stable_signature = None
    stable_hits = 0
    while True:
        last = reader(
            env_config,
            profile_definition,
            telephone=telephone,
            port_name=port_name,
            attachment_name=attachment_name,
        )
        if last.matches:
            command = ge_running_config_command(env_config.dut.ge_slot_id, env_config.dut.ge_port_id)
            signature = canonical_running_config(last.output_by_command.get(command, ""))
            if signature and signature == stable_signature:
                stable_hits += 1
            else:
                stable_signature = signature
                stable_hits = 1 if signature else 0
            if stable_hits >= consecutive_stable_successes:
                return last
        else:
            stable_signature = None
            stable_hits = 0
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(interval, remaining))
    raise AssertionError("GE CLI configuration did not match REST service data: " + "; ".join(last.mismatches))


def running_config_from_result(result: GeCliConfigResult, slot_id: str, port_id: str) -> str:
    command = ge_running_config_command(slot_id, port_id)
    output = result.output_by_command.get(command)
    if output is None or not canonical_running_config(output):
        raise AssertionError(f"GE CLI result does not contain a usable {command!r} baseline.")
    return output


def monitor_ge_patch_transition(
    env_config,
    *,
    baseline_running_config: str,
    port_name: str,
    telephone: str,
    patch_action: Callable[[], None],
    state_reader: Callable[[], dict],
    timeout: int = 120,
    interval: int = 2,
    success_evidence_grace: int = 20,
) -> GePatchTransitionResult:
    dut = env_config.dut
    command = ge_running_config_command(dut.ge_slot_id, dut.ge_port_id)
    baseline = canonical_running_config(baseline_running_config)
    if not baseline:
        raise AssertionError("PUT CLI baseline is empty; refusing to monitor PATCH reprovision.")

    username, password = ssh_credentials(env_config)
    session = SshCliSession(dut.ssh_host, username, password, timeout=15)
    timeline: list[dict] = []
    snapshots: dict[str, str] = {"put_baseline": baseline_running_config}
    observed_reprovision = False
    observed_cli_cleared = False
    observed_cli_restored = False
    final_service: dict = {}
    final_output = ""
    failure = ""
    started = time.monotonic()
    success_seen_at: float | None = None
    previous_config = baseline

    try:
        session.connect()
        pre_patch_deadline = time.monotonic() + min(timeout, 30)
        pre_patch_attempt = 0
        pre_patch_output = ""
        pre_patch = ()
        while not pre_patch:
            pre_patch_attempt += 1
            pre_patch_output, _elapsed, _confirmed = session.run_command(command, idle_wait=1.5, max_wait=15)
            snapshots[f"pre_patch_attempt_{pre_patch_attempt}"] = pre_patch_output
            pre_patch = canonical_running_config(pre_patch_output)
            if pre_patch:
                break
            remaining = pre_patch_deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError("PUT CLI baseline could not be read before PATCH.")
            time.sleep(min(interval, remaining))
        snapshots["pre_patch"] = pre_patch_output
        if pre_patch != baseline:
            baseline_only = sorted(set(baseline) - set(pre_patch))
            pre_patch_only = sorted(set(pre_patch) - set(baseline))
            snapshots["baseline_only"] = baseline_only
            snapshots["pre_patch_only"] = pre_patch_only
            raise AssertionError(
                "CLI config changed after PUT baseline and before PATCH; refusing ambiguous transition check. "
                f"baseline_only={baseline_only!r}; pre_patch_only={pre_patch_only!r}"
            )
        if not _identity_present(pre_patch_output, port_name, telephone):
            raise AssertionError("PUT CLI baseline does not contain the expected PortName and Telephone.")

        patch_action()
        deadline = time.monotonic() + timeout
        while time.monotonic() <= deadline:
            service = state_reader()
            final_service = service
            state = str(service.get("state") or "")
            normalized_state = state.strip().lower()
            if normalized_state == "reprovision":
                observed_reprovision = True
            if normalized_state == "fail":
                raise AssertionError("GE service entered Fail state during PATCH reprovision.")

            output, _elapsed, _confirmed = session.run_command(command, idle_wait=1.5, max_wait=15)
            final_output = output
            current_config = canonical_running_config(output)
            identity_present = _identity_present(output, port_name, telephone)
            baseline_equal = current_config == baseline
            if not identity_present:
                observed_cli_cleared = True
            if observed_cli_cleared and identity_present and baseline_equal:
                observed_cli_restored = True
            if current_config != previous_config:
                snapshots[f"change_{len(snapshots)}"] = output
                previous_config = current_config

            elapsed = round(time.monotonic() - started, 3)
            timeline.append(
                {
                    "elapsed_seconds": elapsed,
                    "state": state,
                    "identity_present": identity_present,
                    "put_baseline_equal": baseline_equal,
                    "config_line_count": len(current_config),
                }
            )

            final_success = normalized_state == "success"
            evidence_complete = observed_reprovision or (observed_cli_cleared and observed_cli_restored)
            if final_success and evidence_complete and baseline_equal:
                return GePatchTransitionResult(
                    observed_reprovision,
                    observed_cli_cleared,
                    observed_cli_restored,
                    dict(service),
                    output,
                    tuple(timeline),
                )
            if final_success and success_seen_at is None:
                success_seen_at = time.monotonic()
            if success_seen_at is not None and time.monotonic() - success_seen_at >= success_evidence_grace:
                break
            time.sleep(interval)

        if str(final_service.get("state") or "").strip().lower() != "success":
            raise AssertionError("PATCH did not finish with GE service state Success.")
        if canonical_running_config(final_output) != baseline:
            raise AssertionError("PATCH final CLI config does not match the PUT baseline.")
        raise AssertionError(
            "PATCH finished with Success and the PUT config, but neither Reprovision state nor CLI clear/restore was observed."
        )
    except Exception as error:
        failure = str(error)
        raise
    finally:
        session.close(logout=True)
        attach_json(
            "EMS1-6663 PATCH reprovision evidence",
            {
                "node": dut.node_key,
                "device": dut.device_name,
                "port": f"{dut.ge_slot_id}-{dut.ge_port_id}",
                "observed_reprovision": observed_reprovision,
                "observed_cli_cleared": observed_cli_cleared,
                "observed_cli_restored": observed_cli_restored,
                "final_state": final_service.get("state"),
                "failure": failure,
                "timeline": timeline,
                "running_config_snapshots": snapshots,
                "final_running_config": final_output,
            },
        )


def canonical_running_config(output: str) -> tuple[str, ...]:
    lines = []
    for raw_line in str(output).splitlines():
        line = re.sub(r"[ \t]+", " ", raw_line.strip()).lower()
        if not line:
            continue
        if re.fullmatch(r"(?:\S+[>#]\s*)?show running-config interface ge \d+-\d+", line):
            continue
        if line == "current configuration:":
            continue
        if line.startswith("interface ge ") or line == "exit":
            continue
        if re.search(r"[>#]$", line):
            continue
        lines.append(line)
    return tuple(sorted(lines))


def _identity_present(output: str, port_name: str, telephone: str) -> bool:
    return _field_value_present(output, "name", port_name) and _field_value_present(output, "tel", telephone)


def _field_value_present(output: str, label: str, expected: str) -> bool:
    if label in {"pvid", "pbit"} and _pvid_table_value_present(output, label, expected):
        return True
    label_pattern = re.escape(label).replace(r"\ ", r"[\s_-]*")
    value_pattern = re.escape(expected.lower()).replace(r"\-", r"[\s-]*")
    pattern = rf"\b{label_pattern}\b[ \t]*(?:[:=]|\bis\b)?[ \t]*[\"']?{value_pattern}[\"']?(?=[ \t]|$)"
    return bool(re.search(pattern, output, re.IGNORECASE | re.MULTILINE))


def _pvid_table_value_present(output: str, label: str, expected: str) -> bool:
    index = 1 if label == "pvid" else 2
    for line in str(output).splitlines():
        match = re.match(r"^\s*\d+-\d+\s+(\d+)\s+(\d+)\s*$", line)
        if match and match.group(index) == str(expected):
            return True
    return False


def _contains_cli_error(output: str) -> bool:
    return any(marker in output for marker in ("invalid command", "unknown command", "ambiguous command", "incomplete command"))


def _normalized_output(value: str) -> str:
    return re.sub(r"[ \t]+", " ", str(value).lower())