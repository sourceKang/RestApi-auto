from __future__ import annotations

import json

import pytest

from config_loader.profile import ProfileConfigError, load_profile_definitions


def _profile_yaml(config_key: str, profile_name: str) -> str:
    payload = json.dumps({"enabled": "1"})
    return (
        "profiles:\n"
        f"  {config_key}:\n"
        "    profiletype: 'ExampleProfile'\n"
        f"    profilename: '{profile_name}'\n"
        "    post_profile_info: |\n"
        f"      {payload}\n"
    )


def test_default_profile_directory_loads_all_unique_definitions():
    profiles = load_profile_definitions()

    assert len(profiles) == 45
    assert "ont_alarm_profile_data" in profiles
    assert "ont_alarm_profile_data_1" not in profiles
    identities = {(item["profiletype"], item["profilename"]) for item in profiles.values()}
    assert len(identities) == len(profiles)


def test_profile_loader_keeps_single_file_compatibility(tmp_path):
    profile_file = tmp_path / "profiles.yaml"
    profile_file.write_text(_profile_yaml("example_profile_data", "#Example"), encoding="utf-8")

    profiles = load_profile_definitions(profile_file)

    assert profiles["example_profile_data"]["post_profile_info"] == {"enabled": "1"}


def test_profile_directory_rejects_duplicate_config_keys(tmp_path):
    (tmp_path / "manifest.yaml").write_text(
        'version: 1\nfiles: ["one.yaml", "two.yaml"]\n',
        encoding="utf-8",
    )
    (tmp_path / "one.yaml").write_text(_profile_yaml("duplicate_data", "#One"), encoding="utf-8")
    (tmp_path / "two.yaml").write_text(_profile_yaml("duplicate_data", "#Two"), encoding="utf-8")

    with pytest.raises(ProfileConfigError, match="Duplicate profile config key"):
        load_profile_definitions(tmp_path)


def test_profile_directory_rejects_duplicate_profile_identities(tmp_path):
    (tmp_path / "manifest.yaml").write_text(
        'version: 1\nfiles: ["one.yaml", "two.yaml"]\n',
        encoding="utf-8",
    )
    (tmp_path / "one.yaml").write_text(_profile_yaml("first_data", "#Same"), encoding="utf-8")
    (tmp_path / "two.yaml").write_text(_profile_yaml("second_data", "#Same"), encoding="utf-8")

    with pytest.raises(ProfileConfigError, match="duplicate profile identity"):
        load_profile_definitions(tmp_path)
