"""
Small-Cap Edge Lab - fil-läsande statusdashboard (read-mostly).

Detta är ett OBSERVATIONSVERKTYG för CEO, inte en agent i pipelinen
(se CLAUDE.md / mini_hedge_fund_build_spec_v3.md avsnitt 3-5). Den äger
ingen roll, genererar inga hypoteser, och kör aldrig backtests.

HÅRD REGEL - läs detta innan du ändrar något här:

Denna server exponerar EXAKT fem skrivbara endpoints:
  POST /api/candidate/<id>/archive
  POST /api/note
  POST /api/hypothesis/<id>/set-pre-registered
  POST /api/candidate/<id>/draft-hypothesis
  POST /api/candidate/<id>/mark-component

INGEN annan endpoint får skriva något. Ingen endpoint här får NÅGONSIN:
  - ändra pass_fail_criterion
  - ändra tested_capital_levels eller capital_level_results
  - ändra small_cap_definition
  - sätta status till "passed" eller "failed"
  - sätta status till "pre-registered" UTAN att pass_fail_criterion
    (och för small-cap: tested_capital_levels) redan är ifyllt - se
    set_pre_registered() nedan, som kontrollerar detta PROGRAMMATISKT
    innan den skriver något, oavsett vad frontend visar/döljer
  - trigga en backtest-körning

set_pre_registered() är INTE en genväg runt kriterielåsningen. Kriteriet
måste redan finnas, skrivet av CEO manuellt i chatt, INNAN knappen ens
blir synlig i gränssnittet - endpointen bara flyttar en redan
kriterie-låst hypotes från "olåst status" till "pre-registered", och
rör aldrig själva kriterietexten, kapitalnivåerna, eller
small_cap_definition. Den vägrar även flytta en hypotes som redan är
"tested"/"passed"/"failed" tillbaka till "pre-registered" - att dölja
ett redan existerande testresultat kräver ett manuellt CEO-beslut i
YAML-filen, inte en knapptryckning.

Sedan 2026-07-28: EFTER en lyckad statusändring triggar endpointen även
(via launch_chain_if_not_running()) en LOKAL, icke-blockerande
bakgrundsprocess (scripts/run_chain.py) som kör Strategy Builder ->
Coder-A -> Coder-B -> validate_code_review.py ->
validate_friction_usage.py -> validate_hypothesis.py -> Backtester.
Detta är EN process, startad av redan godkänd statusändring - ingen ny
skrivbar endpoint, och triggas därför fortfarande ALDRIG för en hypotes
med tomt pass_fail_criterion (samma spärr som innan, oförändrad).
Kedjekörningen sker som en lokal subprocess (kräver `claude` CLI,
autentiserad via `claude /login` en gång interaktivt) - INTE en
cloud-routine, eftersom kedjan behöver den lokala datacachen i
data/cache/. Status för en pågående/klar/misslyckad kedja läses från
dashboard/chain_status.json och exponeras read-only i /api/state.

Godkännande av SJÄLVA KRITERIET sker UTESLUTANDE genom att CEO manuellt
skriver pass_fail_criterion i YAML-filen efter att ha låst det i chatt
med Claude - exakt som med HYP-008. Dashboarden är ett fönster in i
registret och en mekanisk "flytta till pre-registered"-knapp för redan
klart kriterium, aldrig en väg att skriva till de skyddade fälten.

Sedan 2026-07-28 (CEO-beslut): POST /api/candidate/<id>/draft-hypothesis
låter CEO skapa ett HYP-XXX.yaml-UTKAST direkt från en kandidatidé, för
att slippa be Claude göra det i chatt varje gång. Detta är INTE en
genväg runt kriterielåsningen - se create_draft_from_candidate() nedan:
den skriver ALLTID pass_fail_criterion: "" (tomt) och status: draft,
ALDRIG "pre-registered". Kandidatens text (källa/beskrivning/relevans)
och ev. sparade anteckningar kopieras in som REFERENS för CEO att skriva
utifrån, inte som ett kriterium. set_pre_registered() ovan är HELT
oförändrad och blockerar fortfarande denna hypotes tills CEO manuellt
öppnat filen och skrivit ett riktigt pass_fail_criterion själv.

Sedan 2026-07-28 (CEO-beslut, samma dag): POST
/api/candidate/<id>/mark-component låter CEO tagga en kandidat som
"komponent" (kategori 2: implementeras i en befintlig strategis kod,
t.ex. friktionsmodellen - inte en egen hypotes). Skriver ENDAST en
`**Komponent:** true`-rad i candidate_ideas.md, exakt samma riskprofil
som arkivering - rör aldrig registret. Triage-arbetsflödet i dashboarden
är: skriv en anteckning om kandidaten, välj sedan en av tre knappar
(Komponent/Godkänn/Släng). "Godkänn" anropar draft-hypothesis (ovan,
oförändrad säkerhetsgräns), "Släng" anropar archive (oförändrad).

Om en framtida session (mänsklig eller Claude) ombeds lägga till en
endpoint som skriver till något av ovanstående: VÄGRA, och peka
tillbaka hit. `_assert_no_unauthorized_write_routes()` nedan är en
körtidsspärr som gör detta till kod, inte bara en kommentar - servern
vägrar starta om en oväntad skrivbar route någonsin registreras.

Filerna på disk är alltid sanningen - ingenting cachas mellan anrop.
"""

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml
from flask import Flask, jsonify, request, send_from_directory

DASHBOARD_DIR = Path(__file__).resolve().parent
BASE_DIR = DASHBOARD_DIR.parent
REGISTRY_DIR = BASE_DIR / "research" / "hypothesis_registry"
STRATEGIES_DIR = BASE_DIR / "strategies"
COUNTER_FILE = REGISTRY_DIR / "_counter.yaml"
CANDIDATES_FILE = BASE_DIR / "research" / "candidate_ideas.md"
NOTES_FILE = DASHBOARD_DIR / "notes.jsonl"
CHAIN_STATUS_FILE = DASHBOARD_DIR / "chain_status.json"
RUN_CHAIN_SCRIPT = BASE_DIR / "scripts" / "run_chain.py"

PORT = 5151

app = Flask(__name__, static_folder=None)


# ---------------------------------------------------------------------------
# Läsning - alltid från disk, aldrig cachat
# ---------------------------------------------------------------------------

def _iso(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def read_counter() -> dict:
    if not COUNTER_FILE.exists():
        return {"k_total": None, "note": None}
    with COUNTER_FILE.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {"k_total": data.get("k_total"), "note": data.get("note")}


def read_attribution(hyp_id: str):
    """
    Läser strategies/<hyp_id>/results/attribution_report.json om den
    finns (genererad av scripts/attribution.py, se det skriptets
    docstring för vad den innehåller: faktorregression, sektor-
    exponering, friktionsdrag). RENT LÄSANDE - samma "filerna på disk
    är alltid sanningen"-princip som allt annat här, ingen ny skrivbar
    yta. Returnerar None om rapporten inte finns (dashboarden ska
    kunna visa hypoteser utan attribution utan att krascha).
    """
    path = STRATEGIES_DIR / hyp_id / "results" / "attribution_report.json"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def read_hypotheses() -> list:
    hypotheses = []
    if not REGISTRY_DIR.exists():
        return hypotheses
    for path in sorted(REGISTRY_DIR.glob("HYP-*.yaml")):
        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except yaml.YAMLError as exc:
            hypotheses.append({"id": path.stem, "_parse_error": str(exc)})
            continue

        hypotheses.append({
            "id": data.get("id", path.stem),
            "title": data.get("title"),
            "status": data.get("status"),
            "universe": data.get("universe"),
            "small_cap_definition": data.get("small_cap_definition"),
            "data_range": data.get("data_range"),
            "date_registered": _iso(data.get("date_registered")),
            "date_tested": _iso(data.get("date_tested")),
            "k_total_hypotheses_before_this": data.get("k_total_hypotheses_before_this"),
            "tested_capital_levels": data.get("tested_capital_levels"),
            "capital_level_results": data.get("capital_level_results"),
            "sharpe_raw": data.get("sharpe_raw"),
            "deflated_sharpe_ratio": data.get("deflated_sharpe_ratio"),
            "result_summary": data.get("result_summary"),
            "pass_fail_criterion": data.get("pass_fail_criterion"),
            "yaml_notes": data.get("notes"),
            "source_file": path.name,
            "attribution": read_attribution(data.get("id", path.stem)),
        })
    return hypotheses


_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_HEADER_RE = re.compile(r"(?m)^## +")
_ARCHIVED_RE = re.compile(r"\*\*Arkiverad:\*\*\s*true", re.IGNORECASE)
_COMPONENT_RE = re.compile(r"\*\*Komponent:\*\*\s*true", re.IGNORECASE)


def _field(body: str, label: str):
    m = re.search(rf"\*\*{re.escape(label)}:\*\*\s*(.+)", body)
    return m.group(1).strip() if m else None


def read_candidates() -> list:
    """
    Parsar /research/candidate_ideas.md. Mall-exemplet i filen ligger i ett
    ```-kodblock och tas bort innan parsning, så det aldrig räknas som en
    riktig kandidat. Varje kandidat får ett stabilt 1-baserat id motsvarande
    dess ordning i filen (Hypothesis Miner skriver bara i slutet av filen,
    så ordningen är stabil så länge poster inte tas bort manuellt).
    """
    if not CANDIDATES_FILE.exists():
        return []

    raw = CANDIDATES_FILE.read_text(encoding="utf-8")
    cleaned = _FENCE_RE.sub("", raw)
    parts = _HEADER_RE.split(cleaned)
    entries = parts[1:]

    candidates = []
    for idx, block in enumerate(entries, start=1):
        lines = block.splitlines()
        header = lines[0].strip() if lines else ""
        body = "\n".join(lines[1:])
        candidates.append({
            "id": str(idx),
            "header": header,
            "source": _field(body, "Källa"),
            "description": _field(body, "Kort beskrivning"),
            "relevance": _field(body, "Varför relevant"),
            "archived": bool(_ARCHIVED_RE.search(body)),
            "component": bool(_COMPONENT_RE.search(body)),
            "draft_hypothesis_id": _field(body, "Hypotesutkast"),
        })
    return candidates


def read_chain_status() -> dict:
    """Alltid från disk, aldrig cachat - samma princip som allt annat här."""
    if not CHAIN_STATUS_FILE.exists():
        return {}
    try:
        with CHAIN_STATUS_FILE.open("r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def read_notes() -> list:
    if not NOTES_FILE.exists():
        return []
    notes = []
    with NOTES_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                notes.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return notes


# ---------------------------------------------------------------------------
# Skrivning - ENDAST de två tillåtna operationerna
# ---------------------------------------------------------------------------

def _entries_start_offset(raw: str) -> int:
    """Position i råtexten efter mallens stängande ``` - allt före denna
    punkt rörs aldrig av arkivering, så mall-exemplet kan aldrig skrivas
    över eller misstas för en riktig post."""
    fence_matches = list(re.finditer(r"```", raw))
    if len(fence_matches) >= 2:
        return fence_matches[1].end()
    return 0


def _find_candidate_entry(candidate_id: str):
    """
    Delad uppslagslogik mellan archive_candidate och nedladdning - samma
    1-baserade id-ordning som read_candidates() anvander. Returnerar
    (tail, entry_start, entry_end, entry) eller None om id inte finns.
    """
    if not CANDIDATES_FILE.exists():
        return None
    raw = CANDIDATES_FILE.read_text(encoding="utf-8")
    start = _entries_start_offset(raw)
    tail = raw[start:]

    header_positions = [m.start() for m in re.finditer(r"(?m)^## +", tail)]
    try:
        idx = int(candidate_id) - 1
    except ValueError:
        return None
    if idx < 0 or idx >= len(header_positions):
        return None

    entry_start = header_positions[idx]
    entry_end = header_positions[idx + 1] if idx + 1 < len(header_positions) else len(tail)
    return tail, entry_start, entry_end, tail[entry_start:entry_end]


def _tag_candidate_entry(candidate_id: str, label: str, value: str, already_tagged_re: "re.Pattern") -> bool:
    """
    Delad logik för att lägga till en enkel `**Label:** value`-tagg i slutet
    av en kandidatpost - används av arkivering, komponent-märkning, och
    hypotesutkasts-spårning. Rör ALDRIG hypothesis_registry/ eller något
    kriterium - skriver bara en rad text i candidate_ideas.md.
    """
    found = _find_candidate_entry(candidate_id)
    if found is None:
        return False
    tail, entry_start, entry_end, entry = found
    raw = CANDIDATES_FILE.read_text(encoding="utf-8")
    head = raw[:_entries_start_offset(raw)]

    if already_tagged_re.search(entry):
        return True  # redan taggad - inget att göra, inte ett fel

    entry = entry.rstrip("\n") + f"\n\n**{label}:** {value}\n\n"
    new_tail = tail[:entry_start] + entry + tail[entry_end:]
    CANDIDATES_FILE.write_text(head + new_tail, encoding="utf-8")
    return True


def archive_candidate(candidate_id: str) -> bool:
    return _tag_candidate_entry(candidate_id, "Arkiverad", "true", _ARCHIVED_RE)


def mark_component(candidate_id: str) -> bool:
    return _tag_candidate_entry(candidate_id, "Komponent", "true", _COMPONENT_RE)


def append_note(target_type: str, target_id: str, text: str) -> dict:
    note = {
        "target_type": target_type,
        "target_id": str(target_id),
        "text": text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with NOTES_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(note, ensure_ascii=False) + "\n")
    return note


# En hypotes som redan är i något av dessa lägen har redan körts en gång -
# att flytta den TILLBAKA till "pre-registered" skulle dölja ett existerande
# resultat och kräver ett manuellt CEO-beslut i YAML-filen, inte en
# knapptryckning. set_pre_registered() vägrar alltid detta, oavsett vad
# frontend råkar visa.
PIPELINE_TERMINAL_STATUSES = {"tested", "passed", "failed"}

_STATUS_LINE_RE = re.compile(r"(?m)^status:\s*.*$")


def _find_hypothesis_path(hyp_id: str):
    if not REGISTRY_DIR.exists():
        return None
    for path in REGISTRY_DIR.glob("HYP-*.yaml"):
        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except yaml.YAMLError:
            continue
        if str(data.get("id")) == str(hyp_id):
            return path
    return None


def _replace_status_line(raw_text: str, new_status: str) -> str:
    """
    Ersätter ENDAST status-raden med en riktad textersättning - dumpar
    INTE om hela YAML-strukturen. Det skulle riskera att omformatera eller
    tappa kommentarer/formatering i pass_fail_criterion-blocket. Denna
    funktion rör bokstavligen inga andra byte i filen än status-raden.
    """
    replacement = f"status: {new_status}   # pre-registered -> tested -> passed/failed"
    new_text, n = _STATUS_LINE_RE.subn(replacement, raw_text, count=1)
    if n != 1:
        raise RuntimeError(
            f"hittade {n} status-rader (väntade exakt 1) - vägrar skriva, för säkerhets skull"
        )
    return new_text


def _git_commit_status_change(path: Path, hyp_id: str) -> dict:
    """
    Committar ENDAST den specifika hypotes-filen (aldrig `git add -A`),
    med det exakta meddelandet som krävdes när denna endpoint
    specificerades. Om git-stegen skulle misslyckas: filen är redan
    skriven till disk, så vi rapporterar det tydligt istället för att
    låtsas att inget hände eller att rulla tillbaka skrivningen.
    """
    rel_path = path.relative_to(BASE_DIR)
    message = f"Set {hyp_id} to pre-registered via dashboard (criterion already locked)"
    try:
        subprocess.run(["git", "add", str(rel_path)], cwd=BASE_DIR, check=True,
                        capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", message], cwd=BASE_DIR, check=True,
                        capture_output=True, text=True)
        commit_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=BASE_DIR, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        return {"committed": True, "commit": commit_hash, "message": message}
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        return {"committed": False, "error": str(exc), "message": message}


def launch_chain_if_not_running(hyp_id: str) -> dict:
    """
    Startar scripts/run_chain.py <hyp_id> som en LOKAL, icke-blockerande
    subprocess - kallaren (api_set_pre_registered) väntar ALDRIG på att
    detta blir klart, det kan ta lång tid (se HYP-008, timmar).

    Dubbelklicksskydd: om chain_status.json redan visar "running" för
    detta ID, startas INGEN ny process - den befintliga körningens
    status returneras bara. Detta är en enkel, icke-atomär
    read-then-write-kontroll (gott nog för ett lokalt, en-användar-
    verktyg som detta - ingen verklig samtidighetsrisk i praktiken).
    """
    all_status = read_chain_status()
    existing = all_status.get(hyp_id)
    if existing and existing.get("status") == "running":
        return {"launched": False, "reason": "kedjan körs redan för denna hypotes", "current": existing}

    all_status[hyp_id] = {
        "status": "running",
        "step": "start",
        "message": "",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    DASHBOARD_DIR.mkdir(exist_ok=True)
    with CHAIN_STATUS_FILE.open("w", encoding="utf-8") as f:
        json.dump(all_status, f, ensure_ascii=False, indent=2)

    try:
        subprocess.Popen(
            ["python", str(RUN_CHAIN_SCRIPT), hyp_id],
            cwd=BASE_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except Exception as exc:
        all_status[hyp_id]["status"] = "error"
        all_status[hyp_id]["message"] = f"kunde inte starta kedjan: {exc}"
        with CHAIN_STATUS_FILE.open("w", encoding="utf-8") as f:
            json.dump(all_status, f, ensure_ascii=False, indent=2)
        return {"launched": False, "reason": str(exc)}

    return {"launched": True}


def _next_hypothesis_id() -> str:
    """Näst lediga HYP-numret, baserat på existerande filer i registret."""
    max_n = 0
    if REGISTRY_DIR.exists():
        for path in REGISTRY_DIR.glob("HYP-*.yaml"):
            m = re.match(r"HYP-(\d+)", path.stem)
            if m:
                max_n = max(max_n, int(m.group(1)))
    return f"HYP-{max_n + 1:03d}"


def _slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text or "").strip("-").lower()
    return slug[:max_len].strip("-") or "candidate"


def create_draft_from_candidate(candidate_id: str) -> dict:
    """
    Skapar ett HYP-XXX.yaml-UTKAST fran en kandidatide - status: draft,
    pass_fail_criterion: "" (tomt MED FLIT). Skriver ALDRIG kriteriet,
    ALDRIG status: pre-registered - se modul-docstringen for varfor detta
    inte ar en genvag runt kriterielasningen.
    """
    found = _find_candidate_entry(candidate_id)
    if found is None:
        return {"ok": False, "message": f"okänd kandidatidé: {candidate_id}"}
    _tail, _start, _end, entry = found

    lines = entry.splitlines()
    header = lines[0].strip().lstrip("#").strip() if lines else f"Kandidat {candidate_id}"
    body = "\n".join(lines[1:])
    source = _field(body, "Källa") or ""
    description = _field(body, "Kort beskrivning") or ""
    relevance = _field(body, "Varför relevant") or ""

    candidate_notes = [n["text"] for n in read_notes()
                        if n.get("target_type") == "candidate" and n.get("target_id") == str(candidate_id)]

    title = source or header
    new_id = _next_hypothesis_id()
    slug = _slugify(source or header)
    path = REGISTRY_DIR / f"{new_id}-{slug}.yaml"
    if path.exists():
        return {"ok": False, "message": f"filen finns redan: {path.name}"}

    data = {
        "id": new_id,
        "date_registered": datetime.now(timezone.utc).date().isoformat(),
        "title": title,
        "universe": "",
        "small_cap_definition": "",
        "data_range": "",
        "pass_fail_criterion": "",
        "status": "draft",
        "k_total_hypotheses_before_this": read_counter().get("k_total"),
        "tested_capital_levels": [],
        "source_candidate": {
            "id": str(candidate_id),
            "header": header,
            "source": source,
            "description": description,
            "relevance": relevance,
        },
        "draft_notes_from_dashboard": "\n\n".join(candidate_notes) if candidate_notes else None,
    }

    comment_header = (
        "# UTKAST skapat via dashboarden fran kandidatide "
        f"{candidate_id} ({datetime.now(timezone.utc).date().isoformat()}).\n"
        "# pass_fail_criterion ar TOMT MED FLIT - CEO maste skriva det sjalv,\n"
        "# i chatt, innan status nagonsin kan bli pre-registered. Ingen agent\n"
        "# fyller i det ha faltet at dig. source_candidate/draft_notes_from_dashboard\n"
        "# ar bara REFERENS - inte ett kriterium.\n"
        "# status: draft -> (CEO fyller i universe/pass_fail_criterion/tested_capital_levels) -> pre-registered -> tested -> passed/failed\n\n"
    )
    yaml_body = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100)
    path.write_text(comment_header + yaml_body, encoding="utf-8")

    try:
        subprocess.run(["git", "add", str(path.relative_to(BASE_DIR))], cwd=BASE_DIR,
                        check=True, capture_output=True, text=True)
        subprocess.run(
            ["git", "commit", "-m",
             f"Draft {new_id} scaffolded from candidate {candidate_id} via dashboard (criterion NOT locked)"],
            cwd=BASE_DIR, check=True, capture_output=True, text=True,
        )
        git_ok = True
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        git_ok = False
        git_error = str(exc)

    _tag_candidate_entry(candidate_id, "Hypotesutkast", new_id, re.compile(rf"\*\*Hypotesutkast:\*\*\s*{re.escape(new_id)}"))

    result = {"ok": True, "id": new_id, "file": path.name, "git_committed": git_ok}
    if not git_ok:
        result["git_error"] = git_error
    return result


def set_pre_registered(hyp_id: str) -> dict:
    """
    Flyttar en hypotes till status: pre-registered - men ENDAST om
    pass_fail_criterion (och för small-cap: tested_capital_levels) redan
    är ifyllt. Detta är en PROGRAMMATISK kontroll, inte bara en knapp som
    döljs i frontend - anropas endpointen direkt utan att gå via
    knappen, gäller samma spärr.

    Rör ALDRIG pass_fail_criterion, tested_capital_levels,
    capital_level_results, eller small_cap_definition - läser dem bara
    för att verifiera att de finns. Skriver bara om status-raden.
    """
    path = _find_hypothesis_path(hyp_id)
    if path is None:
        return {"ok": False, "message": f"okänd hypotes: {hyp_id}"}

    raw_text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw_text) or {}

    if not data.get("pass_fail_criterion"):
        return {
            "ok": False,
            "message": (
                "pass_fail_criterion är tomt - måste låsas manuellt i chatt "
                "med CEO innan detta kan sättas. Ändrar ingenting."
            ),
        }

    universe = str(data.get("universe", "")).lower()
    is_smallcap = "small-cap" in universe or "small cap" in universe
    if is_smallcap and not data.get("tested_capital_levels"):
        return {
            "ok": False,
            "message": (
                "tested_capital_levels är tomt - obligatoriskt för "
                "small-cap-hypoteser innan detta kan sättas. Ändrar ingenting."
            ),
        }

    current_status = data.get("status")
    if current_status == "pre-registered":
        return {"ok": False, "message": "status är redan 'pre-registered'. Ändrar ingenting."}
    if current_status in PIPELINE_TERMINAL_STATUSES:
        return {
            "ok": False,
            "message": (
                f"status är redan '{current_status}' - denna endpoint flyttar "
                "aldrig en redan testad hypotes tillbaka till 'pre-registered', "
                "det skulle dölja ett existerande testresultat. Kräver ett "
                "manuellt CEO-beslut i YAML-filen. Ändrar ingenting."
            ),
        }

    new_text = _replace_status_line(raw_text, "pre-registered")
    path.write_text(new_text, encoding="utf-8")

    git_result = _git_commit_status_change(path, hyp_id)
    chain_result = launch_chain_if_not_running(hyp_id)
    return {
        "ok": True,
        "message": "status satt till pre-registered",
        "git": git_result,
        "chain": chain_result,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(DASHBOARD_DIR, "index.html")


@app.route("/api/state")
def api_state():
    hypotheses = read_hypotheses()
    chain_status = read_chain_status()
    for h in hypotheses:
        h["chain"] = chain_status.get(h["id"])

    status_counts = {"pre-registered": 0, "passed": 0, "failed": 0, "other": 0}
    for h in hypotheses:
        status_counts[h.get("status")] = status_counts.get(h.get("status"), 0)
        key = h.get("status") if h.get("status") in ("pre-registered", "passed", "failed") else "other"
        status_counts[key] += 1

    sharpe_timeline = [
        {
            "id": h["id"],
            "title": h["title"],
            "date_tested": h["date_tested"],
            "sharpe_raw": h["sharpe_raw"],
            "deflated_sharpe_ratio": h["deflated_sharpe_ratio"],
        }
        for h in hypotheses
        if h.get("sharpe_raw") is not None
    ]

    return jsonify({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counter": read_counter(),
        "hypotheses": hypotheses,
        "status_counts": status_counts,
        "candidates": read_candidates(),
        "notes": read_notes(),
        "sharpe_timeline": sharpe_timeline,
    })


@app.route("/api/candidate/<candidate_id>/archive", methods=["POST"])
def api_archive_candidate(candidate_id):
    ok = archive_candidate(candidate_id)
    if not ok:
        return jsonify({"error": f"okänt kandidat-id: {candidate_id}"}), 404
    return jsonify({"ok": True, "id": candidate_id, "archived": True})


@app.route("/api/candidate/<candidate_id>/mark-component", methods=["POST"])
def api_mark_component(candidate_id):
    ok = mark_component(candidate_id)
    if not ok:
        return jsonify({"error": f"okänt kandidat-id: {candidate_id}"}), 404
    return jsonify({"ok": True, "id": candidate_id, "component": True})


@app.route("/api/note", methods=["POST"])
def api_add_note():
    payload = request.get_json(silent=True) or {}
    target_type = payload.get("target_type")
    target_id = payload.get("target_id")
    text = (payload.get("text") or "").strip()

    if target_type not in ("candidate", "hypothesis"):
        return jsonify({"error": "target_type måste vara 'candidate' eller 'hypothesis'"}), 400
    if not target_id:
        return jsonify({"error": "target_id saknas"}), 400
    if not text:
        return jsonify({"error": "text saknas"}), 400

    note = append_note(target_type, target_id, text)
    return jsonify({"ok": True, "note": note}), 201


@app.route("/api/hypothesis/<hyp_id>/set-pre-registered", methods=["POST"])
def api_set_pre_registered(hyp_id):
    result = set_pre_registered(hyp_id)
    return jsonify(result), (200 if result["ok"] else 400)


@app.route("/api/candidate/<candidate_id>/draft-hypothesis", methods=["POST"])
def api_draft_hypothesis(candidate_id):
    result = create_draft_from_candidate(candidate_id)
    return jsonify(result), (201 if result["ok"] else 400)


@app.route("/api/candidate/<candidate_id>/download")
def api_download_candidate(candidate_id):
    """
    Ren lasoperation - laddar ner EN specifik kandidatides text som en
    fristående .md-fil (samma post som visas i kandidatidé-listan,
    identifierad med samma 1-baserade id som read_candidates() ger den).
    Rör write-spärren inte alls (GET ar inte i write_methods i
    _assert_no_unauthorized_write_routes nedan), och skriver ingenting.
    """
    found = _find_candidate_entry(candidate_id)
    if found is None:
        return jsonify({"error": f"okänd kandidatidé: {candidate_id}"}), 404
    _tail, _start, _end, entry = found
    header_line = entry.splitlines()[0].strip() if entry.splitlines() else f"Kandidat {candidate_id}"
    filename = f"candidate-{candidate_id}-{re.sub(r'[^a-zA-Z0-9]+', '-', header_line).strip('-')[:60]}.md"
    return app.response_class(
        entry.strip() + "\n",
        mimetype="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Körtidsspärr: vägrar starta om en oväntad skrivbar route någonsin finns.
# Detta är samma princip som scripts/validate_hypothesis.py - enforcement
# är kod, inte bara en kommentar en framtida session kan råka ignorera.
# ---------------------------------------------------------------------------

_ALLOWED_WRITE_RULES = {
    ("POST", "/api/candidate/<candidate_id>/archive"),
    ("POST", "/api/note"),
    ("POST", "/api/hypothesis/<hyp_id>/set-pre-registered"),
    ("POST", "/api/candidate/<candidate_id>/draft-hypothesis"),
    ("POST", "/api/candidate/<candidate_id>/mark-component"),
}


def _assert_no_unauthorized_write_routes():
    write_methods = {"POST", "PUT", "PATCH", "DELETE"}
    for rule in app.url_map.iter_rules():
        methods = (rule.methods or set()) - {"HEAD", "OPTIONS"}
        write_overlap = methods & write_methods
        if not write_overlap:
            continue
        if (next(iter(write_overlap)), rule.rule) in _ALLOWED_WRITE_RULES and len(write_overlap) == 1:
            continue
        raise RuntimeError(
            "VÄGRAR STARTA: oväntad skrivbar endpoint upptäckt: "
            f"{write_overlap} {rule.rule}. Den här dashboarden får ENDAST "
            "exponera POST /api/candidate/<id>/archive, POST /api/note, och "
            "POST /api/hypothesis/<id>/set-pre-registered - se "
            "modul-docstringen högst upp i server.py."
        )


if __name__ == "__main__":
    _assert_no_unauthorized_write_routes()
    print(f"Small-Cap Edge Lab dashboard: http://127.0.0.1:{PORT}")
    print("Endast localhost - servern binder inte till nätverket.")
    app.run(host="127.0.0.1", port=PORT, debug=False)
