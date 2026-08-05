"""
Sidotest (kodgranskning 2026-08-05) - INTE en registeruppdatering: kör
HYP-037:s genuina OOS-2025-test (paper_trading/HYP-037/oos_backtest_2025.py)
med BÅDA universum-källorna bytta mot de filed-datum-korrigerade
versionerna - huvudserien (smallcap_universe_by_month_filed_date.json,
se data/rebuild_smallcap_classification_filed_date.py) OCH 2025-
utökningen (smallcap_universe_2025_extension_filed_date.json, se
data/build_universe_2025_filed_date.py).

Identisk metod/logik till den ursprungliga oos_backtest_2025.py - enda
skillnaden är vilka två universum-filer som slås ihop. Svarar på: håller
HYP-037:s villkor 3 (OOS-2025 Sharpe vid $10M >= HYP-023:s 0.08) fortfarande
under ett fullständigt look-ahead-korrigerat universum (bade 2010-2024 och
2025)?

Skriver till paper_trading/HYP-037/oos_2025_results_filed_date_test/ - rör
ALDRIG de riktiga registrerade OOS-resultaten.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
HYP037_DIR = REPO_ROOT / "strategies" / "HYP-037"
RESULTS_DIR = REPO_ROOT / "paper_trading" / "HYP-037" / "oos_2025_results_filed_date_test"

ORIGINAL_UNIVERSE_FILE_CORRECTED = CACHE_DIR / "smallcap_universe_by_month_filed_date.json"
EXTENSION_UNIVERSE_FILE_CORRECTED = CACHE_DIR / "smallcap_universe_2025_extension_filed_date.json"

sys.path.insert(0, str(REPO_ROOT / "strategies" / "common"))
sys.path.insert(0, str(HYP037_DIR))
from data_hygiene import clean_price_matrix, flag_implausible_liquidity  # noqa: E402
from sector import load_bank_financial_flags  # noqa: E402
import backtest as hyp037  # noqa: E402 - source of truth, OFÖRÄNDRAD

OOS_START = "2025-01-01"
FULL_END = "2025-12-31"
HYP023_OOS_SHARPE_10M = 0.08  # samma jämförelsepunkt som originaltestet


def sharpe(s, rf=0.02):
    r = s.pct_change().dropna()
    return float(np.sqrt(252) * (r - rf / 252).mean() / r.std()) if r.std() > 0 else 0.0


def max_drawdown(s):
    return float(((s - s.cummax()) / s.cummax()).min())


def main():
    assert ORIGINAL_UNIVERSE_FILE_CORRECTED.exists(), "kör huvudserie-ombyggnaden först"
    assert EXTENSION_UNIVERSE_FILE_CORRECTED.exists(), "kör 2025-ombyggnaden först (build_universe_2025_filed_date.py)"

    print("Laddar och sammanfogar KORRIGERADE universum (huvudserie + 2025-utökning)...")
    with ORIGINAL_UNIVERSE_FILE_CORRECTED.open(encoding="utf-8") as f:
        universe_orig = json.load(f)
    with EXTENSION_UNIVERSE_FILE_CORRECTED.open(encoding="utf-8") as f:
        universe_2025 = json.load(f)
    universe_merged = {**universe_orig, **universe_2025}
    all_tickers = sorted({t for tickers in universe_merged.values() for t in tickers})
    print(f"  {len(universe_orig)} månader (huvudserie) + {len(universe_2025)} månader (2025) = "
          f"{len(universe_merged)} totalt. {len(all_tickers)} unika tickers.\n")

    print("Laddar prismatriser (2010-01-01 till 2025-12-31)...")
    close, close_adj, high, low, volume = hyp037.load_price_matrices(all_tickers, hyp037.FULL_START, FULL_END)
    hedge = hyp037.load_hedge(hyp037.FULL_START, FULL_END)
    print(f"  Prismatris: {close.shape}\n")

    print("Sanerar prisdata...")
    close, high, low = clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    implausible = flag_implausible_liquidity(close, volume, max_market_cap=hyp037.MAX_MARKET_CAP,
                                              window=hyp037.ADV_WINDOW, multiplier=1.0)
    close = close.mask(implausible)
    close_adj = close_adj.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)

    print("Beräknar beta, idiosynkratisk vol, spread, bank-/finanskomposit...")
    beta_df = hyp037.compute_beta(close_adj, hedge, hyp037.BETA_WINDOW)
    vol_df = hyp037.compute_idiosyncratic_vol(close_adj, hedge, beta_df, hyp037.VOL_LOOKBACK_DAYS)
    spread_df = hyp037.compute_spread_matrix(high, low)
    bank_flags = load_bank_financial_flags(all_tickers)

    RESULTS_DIR.mkdir(exist_ok=True, parents=True)
    all_results = []
    for capital_level in [100_000, 1_000_000, 10_000_000]:
        print(f"\n--- Kapitalnivå: ${capital_level:,.0f} ---")
        pv, tl, stl, crl = hyp037.run_backtest(close, close_adj, hedge, vol_df, beta_df, spread_df, volume,
                                                universe_merged, capital_level, bank_flags)

        oos_pv = pv.loc[OOS_START:]
        oos_tl = tl[tl["date"] >= OOS_START] if len(tl) else tl

        full_sharpe = sharpe(pv)
        oos_sharpe = sharpe(oos_pv)
        oos_maxdd = max_drawdown(oos_pv)
        oos_total_return = float(oos_pv.iloc[-1] / oos_pv.iloc[0] - 1) if len(oos_pv) > 1 else None

        result = {
            "capital_level": capital_level,
            "full_series_sharpe_2011_2025": full_sharpe,
            "oos_2025_sharpe": oos_sharpe,
            "oos_2025_total_return": oos_total_return,
            "oos_2025_max_drawdown": oos_maxdd,
            "oos_2025_n_trades": int(len(oos_tl)),
            "oos_2025_trading_days": int(len(oos_pv)),
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

    r10m = next(r for r in all_results if r["capital_level"] == 10_000_000)
    gate_pass = r10m["oos_2025_sharpe"] >= HYP023_OOS_SHARPE_10M
    print(f"\n{'='*60}")
    print(f"VILLKOR 3 (OOS-2025 Sharpe vid $10M >= HYP-023:s {HYP023_OOS_SHARPE_10M}), "
          f"KORRIGERAT UNIVERSUM: {'PASS' if gate_pass else 'FAIL'} ({r10m['oos_2025_sharpe']:.3f})")
    print(f"{'='*60}")
    print(f"\nKLART. Sammanfattning sparad till {RESULTS_DIR / 'summary.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
