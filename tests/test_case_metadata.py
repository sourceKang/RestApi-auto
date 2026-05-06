from __future__ import annotations

import sys
from types import SimpleNamespace

from utils import case_metadata


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


def test_attach_legacy_case_sets_multi_id_allure_title(monkeypatch):
    titles = []

    fake_allure = SimpleNamespace(
        dynamic=SimpleNamespace(
            label=lambda *_args, **_kwargs: None,
            testcase=lambda *_args, **_kwargs: None,
            title=lambda value: titles.append(value),
        )
    )
    monkeypatch.setitem(sys.modules, "allure", fake_allure)

    case_metadata.attach_legacy_case(
        {
            "case_ids": ["EMS1-6666", "EMS1-6647"],
            "legacy_name": "test_ont_service_workflow",
        }
    )

    assert titles == ["[EMS1-6666][EMS1-6647][test_ont_service_workflow]"]
