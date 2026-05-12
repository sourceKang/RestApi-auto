from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config_loader.simple_yaml import SimpleYamlError, load_simple_yaml


CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"
DEFAULT_PROFILES_FILE = CONFIG_DIR / "profiles.yaml"
JSON_PAYLOAD_FIELDS = {"post_profile_info", "patch_profile_info", "invalid_params_to_test"}


class ProfileConfigError(RuntimeError):
    pass


def load_profile_definitions(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    config_path = Path(path or DEFAULT_PROFILES_FILE)
    try:
        raw = load_simple_yaml(config_path)
    except OSError as error:
        raise ProfileConfigError(f"Cannot load profile YAML configuration from {config_path}: {error}") from error
    except SimpleYamlError as error:
        raise ProfileConfigError(f"Invalid profile YAML configuration in {config_path}: {error}") from error

    profiles = raw.get("profiles")
    if not isinstance(profiles, dict):
        raise ProfileConfigError(f"{config_path} must contain profiles: mapping")

    for name, profile in profiles.items():
        if not isinstance(profile, dict):
            raise ProfileConfigError(f"{config_path} profile {name!r} must be a mapping")
        for field in JSON_PAYLOAD_FIELDS:
            if isinstance(profile.get(field), str):
                try:
                    profile[field] = json.loads(profile[field])
                except json.JSONDecodeError as error:
                    raise ProfileConfigError(
                        f"{config_path} profile {name!r} field {field!r} must contain valid JSON"
                    ) from error
        if not profile.get("profiletype"):
            raise ProfileConfigError(f"{config_path} profile {name!r} must define profiletype")
        if not profile.get("profilename"):
            raise ProfileConfigError(f"{config_path} profile {name!r} must define profilename")
        if "post_profile_info" not in profile:
            raise ProfileConfigError(f"{config_path} profile {name!r} must define post_profile_info")

    return profiles
