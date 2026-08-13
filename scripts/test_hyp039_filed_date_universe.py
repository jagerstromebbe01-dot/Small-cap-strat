"""
Sidotest (kodgranskning 2026-08-05) - INTE en registeruppdatering, INTE en
ny hypotes, ingen K-kostnad: kör HYP-039:s OFÖRÄNDRADE 50/50-kombinations-
matematik mot HYP-037:s FILED-DATUM-KORRIGERADE portföljvärdeserie (från
scripts/test_hyp037_filed_date_universe.py) istället för den riktiga,
registrerade serien.

Syfte: svarar direkt på frågan "klarar HYP-039 fortfarande Sharpe>=1.0/
CAGR>10%/battre MaxDD an SPY, om vi anvander den look-ahead-korrigerade
HYP-037-serien?" - utan att gissa.

Skriver INGENTING till strategies/HYP-039/results/ eller registret - bara
till strategies/HYP-039/results_filed_date_test/.
"""

import sys
from pathlib import Path

STRATEGY_DIR = Path(__file__).resolve().parent.parent / "strategies" / "HYP-039"
sys.path.insert(0, str(STRATEGY_DIR))
import backtest as hyp039  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

hyp039.HYP037_RESULTS = REPO_ROOT / "strategies" / "HYP-037" / "results_filed_date_test"
hyp039.RESULTS_DIR = STRATEGY_DIR / "results_filed_date_test"

SPY_MAXDD_REF = hyp039.SPY_MAXDD_REF  # -0.337, opaverkad av universum-fixen (SPY ar inte small-cap)


def main():
    assert hyp039.HYP037_RESULTS.exists(), f"saknas: {hyp039.HYP037_RESULTS} - kör HYP-037-sidotestet först"
    print(f"HYP-037-KÄLLA (sidotest): {hyp039.HYP037_RESULTS}")
    print(f"RESULTAT SPARAS TILL (sidotest, rör INTE de riktiga resultaten): {hyp039.RESULTS_DIR}\n")

    levels = [100_000, 1_000_000, 10_000_000]
    print("=== HYP-039 sidotest: 50/50 SPY+HYP-037(korrigerat universum), 2011-2024 ===")
    for level in levels:
        r = hyp039.run_main_backtest(level)
        gate1 = "PASS" if r["sharpe"] >= 1.0 else "FAIL"
        gate2 = "PASS" if r["max_drawdown"] > SPY_MAXDD_REF else "FAIL"
        print(f"  ${level:>10,.0f}  Sharpe={r['sharpe']:.4f} ({gate1}, kräver >=1.0)  "
              f"MaxDD={r['max_drawdown']:.2%} ({gate2}, kräver bättre än {SPY_MAXDD_REF:.1%})  "
              f"CAGR={r['cagr']:+.2%}  Calmar={r['calmar']:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
