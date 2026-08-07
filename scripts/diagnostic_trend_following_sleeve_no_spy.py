#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes an - ingen K-kostnad): variant av
scripts/diagnostic_trend_following_sleeve.py UTAN SPY i tillgangskorgen.

Motivering (2026-08-07): originalversionen inkluderade SPY som en av de
fyra trendade tillgangarna, vilket gav 0.516 korrelation mot SPY - allt
for hogt for ett kandidat-4:e-ben i en portfolj som REDAN har SPY som
ett eget ben (1/3 av HYP-039/043). En trendsvit som bara ar "SPY nar SPY
trendar" tillfor ingen genuin diversifiering, den delvis DUBBLERAR ett
befintligt ben. Denna variant testar bara TLT/GLD/DBC (rena makro-
tillgangar, ingen aktieindexexponering) - en renare test av om
tillgangsklass-trendfoljning (utan aktieindex) kan tillfora nagot som
INTE redan finns i portfoljen.

Samma mekanism i ovrigt: kvartalsvis, 12-manaders trailing avkastning >0
-> long till nasta kvartal, annars kontanter (ingen blankning), likaviktat
mellan tillgangar "i trend".
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
STRATEGIES_ROOT = REPO_ROOT / "strategies"
OHLCV_DIR = REPO_ROOT / "data" / "cache" / "ohlcv"

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
from rebalancing import snap_rebalance_dates  # noqa: E402

ASSETS = ["TLT", "GLD", "DBC"]  # SPY BORTTAGEN, se moduldocstring
REBAL_FREQ = "QE"
LOOKBACK_DAYS = 252


def load_prices(ticker):
    path = OHLCV_DIR / f"{ticker}.csv"
    df = pd.read_csv(path, usecols=["date", "adjusted_close"], parse_dates=["date"])
    df = df.drop_duplicates(subset="date", keep="last").set_index("date").sort_index()
    return df["adjusted_close"]


def build_trend_sleeve(start=None, end=None, start_capital=1.0):
    prices = pd.concat([load_prices(t).rename(t) for t in ASSETS], axis=1, join="inner").dropna()
    if start is not None or end is not None:
        prices = prices.loc[start:end]

    trailing_ret = prices.pct_change(LOOKBACK_DAYS)
    in_trend = trailing_ret > 0

    calendar_dates = prices.resample(REBAL_FREQ).last().index
    calendar_dates = calendar_dates[calendar_dates >= prices.index[LOOKBACK_DAYS]]
    snapped = snap_rebalance_dates(calendar_dates, prices.index)
    rebal_set = set(snapped["execution_date"])

    daily_ret = prices.pct_change()
    weights = pd.Series(0.0, index=ASSETS)
    pv = start_capital
    values, dates = [], []

    start_idx = prices.index.get_indexer([snapped["execution_date"].iloc[0]])[0]
    for i in range(start_idx, len(prices.index)):
        date = prices.index[i]
        if date in rebal_set:
            today_in_trend = in_trend.loc[date]
            n_in_trend = int(today_in_trend.sum())
            weights = pd.Series(0.0, index=ASSETS)
            if n_in_trend > 0:
                weights[today_in_trend] = 1.0 / n_in_trend

        if i > start_idx:
            r = daily_ret.loc[date]
            pv *= (1 + (weights * r).sum())

        values.append(pv)
        dates.append(date)

    return pd.Series(values, index=dates)


def sharpe(s, rf=0.02):
    r = s.pct_change().dropna()
    return float(np.sqrt(252) * (r - rf / 252).mean() / r.std()) if r.std() > 0 else 0.0


def max_drawdown(s):
    return float(((s - s.cummax()) / s.cummax()).min())


def cagr(s):
    return float((s.iloc[-1] / s.iloc[0]) ** (252 / len(s)) - 1)


def main():
    print("Bygger trendfoljningssvit (TLT/GLD/DBC, INGEN SPY, kvartalsvis, 12-manaders trend)...")
    sleeve = build_trend_sleeve()
    print(f"  {len(sleeve)} dagar, {sleeve.index[0].date()} till {sleeve.index[-1].date()}\n")

    print(f"Sviten egen prestanda: Sharpe={sharpe(sleeve):.4f}  CAGR={cagr(sleeve):+.2%}  "
          f"MaxDD={max_drawdown(sleeve):.2%}\n")

    spy = load_prices("SPY")
    h37 = pd.read_csv(STRATEGIES_ROOT / "HYP-037" / "results" / "portfolio_value_100000.csv",
                       index_col=0, parse_dates=True).iloc[:, 0]
    mom_ls = pd.read_csv(STRATEGIES_ROOT / "HYP-043" / "results" / "momentum_ls_sleeve_pv.csv",
                          index_col=0, parse_dates=True).iloc[:, 0]
    combo43 = pd.read_csv(STRATEGIES_ROOT / "HYP-043" / "results" / "portfolio_value_combined_100000.csv",
                           index_col=0, parse_dates=True).iloc[:, 0]

    series = {"TrendNoSPY": sleeve, "SPY": spy, "HYP037": h37, "MomentumLS": mom_ls, "HYP043_combo": combo43}
    rets = pd.concat({k: v.pct_change() for k, v in series.items()}, axis=1, join="inner").dropna()
    print(f"Overlappande dagar: {len(rets)} ({rets.index.min().date()} till {rets.index.max().date()})\n")
    print("Korrelationsmatris:")
    print(rets.corr().round(4).to_string())

    sleeve.to_csv(Path(__file__).resolve().parent.parent / "data" / "cache" / "trend_sleeve_no_spy_pv.csv",
                  header=["portfolio_value"])
    print("\nSparad till data/cache/trend_sleeve_no_spy_pv.csv for ateranvandning om detta blir en hypotes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
