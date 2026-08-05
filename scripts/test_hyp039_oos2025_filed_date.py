"""
Sidotest: HYP-039:s OOS-2025-villkor (combined Sharpe > 0) mot HYP-037:s
FULLT korrigerade OOS-2025-serie (scripts/test_hyp037_oos2025_filed_date.py).
Samma metod som scripts/test_hyp039_filed_date_universe.py, men för
OOS-benet. Skriver till strategies/HYP-039/results_filed_date_test/ (samma
katalog som huvudtestet, olika filnamn) - rör INTE de riktiga resultaten.
"""

import sys
from pathlib import Path

STRATEGY_DIR = Path(__file__).resolve().parent.parent / "strategies" / "HYP-039"
sys.path.insert(0, str(STRATEGY_DIR))
import backtest as hyp039  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

hyp039.HYP037_OOS_RESULTS = REPO_ROOT / "paper_trading" / "HYP-037" / "oos_2025_results_filed_date_test"
hyp039.RESULTS_DIR = STRATEGY_DIR / "results_filed_date_test"


def main():
    assert hyp039.HYP037_OOS_RESULTS.exists(), "kör OOS-sidotestet (test_hyp037_oos2025_filed_date.py) först"
    print(f"HYP-037 OOS-KÄLLA (sidotest): {hyp039.HYP037_OOS_RESULTS}\n")

    print("=== HYP-039 OOS-2025 sidotest: 50/50 SPY+HYP-037(fullt korrigerat universum) ===")
    for level in [100_000, 1_000_000, 10_000_000]:
        r = hyp039.run_oos_2025(level)
        gate3 = "PASS" if r["oos_2025_sharpe"] > 0 else "FAIL"
        print(f"  ${level:>10,.0f}  OOS-Sharpe={r['oos_2025_sharpe']:.4f} ({gate3}, kräver >0)  "
              f"OOS-avkastning={r['oos_2025_total_return']:+.2%}  OOS-MaxDD={r['oos_2025_max_drawdown']:.2%}  "
              f"({r['n_days']} dagar)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
