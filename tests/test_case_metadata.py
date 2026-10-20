from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from utils import case_metadata, reporting


pytestmark = pytest.mark.offline


@pytest.fixture(autouse=True)
def fresh_report_state(monkeypatch):
    # attach_case_* registers case IDs in the session-wide report state; a leaked ID makes
    # an offline run write a formal report under reports/<version>/.
    state = reporting.ReportState()
    monkeypatch.setattr(reporting, "REPORT_STATE", state)
    return state


def test_format_case_title_matches_txt_report_prefix():
    assert case_metadata.format_case_title(["EMS1-6643"], "test_get_device_all") == "[EMS1-6643][test_get_device_all]"


def test_attach_case_id_sets_allure_title_like_txt_report(monkeypatch):
    titles = []

    fake_allure = SimpleNamespace(
        dynamic=SimpleNamespace(
            label=lambda *_args, **_kwargs: None,
            testcase=lambda *_args, **_kwargs: None,
            title=lambda value: titles.append(value),
        )
    )
    monkeypatch.setitem(sys.modules, "allure", fake_allure)

    case_metadata.attach_case_id("EMS1-6643", "test_get_device_all", register_txt=False)

    assert titles == ["[EMS1-6643][test_get_device_all]"]


def test_attach_case_metadata_sets_multi_id_allure_title(monkeypatch):
    titles = []

    fake_allure = SimpleNamespace(
        dynamic=SimpleNamespace(
            label=lambda *_args, **_kwargs: None,
            testcase=lambda *_args, **_kwargs: None,
            title=lambda value: titles.append(value),
        )
    )
    monkeypatch.setitem(sys.modules, "allure", fake_allure)

    case_metadata.attach_case_metadata(
        {
            "case_ids": ["EMS1-6666", "EMS1-6647"],
            "name": "test_ont_service_workflow",
        }
    )

    assert titles == ["[EMS1-6666][EMS1-6647][test_ont_service_workflow]"]
