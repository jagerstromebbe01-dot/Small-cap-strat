#!/usr/bin/env python3
"""
Numerisk validering: jamfor den optimerade run_backtest() i
strategies/HYP-009/backtest_optimized.py (numpy-array-indexering
istallet for pandas .loc[]) mot den ORIGINALA versionen i
strategies/HYP-009/backtest.py (ej rord), pa en delmangd av riktiga
tickers och en kortare period - for att originalversionen ska hinna
kora klart pa rimlig tid i ett valideringssteg.

identify_pairs_dynamic/compute_zscore/compute_spread_matrix ar
IDENTISK kod i bada filerna (inte andrade av optimeringen) - anvands
darfor bara en gang fran endera modulen for att generera indata.
compute_beta ar redan validerad separat (se
validate_beta_optimization.py) - anvander den optimerade versionen har
for hastighet.

Om detta INTE visar identiska (inom floating-point-tolerans) trade_log
och portfolio_value: den optimerade versionen far ALDRIG anvandas for
en riktig hypotes-korning, oavsett hur mycket snabbare den ar.
"""

import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "strategies" / "HYP-009"))

import backtest as orig  # noqa: E402
import backtest_optimized as opt  # noqa: E402

N_TICKERS_TO_TEST = 300
TEST_END = "2016-12-31"  # kortare period - racker for att fa aktiva trades, snabbare original-korning


def main() -> int:
    print("Laddar universum...")
    tickers, universe_by_month = orig.load_universe()
    subset = tickers[:N_TICKERS_TO_TEST]
    print(f"Testar pa {len(subset)} tickers, period {orig.FULL_START}..{TEST_END}\n")

    close, high, low, volume = orig.load_price_matrices(subset, orig.FULL_START, TEST_END)
    hedge = orig.load_hedge(orig.FULL_START, TEST_END)
    tidx = {t: i for i, t in enumerate(close.columns)}
    log_ret = np.log(close).diff()
    log_p = np.log(close)

    print("Identifierar par (delad kod, oforandrad)...")
    pairs_by_date = orig.identify_pairs_dynamic(
        close, log_ret, universe_by_month, orig.COINT_WINDOW, orig.MIN_PAIRS, orig.CORR_THRESH, orig.MAX_PAIRS
    )

    print("Beraknar z-score (delad kod, oforandrad)...")
    zscore_df = orig.compute_zscore(close, log_p, pairs_by_date, orig.COINT_WINDOW, orig.ZSCORE_WINDOW, tidx)

    print("Beraknar beta (optimerad version, validerad separat)...")
    beta_df = opt.compute_beta(close, hedge, opt.BETA_WINDOW)

    print("Beraknar spread (delad kod, oforandrad)...\n")
    spread_df = orig.compute_spread_matrix(high, low)

    capital_level = 100_000.0

    print("Kor ORIGINAL run_backtest...")
    t0 = time.time()
    pv_orig, tl_orig = orig.run_backtest(close, hedge, zscore_df, beta_df, spread_df, volume, capital_level)
    t_orig = time.time() - t0
    print(f"  Klar pa {t_orig:.1f}s - {len(tl_orig)} trades\n")

    print("Kor OPTIMERAD run_backtest...")
    t0 = time.time()
    pv_opt, tl_opt = opt.run_backtest(close, hedge, zscore_df, beta_df, spread_df, volume, capital_level)
    t_opt = time.time() - t0
    print(f"  Klar pa {t_opt:.1f}s - {len(tl_opt)} trades\n")

    print("=" * 60)
    ok = True

    if len(tl_orig) != len(tl_opt):
        print(f"FEL: olika antal trades! orig={len(tl_orig)} opt={len(tl_opt)}")
        ok = False
    elif len(tl_orig) == 0:
        print("VARNING: noll trades i bada - inget att jamfora i trade_log, bara ett svagt test.")
    else:
        for col in ["ticker", "type"]:
            if not (tl_orig[col].values == tl_opt[col].values).all():
                print(f"FEL: trade_log-kolumnen '{col}' skiljer sig")
                ok = False
        for col in ["ret", "gross_ret"]:
            diff = np.abs(tl_orig[col].values - tl_opt[col].values)
            max_diff = diff.max() if len(diff) else 0.0
            print(f"trade_log['{col}']: max abs-diff = {max_diff:.10f}")
            if max_diff > 1e-9:
                ok = False

    pv_diff = np.abs(pv_orig.values - pv_opt.values)
    max_pv_diff = pv_diff.max()
    print(f"portfolio_value: max abs-diff = {max_pv_diff:.8f} (av vardefull ~{capital_level:,.0f})")
    if max_pv_diff > 1e-6:
        ok = False

    print(f"\nTidsvinst pa {len(subset)} tickers: {t_orig / t_opt:.1f}x snabbare")
    print("=" * 60)

    if not ok:
        print("\nFEL: DEN OPTIMERADE VERSIONEN GER ANDRA RESULTAT. Anvand INTE den.")
        return 1

    print("\nOK: identiska trades och portfoljvarde (inom floating-point-tolerans).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
