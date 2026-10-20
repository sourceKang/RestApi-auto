from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from clients.ssh_cli import SshCliClient
from config_loader import load_environment
from config_loader.hardware import DEFAULT_TEST_TARGETS_FILE, load_hardware_config


@dataclass(frozen=True)
class LineCardInfo:
    slot_id: str
    card: str
    fw_version: str
    state: str


@dataclass(frozen=True)
class TargetSyncResult:
    ok: bool
    reason: str = ""
    changed: bool = False


def sync_target_data_from_cli(
    node: str | None,
    auth_profile: str | None,
    *,
    targets_path: Path = DEFAULT_TEST_TARGETS_FILE,
) -> TargetSyncResult:
    if not node:
        return TargetSyncResult(False, "missing EMS node for target sync")

    try:
        hardware = load_hardware_config(targets_path=targets_path)
        target = hardware.node_target(node)
        if not target:
            return TargetSyncResult(False, f"{node} is not defined in test_targets.yaml")
        if not target.get("slots"):
            return TargetSyncResult(True, f"{node} has no slot-based target data; show lc st sync skipped")

        env_config = load_environment(node=node, auth_profile=auth_profile)
        if env_config.dut.ssh_backend == "openssh_legacy":
            return TargetSyncResult(
                True,
                f"{node} uses openssh_legacy; NeoX show lc st target sync skipped",
            )
        client = SshCliClient(env_config.dut.ssh_host, env_config.readwrite.username, env_config.readwrite.password)
        results = client.run_commands(["show lc st"])
        output = results[0].output if results else ""
        live_cards = parse_show_lc_status(output)
        if not live_cards:
            return TargetSyncResult(False, f"{node} show lc st did not return parseable active line-card data")

        controller_cards = set(str(item) for item in hardware.chassis_rules(str(target.get("chassis", ""))).get("controller_cards", []))
        changed = update_topology_v2_target_slots(targets_path, node, live_cards, controller_cards)
        status = "updated" if changed else "already matches"
        summary = ", ".join(f"slot {card.slot_id} {card.card} {card.fw_version}" for card in desired_slot_order(live_cards, controller_cards))
        return TargetSyncResult(True, f"{node} target data {status}: {summary}", changed=changed)
    except Exception as error:
        return TargetSyncResult(False, f"target data sync failed: {type(error).__name__}: {error}")


def parse_show_lc_status(output: str) -> list[LineCardInfo]:
    cards: list[LineCardInfo] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        match = re.match(r"^\*?\s*(\d+)\s+(\S+)\s+(.+)$", line)
        if not match:
            continue
        slot_id, state, rest = match.groups()
        if state.lower() != "active":
            continue
        columns = re.split(r"\s{2,}", rest.strip())
        if not columns:
            continue
        card = columns[0].strip()
        fw_version = next((column.strip() for column in columns[1:] if column.strip().startswith("V")), "")
        if not card or not fw_version:
            continue
        cards.append(LineCardInfo(slot_id=slot_id, card=card, fw_version=fw_version, state=state))
    return cards


def update_topology_v2_target_slots(
    targets_path: Path,
    node: str,
    live_cards: list[LineCardInfo],
    controller_cards: set[str],
) -> bool:
    original = targets_path.read_text(encoding="utf-8")
    lines = original.splitlines()
    node_start, node_end = find_mapping_block(lines, 2, node)
    slots_header = find_child_key(lines, node_start + 1, node_end, 4, "slots")
    targets_header = find_child_key(lines, node_start + 1, node_end, 4, "test_targets")
    if slots_header is None:
        raise ValueError(f"{node}.slots was not found in {targets_path}")
    slots_end = next_block_boundary(lines, slots_header + 1, node_end, 4)

    existing_blocks = parse_slot_blocks(lines, slots_header + 1, slots_end)
    desired_cards = desired_slot_order(live_cards, controller_cards)
    used_existing: set[str] = set()
    rendered_blocks: list[list[str]] = []

    for card in desired_cards:
        block = existing_blocks.get(card.slot_id)
        source_slot = card.slot_id
        if block is None and card.card in controller_cards:
            source_slot, block = find_reusable_slot_by_role(existing_blocks, used_existing, "controller")
        if block is None:
            block = minimal_slot_block(card, "controller" if card.card in controller_cards else "line")
        else:
            used_existing.add(source_slot)
        rendered_blocks.extend(update_slot_block(block, card))

    new_lines = lines[: slots_header + 1] + rendered_blocks + lines[slots_end:]

    if targets_header is not None:
        offset = len(rendered_blocks) - (slots_end - (slots_header + 1))
        adjusted_node_end = node_end + offset
        adjusted_targets_header = targets_header + offset
        new_lines = replace_report_slots(new_lines, adjusted_targets_header, adjusted_node_end, [card.slot_id for card in desired_cards])

    updated = "\n".join(new_lines) + ("\n" if original.endswith("\n") else "")
    if updated == original:
        return False
    targets_path.write_text(updated, encoding="utf-8")
    return True


def desired_slot_order(live_cards: Iterable[LineCardInfo], controller_cards: set[str]) -> list[LineCardInfo]:
    cards = list(live_cards)
    controllers = [card for card in cards if card.card in controller_cards]
    lines = [card for card in cards if card.card not in controller_cards]
    return sorted(controllers, key=slot_sort_key) + sorted(lines, key=slot_sort_key)


def slot_sort_key(card: LineCardInfo) -> tuple[int, str]:
    try:
        return int(card.slot_id), card.slot_id
    except ValueError:
        return 9999, card.slot_id


def find_mapping_block(lines: list[str], indent: int, key: str) -> tuple[int, int]:
    pattern = re.compile(rf"^ {{{indent}}}{re.escape(key)}:\s*$")
    for index, line in enumerate(lines):
        if not pattern.match(line):
            continue
        return index, next_block_boundary(lines, index + 1, len(lines), indent)
    raise ValueError(f"mapping key {key!r} was not found")


def find_child_key(lines: list[str], start: int, end: int, indent: int, key: str) -> int | None:
    pattern = re.compile(rf"^ {{{indent}}}{re.escape(key)}:\s*(?:#.*)?$")
    for index in range(start, end):
        if pattern.match(lines[index]):
            return index
    return None


def next_block_boundary(lines: list[str], start: int, end: int, indent: int) -> int:
    for index in range(start, end):
        line = lines[index]
        if not line.strip():
            continue
        current_indent = len(line) - len(line.lstrip(" "))
        if current_indent <= indent:
            return index
    return end


def parse_slot_blocks(lines: list[str], start: int, end: int) -> dict[str, list[str]]:
    blocks: dict[str, list[str]] = {}
    index = start
    while index < end:
        match = re.match(r"^      (\S[^:]*):\s*$", lines[index])
        if not match:
            index += 1
            continue
        slot_id = match.group(1).strip().strip('"')
        block_end = index + 1
        while block_end < end and not re.match(r"^      \S[^:]*:\s*$", lines[block_end]):
            block_end += 1
        blocks[slot_id] = lines[index:block_end]
        index = block_end
    return blocks


def find_reusable_slot_by_role(
    blocks: dict[str, list[str]],
    used_existing: set[str],
    role: str,
) -> tuple[str, list[str] | None]:
    for slot_id, block in blocks.items():
        if slot_id in used_existing:
            continue
        if any(re.match(rf"^        role:\s*[\"']?{re.escape(role)}[\"']?\s*$", line) for line in block):
            return slot_id, block
    return "", None


def update_slot_block(block: list[str], card: LineCardInfo) -> list[str]:
    output: list[str] = [f"      {card.slot_id}:"]
    saw_card = False
    saw_fw = False
    for line in block[1:]:
        stripped = line.strip()
        if stripped.startswith("card:"):
            output.append(f"        card: \"{card.card}\"")
            saw_card = True
            continue
        if stripped.startswith("model:"):
            continue
        if stripped.startswith("fw_version:"):
            output.append(f"        fw_version: \"{card.fw_version}\"")
            saw_fw = True
            continue
        output.append(line)
    insert_at = 1
    if not saw_card:
        output.insert(insert_at, f"        card: \"{card.card}\"")
        insert_at += 1
    if not saw_fw:
        output.insert(insert_at + (1 if saw_card else 0), f"        fw_version: \"{card.fw_version}\"")
    return output


def minimal_slot_block(card: LineCardInfo, role: str) -> list[str]:
    return [
        f"      {card.slot_id}:",
        f"        card: \"{card.card}\"",
        f"        fw_version: \"{card.fw_version}\"",
        f"        role: \"{role}\"",
    ]


def replace_report_slots(lines: list[str], targets_header: int, node_end: int, slots: list[str]) -> list[str]:
    rendered = ", ".join(f'"{slot}"' for slot in slots)
    replacement = f"      report_slots: [{rendered}]"
    for index in range(targets_header + 1, node_end):
        if re.match(r"^      report_slots:\s*", lines[index]):
            lines[index] = replacement
            return lines
    lines.insert(targets_header + 1, replacement)
    return lines
