#!/usr/bin/env python3
"""
Kod-baserad kontroll: Backtester får INTE köra en strategis kod förrän
Coder-B (oberoende, kritisk granskare - se /agents/coder_b/ROLE.md) har
godkänt den i strategins code_review.yaml. En prompt-instruktion om att
"Coder-B ska granska innan Backtester kör" räcker inte ensam - det är
exakt den typen av tillit till att en agent kommer ihåg sin roll som
spec-dokumentet (avsnitt 4, "ENFORCEMENT ÄR KOD") varnar för. Samma
princip som validate_hypothesis.py och validate_friction_usage.py.

Kräver, i /strategies/HYP-XXX/code_review.yaml:
  - coder_b_approved: true (exakt boolean true, inte "true" som sträng,
    inte frånvarande)
  - coder_b_notes: en ICKE-TOM konkret motivering (varken godkännande
    eller underkännande utan förklaring accepteras)
  - revision_history: minst en post (granskningsspåret får aldrig vara
    tomt - även en första, godkänd granskning ska loggas)

Usage:
    python validate_code_review.py <path-till-code_review.yaml>
"""

import sys
from pathlib import Path

import yaml


def validate_code_review(path: Path) -> dict:
    path = Path(path)
    if not path.is_file():
        return {"ok": False, "error": f"code_review.yaml finns inte: {path}"}

    with path.open("r", encoding="utf-8") as f:
        try:
            review = yaml.safe_load(f) or {}
        except yaml.YAMLError as exc:
            return {"ok": False, "error": f"ogiltig YAML i {path}: {exc}"}

    errors = []

    if review.get("coder_b_approved") is not True:
        errors.append(
            f"coder_b_approved är inte true (värde: {review.get('coder_b_approved')!r}) "
            "- Coder-B måste explicit godkänna, tystnad/frånvaro räknas inte"
        )

    if not review.get("coder_b_notes"):
        errors.append(
            "coder_b_notes är tomt - måste innehålla konkret motivering, "
            "både vid godkännande och underkännande"
        )

    if not review.get("revision_history"):
        errors.append(
            "revision_history saknas eller är tom - varje granskningsomgång "
            "måste loggas, även en första godkänd granskning"
        )

    return {"ok": len(errors) == 0, "errors": errors}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_code_review.py <path-till-code_review.yaml>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    result = validate_code_review(path)

    if result.get("error"):
        print(f"REJECTED: {result['error']}", file=sys.stderr)
        return 1

    if not result["ok"]:
        print(f"REJECTED: {path} - koden är INTE godkänd för Backtester:", file=sys.stderr)
        for err in result["errors"]:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"OK: {path} - Coder-B har godkänt koden, Backtester får köra den.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
