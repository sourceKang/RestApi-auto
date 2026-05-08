from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config_loader.simple_yaml import load_simple_yaml


REGRESSION_CASES_FILE = Path(__file__).resolve().parent.parent / "configs" / "regression_cases.yaml"


@dataclass(frozen=True)
class RegressionCase:
    regression_id: str
    title: str
    domain: str
    runner: str
    status: str = "active"
    customer_issue: str | None = None
    severity: str | None = None
    linked_case_ids: tuple[str, ...] = ()
    markers: tuple[str, ...] = ("regression",)
    requires: dict[str, Any] | None = None


def load_regression_cases(path: str | Path | None = None) -> tuple[RegressionCase, ...]:
    raw = load_simple_yaml(Path(path) if path else REGRESSION_CASES_FILE)
    if not isinstance(raw, dict):
        raise ValueError("regression_cases.yaml must contain a mapping")
    if raw.get("version") != 1:
        raise ValueError("regression_cases.yaml must declare version: 1")
    cases = raw.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("regression_cases.yaml cases must be a list")
    return tuple(_case_from_raw(item) for item in cases)


def _case_from_raw(item: Any) -> RegressionCase:
    if not isinstance(item, dict):
        raise ValueError("Each regression case must be a mapping")
    required = ("id", "title", "domain", "runner")
    missing = [field for field in required if not item.get(field)]
    if missing:
        raise ValueError(f"Regression case is missing required field(s): {', '.join(missing)}")
    linked_case_ids = item.get("linked_case_ids", [])
    markers = item.get("markers", ["regression"])
    requires = item.get("requires")
    return RegressionCase(
        regression_id=str(item["id"]),
        title=str(item["title"]),
        domain=str(item["domain"]),
        runner=str(item["runner"]),
        status=str(item.get("status", "active")),
        customer_issue=str(item["customer_issue"]) if item.get("customer_issue") else None,
        severity=str(item["severity"]) if item.get("severity") else None,
        linked_case_ids=tuple(str(case_id) for case_id in linked_case_ids),
        markers=tuple(str(marker) for marker in markers),
        requires=requires if isinstance(requires, dict) else None,
    )
