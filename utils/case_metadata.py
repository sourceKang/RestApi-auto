from __future__ import annotations

from typing import Any

from utils.allure_helpers import attach_json
from utils.reporting import register_case


def attach_legacy_case(case: dict[str, Any]) -> None:
    case_ids = case.get("case_ids") or []
    for case_id in case_ids:
        register_case(case_id, case.get("legacy_name", ""))
    try:
        import allure

        for case_id in case_ids:
            allure.dynamic.label("case_id", case_id)
            allure.dynamic.testcase(case_id, case_id)
        allure.dynamic.label("legacy_name", case.get("legacy_name", ""))
    except Exception:
        pass

    attach_json(
        "legacy case metadata",
        {
            "case_ids": case_ids,
            "legacy_name": case.get("legacy_name"),
            "markers": case.get("markers"),
            "config_data_refs": case.get("config_data_refs"),
            "validation_refs": case.get("validation_refs"),
            "source_line": case.get("source_line"),
        },
    )


def attach_case_id(case_id: str | None, name: str) -> None:
    if not case_id:
        return
    register_case(case_id, name)
    try:
        import allure

        allure.dynamic.label("case_id", case_id)
        allure.dynamic.testcase(case_id, case_id)
        allure.dynamic.label("legacy_name", name)
    except Exception:
        pass
    attach_json("legacy case metadata", {"case_ids": [case_id], "legacy_name": name})
