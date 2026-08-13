"""
Genuin OOS-validering av HYP-034 (stale-price/nolldags-filter pa HYP-023)
over 2025 - diagnostik (b) i HYP-034:s pass_fail_criterion, GATAR INTE
PASS/FAIL. Se paper_trading/HYP-023/oos_backtest_2025.py for den fulla
motiveringen till varfor detta ar en akta blind OOS-test - IDENTISK metod,
enda skillnaden ar att HYP-034:s (INTE HYP-023:s) egna, ofrandrade
funktioner importeras.

Syfte: HYP-023:s motsvarande test visade en Sharpe-nedgang isolerat till
2025 som var STORRE vid hogre kapitalniva (0.39/0.17/0.08 vid 100k/1M/10M)
- den kapacitetsspärr-beteende AI-brainstormen 2026-07-31 diagnostiserade
som mojligen likviditets-/mikrostrukturdrivet. HYP-034:s huvudresultat
(2011-2024-backtesten) visade redan ett tydligt FAIL (MaxDD samre an
HYP-023 pa ALLA tre nivaer) - detta diagnostik-steg kors anda, per det
lasta kriteriet ("rapporteras oavsett utfall"), for att se om filtret
atminstone mildrar den ursprungliga kapitalnivaberoende OOS-avklingningen.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PAPER_DIR = Path(__file__).resolve().parent
CACHE_DIR = REPO_ROOT / "data" / "cache"
ORIGINAL_UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_by_month.json"
EXTENSION_UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_2025_extension.json"
HYP034_DIR = REPO_ROOT / "strategies" / "HYP-034"
RESULTS_DIR = PAPER_DIR / "oos_2025_results"

sys.path.insert(0, str(REPO_ROOT / "strategies" / "common"))
sys.path.insert(0, str(HYP034_DIR))
from data_hygiene import clean_price_matrix, flag_implausible_liquidity  # noqa: E402
from sector import load_bank_financial_flags  # noqa: E402
import backtest as hyp034  # noqa: E402 - source of truth, INTE omskriven

OOS_START = "2025-01-01"
FULL_END = "2025-12-31"


def sharpe(s, rf=0.02):
    r = s.pct_change().dropna()
    return float(np.sqrt(252) * (r - rf / 252).mean() / r.std()) if r.std() > 0 else 0.0


def max_drawdown(s):
    return float(((s - s.cummax()) / s.cummax()).min())


def cagr(s):
    if len(s) < 2:
        return None
    return float((s.iloc[-1] / s.iloc[0]) ** (252 / len(s)) - 1)


def main():
    print("Laddar och sammanfogar universum (2011-2024 grundsanning + 2025-utökning)...")
    with ORIGINAL_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_orig = json.load(f)
    with EXTENSION_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_2025 = json.load(f)
    universe_merged = {**universe_orig, **universe_2025}
    all_tickers = sorted({t for tickers in universe_merged.values() for t in tickers})
    print(f"  {len(universe_orig)} manader (grundsanning) + {len(universe_2025)} manader (2025) = "
          f"{len(universe_merged)} totalt. {len(all_tickers)} unika tickers.\n")

    print("Laddar prismatriser (2010-01-01 till 2025-12-31)...")
    close, close_adj, high, low, volume = hyp034.load_price_matrices(all_tickers, hyp034.FULL_START, FULL_END)
    hedge = hyp034.load_hedge(hyp034.FULL_START, FULL_END)
    print(f"  Prismatris: {close.shape}\n")

    print("Sanerar prisdata...")
    close, high, low = clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    implausible = flag_implausible_liquidity(close, volume, max_market_cap=hyp034.MAX_MARKET_CAP,
                                              window=hyp034.ADV_WINDOW, multiplier=1.0)
    close = close.mask(implausible)
    close_adj = close_adj.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)

    print("Beräknar beta, idiosynkratisk vol, nolldags-filter, spread, bank-/finanskomposit "
          "(HYP-034:s egna, OFÖRÄNDRADE funktioner)...")
    beta_df = hyp034.compute_beta(close_adj, hedge, hyp034.BETA_WINDOW)
    vol_df = hyp034.compute_idiosyncratic_vol(close_adj, hedge, beta_df, hyp034.VOL_LOOKBACK_DAYS)
    zero_days_df = hyp034.compute_zero_return_days(close_adj, hyp034.ZERO_RETURN_WINDOW)
    spread_df = hyp034.compute_spread_matrix(high, low)
    bank_flags = load_bank_financial_flags(all_tickers)

    RESULTS_DIR.mkdir(exist_ok=True)
    all_results = []
    for capital_level in [100_000, 1_000_000, 10_000_000]:
        print(f"\n--- Kapitalnivå: ${capital_level:,.0f} ---")
        pv, tl, stl, sfl = hyp034.run_backtest(close, close_adj, hedge, vol_df, beta_df, spread_df, volume,
                                                universe_merged, capital_level, bank_flags, zero_days_df)

        oos_pv = pv.loc[OOS_START:]
        oos_tl = tl[tl["date"] >= OOS_START] if len(tl) else tl
        oos_sfl = sfl[sfl["date"] >= OOS_START] if len(sfl) else sfl

        full_sharpe = sharpe(pv)
        oos_sharpe = sharpe(oos_pv)
        oos_cagr = cagr(oos_pv)
        oos_maxdd = max_drawdown(oos_pv)
        oos_total_return = float(oos_pv.iloc[-1] / oos_pv.iloc[0] - 1) if len(oos_pv) > 1 else None

        result = {
            "capital_level": capital_level,
            "full_series_sharpe_2011_2025": full_sharpe,
            "oos_2025_sharpe": oos_sharpe,
            "oos_2025_cagr": oos_cagr,
            "oos_2025_total_return": oos_total_return,
            "oos_2025_max_drawdown": oos_maxdd,
            "oos_2025_n_trades": int(len(oos_tl)),
            "oos_2025_trading_days": int(len(oos_pv)),
            "oos_2025_avg_stale_excluded_per_rebal": float(oos_sfl["n_stale_excluded"].mean()) if len(oos_sfl) else None,
        }
        all_results.append(result)

        print(f"    Full serie (2011-2025) Sharpe: {full_sharpe:.3f}")
        print(f"    OOS 2025 ENDAST: Sharpe={oos_sharpe:.3f}  Totalavkastning={oos_total_return:+.2%}  "
              f"MaxDD={oos_maxdd:.1%}  Trades={len(oos_tl)}  Handelsdagar={len(oos_pv)}")

        pv.to_csv(RESULTS_DIR / f"portfolio_value_full_{capital_level}.csv", header=["portfolio_value"])
        oos_pv.to_csv(RESULTS_DIR / f"portfolio_value_oos_2025_{capital_level}.csv", header=["portfolio_value"])
        tl.to_csv(RESULTS_DIR / f"trade_log_full_{capital_level}.csv", index=False)

    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, default=str, ensure_ascii=False)

    print(f"\nKLART. Sammanfattning sparad till {RESULTS_DIR / 'summary.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
