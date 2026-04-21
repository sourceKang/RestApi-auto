from __future__ import annotations

import pytest

from cases.neox_legacy import legacy_payload, legacy_profile_data, legacy_test_cases


@pytest.mark.smoke
def test_neox_legacy_registry_contains_all_extracted_cases():
    payload = legacy_payload()
    cases = legacy_test_cases()
    assert payload["source_file"].endswith("test_rest_api_neox.py")
    assert payload["test_case_count"] == len(cases) == 169
    assert sum(bool(case["case_ids"]) for case in cases) == 166


@pytest.mark.smoke
def test_neox_legacy_profile_data_contains_test_and_validation_data():
    profiles = legacy_profile_data()
    assert len(profiles) == 30
    for name, profile in profiles.items():
        assert profile["profiletype"], name
        assert profile["profilename"], name
        assert "post_profile_info" in profile, name
