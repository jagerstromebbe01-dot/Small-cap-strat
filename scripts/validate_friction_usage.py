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

UTÖKAD 2026-08-13 (BATCH-004, accrual-varianterna HYP-097-100): dessa
fyra delar EN gemensam motor (strategies/common/accrual_engine.py,
samma delade-modul-princip som redan används av crypto_data.py för
HYP-060-064/089/090) istället för att var och en kopierar in
friktionsanropen direkt i sin egen backtest.py. Ett rent en-fil-AST-
test missade därför friktionen helt trots att den faktiskt användes -
inte ett hål att kringgå kontrollen, utan ett genuint gap i vad den
kunde se. Kontrollen följer nu ETT steg av lokala modulimporter (endast
filer inuti strategies/ i detta repo, aldrig tredjepartspaket) och slår
ihop fynden - fortfarande "importerat OCH anropat", bara att båda
villkoren nu får vara uppfyllda i endera filen, inte nödvändigtvis
samma. Detta är en STÄRKNING av kontrollen (den kan nu se ett tidigare
osynligt, men redan legitimt, mönster), inte en uppmjukning - ett
anrop som INTE finns någonstans i kedjan flaggas fortfarande.

Usage:
    python validate_friction_usage.py <path-till-strategifil.py>
"""

import ast
import sys
from pathlib import Path

REQUIRED_FRICTION_FUNCTIONS = ["corwin_schultz_spread", "borrow_cost"]
REPO_ROOT = Path(__file__).resolve().parent.parent


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


def _find_local_module_imports(tree: ast.AST) -> set:
    """Hittar 'import X' / 'import X as Y'-satser dar X sannolikt ar en
    lokal modul i detta repo (INTE 'from X import Y' - de namnen fångas
    redan av _find_imported_names). Returnerar de RÅA modulnamnen
    (t.ex. 'accrual_engine'), inte alias."""
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
    return modules


def _resolve_local_module(module_name: str) -> Path | None:
    """Sok EN gang efter modulen bland de platser strategikoden
    faktiskt anvander sys.path.insert mot (strategies/common/ och varje
    strategies/HYP-*/ mapp) - inte ett generellt Python-importsystem,
    bara de kanda, redan etablerade platserna i denna kodbas."""
    candidates = [
        REPO_ROOT / "strategies" / "common" / f"{module_name}.py",
        REPO_ROOT / "scripts" / f"{module_name}.py",
    ]
    for c in candidates:
        if c.is_file():
            return c
    for hyp_dir in (REPO_ROOT / "strategies").glob("HYP-*"):
        c = hyp_dir / f"{module_name}.py"
        if c.is_file():
            return c
    return None


def validate_friction_usage(strategy_file: Path) -> dict:
    """
    Returnerar {"ok": bool, "missing": [...], "found_imports": [...],
    "found_calls": [...]} eller {"ok": False, "error": "..."} om filen
    saknas eller inte går att parsa. Följer ETT steg av lokala
    modulimporter (se moduldocstringen, 2026-08-13-tillägget) - en
    delad motor som backtest.py importerar räknas med.
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

    for module_name in _find_local_module_imports(tree):
        resolved = _resolve_local_module(module_name)
        if resolved is None:
            continue
        try:
            sub_source = resolved.read_text(encoding="utf-8")
            sub_tree = ast.parse(sub_source, filename=str(resolved))
        except (OSError, SyntaxError):
            continue
        imported |= _find_imported_names(sub_tree)
        called |= _find_called_names(sub_tree)

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
