#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes an - ingen K-kostnad): bygger TRE nya
kandidat-ben (dollarneutrala L/S-sviter over small-cap-universumet,
samma konstruktionsdisciplin som momentum L/S-sviten i HYP-043) och
mater deras EGEN Sharpe/CAGR/MaxDD samt korrelation mot de redan kanda
serierna - FORE nagon vikt eller kriterium las, samma princip som
HYP-039/041/043:s egna forhandskontroller (spec §5b).

Kandidater (CEO-godkant sokutrymme 2026-08-07: kandidat-ben for ett
mojligt 4:e ben i den redan godkanda SPY+HYP-037+momentum-L/S-
kombinationen, INGET av detta ar annu last):

  1. LOW-VOL L/S: long lagsta-decilen trailing realiserad volatilitet
     (126 dagar), kort hogsta-decilen, dollarneutralt.
  2. KVALITET L/S: long topp-decilen rorelselonsamhet
     (OperatingIncomeLoss/Assets, samma as-of-filed-data som HYP-024),
     kort botten-decilen, bank-/finansnamn exkluderade (samma skal som
     HYP-024 - rorelseresultat ej jamforbart for banker/REITs).
  3. 52-VECKORS-HOGSTA L/S: long namn nara sitt eget 252-dagars hogsta
     (George & Hwang 2004-stil), kort namn langt under.

(Multi-asset trendfoljningssviten testas separat, se
scripts/diagnostic_trend_following_sleeve_no_spy.py - annan datakalla,
ingen small-cap-universumladdning behovs dar.)

Samma motorkrav som momentum L/S-sviten (HYP-043): adjusted_close
genomgaende, data_hygiene.clean_price_matrix + flag_implausible_liquidity,
sarheten mot konstant orimlig adjusted_close/close-kvot (>100x/<0.01x).
Universum/prismatriser laddas EN gang och ateranvands for alla tre
sviterna (kostsamt steg, ~2 minuter for 5162 tickers).
"""

import bisect
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
from sector import load_bank_financial_flags  # noqa: E402

PROFITABILITY_FILE = CACHE_DIR / "profitability_by_ticker.jsonl"

REBAL_FREQ = "QE"
DECILE_FRACTION = 0.10
BORROW_ANNUAL_RATE = 0.03
RF_ANNUAL = 0.02
VOL_WINDOW = 126
HIGH_WINDOW = 252
MIN_HISTORY_DAYS = 260  # 252 (hogsta-fonster) + lite marginal, samma anda som MIN_HISTORY_DAYS pa HYP-024


# ════════════════════════════════════════════════════════════
#  DATA (laddas EN gang, ateranvands for alla tre sviterna)
# ════════════════════════════════════════════════════════════
def load_profitability_data() -> dict:
    """Identisk med HYP-024:s backtest.py:load_profitability_data()."""
    profitability = {}
    if not PROFITABILITY_FILE.exists():
        return profitability
    with PROFITABILITY_FILE.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            opinc_list = row.get("operating_income", [])
            assets_list = row.get("assets", [])
            if not opinc_list or not assets_list:
                continue
            assets_by_end = {a["end"]: a for a in assets_list if a.get("val") not in (None, 0)}
            observations = []
            for oi in opinc_list:
                a = assets_by_end.get(oi["end"])
                if a is None or oi.get("val") is None:
                    continue
                ratio = oi["val"] / a["val"]
                observations.append((oi["filed"], ratio))
            if observations:
                observations.sort()
                profitability[row["ticker"]] = observations
    return profitability


def profitability_asof(profitability: dict, ticker: str, as_of_date_str: str):
    obs = profitability.get(ticker)
    if not obs:
        return None
    dates = [o[0] for o in obs]
    idx = bisect.bisect_left(dates, as_of_date_str) - 1
    if idx < 0:
        return None
    return obs[idx][1]


# ════════════════════════════════════════════════════════════
#  GENERISK DOLLARNEUTRAL DECIL-L/S-MOTOR (delad av alla tre sviterna)
# ════════════════════════════════════════════════════════════
def run_ls_sleeve(name, close, daily_ret, universe_by_month, tidx, rebal_map, rebal_set,
                   start_idx, trade_dates, score_fn):
    """score_fn(date, date_i, eligible_tickers) -> dict[ticker] = score (hogre = "battre",
    LONG = topp-decilen, SHORT = botten-decilen av score). Samma dollarneutrala
    50/50-struktur och lanekostnadsmodell som momentum L/S-sviten (HYP-043)."""
    long_names, short_names = [], []
    pv_list = [1.0]
    n_rebals_with_data = 0

    for date_i in range(start_idx, len(close.index)):
        date = close.index[date_i]

        if date in rebal_set:
            month_key = rebal_map[date].strftime("%Y-%m-%d")
            eligible = [t for t in universe_by_month.get(month_key, []) if t in tidx]
            scores = score_fn(date, date_i, eligible)
            if len(scores) >= 20:
                n_rebals_with_data += 1
                ranked = sorted(scores.items(), key=lambda kv: kv[1])  # stigande: lagst forst
                n_decile = max(1, int(len(ranked) * DECILE_FRACTION))
                short_names = [t for t, _ in ranked[:n_decile]]   # lagst score = short
                long_names = [t for t, _ in ranked[-n_decile:]]   # hogst score = long

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

    print(f"  [{name}] {n_rebals_with_data} ombalanseringar med tillrackligt data (>=20 namn).")
    return pd.Series(pv_list[1:], index=trade_dates)


def sharpe(s, rf=RF_ANNUAL):
    r = s.pct_change().dropna()
    return float(np.sqrt(252) * (r - rf / 252).mean() / r.std()) if r.std() > 0 else 0.0


def max_drawdown(s):
    return float(((s - s.cummax()) / s.cummax()).min())


def cagr(s):
    return float((s.iloc[-1] / s.iloc[0]) ** (252 / len(s)) - 1)


def main():
    t0 = time.time()
    print("Laddar universum + prismatriser (EN gang, ateranvands for alla tre sviterna)...")
    tickers, universe_by_month = hyp037.load_universe()
    close, close_adj, high, low, volume = hyp037.load_price_matrices(tickers, hyp037.FULL_START, hyp037.FULL_END)
    print(f"  {close.shape}, {time.time() - t0:.0f}s\n")

    print("Sanerar prisdata (standardfilter + konstant-kvot-sarhet)...")
    close, high, low = hyp037.clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    implausible = hyp037.flag_implausible_liquidity(close, volume, max_market_cap=hyp037.MAX_MARKET_CAP,
                                                      window=hyp037.ADV_WINDOW, multiplier=1.0)
    close_adj = close_adj.mask(implausible)
    ratio = (close_adj / close).replace([np.inf, -np.inf], np.nan)
    implausible_ratio = (ratio > 100) | (ratio < 0.01)
    close_adj = close_adj.mask(implausible_ratio)
    daily_ret = close_adj.pct_change()

    print("Beräknar signalmatriser (trailing vol 126d, 252-dagars-hogsta-narhet)...")
    trailing_vol = daily_ret.rolling(VOL_WINDOW).std()
    rolling_high = close_adj.rolling(HIGH_WINDOW).max()
    high_proximity = close_adj / rolling_high

    print("Laddar rörelselönsamhet + bank-/finansflaggor (for kvalitetssviten)...")
    profitability = load_profitability_data()
    bank_flags = load_bank_financial_flags(tickers)
    print(f"  {len(profitability)} tickers med lonsamhetsdata, "
          f"{sum(bank_flags.values())} klassade bank/finans (exkluderas fran kvalitetssviten).\n")

    tidx = {t: i for i, t in enumerate(close.columns)}
    calendar_dates = close.resample(REBAL_FREQ).last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[MIN_HISTORY_DAYS])
                                     & (calendar_dates <= close.index[-1])]
    snapped = snap_rebalance_dates(calendar_dates, close.index)
    rebal_map = dict(zip(snapped["execution_date"], snapped["calendar_label"]))
    rebal_set = set(snapped["execution_date"])
    start_idx = close.index.get_indexer([snapped["execution_date"].iloc[0]])[0]
    trade_dates = close.index[start_idx:]

    def lowvol_score_fn(date, date_i, eligible):
        vals = trailing_vol.loc[date, eligible].dropna()
        # LAGST vol ska bli LONG -> negera sa att "hogre score = battre" halls konsekvent
        return {t: -v for t, v in vals.items()}

    def quality_score_fn(date, date_i, eligible):
        as_of = date.strftime("%Y-%m-%d")
        elig_nonbank = [t for t in eligible if not bank_flags.get(t, False)]
        out = {}
        for t in elig_nonbank:
            r = profitability_asof(profitability, t, as_of)
            if r is not None:
                out[t] = r
        return out

    def highprox_score_fn(date, date_i, eligible):
        vals = high_proximity.loc[date, eligible].dropna()
        return dict(vals)

    print("=== Bygger LOW-VOL L/S-sviten ===")
    lowvol_pv = run_ls_sleeve("low-vol", close, daily_ret, universe_by_month, tidx, rebal_map, rebal_set,
                               start_idx, trade_dates, lowvol_score_fn)

    print("=== Bygger KVALITET (rorelselonsamhet) L/S-sviten ===")
    quality_pv = run_ls_sleeve("kvalitet", close, daily_ret, universe_by_month, tidx, rebal_map, rebal_set,
                                start_idx, trade_dates, quality_score_fn)

    print("=== Bygger 52-VECKORS-HOGSTA L/S-sviten ===")
    highprox_pv = run_ls_sleeve("52w-high", close, daily_ret, universe_by_month, tidx, rebal_map, rebal_set,
                                 start_idx, trade_dates, highprox_score_fn)

    RESULTS_DIR = CACHE_DIR
    lowvol_pv.to_csv(RESULTS_DIR / "diag_lowvol_ls_sleeve_pv.csv", header=["portfolio_value"])
    quality_pv.to_csv(RESULTS_DIR / "diag_quality_ls_sleeve_pv.csv", header=["portfolio_value"])
    highprox_pv.to_csv(RESULTS_DIR / "diag_highprox_ls_sleeve_pv.csv", header=["portfolio_value"])

    print("\n=== EGEN PRESTANDA (2010-2024, isolerat ben, ingen kombination) ===")
    for name, pv in [("Low-vol L/S", lowvol_pv), ("Kvalitet L/S", quality_pv), ("52w-hogsta L/S", highprox_pv)]:
        print(f"  {name:<18} Sharpe={sharpe(pv):.4f}  CAGR={cagr(pv):+.2%}  MaxDD={max_drawdown(pv):.2%}")

    print("\n=== KORRELATIONSMATRIS (dagliga avkastningar, mot redan kanda serier) ===")
    spy = hyp037.load_hedge(hyp037.FULL_START, hyp037.FULL_END)
    h37 = pd.read_csv(STRATEGIES_ROOT / "HYP-037" / "results" / "portfolio_value_100000.csv",
                       index_col=0, parse_dates=True).iloc[:, 0]
    mom_ls = pd.read_csv(STRATEGIES_ROOT / "HYP-043" / "results" / "momentum_ls_sleeve_pv.csv",
                          index_col=0, parse_dates=True).iloc[:, 0]
    combo43 = pd.read_csv(STRATEGIES_ROOT / "HYP-043" / "results" / "portfolio_value_combined_100000.csv",
                           index_col=0, parse_dates=True).iloc[:, 0]

    series = {
        "SPY": spy, "HYP037": h37, "MomentumLS": mom_ls, "HYP043_combo": combo43,
        "LowVolLS": lowvol_pv, "QualityLS": quality_pv, "HighProxLS": highprox_pv,
    }
    rets = pd.concat({k: v.pct_change() for k, v in series.items()}, axis=1, join="inner").dropna()
    print(f"  ({len(rets)} overlappande dagar)\n")
    print(rets.corr().round(4).to_string())

    print(f"\nKLART, {time.time() - t0:.0f}s totalt. Sparat till data/cache/diag_*_ls_sleeve_pv.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
