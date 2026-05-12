from __future__ import annotations

import pytest

from cases.case_catalog import case_catalog_payload, catalog_profile_data, catalog_test_cases
from config_loader.profile import load_profile_definitions


@pytest.mark.smoke
def test_case_catalog_contains_all_extracted_cases():
    payload = case_catalog_payload()
    cases = catalog_test_cases()
    assert payload["source_file"].endswith("test_rest_api_neox.py")
    assert payload["test_case_count"] == len(cases) == 169
    assert sum(bool(case["case_ids"]) for case in cases) == 166


@pytest.mark.smoke
def test_case_catalog_profile_data_contains_test_and_validation_data():
    profiles = catalog_profile_data()
    assert len(profiles) == 30
    for name, profile in profiles.items():
        assert profile["profiletype"], name
        assert profile["profilename"], name
        assert "post_profile_info" in profile, name


@pytest.mark.smoke
def test_profiles_yaml_contains_all_catalog_profile_refs():
    profiles = load_profile_definitions()
    refs = {
        ref
        for case in catalog_test_cases()
        for ref in case.get("config_data_refs", [])
        if ref.endswith("_profile_data") or "_profile_data_" in ref
    }
    assert refs <= set(profiles)
