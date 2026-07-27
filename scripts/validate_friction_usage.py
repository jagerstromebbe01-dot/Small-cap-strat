#!/usr/bin/env python3
"""
Kod-baserad kontroll: verifierar att en hypotes' backtest-kod FAKTISKT
importerar OCH anropar friktionsfunktionerna (Corwin-Schultz-spread,
borrow-kostnad) - inte bara att pass_fail_criterion NÄMNER friktion i
text. Stänger gapet mellan "kriteriet säger att friktion ska ingå" och
"koden faktiskt gör det".

Ägs av Risk Manager-rollen, se /agents/risk_manager/ROLE.md. Detta är
samma princip som scripts/validate_hypothesis.py: enforcement är kod,
inte tillit till att en agent "kom ihåg" att implementera det kriteriet
redan lovar.

Analysmetod: parsar källkoden som ett syntaxträd (ast-modulen) och
kontrollerar två separata saker för varje krävd funktion:
  1. Namnet är IMPORTERAT någonstans i filen.
  2. Namnet förekommer som ett faktiskt FUNKTIONSANROP någonstans.
Bara import utan anrop (eller anrop av en lokal funktion med samma namn
utan att ha importerat den riktiga) räknas INTE som godkänt - båda
villkoren måste vara sanna.

Usage:
    python validate_friction_usage.py <path-till-strategifil.py>
"""

import ast
import sys
from pathlib import Path

REQUIRED_FRICTION_FUNCTIONS = ["corwin_schultz_spread", "borrow_cost"]


def _find_imported_names(tree: ast.AST) -> set:
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.asname or alias.name.split(".")[0])
    return imported


def _find_called_names(tree: ast.AST) -> set:
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called.add(func.id)
            elif isinstance(func, ast.Attribute):
                called.add(func.attr)
    return called


def validate_friction_usage(strategy_file: Path) -> dict:
    """
    Returnerar {"ok": bool, "missing": [...], "found_imports": [...],
    "found_calls": [...]} eller {"ok": False, "error": "..."} om filen
    saknas eller inte går att parsa.
    """
    strategy_file = Path(strategy_file)
    if not strategy_file.is_file():
        return {"ok": False, "error": f"strategifilen finns inte: {strategy_file}"}

    source = strategy_file.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(strategy_file))
    except SyntaxError as exc:
        return {"ok": False, "error": f"syntaxfel i {strategy_file}: {exc}"}

    imported = _find_imported_names(tree)
    called = _find_called_names(tree)

    missing = [
        fn for fn in REQUIRED_FRICTION_FUNCTIONS
        if fn not in imported or fn not in called
    ]

    return {
        "ok": len(missing) == 0,
        "missing": missing,
        "found_imports": sorted(imported & set(REQUIRED_FRICTION_FUNCTIONS)),
        "found_calls": sorted(called & set(REQUIRED_FRICTION_FUNCTIONS)),
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_friction_usage.py <path-till-strategifil.py>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    result = validate_friction_usage(path)

    if result.get("error"):
        print(f"REJECTED: {result['error']}", file=sys.stderr)
        return 1

    if not result["ok"]:
        print(
            f"REJECTED: {path} saknar faktisk användning av: {', '.join(result['missing'])}",
            file=sys.stderr,
        )
        print(
            f"  (importerade friktionsnamn hittade: {result['found_imports']}, "
            f"anropade: {result['found_calls']})",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: {path} importerar och anropar båda friktionsfunktionerna "
        f"({', '.join(REQUIRED_FRICTION_FUNCTIONS)})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
