#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes an - ingen K-kostnad): "bear catcher" -
trendfoljande INDEX-SHORT pa SPY, framtagen fran en 4-AI-brainstorm
2026-08-07 (se session samma datum). Starkast samstammiga rekommendation
av fyra oberoende AI-svar (trendfoljning/managed-futures-stil "crisis
alpha", Hurst/Ooi/Pedersen-traditionen).

MEKANISM: SPY under sitt eget 200-dagars glidande medel -> KORT SPY
(inte bara kontant - det ar hela poangen, "offensiv" inte "defensiv").
SPY over 200-dagars MA -> kontant (INGEN lang position har - portfoljen
har redan ett eget SPY-lang-ben pa annat hall, denna svit ska INTE
duplicera den exponeringen, bara tillfora den korta/kris-sidan).

VIKTIG METODOLOGISK SKARPNING (adresserar en explicit kritik fran en av
de fyra AI:erna): min tidigare attributionsanalys (5 kanda krisepisoder
= 8% av dagarna = -26.76% av avkastningen) ar SJALV hindsight-vald som
designunderlag - VILKEN mekanism som helst som fangar just de 5 kanda
kriserna kan ocksa ha triggat FALSKT vid manga andra tillfallen som
INTE syns i den attributionen. Denna diagnostik matter darfor INTE bara
prestanda under de 5 kanda fonstren, utan:
  1. Sviten egen prestanda over HELA 2010-2024 (alla episoder den
     faktiskt handlar, inte bara de kanda kriserna).
  2. Varje enskild "kort-episod" (sammanhangande period med position=-1)
     listad separat med sin egen avkastning - for att se hur manga som
     var "traffar" (SPY fortsatte falla) mot "falsklarm" (SPY vande upp
     efter entry).
  3. Hur stor andel av den TOTALA vinsten/forlusten som kommer fran de
     5 redan kanda krisepisoderna vs. fran ovriga episoder - om nastan
     all vinst sitter i just de 5 kanda fonstren ar det en varningssignal
     om att mekanismen ar mer "tur i just dessa fall" an en genuint
     robust, generaliserbar edge.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
STRATEGIES_ROOT = REPO_ROOT / "strategies"
OHLCV_DIR = REPO_ROOT / "data" / "cache" / "ohlcv"

SMA_WINDOW = 200
BORROW_ANNUAL_RATE = 0.03  # samma konvention som resten av registret, sannolikt konservativt for SPY
RF_ANNUAL = 0.02

FULL_START = "2010-01-01"
FULL_END = "2024-12-31"

KNOWN_CRISIS_WINDOWS = {
    "2011 skuldtak": ("2011-07-25", "2011-08-15"),
    "2015 Black Monday": ("2015-08-17", "2015-08-31"),
    "2018 julafton": ("2018-12-01", "2018-12-26"),
    "2020 covid": ("2020-02-19", "2020-03-23"),
    "2022 bjornmarknad": ("2022-01-01", "2022-10-31"),
}


def load_prices(ticker):
    path = OHLCV_DIR / f"{ticker}.csv"
    df = pd.read_csv(path, usecols=["date", "adjusted_close"], parse_dates=["date"])
    df = df.drop_duplicates(subset="date", keep="last").set_index("date").sort_index()
    return df["adjusted_close"]


def build_bear_catcher(spy: pd.Series, start=None, end=None, start_capital=1.0):
    if start is not None or end is not None:
        spy = spy.loc[start:end]
    sma = spy.rolling(SMA_WINDOW).mean()
    short_signal = spy < sma  # True = kort SPY, False = kontant

    daily_ret = spy.pct_change()
    pv = start_capital
    values, dates, positions = [], [], []

    start_idx = SMA_WINDOW  # forsta dagen med ett giltigt 200-dagars MA
    for i in range(start_idx, len(spy)):
        date = spy.index[i]
        is_short = bool(short_signal.iloc[i])
        r = daily_ret.iloc[i]
        r = 0.0 if np.isnan(r) else r

        if is_short:
            daily_borrow = (BORROW_ANNUAL_RATE / 252)
            period_ret = -r - daily_borrow
        else:
            period_ret = RF_ANNUAL / 252

        pv *= (1 + period_ret)
        values.append(pv)
        dates.append(date)
        positions.append(-1 if is_short else 0)

    pv_series = pd.Series(values, index=dates)
    pos_series = pd.Series(positions, index=dates)
    return pv_series, pos_series


def find_episodes(pos_series: pd.Series, pv_series: pd.Series):
    """Identifierar sammanhangande kort-episoder (position==-1) och
    beraknar varje episods egen avkastning (portfoljvarde vid slut / vid
    start - 1, isolerat till just den episoden)."""
    episodes = []
    in_episode = False
    start_date = None
    start_pv = None
    prev_pv = None

    for date, pos in pos_series.items():
        pv = pv_series.loc[date]
        if pos == -1 and not in_episode:
            in_episode = True
            start_date = date
            start_pv = prev_pv if prev_pv is not None else pv
        elif pos == 0 and in_episode:
            in_episode = False
            episodes.append({"start": start_date, "end": prev_date, "return": prev_pv / start_pv - 1})
        prev_pv = pv
        prev_date = date

    if in_episode:
        episodes.append({"start": start_date, "end": prev_date, "return": prev_pv / start_pv - 1})

    return episodes


def sharpe(s, rf=RF_ANNUAL):
    r = s.pct_change().dropna()
    return float(np.sqrt(252) * (r - rf / 252).mean() / r.std()) if r.std() > 0 else 0.0


def max_drawdown(s):
    return float(((s - s.cummax()) / s.cummax()).min())


def cagr(s):
    return float((s.iloc[-1] / s.iloc[0]) ** (252 / len(s)) - 1)


def main():
    spy = load_prices("SPY")
    print("Bygger 'bear catcher' (kort SPY under 200-dagars MA, annars kontant)...")
    pv, pos = build_bear_catcher(spy, start=FULL_START, end=FULL_END)
    print(f"  {len(pv)} dagar, {pv.index[0].date()} till {pv.index[-1].date()}\n")

    print(f"Sviten egen prestanda (2010-2024, ALLA episoder): Sharpe={sharpe(pv):.4f}  "
          f"CAGR={cagr(pv):+.2%}  MaxDD={max_drawdown(pv):.2%}")
    frac_short = float((pos == -1).mean())
    print(f"  Andel av dagarna kort: {frac_short:.1%}\n")

    episodes = find_episodes(pos, pv)
    wins = [e for e in episodes if e["return"] > 0]
    losses = [e for e in episodes if e["return"] <= 0]
    print(f"=== Episodanalys (adresserar hindsight-kritiken) ===")
    print(f"Totalt {len(episodes)} sammanhangande kort-episoder over hela perioden.")
    print(f"  {len(wins)} traffar (positiv avkastning), {len(losses)} falsklarm (negativ/noll avkastning)")
    print(f"  Traffprocent: {len(wins)/len(episodes):.1%}\n")

    print("Alla episoder, kronologiskt:")
    for e in episodes:
        flag = "TRAFF" if e["return"] > 0 else "falsklarm"
        print(f"  {e['start'].date()} -> {e['end'].date()}  avkastning={e['return']:+.2%}  [{flag}]")

    # Hur stor andel av total P&L kommer fran de 5 KANDA krisfonstren vs ovriga episoder?
    def overlaps_known_crisis(ep):
        for _, (s, e) in KNOWN_CRISIS_WINDOWS.items():
            if not (ep["end"] < pd.Timestamp(s) or ep["start"] > pd.Timestamp(e)):
                return True
        return False

    known_crisis_episodes = [e for e in episodes if overlaps_known_crisis(e)]
    other_episodes = [e for e in episodes if not overlaps_known_crisis(e)]

    def total_log_return(eps):
        if not eps:
            return 0.0
        return sum(np.log1p(e["return"]) for e in eps)

    total_pnl = total_log_return(episodes)
    known_pnl = total_log_return(known_crisis_episodes)
    other_pnl = total_log_return(other_episodes)

    print(f"\n=== Fordelning av total P&L (log-avkastning, additiv) ===")
    print(f"  Fran de 5 KANDA krisfonstren ({len(known_crisis_episodes)} episoder): {known_pnl:+.4f} "
          f"({100*known_pnl/total_pnl:.1f}% av total)" if total_pnl != 0 else "  (total P&L ar noll)")
    print(f"  Fran OVRIGA {len(other_episodes)} episoder: {other_pnl:+.4f} "
          f"({100*other_pnl/total_pnl:.1f}% av total)" if total_pnl != 0 else "")
    print(f"  Totalt: {total_pnl:+.4f}")

    print(f"\n=== Prestanda under de 5 kanda krisfonstren specifikt ===")
    for name, (s, e) in KNOWN_CRISIS_WINDOWS.items():
        seg = pv.loc[s:e]
        if len(seg) > 1:
            print(f"  {name:<20} {seg.iloc[-1]/seg.iloc[0]-1:+.2%}")

    print("\n=== Korrelationsmatris (dagliga avkastningar, mot redan kanda serier) ===")
    h37 = pd.read_csv(STRATEGIES_ROOT / "HYP-037" / "results" / "portfolio_value_100000.csv",
                       index_col=0, parse_dates=True).iloc[:, 0]
    mom_ls = pd.read_csv(STRATEGIES_ROOT / "HYP-043" / "results" / "momentum_ls_sleeve_pv.csv",
                          index_col=0, parse_dates=True).iloc[:, 0]
    combo43 = pd.read_csv(STRATEGIES_ROOT / "HYP-043" / "results" / "portfolio_value_combined_100000.csv",
                           index_col=0, parse_dates=True).iloc[:, 0]
    series = {"BearCatcher": pv, "SPY": spy, "HYP037": h37, "MomentumLS": mom_ls, "HYP043_combo": combo43}
    rets = pd.concat({k: v.pct_change() for k, v in series.items()}, axis=1, join="inner").dropna()
    print(f"  ({len(rets)} overlappande dagar)\n")
    print(rets.corr().round(4).to_string())

    pv.to_csv(REPO_ROOT / "data" / "cache" / "bear_catcher_trend_short_pv.csv", header=["portfolio_value"])
    print("\nSparad till data/cache/bear_catcher_trend_short_pv.csv for ateranvandning om detta blir en hypotes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
