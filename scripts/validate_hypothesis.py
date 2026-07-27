#!/usr/bin/env python3
"""
Hard enforcement gate for the pre-registration system (build spec avsnitt 4).

Usage:
    python validate_hypothesis.py <path-to-hypothesis.yaml>

Exits non-zero and prints a clear error if the hypothesis file is missing,
not pre-registered, has no pass_fail_criterion, or (for small-cap
hypotheses) has no tested_capital_levels. Writes nothing to the registry.

Since 2026-07-27 (Risk Manager, code-based enforcement): for any
hypothesis whose pass_fail_criterion mentions friction, this script also
runs validate_friction_usage.py against the hypothesis's strategy code
(convention: /strategies/<id>/backtest.py). A criterion that PROMISES
friction is not enough - the actual backtest code must import AND call
the friction functions, or this gate rejects it. Same principle as the
rest of this file: enforcement is code, not trust that an agent
remembered its instructions.

The Backtester agent MUST run this (or have it enforced via a git
pre-commit hook) before executing any backtest code.
"""

import sys
from pathlib import Path

import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))
from validate_friction_usage import validate_friction_usage  # noqa: E402


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

    criterion_text = str(hypothesis.get("pass_fail_criterion", "")).lower()
    if "friktion" in criterion_text or "friction" in criterion_text:
        hyp_id = hypothesis.get("id")
        strategy_file = REPO_ROOT / "strategies" / str(hyp_id) / "backtest.py"
        friction_result = validate_friction_usage(strategy_file)
        if friction_result.get("error"):
            errors.append(
                f"criterion mentions friction but strategy code could not be checked: "
                f"{friction_result['error']}"
            )
        elif not friction_result["ok"]:
            errors.append(
                f"criterion mentions friction but {strategy_file} does not actually "
                f"import+call: {', '.join(friction_result['missing'])}"
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
