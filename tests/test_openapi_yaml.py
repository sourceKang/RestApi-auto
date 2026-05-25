from __future__ import annotations

import os
from pathlib import Path

import pytest

from cases.openapi_contract import (
    build_openapi_contract,
    configured_openapi_yaml_file,
    diff_contracts,
    format_contract_differences,
    load_baseline_contract,
    load_openapi_document,
    normalize_ems_version,
    openapi_version_dir_name,
)
from config_loader.settings import DEFAULT_EMS_FILE
from config_loader.simple_yaml import load_simple_yaml
from utils.case_metadata import attach_case_id


@pytest.mark.openapi
@pytest.mark.smoke
def test_openapi_yaml_contract_matches_baseline():
    attach_case_id("EMS1-7116", "YAML File")

    configured_version = _configured_ems_version()
    openapi_file = configured_openapi_yaml_file(configured_version)
    document = load_openapi_document(openapi_file)

    info = document.get("info", {})
    actual_info_version = info.get("version", "") if isinstance(info, dict) else ""
    expected_version = normalize_ems_version(configured_version)
    actual_version = normalize_ems_version(actual_info_version)
    assert actual_version == expected_version, (
        f"{openapi_file} info.version {actual_version!r} does not match "
        f"configured EMS version {expected_version!r}"
    )

    expected_contract = load_baseline_contract()
    actual_contract = build_openapi_contract(document)
    differences = diff_contracts(expected_contract, actual_contract)
    assert not differences, (
        f"{openapi_file} OpenAPI contract differs from baseline:\n"
        f"{format_contract_differences(differences)}"
    )


def _configured_ems_version() -> str:
    ems_file = Path(os.environ.get("EMS_YAML_FILE", DEFAULT_EMS_FILE))
    raw = load_simple_yaml(ems_file)
    ems = raw.get("ems", {}) if isinstance(raw, dict) else {}
    return str(ems.get("version", ""))


def test_openapi_version_dir_name_uses_ems_release_folder():
    assert openapi_version_dir_name("03.00.11 (AAVV.221) b2") == "03.00.11 (AAVV.221)"
