from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SECRET_KEY = re.compile(
    r"^\s*-?\s*(?P<key>[A-Za-z0-9_]*(?:password|passwd|token|devkey|secret|api_key)[A-Za-z0-9_]*)\s*:\s*(?P<value>.*)$",
    re.IGNORECASE,
)
ENV_REFERENCE = re.compile(r"^\$\{(?P<var>[A-Za-z_][A-Za-z0-9_]*)(?::-(?P<default>[^}]*))?\}$")
PLACEHOLDER_DEFAULT = re.compile(
    r"^(?:|change_me|example_[a-z0-9_]+|[A-Z0-9_]*(?:CHANGE|SET|REPLACE|PLACEHOLDER)[A-Z0-9_]*)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    key: str
    reason: str


def _strip_value(raw: str) -> str:
    value = raw.strip()
    if value[:1] in {'"', "'"}:
        quote = value[0]
        end = value.find(quote, 1)
        return value[1:end] if end > 0 else value[1:]
    return value.split(" #", 1)[0].strip()


def _reason(value: str) -> str | None:
    """Return why a secret-like value is unsafe to commit, or None when it is a placeholder."""
    if value in {"", "~", "null"}:
        return None
    reference = ENV_REFERENCE.match(value)
    if reference is None:
        return "literal value; use ${ENV_VAR} or ${ENV_VAR:-change_me}"
    if not PLACEHOLDER_DEFAULT.match(reference.group("default") or ""):
        return "environment default is not a placeholder"
    return None


def scan_text(text: str, path: str) -> list[Finding]:
    findings = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = SECRET_KEY.match(line)
        if match is None:
            continue
        reason = _reason(_strip_value(match.group("value")))
        if reason:
            findings.append(Finding(path, number, match.group("key"), reason))
    return findings


def tracked_config_files() -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "--", "configs/*.yaml", "configs/*.yml"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [ROOT / name for name in output.splitlines() if name]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fail when a tracked config YAML holds a plaintext password, token, devKey or secret. "
            "Only file, line and key are printed, never the value."
        ),
    )
    parser.add_argument("paths", nargs="*", type=Path, help="Files to scan. Defaults to tracked configs/**/*.yaml.")
    args = parser.parse_args()

    paths = args.paths or tracked_config_files()
    findings = []
    for path in paths:
        display = path.resolve().relative_to(ROOT).as_posix() if path.resolve().is_relative_to(ROOT) else str(path)
        findings.extend(scan_text(path.read_text(encoding="utf-8-sig"), display))

    for finding in findings:
        print(f"{finding.path}:{finding.line}: {finding.key}: {finding.reason}")
    print(f"Scanned {len(paths)} config file(s); {len(findings)} plaintext secret finding(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
