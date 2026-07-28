#!/usr/bin/env python3
"""
Lokal kedje-orkestrerare: Strategy Builder -> Coder-A -> Coder-B ->
validate_code_review.py -> validate_friction_usage.py ->
validate_hypothesis.py -> Backtester.

Körs som en fristående, icke-blockerande subprocess - triggas av
dashboard/server.py::api_set_pre_registered() EFTER att status redan
satts till pre-registered (den logiken är oförändrad, se server.py).
Denna fil rör ALDRIG pass_fail_criterion/tested_capital_levels/status
själv - den kör bara redan specade steg i ordning och rapporterar
status.

De LLM-drivna stegen (Strategy Builder, Coder-A, Coder-B) anropas via
den lokala `claude` CLI:n i headless-läge (`claude -p "..."`) - INTE en
cloud-routine, eftersom kedjan behöver den lokala datacachen
(data/cache/, som inte finns i molnet). Detta KRÄVER att `claude
/login` redan körts en gång interaktivt på den här maskinen - om det
inte är gjort misslyckas kedjan med ett tydligt felmeddelande vid
första LLM-steget, den kraschar inte tyst.

De mekaniska stegen (validate_*.py, själva backtest-körningen) körs som
vanliga Python-subprocesser, ingen LLM behövs för dem.

Status skrivs löpande till dashboard/chain_status.json (en rad per
hypotes-ID) så dashboarden kan visa "körs"/"klar"/"fel" via /api/state,
utan att API-anropet som startade kedjan någonsin behöver vänta på den.
"""

import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# npm-installerad claude CLI skapar claude/claude.cmd/claude.ps1 på Windows.
# subprocess.run(["claude", ...]) hittar den INTE automatiskt (till skillnad
# från cmd.exe:s egen PATH-uppslagning, som känner till PATHEXT) - shutil.which
# löser detta korrekt och säkert, utan att behöva shell=True (som skulle
# öppna för shell-injektion via hyp_id/prompttext).
CLAUDE_EXECUTABLE = shutil.which("claude") or "claude"

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
CHAIN_STATUS_FILE = DASHBOARD_DIR / "chain_status.json"
REGISTRY_DIR = REPO_ROOT / "research" / "hypothesis_registry"
STRATEGY_SPECS_DIR = REPO_ROOT / "research" / "strategy_specs"

MAX_CODER_REVISIONS = 2  # Coder-A får max detta många omtag efter Coder-B-underkännande
CLAUDE_TIMEOUT_SECONDS = 1800  # 30 min per LLM-anrop innan det räknas som fel, inte hänger for evigt


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_status() -> dict:
    if not CHAIN_STATUS_FILE.exists():
        return {}
    with CHAIN_STATUS_FILE.open("r", encoding="utf-8") as f:
        return json.load(f) or {}


def _write_status(all_status: dict):
    DASHBOARD_DIR.mkdir(exist_ok=True)
    with CHAIN_STATUS_FILE.open("w", encoding="utf-8") as f:
        json.dump(all_status, f, ensure_ascii=False, indent=2)


def set_chain_status(hyp_id: str, status: str, step: str = "", message: str = ""):
    all_status = _read_status()
    entry = all_status.get(hyp_id, {"started_at": _now()})
    entry["status"] = status
    entry["step"] = step
    entry["message"] = message
    entry["updated_at"] = _now()
    if status in ("done", "error"):
        entry["finished_at"] = _now()
    all_status[hyp_id] = entry
    _write_status(all_status)


def find_hypothesis_file(hyp_id: str) -> Path | None:
    for path in REGISTRY_DIR.glob("HYP-*.yaml"):
        if path.stem.startswith(hyp_id) or hyp_id in path.stem:
            return path
    return None


def run_claude_step(prompt: str, step_name: str) -> tuple[bool, str]:
    """
    Kör ett LLM-drivet steg via lokal `claude -p`. Returnerar (ok, output).
    Om `claude` inte är autentiserad, eller kraschar, eller tar för lång
    tid: ok=False med ett tydligt felmeddelande - kraschar aldrig tyst.
    """
    try:
        result = subprocess.run(
            [CLAUDE_EXECUTABLE, "-p", prompt],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return False, f"[{step_name}] 'claude' CLI hittades inte i PATH"
    except subprocess.TimeoutExpired:
        return False, f"[{step_name}] tidsgräns ({CLAUDE_TIMEOUT_SECONDS}s) överskreds"

    if result.returncode != 0:
        # claude CLI:ns felmeddelanden (t.ex. "Not logged in") kommer på
        # stdout, inte stderr - upptäckt vid testning 2026-07-28. Visa båda.
        combined = (result.stdout or "").strip() + " " + (result.stderr or "").strip()
        return False, f"[{step_name}] claude -p misslyckades (exit {result.returncode}): {combined.strip()[:2000]}"

    return True, result.stdout


def run_python_step(args: list, step_name: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [sys.executable] + args,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
    except Exception as exc:  # robust: logga och rapportera, aldrig okontrollerad krasch
        return False, f"[{step_name}] oväntat fel: {exc}"

    ok = result.returncode == 0
    output = (result.stdout or "") + (result.stderr or "")
    return ok, f"[{step_name}] {output[:2000]}"


def run_chain(hyp_id: str) -> int:
    set_chain_status(hyp_id, "running", step="start")

    hyp_path = find_hypothesis_file(hyp_id)
    if hyp_path is None:
        set_chain_status(hyp_id, "error", step="lookup", message=f"hittade ingen hypotesfil för {hyp_id}")
        return 1

    spec_path = STRATEGY_SPECS_DIR / f"{hyp_id}-spec.md"
    strategy_dir = REPO_ROOT / "strategies" / hyp_id
    backtest_path = strategy_dir / "backtest.py"
    review_path = strategy_dir / "code_review.yaml"

    # ── Steg 1: Strategy Builder ──────────────────────────────
    set_chain_status(hyp_id, "running", step="strategy_builder")
    ok, msg = run_claude_step(
        f"Du agerar Strategy Builder-rollen (/agents/strategy_builder/ROLE.md). "
        f"Hypotesen {hyp_id} ({hyp_path.relative_to(REPO_ROOT)}) har status pre-registered "
        f"och ett redan ifyllt pass_fail_criterion. Skriv en strategispec till "
        f"research/strategy_specs/{hyp_id}-spec.md enligt din rolls mall - vilka signaler, "
        f"vilket universum, vilken befintlig kodmodul (reference_code/v6_core_large_cap.py, "
        f"strategies/common/friction.py) som återanvänds. Skriv INGEN körbar kod, ändra "
        f"INGET i hypotesens YAML-fil.",
        "Strategy Builder",
    )
    if not ok:
        set_chain_status(hyp_id, "error", step="strategy_builder", message=msg)
        return 1

    # ── Steg 2-4: Coder-A -> Coder-B -> validate_code_review.py, med begränsat antal omtag ──
    coder_b_notes_feedback = ""
    for attempt in range(1, MAX_CODER_REVISIONS + 2):
        set_chain_status(hyp_id, "running", step=f"coder_a (försök {attempt})")
        ok, msg = run_claude_step(
            f"Du agerar Coder-A-rollen (/agents/coder/ROLE.md). Implementera backtest-kod för "
            f"{hyp_id} i strategies/{hyp_id}/backtest.py, baserat på specen "
            f"research/strategy_specs/{hyp_id}-spec.md. Kopiera reference_code/v6_core_large_cap.py "
            f"och strategies/common/friction.py - ändra dem aldrig direkt. "
            + (f"Coder-B underkände en tidigare version med denna kritik, åtgärda den specifikt: "
               f"{coder_b_notes_feedback}" if coder_b_notes_feedback else ""),
            f"Coder-A försök {attempt}",
        )
        if not ok:
            set_chain_status(hyp_id, "error", step="coder_a", message=msg)
            return 1

        set_chain_status(hyp_id, "running", step=f"coder_b (försök {attempt})")
        ok, msg = run_claude_step(
            f"Du agerar Coder-B-rollen (/agents/coder_b/ROLE.md). Granska KRITISKT "
            f"strategies/{hyp_id}/backtest.py mot specen research/strategy_specs/{hyp_id}-spec.md. "
            f"Skriv ditt resultat till strategies/{hyp_id}/code_review.yaml med coder_b_approved "
            f"(true/false), coder_b_notes (konkret motivering, aldrig tomt), och revision_history "
            f"(lägg till en ny post, radera aldrig gamla). Ändra ALDRIG Coder-A:s kod själv.",
            f"Coder-B försök {attempt}",
        )
        if not ok:
            set_chain_status(hyp_id, "error", step="coder_b", message=msg)
            return 1

        ok, msg = run_python_step(
            ["scripts/validate_code_review.py", str(review_path.relative_to(REPO_ROOT))],
            "validate_code_review.py",
        )
        if ok:
            break

        if attempt > MAX_CODER_REVISIONS:
            set_chain_status(
                hyp_id, "error", step="validate_code_review",
                message=f"Coder-B godkände inte koden efter {MAX_CODER_REVISIONS} omtag: {msg}",
            )
            return 1

        coder_b_notes_feedback = msg

    # ── Steg 5: validate_friction_usage.py ────────────────────
    set_chain_status(hyp_id, "running", step="validate_friction_usage")
    ok, msg = run_python_step(
        ["scripts/validate_friction_usage.py", str(backtest_path.relative_to(REPO_ROOT))],
        "validate_friction_usage.py",
    )
    if not ok:
        set_chain_status(hyp_id, "error", step="validate_friction_usage", message=msg)
        return 1

    # ── Steg 6: validate_hypothesis.py (den ursprungliga, oförändrade spärren) ──
    set_chain_status(hyp_id, "running", step="validate_hypothesis")
    ok, msg = run_python_step(
        ["scripts/validate_hypothesis.py", str(hyp_path.relative_to(REPO_ROOT))],
        "validate_hypothesis.py",
    )
    if not ok:
        set_chain_status(hyp_id, "error", step="validate_hypothesis", message=msg)
        return 1

    # ── Steg 7: Backtester - kör den redan godkända koden ─────
    set_chain_status(hyp_id, "running", step="backtester")
    ok, msg = run_python_step(
        [str(backtest_path.relative_to(REPO_ROOT)), "--all-levels"],
        "Backtester",
    )
    if not ok:
        set_chain_status(hyp_id, "error", step="backtester", message=msg)
        return 1

    set_chain_status(hyp_id, "done", step="complete", message="Kedjan slutförd, se strategies/<id>/results/")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: run_chain.py <hyp_id>", file=sys.stderr)
        return 2
    return run_chain(sys.argv[1])


if __name__ == "__main__":
    sys.exit(main())
