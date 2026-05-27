from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VlanCliExpectation:
    expected_checks: list[str]
    missing: list[str]


def normalize_cli_output(output: str, ignored_line_prefixes: tuple[str, ...] = ()) -> str:
    lines = [line.rstrip() for line in output.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(
        _normalize_cli_line(line)
        for line in lines
        if line.strip() and not _is_ignored_cli_line(line, ignored_line_prefixes) and not _is_prompt_line(line)
    )


def clear_ignored_line_prefixes(feature: str) -> tuple[str, ...]:
    if feature == "nni":
        return ("flow-control ", "speed ")
    return ()


def ge_cli_checks(content: dict[str, Any]) -> list[str]:
    checks = []
    if content.get("portenable") == "enable":
        checks.append("enable")
    if "auto_nego" in content:
        checks.append(f"auto-negotiation {content['auto_nego']}")
    if "flow" in content:
        checks.append(f"flow-control {content['flow']}")
    if "portspeed" in content:
        checks.append(f"speed {content['portspeed']}")
    if "portname" in content:
        checks.append(f"name \"{content['portname']}\"")
    if "arpinspection" in content:
        checks.append(f"arp-inspection {content['arpinspection']}")
    if "copycpbit" in content:
        checks.append(f"vlan copy_cpbit {content['copycpbit']}")
    if "outertpid" in content:
        checks.append(f"vlan outer-tpid {content['outertpid']}")
    if "frametype" in content:
        checks.append(f"frame-type {content['frametype']}")
    return checks


def vlan_cli_expectation(vid: str, payload: dict[str, Any], output: str) -> VlanCliExpectation:
    expected_tokens = vlan_expected_tokens(vid, payload)
    expected_port_states = vlan_expected_port_states(payload)
    expected_checks = expected_tokens + vlan_port_state_checks(expected_port_states)
    missing = _missing_tokens(output, expected_tokens)
    missing.extend(missing_vlan_port_states(output, vid, expected_port_states))
    return VlanCliExpectation(expected_checks=expected_checks, missing=missing)


def vlan_expected_tokens(vid: str, payload: dict[str, Any]) -> list[str]:
    tokens = [vid, f"VLAN Name: {payload['vlanname']}"]
    if payload.get("tpid") == "qinq-tpid":
        tokens.append("QinQ")
    elif payload.get("tpid") == "default-tpid":
        tokens.append("default")
    return tokens


def vlan_expected_port_states(payload: dict[str, Any]) -> dict[int, str]:
    fixed_ports = parse_vlan_ports(payload.get("fixedport"))
    untagged_ports = parse_vlan_ports(payload.get("untaggedport"))
    forbidden_ports = parse_vlan_ports(payload.get("forbiddenport"))
    conflicts = untagged_ports & forbidden_ports
    if conflicts:
        raise AssertionError(f"VLAN payload has overlapping untaggedport/forbiddenport values: {sorted(conflicts)}")

    states: dict[int, str] = {}
    for port in range(1, 13):
        if port in forbidden_ports:
            states[port] = "X"
        elif port in fixed_ports and port in untagged_ports:
            states[port] = "U"
        elif port in fixed_ports:
            states[port] = "T"
        else:
            states[port] = "."
    return states


def parse_vlan_ports(value: Any) -> set[int]:
    if value in (None, ""):
        return set()
    ports: set[int] = set()
    for part in str(value).replace(" ", "").split(","):
        if not part:
            continue
        if "~" in part:
            start, end = part.split("~", 1)
            ports.update(range(int(start), int(end) + 1))
        else:
            ports.add(int(part))
    return ports


def vlan_port_state_checks(expected_states: dict[int, str]) -> list[str]:
    return [f"port {port}={state}" for port, state in sorted(expected_states.items())]


def missing_vlan_port_states(output: str, vid: str, expected_states: dict[int, str]) -> list[str]:
    actual_states = parse_vlan_cli_port_states(output, vid)
    if not actual_states and expected_states:
        return [f"vlan {vid} port table"]
    return [
        f"port {port}={expected_state}"
        for port, expected_state in sorted(expected_states.items())
        if actual_states.get(port) != expected_state
    ]


def parse_vlan_cli_port_states(output: str, vid: str) -> dict[int, str]:
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 13 and parts[0] == vid:
            return {port: parts[port] for port in range(1, 13)}
    return {}


def ont_running_config_tokens(remote_xont: str, content: dict[str, Any]) -> list[str]:
    tokens = [f"interface remote xont {remote_xont}", f"sn {neox_cli_sn(content['sn'])}"]
    registid = content.get("registid")
    if registid:
        tokens.append(f"registration-id {registid}")
    description = content.get("ontdescription")
    if description:
        tokens.append(f"description {description}")
    if content.get("adminstate") == "enable":
        tokens.append("adminstate enable")
    if content.get("ontenable") == "enable":
        tokens.append("no inactive")
    return tokens


def neox_cli_sn(sn: str) -> str:
    try:
        raw = bytes.fromhex(sn)
    except ValueError:
        return sn
    prefix = raw[:4]
    if all(32 <= byte < 127 for byte in prefix):
        return prefix.decode("ascii") + sn[8:]
    return sn


def _missing_tokens(output: str, expected_tokens: list[str]) -> list[str]:
    normalized_output = output.casefold()
    return [token for token in expected_tokens if token.casefold() not in normalized_output]


def _is_ignored_cli_line(line: str, ignored_line_prefixes: tuple[str, ...]) -> bool:
    stripped = line.strip()
    return any(stripped.startswith(prefix) for prefix in ignored_line_prefixes)


def _is_prompt_line(line: str) -> bool:
    return bool(re.fullmatch(r"[\w.:-]+#\s*", line.strip()))


def _normalize_cli_line(line: str) -> str:
    stripped = re.sub(r"^[\w.:-]+#\s+(show\s+.+)$", r"\1", line.strip())
    return re.sub(
        r"\s-?\d+(?:\.\d+)?\s+([A-Za-z]+)\s+(?:(?:\d+d\s+)?(?:\d+h\s+)?\d+m\s+\d+s)\s+",
        r" <rxpwr> \1 <elapsed> ",
        stripped,
    )
