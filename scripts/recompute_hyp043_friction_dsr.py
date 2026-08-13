#!/usr/bin/env python3
"""
Kompletterar diagnostic_hyp043_friction_robustness.py (2026-08-07) med
DSR för den friktionskorrigerade (corwin_schultz_spread inkluderad)
momentum L/S-sviten, mot dagens k_total=46. Den ursprungliga diagnostiken
skrev bara ut Sharpe/MaxDD/CAGR/Calmar, ingen DSR.

ÄNDRAR INTE HYP-043:s redan låsta status eller registerpost - ren
tilläggsinformation för en daterad tilläggsnot (samma disciplin som
redan etablerad för HYP-037/HYP-039).
"""

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import diagnostic_hyp043_friction_robustness as diag  # noqa: E402
from deflated_sharpe_ratio import deflated_sharpe_ratio_from_returns  # noqa: E402

K_TOTAL = 46
RF_PER_PERIOD = 0.02 / 252


def main():
    t0 = time.time()
    import json
    with diag.ORIGINAL_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_orig = json.load(f)
    with diag.EXTENSION_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_2025 = json.load(f)
    universe_merged = {**universe_orig, **universe_2025}

    print("Bygger om momentum L/S-sviten MED spreadkostnad...")
    mom_ls_full = diag.compute_momentum_ls_sleeve_with_spread(universe_merged)
    print(f"  klart, {time.time()-t0:.0f}s\n")

    spy_full = diag.load_spy()
    for level in [100_000, 1_000_000, 10_000_000]:
        hyp037_pv = diag.pd.read_csv(diag.HYP037_RESULTS / f"portfolio_value_{level}.csv",
                                      index_col=0, parse_dates=True)["portfolio_value"]
        combined = diag.combine_thirds(spy_full, hyp037_pv, mom_ls_full)
        returns = combined.pct_change().dropna()
        result = deflated_sharpe_ratio_from_returns(returns.values, n_trials=K_TOTAL,
                                                      risk_free_per_period=RF_PER_PERIOD)
        print(f"${level:>10,.0f}  SR(daglig)={result['sharpe_ratio']:.4f}  "
              f"DSR(K={K_TOTAL})={result['deflated_sharpe_ratio']:.4f}  n_obs={result['n_obs']}")

    print(f"\nKLART, {time.time()-t0:.0f}s totalt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
