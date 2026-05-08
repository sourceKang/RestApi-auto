from __future__ import annotations

from typing import Any

from utils.allure_helpers import attach_json
from utils.reporting import register_case


def attach_case_metadata(case: dict[str, Any]) -> None:
    case_ids = case.get("case_ids") or []
    name = case.get("name", "")
    for case_id in case_ids:
        register_case(case_id, name)
    try:
        import allure

        for case_id in case_ids:
            allure.dynamic.label("case_id", case_id)
            allure.dynamic.testcase(case_id, case_id)
        allure.dynamic.label("case_name", name)
        if name:
            allure.dynamic.title(format_case_title(case_ids, name))
    except Exception:
        pass

    attach_json(
        "case metadata",
        {
            "case_ids": case_ids,
            "name": name,
            "markers": case.get("markers"),
            "config_data_refs": case.get("config_data_refs"),
            "validation_refs": case.get("validation_refs"),
            "source_line": case.get("source_line"),
        },
    )


def attach_case_id(
    case_id: str | None,
    name: str,
    *,
    register_txt: bool = True,
    summary_group: str | None = None,
) -> None:
    if not case_id:
        return
    if register_txt:
        register_case(case_id, name)
    try:
        import allure

        allure.dynamic.label("case_id", case_id)
        allure.dynamic.testcase(case_id, case_id)
        allure.dynamic.label("case_name", name)
        if name:
            allure.dynamic.title(format_case_title([case_id], name))
        if summary_group:
            allure.dynamic.label("summary_group", summary_group)
    except Exception:
        pass
    attach_json("case metadata", {"case_ids": [case_id], "name": name})


def format_case_title(case_ids: list[str] | tuple[str, ...], name: str) -> str:
    ids = "".join(f"[{case_id}]" for case_id in case_ids if case_id)
    return f"{ids}[{name}]" if ids else name
