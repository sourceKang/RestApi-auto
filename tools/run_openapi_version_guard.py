from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the per-version OpenAPI YAML and live Swagger key guard.",
    )
    parser.add_argument(
        "--swagger-url",
        default=None,
        help="Swagger UI or /v3/api-docs URL. Defaults to the selected EMS target in configs/ems.yaml.",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Run only local OpenAPI YAML/baseline checks without connecting to live Swagger.",
    )
    parser.add_argument(
        "--collect-all",
        action="store_true",
        help="Do not stop at the first failure. Useful when diagnosing OpenAPI YAML versus Swagger key drift.",
    )
    parser.add_argument(
        "--allure-html",
        action="store_true",
        help="Also ask pytest to generate an Allure HTML report.",
    )
    args = parser.parse_args()

    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_openapi_yaml.py",
    ]
    if not args.collect_all:
        command.append("-x")
    if not args.local_only:
        command.append("--run-live-swagger-check")
        if args.swagger_url:
            command.extend(["--neox-swagger-api-docs-url", args.swagger_url])
    if args.allure_html:
        command.append("--generate-allure-html")

    print("Running OpenAPI version guard:", flush=True)
    print(" ".join(_quote(part) for part in command), flush=True)
    return subprocess.call(command, cwd=ROOT)


def _quote(value: str) -> str:
    if not any(char.isspace() for char in value):
        return value
    return f'"{value}"'


if __name__ == "__main__":
    raise SystemExit(main())
