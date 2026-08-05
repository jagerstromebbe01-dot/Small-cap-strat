"""
Sidotest (kodgranskning 2026-08-05) - INTE en registeruppdatering, INTE en
ny hypotes, ingen K-kostnad: kör HYP-037:s OFÖRÄNDRADE backtest-logik mot
det filed-datum-korrigerade universumet
(data/cache/smallcap_universe_by_month_filed_date.json, se
data/rebuild_smallcap_classification_filed_date.py) istället för
originalet (periodslut-daterat, look-ahead-biasat - se den pågående
diskussionen om SEC-filed-datum-buggen).

Syfte: universumdiffen visade att en betydande andel ticker-månader byter
medlemskap. Men det säger bara att den VALBARA POOLEN ändras - inte om
HYP-037:s faktiska decilurval (lägsta idiosynkratisk-vol) och därmed
Sharpe/CAGR/MaxDD faktiskt rör sig i praktiken. Detta skript mäter DEN
frågan direkt, genom att köra exakt samma strategikod mot båda
universum-filerna och jämföra.

Skriver resultat till strategies/HYP-037/results_filed_date_test/ - rör
ALDRIG strategies/HYP-037/results/ (de riktiga, registrerade resultaten)
eller research/hypothesis_registry/. Ren diagnostik.
"""

import sys
from pathlib import Path

STRATEGY_DIR = Path(__file__).resolve().parent.parent / "strategies" / "HYP-037"
sys.path.insert(0, str(STRATEGY_DIR))
import backtest as hyp037  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

hyp037.UNIVERSE_FILE = DATA_DIR / "cache" / "smallcap_universe_by_month_filed_date.json"
hyp037.RESULTS_DIR = STRATEGY_DIR / "results_filed_date_test"

if __name__ == "__main__":
    assert hyp037.UNIVERSE_FILE.exists(), f"saknas: {hyp037.UNIVERSE_FILE} - kör universum-ombyggnaden först"
    print(f"UNIVERSUM-KÄLLA (sidotest): {hyp037.UNIVERSE_FILE}")
    print(f"RESULTAT SPARAS TILL (sidotest, rör INTE de riktiga resultaten): {hyp037.RESULTS_DIR}\n")
    sys.argv = ["backtest.py", "--all-levels"]
    sys.exit(hyp037.main())
