from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


METHODOLOGY_FILE = Path(__file__).resolve().parent.parent / "configs" / "test_methodology.json"
METHODOLOGY_STATUSES = frozenset({"covered", "partial", "gap"})
PQA_METHODOLOGY_CRITERIA = frozenset(
    {
        "parameter_boundaries",
        "string_whitespace_special_characters",
        "maximum_capacity",
        "error_messages",
        "crud_controls",
        "relationship_conflicts",
        "delete_nonexistent",
        "persistence_backup_restore_reboot",
        "nondefault_maximum_names",
        "workflow_interruption",
        "stress_overnight",
        "scenario_integration",
        "state_transition_sequences",
        "dynamic_table_concurrency",
    }
)


@dataclass(frozen=True)
class MethodologyCriterion:
    criterion_id: str
    title: str
    source_slides: tuple[int, ...]
    status: str
    risk: str
    evidence: tuple[str, ...]
    next_actions: tuple[str, ...]
    safety_gate: str | None = None


def load_methodology_criteria(path: str | Path | None = None) -> tuple[MethodologyCriterion, ...]:
    source = Path(path) if path else METHODOLOGY_FILE
    raw = json.loads(source.read_text(encoding="utf-8"))
    if raw.get("version") != 1:
        raise ValueError("test_methodology.json must declare version 1")
    criteria = raw.get("criteria")
    if not isinstance(criteria, list):
        raise ValueError("test_methodology.json criteria must be a list")
    return tuple(_criterion_from_raw(item) for item in criteria)


def load_methodology_source(path: str | Path | None = None) -> dict[str, Any]:
    source = Path(path) if path else METHODOLOGY_FILE
    raw = json.loads(source.read_text(encoding="utf-8"))
    value = raw.get("source")
    if not isinstance(value, dict):
        raise ValueError("test_methodology.json source must be an object")
    return value


def evidence_file(evidence: str) -> Path:
    relative_path = evidence.split("::", 1)[0]
    return METHODOLOGY_FILE.parent.parent / Path(relative_path)


def _criterion_from_raw(item: Any) -> MethodologyCriterion:
    if not isinstance(item, dict):
        raise ValueError("Each methodology criterion must be an object")
    required = ("id", "title", "source_slides", "status", "risk")
    missing = [key for key in required if not item.get(key)]
    if missing:
        raise ValueError(f"Methodology criterion is missing: {', '.join(missing)}")
    status = str(item["status"])
    if status not in METHODOLOGY_STATUSES:
        raise ValueError(f"Unsupported methodology status: {status}")
    return MethodologyCriterion(
        criterion_id=str(item["id"]),
        title=str(item["title"]),
        source_slides=tuple(int(slide) for slide in item["source_slides"]),
        status=status,
        risk=str(item["risk"]),
        evidence=tuple(str(value) for value in item.get("evidence", [])),
        next_actions=tuple(str(value) for value in item.get("next_actions", [])),
        safety_gate=str(item["safety_gate"]) if item.get("safety_gate") else None,
    )
