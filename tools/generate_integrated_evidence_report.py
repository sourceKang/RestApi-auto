"""CLI for the integrated HTML evidence report; the implementation is utils/integrated_evidence_report.py."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.integrated_evidence_report import (  # noqa: E402
    load_allure_results,
    parse_txt_report,
    write_integrated_evidence_report,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--txt-report", required=True, type=Path)
    parser.add_argument("--legacy-html", required=True, type=Path)
    parser.add_argument("--allure-dir", required=True, type=Path)
    parser.add_argument("--stdout-log", required=False, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    output = write_integrated_evidence_report(
        txt_report=args.txt_report,
        legacy_html=args.legacy_html,
        allure_dir=args.allure_dir,
        stdout_log=args.stdout_log,
        output=args.output,
    )
    metadata, cases = parse_txt_report(args.txt_report)
    results = load_allure_results(args.allure_dir)
    print(f"Wrote {output} with {len(cases)} cases and {len(results)} Allure result records.")


if __name__ == "__main__":
    main()
