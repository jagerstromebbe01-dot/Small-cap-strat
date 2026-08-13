#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes - ingen K-kostnad, andrar INGET last
resultat): "forsok att slå sönder" HYP-047:s bear catcher-mekanism
genom att testa den mot AKTA historisk data den ALDRIG sett - 2000-2002
(dotcom-bjornmarknaden) och 2008 (finanskrisen), tva av de mest kanda
utdragna bjornmarknaderna i modern historia, INGENDERA inom HYP-047:s
egen backtestperiod (2010-2024).

Hamtar SPY fran 1999 (ny EODHD-hamtning, sparas INTE i den delade
data/cache/ohlcv/SPY.csv som resten av registret anvander - detta ar
en fristaende diagnostikfil for att inte pav erka nagon redan last
hypotes resultat).

Samma mekanism som HYP-047:s bear catcher-ben, oforandrad: SPY under
200-dagars glidande medel -> kort, annars kontant. Samma episod-
analysmetod som scripts/diagnostic_bear_catcher_trend_short.py (alla
episoder, inte bara handplockade fonster).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
OHLCV_DIR = CACHE_DIR / "ohlcv"
EXT_CACHE_FILE = CACHE_DIR / "spy_extended_1999_2009_diagnostic_only.csv"

sys.path.insert(0, str(DATA_DIR))
from eodhd_adapter import get_daily_ohlcv  # noqa: E402

SMA_WINDOW = 200
BORROW_ANNUAL_RATE = 0.03
RF_ANNUAL = 0.02

STRESS_WINDOWS = {
    "2000-2002 dotcom-bjornmarknad": ("2000-03-01", "2002-10-31"),
    "2008 finanskrisen": ("2008-01-01", "2009-03-31"),
    "2011 skuldtak": ("2011-07-25", "2011-08-15"),
    "2015 Black Monday": ("2015-08-17", "2015-08-31"),
    "2018 julafton": ("2018-12-01", "2018-12-26"),
    "2020 covid": ("2020-02-19", "2020-03-23"),
    "2022 bjornmarknad": ("2022-01-01", "2022-10-31"),
}


def fetch_or_load_extension():
    if EXT_CACHE_FILE.exists():
        return pd.read_csv(EXT_CACHE_FILE, parse_dates=["date"])
    print("Hamtar SPY 1999-01-01 till 2009-12-31 (fristaende diagnostikcache, paverkar INGEN delad fil)...")
    rows = get_daily_ohlcv("SPY", "1999-01-01", "2009-12-31")
    df = pd.DataFrame(rows)
    df.to_csv(EXT_CACHE_FILE, index=False)
    return df


def load_full_spy():
    ext = fetch_or_load_extension()
    ext = ext[["date", "adjusted_close"]].copy()
    ext["date"] = pd.to_datetime(ext["date"])

    main = pd.read_csv(OHLCV_DIR / "SPY.csv", usecols=["date", "adjusted_close"], parse_dates=["date"])

    combined = pd.concat([ext, main], axis=0).drop_duplicates(subset="date", keep="last").sort_values("date")
    combined = combined.set_index("date")["adjusted_close"]
    return combined


def build_bear_catcher(spy: pd.Series) -> tuple[pd.Series, pd.Series]:
    sma = spy.rolling(SMA_WINDOW).mean()
    short_signal = spy < sma
    daily_ret = spy.pct_change()

    pv_list = [1.0]
    dates, positions = [], []
    start_idx = SMA_WINDOW
    for i in range(start_idx, len(spy)):
        date = spy.index[i]
        is_short = bool(short_signal.iloc[i])
        r = daily_ret.iloc[i]
        r = 0.0 if np.isnan(r) else r
        if is_short:
            daily_borrow = BORROW_ANNUAL_RATE / 252
            period_ret = -r - daily_borrow
        else:
            period_ret = RF_ANNUAL / 252
        pv_list.append(pv_list[-1] * (1 + period_ret))
        dates.append(date)
        positions.append(-1 if is_short else 0)

    return pd.Series(pv_list[1:], index=dates), pd.Series(positions, index=dates)


def find_episodes(pos_series: pd.Series, pv_series: pd.Series):
    episodes = []
    in_episode = False
    start_date = start_pv = prev_pv = prev_date = None
    for date, pos in pos_series.items():
        pv = pv_series.loc[date]
        if pos == -1 and not in_episode:
            in_episode = True
            start_date = date
            start_pv = prev_pv if prev_pv is not None else pv
        elif pos == 0 and in_episode:
            in_episode = False
            episodes.append({"start": start_date, "end": prev_date, "return": prev_pv / start_pv - 1})
        prev_pv, prev_date = pv, date
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
    spy = load_full_spy()
    print(f"SPY-serie: {spy.index[0].date()} till {spy.index[-1].date()} ({len(spy)} dagar)\n")

    pv, pos = build_bear_catcher(spy)
    print(f"=== Bear catcher, HELA perioden {pv.index[0].date()}-{pv.index[-1].date()} ===")
    print(f"Sharpe={sharpe(pv):.4f}  CAGR={cagr(pv):+.2%}  MaxDD={max_drawdown(pv):.2%}")
    frac_short = float((pos == -1).mean())
    print(f"Andel av dagarna kort: {frac_short:.1%}\n")

    episodes = find_episodes(pos, pv)
    wins = [e for e in episodes if e["return"] > 0]
    losses = [e for e in episodes if e["return"] <= 0]
    print(f"Totalt {len(episodes)} episoder over HELA perioden (inkl. 1999-2009): "
          f"{len(wins)} traffar, {len(losses)} falsklarm ({len(wins)/len(episodes):.1%} traffprocent)\n")

    print("=== De mest relevanta episoderna: 2000-2002 och 2008 (ALDRIG testade i HYP-047) ===")
    for e in episodes:
        if e["start"] < pd.Timestamp("2010-01-01"):
            flag = "TRAFF" if e["return"] > 0 else "FALSKLARM"
            dur = (e["end"] - e["start"]).days
            print(f"  {e['start'].date()} -> {e['end'].date()}  ({dur:>4} dagar)  avkastning={e['return']:+.2%}  [{flag}]")

    print("\n=== Prestanda under specifika stressfonster (inkl. de tva ALDRIG testade) ===")
    for name, (s, e) in STRESS_WINDOWS.items():
        seg = pv.loc[s:e]
        if len(seg) > 1:
            spy_seg = spy.loc[s:e]
            spy_ret = spy_seg.iloc[-1] / spy_seg.iloc[0] - 1
            print(f"  {name:<32} bear catcher: {seg.iloc[-1]/seg.iloc[0]-1:+8.2%}   (SPY samtidigt: {spy_ret:+8.2%})")

    print(f"\n=== Sub-periods Sharpe (fore vs under HYP-047:s egen testperiod) ===")
    pre_2010 = pv.loc[:"2009-12-31"]
    from_2010 = pv.loc["2010-01-01":]
    if len(pre_2010) > 100:
        print(f"  1999-2009 (ALDRIG testat i HYP-047): Sharpe={sharpe(pre_2010):.4f}  "
              f"CAGR={cagr(pre_2010):+.2%}  MaxDD={max_drawdown(pre_2010):.2%}")
    print(f"  2010-2024 (HYP-047:s egen period):    Sharpe={sharpe(from_2010):.4f}  "
          f"CAGR={cagr(from_2010):+.2%}  MaxDD={max_drawdown(from_2010):.2%}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
