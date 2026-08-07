#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes an - ingen K-kostnad, INGET last kriterium):
OOS-2025-uppfoljning av PEAD/SUE-kandidaten (se
diagnostic_hyp044_pead_and_issuance.py och diagnostic_hyp044_pead_4leg_combo.py).

Bygger om SUE/PEAD-sviten over DET SAMMANSLAGNA universumet (huvudserie +
2025-utokning), EXAKT samma princip som HYP-043:s egen
compute_momentum_ls_sleeve() - en enda genomgang racker for bade
huvudtest (2010-2024, ateranvander redan sparade siffror) och genuin
OOS-2025 (2025-utokningens nycklar LAGGER BARA TILL 2025-manader, paverkar
aldrig 2010-2024-eligibiliteten).

Kombinerar OOS-2025-perioden: SPY + HYP-037 (redan byggd genuin OOS-serie,
paper_trading/HYP-037/oos_2025_results/) + MomentumLS (redan sammanslagen
serie fran HYP-043, tacker redan 2025) + PEAD/SUE (byggd har).
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
STRATEGIES_ROOT = REPO_ROOT / "strategies"
DATA_DIR = REPO_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"

sys.path.insert(0, str(STRATEGIES_ROOT / "HYP-037"))
import backtest as hyp037  # noqa: E402
from friction import borrow_cost  # noqa: E402

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
from rebalancing import snap_rebalance_dates  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from diagnostic_hyp044_pead_and_issuance import load_sue_series, sue_asof  # noqa: E402

ORIGINAL_UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_by_month.json"
EXTENSION_UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_2025_extension.json"
HYP037_OOS_RESULTS = REPO_ROOT / "paper_trading" / "HYP-037" / "oos_2025_results"

REBAL_FREQ = "QE"
DECILE_FRACTION = 0.10
BORROW_ANNUAL_RATE = 0.03
RF_ANNUAL = 0.02
MIN_HISTORY_DAYS = 260
WEIGHT_EACH = 0.25

OOS_START = "2025-01-01"
FULL_END_WITH_OOS = "2025-12-31"

HYP039_OOS_REF = {100_000: 0.9185, 1_000_000: 0.8116, 10_000_000: 0.7932}
HYP043_OOS_REF = {100_000: 1.6163, 1_000_000: 1.5639, 10_000_000: 1.5321}


def sharpe(s, rf=RF_ANNUAL):
    r = s.pct_change().dropna()
    return float(np.sqrt(252) * (r - rf / 252).mean() / r.std()) if r.std() > 0 else 0.0


def max_drawdown(s):
    return float(((s - s.cummax()) / s.cummax()).min())


def combine_quarters(series_dict: dict, start_capital=1.0):
    df = pd.concat({k: v.rename(k) for k, v in series_dict.items()}, axis=1, join="inner").dropna()
    rets = df.pct_change()
    calendar_dates = df.resample(REBAL_FREQ).last().index
    snapped = snap_rebalance_dates(calendar_dates, df.index)
    rebal_set = set(snapped["execution_date"])

    legs = {k: start_capital * WEIGHT_EACH for k in series_dict}
    values, dates = [], []
    for i in range(1, len(df)):
        date = df.index[i]
        for k in legs:
            r = rets[k].iloc[i]
            if not np.isnan(r):
                legs[k] *= (1 + r)
        total = sum(legs.values())
        if date in rebal_set:
            for k in legs:
                legs[k] = total * WEIGHT_EACH
        values.append(total)
        dates.append(date)
    return pd.Series(values, index=dates)


def main():
    t0 = time.time()
    print("Laddar universum (huvudserie + 2025-utokning, sammanslaget)...")
    with ORIGINAL_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_orig = json.load(f)
    with EXTENSION_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_2025 = json.load(f)
    universe_merged = {**universe_orig, **universe_2025}
    tickers = sorted({t for tks in universe_merged.values() for t in tks})

    print("Laddar prismatriser (2010-2025)...")
    close, close_adj, high, low, volume = hyp037.load_price_matrices(tickers, hyp037.FULL_START, FULL_END_WITH_OOS)
    print(f"  {close.shape}, {time.time() - t0:.0f}s\n")

    print("Sanerar prisdata...")
    close, high, low = hyp037.clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    implausible = hyp037.flag_implausible_liquidity(close, volume, max_market_cap=hyp037.MAX_MARKET_CAP,
                                                      window=hyp037.ADV_WINDOW, multiplier=1.0)
    close_adj = close_adj.mask(implausible)
    ratio = (close_adj / close).replace([np.inf, -np.inf], np.nan)
    implausible_ratio = (ratio > 100) | (ratio < 0.01)
    close_adj = close_adj.mask(implausible_ratio)
    daily_ret = close_adj.pct_change()

    print("Bygger SUE-serier (samma EPS-data, oberoende av universum-sammanslagningen)...")
    sue_by_ticker = load_sue_series()

    tidx = {t: i for i, t in enumerate(close.columns)}
    calendar_dates = close.resample(REBAL_FREQ).last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[MIN_HISTORY_DAYS])
                                     & (calendar_dates <= close.index[-1])]
    snapped = snap_rebalance_dates(calendar_dates, close.index)
    rebal_map = dict(zip(snapped["execution_date"], snapped["calendar_label"]))
    rebal_set = set(snapped["execution_date"])
    start_idx = close.index.get_indexer([snapped["execution_date"].iloc[0]])[0]
    trade_dates = close.index[start_idx:]

    print("Bygger PEAD/SUE L/S-sviten over HELA 2010-2025 (en genomgang racker)...")
    long_names, short_names = [], []
    pv_list = [1.0]
    for date_i in range(start_idx, len(close.index)):
        date = close.index[date_i]
        if date in rebal_set:
            month_key = rebal_map[date].strftime("%Y-%m-%d")
            eligible = [t for t in universe_merged.get(month_key, []) if t in tidx]
            as_of = date.strftime("%Y-%m-%d")
            scores = {}
            for t in eligible:
                v = sue_asof(sue_by_ticker, t, as_of)
                if v is not None:
                    scores[t] = v
            if len(scores) >= 20:
                ranked = sorted(scores.items(), key=lambda kv: kv[1])
                n_decile = max(1, int(len(ranked) * DECILE_FRACTION))
                short_names = [t for t, _ in ranked[:n_decile]]
                long_names = [t for t, _ in ranked[-n_decile:]]

        if date_i > start_idx and (long_names or short_names):
            long_r = daily_ret.loc[date, long_names].mean() if long_names else 0.0
            short_r = daily_ret.loc[date, short_names].mean() if short_names else 0.0
            long_r = 0.0 if np.isnan(long_r) else long_r
            short_r = 0.0 if np.isnan(short_r) else short_r
            daily_borrow = borrow_cost(position_value=0.5, holding_days=1, annual_rate=BORROW_ANNUAL_RATE)
            period_ret = 0.5 * long_r - 0.5 * short_r - daily_borrow + (RF_ANNUAL / 252)
            pv_list.append(pv_list[-1] * (1 + period_ret))
        else:
            pv_list.append(pv_list[-1])

    pead_full = pd.Series(pv_list[1:], index=trade_dates)
    pead_full.to_csv(CACHE_DIR / "diag_pead_sue_ls_sleeve_merged_2010_2025_pv.csv", header=["portfolio_value"])
    print(f"  {len(pead_full)} dagar, {pead_full.index[0].date()} till {pead_full.index[-1].date()}\n")

    spy_oos = hyp037.load_hedge(hyp037.FULL_START, FULL_END_WITH_OOS).loc[OOS_START:FULL_END_WITH_OOS]
    mom_ls_full = pd.read_csv(STRATEGIES_ROOT / "HYP-043" / "results" / "momentum_ls_sleeve_pv.csv",
                               index_col=0, parse_dates=True).iloc[:, 0]
    mom_ls_oos = mom_ls_full.loc[OOS_START:FULL_END_WITH_OOS]
    pead_oos = pead_full.loc[OOS_START:FULL_END_WITH_OOS]

    print("=== OOS-2025: 4-vags likaviktad kombination (SPY + HYP-037 + MomentumLS + PEAD/SUE) ===\n")
    levels = [100_000, 1_000_000, 10_000_000]
    for level in levels:
        hyp037_oos_pv = pd.read_csv(HYP037_OOS_RESULTS / f"portfolio_value_oos_2025_{level}.csv",
                                     index_col=0, parse_dates=True)["portfolio_value"]
        combo_oos = combine_quarters({"spy": spy_oos, "hyp037": hyp037_oos_pv, "mom_ls": mom_ls_oos, "pead": pead_oos})
        sh = sharpe(combo_oos)
        md = max_drawdown(combo_oos)
        tot_ret = float(combo_oos.iloc[-1] / combo_oos.iloc[0] - 1) if len(combo_oos) > 1 else None
        ref39, ref43 = HYP039_OOS_REF[level], HYP043_OOS_REF[level]
        print(f"${level:>10,.0f}  OOS-Sharpe={sh:.4f}  OOS-avkastning={tot_ret:+.2%}  OOS-MaxDD={md:.2%}  "
              f"({len(combo_oos)} dagar)")
        print(f"    vs HYP-039 OOS (Sharpe {ref39:.4f}): {'BATTRE' if sh > ref39 else 'SAMRE'}")
        print(f"    vs HYP-043 OOS (Sharpe {ref43:.4f}): {'BATTRE' if sh > ref43 else 'SAMRE'}\n")

    print(f"KLART, {time.time() - t0:.0f}s totalt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
