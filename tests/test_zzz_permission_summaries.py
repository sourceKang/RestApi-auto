from __future__ import annotations

import pytest

from utils.allure_helpers import attach_json, allure_step
from utils.case_metadata import attach_case_id
from utils.reporting import permission_summary_breakdown


@pytest.mark.summary
def test_readonly_permission_summary_allure():
    attach_case_id(
        "EMS1-7109",
        "readonly_permission_summary",
        register_txt=False,
        summary_group="PERM-RO",
    )
    _assert_permission_summary("readonly")


@pytest.mark.summary
def test_noaccess_permission_summary_allure():
    attach_case_id(
        "EMS1-7110",
        "noaccess_permission_summary",
        register_txt=False,
        summary_group="PERM-NA",
    )
    _assert_permission_summary("noaccess")


def _assert_permission_summary(role: str) -> None:
    breakdown = permission_summary_breakdown(role)
    with allure_step(f"Summarize {role} permission results for txt/allure comparison"):
        attach_json("permission summary breakdown", breakdown)

    if breakdown["total"] == 0:
        pytest.skip(f"No collected {role} permission cases were run before the summary testcase.")

    failed_items = breakdown["failed_items"]
    if failed_items:
        failed_names = []
        for item in failed_items:
            label = item["nodeid"]
            if item["case_ids"]:
                label = f"{label} ({', '.join(item['case_ids'])})"
            failed_names.append(label)
        pytest.fail(
            f"{breakdown['case_id']} failed with {len(failed_items)} failing member(s): "
            + "; ".join(failed_names)
        )
