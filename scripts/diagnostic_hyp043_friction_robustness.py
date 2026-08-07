#!/usr/bin/env python3
"""
Diagnostik (INGEN K-kostnad, ANDRAR INTE HYP-043:s redan lasta status
eller registerpost): robusthetskontroll av HYP-043:s egen momentum L/S-
svit MED genuin Corwin-Schultz bid-ask-spread-kostnad tillagd - upptackt
2026-08-07 (vid byggandet av HYP-044) att HYP-043:s ursprungliga svit
ALDRIG anropar corwin_schultz_spread (bara borrow_cost), vilket INTE
skulle klara scripts/validate_friction_usage.py om det kordes idag.

Samma spread-kostnadsmetod som lades till HYP-044:s PEAD/SUE-svit:
halva Corwin-Schultz-spreaden pa den nya decilens namn (bade long- och
kortsidan) vid varje ombalanserings entry. Allt annat i momentum L/S-
sviten (12-1-manaders momentum, decilstorlek, borrow_cost, kvartalsvis
ombalansering) AR OFORANDRAT - detta isolerar SPECIFIKT effekten av
den tidigare saknade spreadkostnaden.

Resultatet av denna diagnostik paverkar INTE HYP-043:s redan lasta
resultat i registret (last historia andras inte i efterhand) - det
ar en fristaende robusthetsnot for CEO:s information.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
STRATEGIES_ROOT = REPO_ROOT / "strategies"
CACHE_DIR = REPO_ROOT / "data" / "cache"

sys.path.insert(0, str(STRATEGIES_ROOT / "HYP-037"))
import backtest as hyp037  # noqa: E402
from friction import borrow_cost  # noqa: E402

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
from rebalancing import snap_rebalance_dates  # noqa: E402

ORIGINAL_UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_by_month.json"
EXTENSION_UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_2025_extension.json"
HYP037_RESULTS = STRATEGIES_ROOT / "HYP-037" / "results"
HYP037_OOS_RESULTS = REPO_ROOT / "paper_trading" / "HYP-037" / "oos_2025_results"

REBAL_FREQ = "QE"
WEIGHT_EACH = 1.0 / 3.0
MOM_LOOKBACK_DAYS = 252
MOM_SKIP_DAYS = 21
DECILE_FRACTION = 0.10
BORROW_ANNUAL_RATE = 0.03
RF_ANNUAL = 0.02

OOS_START = "2025-01-01"
FULL_END_WITH_OOS = "2025-12-31"

# HYP-043:s EGNA redan lasta resultat (utan spreadkostnad) - jamforelsepunkten
HYP043_LOCKED = {
    100_000: {"sharpe": 1.0457, "max_drawdown": -0.1558, "oos_2025_sharpe": 1.6163},
    1_000_000: {"sharpe": 1.0498, "max_drawdown": -0.1568, "oos_2025_sharpe": 1.5639},
    10_000_000: {"sharpe": 0.9864, "max_drawdown": -0.1429, "oos_2025_sharpe": 1.5321},
}


def compute_momentum_ls_sleeve_with_spread(universe_by_month: dict) -> pd.Series:
    tickers = sorted({t for tks in universe_by_month.values() for t in tks})
    close, close_adj, high, low, volume = hyp037.load_price_matrices(tickers, hyp037.FULL_START, FULL_END_WITH_OOS)

    close, high, low = hyp037.clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    implausible = hyp037.flag_implausible_liquidity(close, volume, max_market_cap=hyp037.MAX_MARKET_CAP,
                                                      window=hyp037.ADV_WINDOW, multiplier=1.0)
    close_adj = close_adj.mask(implausible)
    ratio = (close_adj / close).replace([np.inf, -np.inf], np.nan)
    implausible_ratio = (ratio > 100) | (ratio < 0.01)
    close_adj = close_adj.mask(implausible_ratio)

    print("  Berknar Corwin-Schultz-spread-matris (saknades i HYP-043:s ursprungliga svit)...")
    spread_df = hyp037.compute_spread_matrix(high, low)

    momentum = close_adj.shift(MOM_SKIP_DAYS) / close_adj.shift(MOM_LOOKBACK_DAYS) - 1
    daily_ret = close_adj.pct_change()

    tidx = {t: i for i, t in enumerate(close.columns)}
    calendar_dates = close.resample(REBAL_FREQ).last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[MOM_LOOKBACK_DAYS])
                                     & (calendar_dates <= close.index[-1])]
    snapped = snap_rebalance_dates(calendar_dates, close.index)
    rebal_map = dict(zip(snapped["execution_date"], snapped["calendar_label"]))
    rebal_set = set(snapped["execution_date"])
    start_idx = close.index.get_indexer([snapped["execution_date"].iloc[0]])[0]
    trade_dates = close.index[start_idx:]

    long_names, short_names = [], []
    pv_list = [1.0]

    for date_i in range(start_idx, len(close.index)):
        date = close.index[date_i]
        rebalance_cost = 0.0

        if date in rebal_set:
            month_key = rebal_map[date].strftime("%Y-%m-%d")
            eligible = [t for t in universe_by_month.get(month_key, []) if t in tidx]
            mom_today = momentum.loc[date, eligible].dropna()
            if len(mom_today) >= 20:
                ranked = mom_today.sort_values()
                n_decile = max(1, int(len(ranked) * DECILE_FRACTION))
                new_short = list(ranked.index[:n_decile])
                new_long = list(ranked.index[-n_decile:])

                long_spreads = spread_df.loc[date, new_long].dropna() if new_long else pd.Series(dtype=float)
                short_spreads = spread_df.loc[date, new_short].dropna() if new_short else pd.Series(dtype=float)
                avg_long_spread = float(long_spreads.mean()) if len(long_spreads) else 0.0
                avg_short_spread = float(short_spreads.mean()) if len(short_spreads) else 0.0
                rebalance_cost = 0.5 * (avg_long_spread / 2) + 0.5 * (avg_short_spread / 2)

                long_names, short_names = new_long, new_short

        if date_i > start_idx and (long_names or short_names):
            long_r = daily_ret.loc[date, long_names].mean() if long_names else 0.0
            short_r = daily_ret.loc[date, short_names].mean() if short_names else 0.0
            long_r = 0.0 if np.isnan(long_r) else long_r
            short_r = 0.0 if np.isnan(short_r) else short_r
            daily_borrow = borrow_cost(position_value=0.5, holding_days=1, annual_rate=BORROW_ANNUAL_RATE)
            period_ret = 0.5 * long_r - 0.5 * short_r - daily_borrow + (RF_ANNUAL / 252) - rebalance_cost
            pv_list.append(pv_list[-1] * (1 + period_ret))
        else:
            pv_list.append(pv_list[-1])

    return pd.Series(pv_list[1:], index=trade_dates)


def load_spy(start=None, end=None):
    s = hyp037.load_hedge(hyp037.FULL_START, FULL_END_WITH_OOS)
    if start is not None or end is not None:
        s = s.loc[start:end]
    return s


def combine_thirds(spy_price, hyp037_pv, mom_ls_pv, start_capital=1.0):
    df = pd.concat([spy_price.rename("spy"), hyp037_pv.rename("hyp037"), mom_ls_pv.rename("mom_ls")],
                    axis=1, join="inner").dropna()
    spy_ret = df["spy"].pct_change()
    hyp_ret = df["hyp037"].pct_change()
    mom_ret = df["mom_ls"].pct_change()

    calendar_dates = df.resample(REBAL_FREQ).last().index
    snapped = snap_rebalance_dates(calendar_dates, df.index)
    rebal_set = set(snapped["execution_date"])

    spy_leg = start_capital * WEIGHT_EACH
    hyp_leg = start_capital * WEIGHT_EACH
    mom_leg = start_capital * WEIGHT_EACH
    values, dates = [], []

    for i in range(1, len(df)):
        date = df.index[i]
        r_spy, r_hyp, r_mom = spy_ret.iloc[i], hyp_ret.iloc[i], mom_ret.iloc[i]
        if not np.isnan(r_spy):
            spy_leg *= (1 + r_spy)
        if not np.isnan(r_hyp):
            hyp_leg *= (1 + r_hyp)
        if not np.isnan(r_mom):
            mom_leg *= (1 + r_mom)
        total = spy_leg + hyp_leg + mom_leg
        if date in rebal_set:
            spy_leg = total * WEIGHT_EACH
            hyp_leg = total * WEIGHT_EACH
            mom_leg = total * WEIGHT_EACH
        values.append(total)
        dates.append(date)

    return pd.Series(values, index=dates)


def sharpe(s, rf=RF_ANNUAL):
    r = s.pct_change().dropna()
    return float(np.sqrt(252) * (r - rf / 252).mean() / r.std()) if r.std() > 0 else 0.0


def max_drawdown(s):
    return float(((s - s.cummax()) / s.cummax()).min())


def cagr(s):
    return float((s.iloc[-1] / s.iloc[0]) ** (252 / len(s)) - 1)


def calmar(s):
    md = abs(max_drawdown(s))
    return cagr(s) / md if md > 0 else 0.0


def main():
    t0 = time.time()
    print("Laddar universum (huvudserie + 2025-utokning, sammanslaget)...")
    with ORIGINAL_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_orig = json.load(f)
    with EXTENSION_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_2025 = json.load(f)
    universe_merged = {**universe_orig, **universe_2025}

    print("Bygger om momentum L/S-sviten MED spreadkostnad (2010-2025, en genomgang)...")
    mom_ls_full = compute_momentum_ls_sleeve_with_spread(universe_merged)
    print(f"  {len(mom_ls_full)} dagar, {mom_ls_full.index[0].date()} till {mom_ls_full.index[-1].date()}, "
          f"{time.time()-t0:.0f}s\n")

    spy_full = load_spy()
    levels = [100_000, 1_000_000, 10_000_000]

    print("=== ROBUSTHETSKONTROLL: HYP-043 MED spreadkostnad pa momentum L/S-benet ===\n")
    for level in levels:
        hyp037_pv = pd.read_csv(HYP037_RESULTS / f"portfolio_value_{level}.csv",
                                 index_col=0, parse_dates=True)["portfolio_value"]
        combined = combine_thirds(spy_full, hyp037_pv, mom_ls_full)

        sh, md, cg, cm = sharpe(combined), max_drawdown(combined), cagr(combined), calmar(combined)
        ref = HYP043_LOCKED[level]
        print(f"${level:>10,.0f}  Sharpe={sh:.4f} (last: {ref['sharpe']:.4f}, diff {sh-ref['sharpe']:+.4f})  "
              f"MaxDD={md:.2%} (last: {ref['max_drawdown']:.2%})  CAGR={cg:+.2%}  Calmar={cm:.3f}")

    print("\n=== OOS-2025 ===\n")
    spy_oos = load_spy(start=OOS_START, end=FULL_END_WITH_OOS)
    mom_ls_oos = mom_ls_full.loc[OOS_START:FULL_END_WITH_OOS]
    for level in levels:
        hyp037_oos_pv = pd.read_csv(HYP037_OOS_RESULTS / f"portfolio_value_oos_2025_{level}.csv",
                                     index_col=0, parse_dates=True)["portfolio_value"]
        combined_oos = combine_thirds(spy_oos, hyp037_oos_pv, mom_ls_oos)
        sh_oos = sharpe(combined_oos)
        ref = HYP043_LOCKED[level]
        print(f"${level:>10,.0f}  OOS-Sharpe={sh_oos:.4f} (last: {ref['oos_2025_sharpe']:.4f}, "
              f"diff {sh_oos-ref['oos_2025_sharpe']:+.4f})")

    print(f"\nKLART, {time.time()-t0:.0f}s totalt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
