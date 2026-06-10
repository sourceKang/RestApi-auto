from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cases.openapi_contract import (  # noqa: E402
    BASELINE_CONTRACT_FILE,
    BASELINE_YAML_FILE,
    build_openapi_contract,
    build_openapi_yaml_document,
    configured_openapi_yaml_file,
    load_openapi_document,
    openapi_file_date,
)
from config_loader.settings import DEFAULT_EMS_FILE  # noqa: E402
from config_loader.simple_yaml import load_simple_yaml  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Update OpenAPI contract and full YAML baselines.")
    parser.add_argument(
        "--openapi-yaml",
        type=Path,
        default=None,
        help="OpenAPI YAML file to use. Defaults to the YAML resolved from configs/ems.yaml.",
    )
    parser.add_argument(
        "--contract-only",
        action="store_true",
        help="Update only cases/openapi_contract_baseline.json.",
    )
    parser.add_argument(
        "--yaml-only",
        action="store_true",
        help="Update only cases/openapi_yaml_baseline.json.",
    )
    args = parser.parse_args()

    if args.contract_only and args.yaml_only:
        parser.error("--contract-only and --yaml-only cannot be used together.")

    openapi_file = args.openapi_yaml or configured_openapi_yaml_file(_configured_ems_version())
    document = load_openapi_document(openapi_file)
    source = _source_metadata(openapi_file)

    if not args.yaml_only:
        _write_json(BASELINE_CONTRACT_FILE, {"contract": build_openapi_contract(document), "source": source})
        print(f"Updated {BASELINE_CONTRACT_FILE}")

    if not args.contract_only:
        _write_json(BASELINE_YAML_FILE, {"document": build_openapi_yaml_document(document), "source": source})
        print(f"Updated {BASELINE_YAML_FILE}")

    return 0


def _source_metadata(openapi_file: Path) -> dict[str, Any]:
    return {
        "file_date": openapi_file_date(openapi_file),
        "file_name": openapi_file.name,
    }


def _configured_ems_version() -> str:
    raw = load_simple_yaml(DEFAULT_EMS_FILE)
    ems = raw.get("ems", {}) if isinstance(raw, dict) else {}
    return str(ems.get("version", ""))


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
