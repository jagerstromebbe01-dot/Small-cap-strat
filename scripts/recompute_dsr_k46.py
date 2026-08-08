#!/usr/bin/env python3
"""
Granskningsfynd 2026-08-08 (tre oberoende adversariella granskare, samma
fynd oberoende av varandra): Deflated Sharpe Ratio har ALDRIG räknats om
för hypoteser som redan är aktiva/refererade, trots att
agents/overfitting_detector/ROLE.md kräver detta varje gång k_total ökar.
HYP-017/021/023/037/039/041/043 visade alla DSR beräknat mot ett K som
var lägre (i vissa fall mindre än hälften) av dagens k_total.

Detta skript räknar om DSR för dessa hypoteser mot dagens k_total=46,
med existerande, redan sparade portfolio_value_<niva>.csv-serier (INGEN
ny backtest körs, INGA redan låsta Sharpe/MaxDD/CAGR-siffror ändras -
bara DSR-fältet, som per definition alltid ska räknas om mot aktuellt K).

ÄNDRAR INTE status eller pass_fail_criterion för någon hypotes - skriver
bara ut nya DSR-värden för manuell, daterad tilläggsnot i respektive
YAML (samma disciplin som redan etablerad för HYP-037/HYP-039:s
look-ahead-bias-tilläggsnoter).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
STRATEGIES_ROOT = REPO_ROOT / "strategies"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from deflated_sharpe_ratio import deflated_sharpe_ratio_from_returns  # noqa: E402

K_TOTAL = 46
LEVELS = [100_000, 1_000_000, 10_000_000]
RF_ANNUAL = 0.02
RF_PER_PERIOD = RF_ANNUAL / 252  # samma konvention som varje hypotes egna sharpe()-funktion

# (HYP-mapp, filnamnsmonster, tidigare K vid ursprunglig testning)
TARGETS = [
    ("HYP-017", "portfolio_value_{level}.csv", 19),
    ("HYP-021", "portfolio_value_{level}.csv", 20),
    ("HYP-023", "portfolio_value_{level}.csv", 22),
    ("HYP-037", "portfolio_value_{level}.csv", 36),
    ("HYP-039", "portfolio_value_combined_{level}.csv", 38),
    ("HYP-041", "portfolio_value_combined_{level}.csv", 40),
    ("HYP-043", "portfolio_value_combined_{level}.csv", 42),
]


def load_returns(hyp_dir: str, pattern: str, level: int) -> pd.Series:
    path = STRATEGIES_ROOT / hyp_dir / "results" / pattern.format(level=level)
    pv = pd.read_csv(path, index_col=0, parse_dates=True)["portfolio_value"]
    return pv.pct_change().dropna()


def main():
    print(f"=== DSR omräknad mot dagens k_total={K_TOTAL} (RF={RF_ANNUAL:.0%}/ar avdraget, samma konvention som registrets egna sharpe()) ===\n")
    for hyp_dir, pattern, old_k in TARGETS:
        print(f"{hyp_dir} (ursprungligen testad mot K={old_k + 1}):")
        for level in LEVELS:
            try:
                returns = load_returns(hyp_dir, pattern, level)
            except FileNotFoundError:
                print(f"  ${level:>10,.0f}  (ingen portfolio_value-fil hittad, hoppar over)")
                continue
            result = deflated_sharpe_ratio_from_returns(returns.values, n_trials=K_TOTAL,
                                                          risk_free_per_period=RF_PER_PERIOD)
            print(f"  ${level:>10,.0f}  SR={result['sharpe_ratio']:.4f}  "
                  f"DSR(K={K_TOTAL})={result['deflated_sharpe_ratio']:.4f}  "
                  f"n_obs={result['n_obs']}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
