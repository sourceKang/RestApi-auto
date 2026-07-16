from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config_loader.simple_yaml import SimpleYamlError, load_simple_yaml


CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"
DEFAULT_PROFILES_DIR = CONFIG_DIR / "profiles"
DEFAULT_PROFILES_MANIFEST = DEFAULT_PROFILES_DIR / "manifest.yaml"
JSON_PAYLOAD_FIELDS = {"post_profile_info", "patch_profile_info", "invalid_params_to_test"}


class ProfileConfigError(RuntimeError):
    pass


def load_profile_definitions(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    config_path = Path(path) if path is not None else DEFAULT_PROFILES_DIR
    if config_path.is_dir():
        return _load_profile_directory(config_path)
    profiles = _load_profile_file(config_path)
    _validate_unique_profile_identities(profiles, config_path)
    return profiles


def _load_profile_directory(config_dir: Path) -> dict[str, dict[str, Any]]:
    manifest_path = config_dir / "manifest.yaml"
    manifest = _load_yaml(manifest_path)
    if manifest.get("version") != 1:
        raise ProfileConfigError(f"{manifest_path} must declare version: 1")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ProfileConfigError(f"{manifest_path} must define a non-empty files list")

    profiles: dict[str, dict[str, Any]] = {}
    loaded_files: set[str] = set()
    for entry in files:
        if not isinstance(entry, str) or Path(entry).name != entry or not entry.endswith(".yaml"):
            raise ProfileConfigError(f"{manifest_path} contains invalid profile file entry: {entry!r}")
        if entry == "manifest.yaml" or entry in loaded_files:
            raise ProfileConfigError(f"{manifest_path} contains duplicate or recursive entry: {entry!r}")
        loaded_files.add(entry)

        profile_path = config_dir / entry
        for name, profile in _load_profile_file(profile_path).items():
            if name in profiles:
                raise ProfileConfigError(f"Duplicate profile config key {name!r} found in {profile_path}")
            profiles[name] = profile

    _validate_unique_profile_identities(profiles, manifest_path)
    return profiles


def _load_yaml(config_path: Path) -> dict[str, Any]:
    try:
        return load_simple_yaml(config_path)
    except OSError as error:
        raise ProfileConfigError(f"Cannot load profile YAML configuration from {config_path}: {error}") from error
    except SimpleYamlError as error:
        raise ProfileConfigError(f"Invalid profile YAML configuration in {config_path}: {error}") from error


def _load_profile_file(config_path: Path) -> dict[str, dict[str, Any]]:
    raw = _load_yaml(config_path)
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


def _validate_unique_profile_identities(profiles: dict[str, dict[str, Any]], source: Path) -> None:
    identities: dict[tuple[str, str], str] = {}
    for name, profile in profiles.items():
        identity = (str(profile["profiletype"]), str(profile["profilename"]))
        previous = identities.get(identity)
        if previous is not None:
            raise ProfileConfigError(
                f"{source} defines duplicate profile identity {identity[0]}/{identity[1]} "
                f"for config keys {previous!r} and {name!r}"
            )
        identities[identity] = name
