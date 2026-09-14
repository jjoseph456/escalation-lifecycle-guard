"""Command-line interface for escalation lifecycle validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .guard import Finding, validate_cases


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate support escalation lifecycle risks from JSON case data."
    )
    parser.add_argument("input", type=Path, help="Path to a JSON object containing cases.")
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format. Defaults to text.",
    )
    parser.add_argument(
        "--max-update-age-days",
        type=int,
        default=7,
        help="Maximum age for a human update on an open escalation. Defaults to 7.",
    )
    return parser


def load_cases(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError as error:
        raise ValueError(f"Input file does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Input is not valid JSON: {error.msg}") from error

    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise ValueError("Input must be a JSON object with a cases array.")

    return data["cases"]


def render_text(findings: list[Finding], case_count: int) -> str:
    if not findings:
        return f"Checked {case_count} case(s): no lifecycle risks found."

    lines: list[str] = []
    for finding in findings:
        lines.extend(
            (
                f"{finding.severity.upper():<7} {finding.case_id}  {finding.rule}",
                f"        {finding.message}",
            )
        )

    counts = {
        severity: sum(finding.severity == severity for finding in findings)
        for severity in ("high", "medium", "low")
    }
    lines.append("")
    lines.append(
        f"Checked {case_count} case(s): {counts['high']} high, "
        f"{counts['medium']} medium, {counts['low']} low."
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cases = load_cases(args.input)
        findings = validate_cases(
            cases, max_update_age_days=args.max_update_age_days
        )
    except ValueError as error:
        print(f"error: {error}")
        return 1

    if args.format == "json":
        print(
            json.dumps(
                {
                    "case_count": len(cases),
                    "findings": [finding.to_dict() for finding in findings],
                },
                indent=2,
            )
        )
    else:
        print(render_text(findings, len(cases)))

    return 2 if any(finding.severity == "high" for finding in findings) else 0
