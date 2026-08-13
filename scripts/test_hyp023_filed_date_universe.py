"""
Sidotest (kodgranskning 2026-08-05) - INTE en registeruppdatering, INTE en
ny hypotes, ingen K-kostnad: kör HYP-023:s OFÖRÄNDRADE backtest-logik mot
det filed-datum-korrigerade universumet, exakt samma metod som
scripts/test_hyp037_filed_date_universe.py.

Syfte: HYP-037:s sidotest visade att MaxDD blir märkbart sämre i ABSOLUTA
tal under det korrigerade universumet. Men HYP-037:s låsta kriterium
jämför mot HYP-023:s EGNA MaxDD - en RELATIV jämförelse. Om HYP-023 också
blir sämre i ungefär samma utsträckning under samma korrigerade universum
kan den relativa slutsatsen fortfarande hålla. Detta skript ger den
rättvisa jämförelsepunkten.

Skriver resultat till strategies/HYP-023/results_filed_date_test/ - rör
ALDRIG strategies/HYP-023/results/ eller registret.
"""

import sys
from pathlib import Path

STRATEGY_DIR = Path(__file__).resolve().parent.parent / "strategies" / "HYP-023"
sys.path.insert(0, str(STRATEGY_DIR))
import backtest as hyp023  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

hyp023.UNIVERSE_FILE = DATA_DIR / "cache" / "smallcap_universe_by_month_filed_date.json"
hyp023.RESULTS_DIR = STRATEGY_DIR / "results_filed_date_test"

if __name__ == "__main__":
    assert hyp023.UNIVERSE_FILE.exists(), f"saknas: {hyp023.UNIVERSE_FILE} - kör universum-ombyggnaden först"
    print(f"UNIVERSUM-KÄLLA (sidotest): {hyp023.UNIVERSE_FILE}")
    print(f"RESULTAT SPARAS TILL (sidotest, rör INTE de riktiga resultaten): {hyp023.RESULTS_DIR}\n")
    sys.argv = ["backtest.py", "--all-levels"]
    sys.exit(hyp023.main())
