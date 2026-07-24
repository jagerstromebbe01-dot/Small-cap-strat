#!/usr/bin/env python3
"""
Hard enforcement gate for the pre-registration system (build spec avsnitt 4).

Usage:
    python validate_hypothesis.py <path-to-hypothesis.yaml>

Exits non-zero and prints a clear error if the hypothesis file is missing,
not pre-registered, has no pass_fail_criterion, or (for small-cap
hypotheses) has no tested_capital_levels. Writes nothing to the registry.

The Backtester agent MUST run this (or have it enforced via a git
pre-commit hook) before executing any backtest code.
"""

import sys
from pathlib import Path

import yaml


def validate(path: Path) -> list[str]:
    errors = []

    if not path.is_file():
        return [f"hypothesis file not found: {path}"]

    with path.open("r", encoding="utf-8") as f:
        hypothesis = yaml.safe_load(f) or {}

    if hypothesis.get("status") != "pre-registered":
        errors.append(
            f"status must be 'pre-registered', got: {hypothesis.get('status')!r}"
        )

    if not hypothesis.get("pass_fail_criterion"):
        errors.append("pass_fail_criterion is empty — must be locked before any backtest runs")

    universe = str(hypothesis.get("universe", "")).lower()
    if "small-cap" in universe or "small cap" in universe:
        if not hypothesis.get("tested_capital_levels"):
            errors.append(
                "tested_capital_levels is empty — required for all small-cap hypotheses"
            )

    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_hypothesis.py <path-to-hypothesis.yaml>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    errors = validate(path)

    if errors:
        print(f"REJECTED: {path} failed pre-registration validation:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"OK: {path} is a validly pre-registered hypothesis.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
