"""
HYP-047: Bear catcher (trendfoljande SPY-short under 200-dagars MA)
som 4:e ben i den obehandlade HYP-043-basen.

Se research/hypothesis_registry/HYP-047-bear-catcher-trend-short.yaml
for det lasta kriteriet. Sjunde kombinationshypotesen i registret.

Bear catcher-benet ar OFFENSIVT (tar en genuin kort position, tjanar
pengar UNDER nedgangen) - till skillnad fran HYP-045:s overlay som
bara ar DEFENSIV (gar till kontanter). Testas har PA DEN OBEHANDLADE
HYP-043-basen (INGEN HYP-045-overlay), for att isolera bear catcherns
egen marginella effekt - HYP-046 visade redan att tva riskreducerande
mekanismer samtidigt kan overkorrigera.
"""

import bisect
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

STRATEGY_DIR = Path(__file__).resolve().parent
STRATEGIES_ROOT = STRATEGY_DIR.parent
REPO_ROOT = STRATEGIES_ROOT.parent
DATA_DIR = REPO_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
OHLCV_DIR = CACHE_DIR / "ohlcv"
RESULTS_DIR = STRATEGY_DIR / "results"

HYP037_DIR = STRATEGIES_ROOT / "HYP-037"
HYP037_RESULTS = HYP037_DIR / "results"
HYP037_OOS_RESULTS = REPO_ROOT / "paper_trading" / "HYP-037" / "oos_2025_results"

ORIGINAL_UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_by_month.json"
EXTENSION_UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_2025_extension.json"
EPS_FILE = CACHE_DIR / "eps_by_ticker.jsonl"

sys.path.insert(0, str(HYP037_DIR))
import backtest as hyp037  # noqa: E402
from friction import borrow_cost, corwin_schultz_spread  # noqa: E402

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
from rebalancing import snap_rebalance_dates  # noqa: E402

REBAL_FREQ = "QE"
WEIGHT_EACH = 0.25

MOM_LOOKBACK_DAYS = 252
MOM_SKIP_DAYS = 21
DECILE_FRACTION = 0.10
BORROW_ANNUAL_RATE = 0.03
RF_ANNUAL = 0.02
MIN_HISTORY_DAYS = 260
MIN_QUARTERS_FOR_STD = 4
MAX_QUARTERS_FOR_STD = 8
SMA_WINDOW = 200

OOS_START = "2025-01-01"
FULL_END_WITH_OOS = "2025-12-31"

HYP043_FRICTION_CORRECTED_REF = {
    100_000: {"sharpe": 0.8926, "max_drawdown": -0.1558},
    1_000_000: {"sharpe": 0.8940, "max_drawdown": -0.1568},
    10_000_000: {"sharpe": 0.8217, "max_drawdown": -0.1429},
}
HYP039_OOS_REF = {100_000: 0.9185, 1_000_000: 0.8116, 10_000_000: 0.7932}


def compute_spread_matrix(high, low):
    spread = {}
    for t in high.columns:
        spread[t] = corwin_schultz_spread(high[t].values, low[t].values)
    return pd.DataFrame(spread, index=high.index)


def load_spy_ohlc(start=None, end=None):
    df = pd.read_csv(OHLCV_DIR / "SPY.csv", usecols=["date", "high", "low", "adjusted_close"],
                      parse_dates=["date"])
    df = df.drop_duplicates(subset="date", keep="last").set_index("date").sort_index()
    if start is not None or end is not None:
        df = df.loc[start:end]
    return df


def build_bear_catcher(spy_df: pd.DataFrame) -> pd.Series:
    """SPY under 200-dagars MA -> kort (100% notional), annars kontant.
    Bade borrow_cost och halva Corwin-Schultz-spreaden (pa SPY:s egen
    high/low) vid varje in-/utgang tillamps."""
    close = spy_df["adjusted_close"]
    sma = close.rolling(SMA_WINDOW).mean()
    spread_est = corwin_schultz_spread(spy_df["high"].values, spy_df["low"].values)
    spread_series = pd.Series(spread_est, index=spy_df.index)

    daily_ret = close.pct_change()
    short_signal = close < sma

    pv_list = [1.0]
    dates = []
    prev_short = False

    start_idx = SMA_WINDOW
    for i in range(start_idx, len(spy_df)):
        date = spy_df.index[i]
        is_short = bool(short_signal.iloc[i])
        r = daily_ret.iloc[i]
        r = 0.0 if np.isnan(r) else r

        transition_cost = 0.0
        if is_short != prev_short:
            sp = spread_series.iloc[i]
            sp = 0.0 if np.isnan(sp) else sp
            transition_cost = sp / 2

        if is_short:
            daily_borrow = borrow_cost(position_value=1.0, holding_days=1, annual_rate=BORROW_ANNUAL_RATE)
            period_ret = -r - daily_borrow - transition_cost
        else:
            period_ret = (RF_ANNUAL / 252) - transition_cost

        pv_list.append(pv_list[-1] * (1 + period_ret))
        dates.append(date)
        prev_short = is_short

    return pd.Series(pv_list[1:], index=dates)


def load_sue_series() -> dict:
    """oanvand har - kvar fran mall, momentum L/S anvander egen signal."""
    return {}


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

    print("  Berknar Corwin-Schultz-spread-matris (momentum L/S)...")
    spread_df = compute_spread_matrix(high, low)

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
    print("Laddar universum (huvudserie + 2025-utokning, sammanslaget)...")
    with ORIGINAL_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_orig = json.load(f)
    with EXTENSION_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_2025 = json.load(f)
    universe_merged = {**universe_orig, **universe_2025}

    print("Bygger momentum L/S-sviten (MED spreadkostnad) over HELA 2010-2025...")
    mom_ls_raw = compute_momentum_ls_sleeve_with_spread(universe_merged)
    print(f"  {len(mom_ls_raw)} dagar\n")

    print("Bygger bear catcher-benet (SPY under 200-dagars MA)...")
    spy_ohlc = load_spy_ohlc(end=FULL_END_WITH_OOS)
    bear_catcher = build_bear_catcher(spy_ohlc)
    RESULTS_DIR.mkdir(exist_ok=True)
    bear_catcher.to_csv(RESULTS_DIR / "bear_catcher_pv.csv", header=["portfolio_value"])
    print(f"  {len(bear_catcher)} dagar\n")

    spy_raw = load_spy()
    levels = [100_000, 1_000_000, 10_000_000]

    print("=== HYP-047: huvudbacktest (2010-2024) ===")
    main_results = []
    for level in levels:
        hyp037_pv = pd.read_csv(HYP037_RESULTS / f"portfolio_value_{level}.csv",
                                 index_col=0, parse_dates=True)["portfolio_value"]
        combined = combine_quarters({"spy": spy_raw, "hyp037": hyp037_pv, "mom_ls": mom_ls_raw, "bear": bear_catcher})
        combined.to_csv(RESULTS_DIR / f"portfolio_value_combined_{level}.csv", header=["portfolio_value"])

        r = {"capital_level": level, "sharpe": sharpe(combined), "cagr": cagr(combined),
             "max_drawdown": max_drawdown(combined), "calmar": calmar(combined), "n_days": len(combined)}
        main_results.append(r)
        ref = HYP043_FRICTION_CORRECTED_REF[level]
        g1 = "PASS" if r["sharpe"] >= 1.0 else "FAIL"
        g2 = "PASS" if r["sharpe"] > ref["sharpe"] else "FAIL"
        g3 = "PASS" if r["max_drawdown"] > ref["max_drawdown"] else "FAIL"
        print(f"  ${level:>10,.0f}  Sharpe={r['sharpe']:.4f} ({g1} >=1.0; {g2} mot friktionskorr. HYP-043 {ref['sharpe']:.4f})  "
              f"MaxDD={r['max_drawdown']:.2%} ({g3} mot {ref['max_drawdown']:.2%})  "
              f"CAGR={r['cagr']:+.2%}  Calmar={r['calmar']:.3f}")

    print("\n=== HYP-047: OOS-2025 ===")
    oos_results = []
    spy_oos = spy_raw.loc[OOS_START:FULL_END_WITH_OOS]
    mom_ls_oos = mom_ls_raw.loc[OOS_START:FULL_END_WITH_OOS]
    bear_oos = bear_catcher.loc[OOS_START:FULL_END_WITH_OOS]
    for level in levels:
        hyp037_oos_pv = pd.read_csv(HYP037_OOS_RESULTS / f"portfolio_value_oos_2025_{level}.csv",
                                     index_col=0, parse_dates=True)["portfolio_value"]
        combined_oos = combine_quarters({"spy": spy_oos, "hyp037": hyp037_oos_pv, "mom_ls": mom_ls_oos, "bear": bear_oos})
        combined_oos.to_csv(RESULTS_DIR / f"portfolio_value_oos2025_combined_{level}.csv", header=["portfolio_value"])

        r = {"capital_level": level, "oos_2025_sharpe": sharpe(combined_oos),
             "oos_2025_max_drawdown": max_drawdown(combined_oos),
             "oos_2025_total_return": float(combined_oos.iloc[-1] / combined_oos.iloc[0] - 1) if len(combined_oos) > 1 else None,
             "n_days": len(combined_oos)}
        oos_results.append(r)
        ref39 = HYP039_OOS_REF[level]
        g4 = "PASS" if r["oos_2025_sharpe"] > ref39 else "FAIL"
        print(f"  ${level:>10,.0f}  OOS-Sharpe={r['oos_2025_sharpe']:.4f} ({g4} mot HYP-039:s {ref39:.4f})  "
              f"OOS-avkastning={r['oos_2025_total_return']:+.2%}  OOS-MaxDD={r['oos_2025_max_drawdown']:.2%}  "
              f"({r['n_days']} dagar)")

    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump({"main": main_results, "oos_2025": oos_results}, f, indent=2, default=str)

    print("\nKLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
