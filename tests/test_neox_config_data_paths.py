from __future__ import annotations

import re
from pathlib import Path

from services.neox_config.service import (
    NEOX_CONFIG_DATA_FILES,
    NEOX_CONFIG_DIR,
    NEOX_PROFILE_TYPES,
    PROFILE_MINMAX_PAYLOAD_DIR,
)


CONFIG_PATH_PATTERN = re.compile(r"configs/neox_config/[A-Za-z0-9_./-]+\.(?:json|ya?ml|md)")


def test_neox_config_data_files_exist():
    missing = [str(path) for path in NEOX_CONFIG_DATA_FILES if not path.exists()]
    assert not missing


def test_neox_profile_split_minmax_files_exist():
    missing = []
    for profile_type in NEOX_PROFILE_TYPES:
        path = PROFILE_MINMAX_PAYLOAD_DIR / f"{profile_type}.json"
        if not path.exists():
            missing.append(str(path))
    assert not missing


def test_neox_config_internal_path_references_exist():
    missing = []
    root = NEOX_CONFIG_DIR.parents[1]

    for path in NEOX_CONFIG_DIR.rglob("*"):
        if path.suffix not in {".json", ".yaml", ".yml", ".md"}:
            continue
        for match in CONFIG_PATH_PATTERN.findall(path.read_text(encoding="utf-8")):
            target = root / Path(match)
            if not target.exists():
                missing.append(f"{path}: {match}")

    assert not missing
