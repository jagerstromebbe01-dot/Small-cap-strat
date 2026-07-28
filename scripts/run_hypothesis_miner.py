#!/usr/bin/env python3
"""
Lokal, schemalagd korning av Hypothesis Miner-rollen (/agents/hypothesis_miner/ROLE.md).

Ersatter det schemalagda cloud-passet (RemoteTrigger, "Hypothesis Miner (small-cap
lab)"), som visade sig aldrig kunna pusha till master - molnmiljon tillater bara push
till branches som borjar med "claude/" och sakna en synlig installning for att andra
det. Denna lokala variant anvander samma mekanism som scripts/run_chain.py redan
bygger pa: den lokala `claude` CLI:n i headless-lage (`claude -p "..."`), som redan
har fungerande git-push mot master (bekraftat av all commit-historik i repot hittills)
eftersom `claude /login` redan kors interaktivt pa den har maskinen.

Kravs: ett schemalagt Windows-jobb (schtasks) som anropar detta script dagligen -
se scripts/register_hypothesis_miner_task.ps1 for hur det jobbet skapades.

Precis som run_chain.py: kontrollerar FAKTISKT resultat (en ny commit som ror
candidate_ideas.md), inte bara subprocessens exit-kod - "lyckades men gjorde
inget" ska aldrig rapporteras som lyckat (samma buggmonster som redan hittades
och atgardades i kedje-orkestreraren).
"""

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CLAUDE_EXECUTABLE = shutil.which("claude") or "claude"

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
STATUS_FILE = DASHBOARD_DIR / "hypothesis_miner_status.json"
CANDIDATES_FILE = REPO_ROOT / "research" / "candidate_ideas.md"

CLAUDE_TIMEOUT_SECONDS = 1800  # 30 min, samma grans som run_chain.py anvander for LLM-steg

PROMPT = """Du agerar Hypothesis Miner-rollen (/agents/hypothesis_miner/ROLE.md) for detta \
kvantitativa forskningsprojekt. Las FORST den filen - dess harda regler galler absolut \
och far aldrig brytas.

Uppdrag: las /research/candidate_ideas.md for att se vad som redan star dar (undvik att \
dubblera en befintlig post). Valj sedan EN riktig, konkret, EXISTERANDE akademisk artikel, \
empirisk studie, eller val-etablerat marknadsfenomen som ar relevant for projektets teman: \
small-cap-aktieanomalier, statistisk arbitrage/parhandel, kapacitetsbegransningar i \
handelsstrategier, eller faktorinvestering kopplat till bolagsstorlek. Fabricera ALDRIG en \
kalla - anvand bara en artikel/teori du faktiskt kanner till.

Lagg till EXAKT EN ny post i /research/candidate_ideas.md, i slutet av filen, enligt SAMMA \
mall som redan finns dar (## [Datum, AAAA-MM-DD] / **Kalla:** / **Kort beskrivning:** / \
**Varfor relevant:**), skriven pa svenska for att matcha resten av filen. Anvand dagens \
verkliga datum.

HARDA REGLER, far ALDRIG brytas:
- Ror ALDRIG /research/hypothesis_registry/ pa nagot satt - varken lasning for att andra, \
skrivning, eller radering.
- Satter ALDRIG (och antyder aldrig) ett status-falt for nagon hypotes.
- Skriver ALDRIG ett pass_fail_criterion, varken helt eller delvis, for nagon hypotes.
- Andrar ENDAST /research/candidate_ideas.md - ror ingen annan fil i repot.
- Producerar bara ett ICKE-BINDANDE forslag - paminn dig sjalv att detta inte ar en \
registrerad hypotes.

Nar du ar klar: committa din andring till candidate_ideas.md med ett tydligt \
commit-meddelande (t.ex. 'Hypothesis Miner: add candidate idea on <amne>') och pusha \
till master-branchen."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _write_status(status: str, message: str, started_at: str, commit_hash: str = "") -> None:
    DASHBOARD_DIR.mkdir(exist_ok=True)
    payload = {
        "routine": "hypothesis_miner_local",
        "status": status,
        "message": message,
        "started_at": started_at,
        "finished_at": _now(),
        "commit_hash": commit_hash,
    }
    with STATUS_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main() -> int:
    started_at = _now()
    before_hash = _git("rev-parse", "HEAD")

    try:
        # --allowedTools kravs har: utan den fragar `-p` interaktivt om lov att
        # anvanda Edit/Bash, vilket aldrig kan besvaras i schemalagt/headless lage -
        # CLI:t svarar da bara "jag behover tillatelse" i klartext och avslutar med
        # exit 0 utan att ha gjort nagot. Upptackt 2026-07-28 vid test av detta script.
        result = subprocess.run(
            [
                CLAUDE_EXECUTABLE, "-p", PROMPT,
                "--allowedTools", "Read,Write,Edit,Bash,Glob,Grep",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        _write_status("error", "'claude' CLI hittades inte i PATH", started_at)
        return 1
    except subprocess.TimeoutExpired:
        _write_status("error", f"tidsgrans ({CLAUDE_TIMEOUT_SECONDS}s) overskreds", started_at)
        return 1

    if result.returncode != 0:
        combined = (result.stdout or "").strip() + " " + (result.stderr or "").strip()
        _write_status(
            "error",
            f"claude -p misslyckades (exit {result.returncode}): {combined.strip()[:2000]}",
            started_at,
        )
        return 1

    # Verifiera FAKTISKT resultat - en ny commit som ror candidate_ideas.md - inte bara
    # att subprocessen returnerade exit-kod 0 (se docstring for bakgrund).
    after_hash = _git("rev-parse", "HEAD")
    if after_hash == before_hash:
        _write_status(
            "error",
            "claude -p gav exit 0 men ingen ny commit skapades (HEAD oforandrad)",
            started_at,
        )
        return 1

    changed_files = _git("diff", "--name-only", before_hash, after_hash)
    if "research/candidate_ideas.md" not in changed_files.replace("\\", "/"):
        _write_status(
            "error",
            f"ny commit ({after_hash}) skapades men ror inte candidate_ideas.md "
            f"(andrade filer: {changed_files})",
            started_at,
            commit_hash=after_hash,
        )
        return 1

    # Verifiera att commiten faktiskt naddde origin/master, inte bara lokal HEAD -
    # annars ateupprepar vi exakt samma tvetydighet som cloud-korningen (committade
    # lokalt men pushen misslyckades tyst).
    _git("fetch", "--quiet", "origin")
    remote_hash = _git("rev-parse", "origin/master")
    if remote_hash != after_hash:
        _write_status(
            "error",
            f"commit ({after_hash}) skapades lokalt men pushades ALDRIG till "
            f"origin/master (origin/master ar fortfarande {remote_hash})",
            started_at,
            commit_hash=after_hash,
        )
        return 1

    _write_status(
        "success", f"ny kandidatide tillagd och pushad, commit {after_hash}", started_at,
        commit_hash=after_hash,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
