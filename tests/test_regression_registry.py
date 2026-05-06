from __future__ import annotations

from automation.regression import load_regression_cases


def test_regression_registry_loads_empty_default_plan():
    assert load_regression_cases() == ()
