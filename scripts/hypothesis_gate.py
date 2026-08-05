"""
Delad, kod-baserad kärnlogik för pre-registreringsgrinden - använd av
BÅDE scripts/validate_hypothesis.py (den hårda backtest-spärren) OCH
dashboard/server.py::set_pre_registered (status-flytt-knappen). Samma
princip som resten av spec avsnitt 4: enforcement är kod, inte tillit
till att fri text råkar innehålla rätt ord.

BAKGRUND (kodgranskning 2026-08-05): båda anropsställena hade tidigare
sin EGEN, oberoende kopia av en skör substrängsmatchning mot det fria
`universe`-fältet ("small-cap" in universe.lower()) för att avgöra om
en hypotes räknas som small-cap. En hypotes vars universe-text säger
t.ex. "Russell 2000" eller "$100M-$2B equities" utan just de exakta
orden "small-cap"/"small cap" undgick då tyst tested_capital_levels-
kravet. Fixat genom att istället läsa det DEDIKERADE `small_cap_definition`-
fältet (redan obligatoriskt per CLAUDE.md för alla small-cap-hypoteser)
och DEFAULTA TILL small-cap = SANT (kräver allt) om fältet saknas eller
är tomt - fail CLOSED, inte fail OPEN. Endast ett explicit "N/A"-liknande
värde (samma konvention HYP-039 redan använder) räknas som "inte small-cap".
"""

REQUIRED_CAPITAL_LEVELS = {100_000, 1_000_000, 10_000_000}

_NOT_APPLICABLE_PREFIXES = ("n/a", "na", "n.a.", "not applicable", "ej tillämpligt", "ej tillamplig", "none")

_PLACEHOLDER_CRITERION_TOKENS = {"tbd", "todo", "n/a", "na", "xxx", "placeholder", "...", "?", "-", "tba"}

_NO_NEW_ENGINE_PHRASES = ("ingen ny backtest-motor", "no new backtest engine")


def criterion_is_filled(data: dict) -> bool:
    """
    Sant endast om pass_fail_criterion faktiskt innehåller något meningsfullt.
    En whitespace-sträng (" ") eller en uppenbar platshållare ("TBD", "N/A", ...)
    räknas INTE som ifylld, till skillnad från den gamla `not data.get(...)`-
    kontrollen som bara stötte på tomma/None-värden.
    """
    text = str(data.get("pass_fail_criterion") or "").strip()
    if not text:
        return False
    if text.lower() in _PLACEHOLDER_CRITERION_TOKENS:
        return False
    return True


def is_smallcap_hypothesis(data: dict) -> bool:
    """
    Läser det dedikerade small_cap_definition-fältet, INTE en substrängs-
    matchning mot universe-fritexten. Defaultar till SANT (small-cap,
    kräver tested_capital_levels) om fältet saknas eller är tomt - en
    hypotes måste EXPLICIT deklarera sig som "N/A" (samma mönster som
    HYP-039 redan använder) för att undantas, aldrig tvärtom.
    """
    val = str(data.get("small_cap_definition") or "").strip().lower()
    if not val:
        return True  # fail closed: inget ifyllt värde alls -> anta small-cap
    return not val.startswith(_NOT_APPLICABLE_PREFIXES)


def tested_capital_levels_check(data: dict) -> tuple[bool, str]:
    """
    Returnerar (ok, felmeddelande). Kontrollerar INTE bara att fältet är
    icke-tomt (som tidigare) utan att det faktiskt innehåller alla tre
    obligatoriska nivåerna (100k/1M/10M) - CLAUDE.md kräver just dessa,
    inte "någon lista".
    """
    levels = data.get("tested_capital_levels")
    if not levels:
        return False, "tested_capital_levels is empty — required for all small-cap hypotheses"
    try:
        levels_set = {int(x) for x in levels}
    except (TypeError, ValueError):
        return False, f"tested_capital_levels contains non-numeric entries: {levels!r}"
    missing = REQUIRED_CAPITAL_LEVELS - levels_set
    if missing:
        return False, (
            f"tested_capital_levels is missing required level(s): "
            f"{sorted(missing)} (got {sorted(levels_set)})"
        )
    return True, ""


def requires_friction_check(data: dict) -> bool:
    """
    Om True: strategins backtest.py MÅSTE faktiskt importera+anropa
    friktionsfunktionerna (validate_friction_usage.py), oavsett om
    pass_fail_criterion råkar innehålla ordet "friktion"/"friction".

    ÄNDRAT (kodgranskning 2026-08-05): tidigare triggades denna kontroll
    ENDAST av en bokstavlig ordsökning i kriterietexten - lätt att kringgå
    genom omformulering (redan hänt en gång, se HYP-039:s registerpost om
    en falsk positiv som fixades genom att BYTA ORD, inte substans). Spec
    §2 princip 3 säger att friktion ska ingå "från dag ett" i alla
    small-cap-backtester - inte bara de vars kriterietext råkar nämna det.
    Nu: kontrollen gäller som DEFAULT för alla small-cap-hypoteser, med
    ETT uttryckligt, avsiktligt undantag - en hypotes som explicit
    deklarerar att den INTE introducerar en ny backtest-motor (ren
    portföljnivå-kombination av redan kostnadsjusterade serier, t.ex.
    HYP-039) slipper kravet, eftersom validate_friction_usage.py ändå
    inte skulle hitta några friktionsanrop i en fil som bara gör
    portföljmatematik på redan färdiga serier.
    """
    if not is_smallcap_hypothesis(data):
        return False
    criterion_text = str(data.get("pass_fail_criterion") or "").lower()
    if any(phrase in criterion_text for phrase in _NO_NEW_ENGINE_PHRASES):
        return False
    return True
