#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes an - ingen K-kostnad): tva nya kandidat-
ben, framtagna fran en 5-AI-brainstorm 2026-08-07 (extern konsultation,
se session samma datum) - CEO bad om diagnostik pa de kandidater som
verkade anvandbara efter att redan-testade fallor (raw insiderkop =
HYP-035, small-cap kortsiktig reversal = HYP-042) hade filtrerats bort.

  1. PEAD/SUE (Post-Earnings-Announcement Drift via Standardized
     Unexpected Earnings): sasongsjusterad EPS-overraskning
     (Bernard & Thomas 1989/1990-stil), long topp-decilen (storst
     positiv overraskning), kort botten-decilen. NAMND AV 4/5 externa
     AI:er, men EN AI varnade explicit for hog korrelation (0.3-0.5)
     mot 12-1-manaders momentum - denna diagnostik testar just det.
  2. NETTOEMISSION (aktieutspädning/-atekop): long lagsta 12-manaders-
     tillvaxten i utestaende aktier (atekop), kort hogsta (utspädning).
     Pontiff & Woodgate (2008), Daniel & Titman (2006).

BADA byggda med data som REDAN finns lokalt cachad - INGEN ny SEC
EDGAR-hamtning:
  - PEAD: data/cache/eps_by_ticker.jsonl (kvartals-EPS-fakta, redan
    hamtade for annat syfte).
  - Nettoemission: data/cache/market_cap_by_ticker_month_filed_date.csv
    (redan look-ahead-saker "filed date"-variant, se kodgranskningen
    2026-08-05 som fixade period-slut-vs-filed-date-problemet).

METODOLOGISKA FORENKLINGAR (diagnostik, INTE en last hypotes - se
CEO-diskussion 2026-08-07 om varje forenkling skulle behova skarpas
INNAN nagot las):
  - SUE: vid restaterade kvartal anvands FORSTA (tidigast filade)
    vardet per (fy, fp) - inte senare 10-Q/A-omraknade varden. Detta
    ar en KONSERVATIV forenkling (speglar vad som faktiskt var kant i
    realtid), inte en genvag som overskattar edgen.
  - SUE: INGEN split-justering av EPS over tid - en risk for enstaka
    tickers med aktiesplittar mellan de jamforda kvartalen (samma typ
    av risk som redan kanda datahygienproblem i detta register, men
    INTE kord genom samma sanering har).
  - Nettoemission: 12-manaders "shares"-tillvaxt fran monatlig data,
    ingen SEC-form-nivå-distinktion mellan organisk emission,
    optionsutnyttjande och M&A-driven aktieokning.
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

EPS_FILE = CACHE_DIR / "eps_by_ticker.jsonl"
MARKETCAP_FILE = CACHE_DIR / "market_cap_by_ticker_month_filed_date.csv"

REBAL_FREQ = "QE"
DECILE_FRACTION = 0.10
BORROW_ANNUAL_RATE = 0.03
RF_ANNUAL = 0.02
MIN_HISTORY_DAYS = 260
MIN_QUARTERS_FOR_STD = 4   # minst 4 tidigare overraskningar for en stabil std-skattning
MAX_QUARTERS_FOR_STD = 8


# ════════════════════════════════════════════════════════════
#  PEAD/SUE-DATA
# ════════════════════════════════════════════════════════════
def load_sue_series() -> dict:
    """ticker -> sorterad lista av (filed_date_str, sue_varde). Bygger
    fran diskreta (INTE kumulativa YTD-) kvartals-EPS, sasongsjusterad
    overraskning mot samma fiskala kvartal foregaende ar, standardiserad
    med std av upp till 8 tidigare overraskningar."""
    sue_by_ticker = {}
    n_tickers_total = 0
    with EPS_FILE.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            n_tickers_total += 1
            entries = row.get("entries", [])
            discrete = {}
            for e in entries:
                if e.get("val") is None or not e.get("start") or not e.get("end") or not e.get("fp") or not e.get("fy"):
                    continue
                try:
                    days = (pd.Timestamp(e["end"]) - pd.Timestamp(e["start"])).days
                except (ValueError, TypeError):
                    continue
                if not (80 <= days <= 100):
                    continue  # bara diskreta kvartal, inte YTD-kumulativa
                key = (e["fy"], e["fp"])
                # forsta (tidigast filade) vardet per (fy, fp) - se moduldocstring
                if key not in discrete or e["filed"] < discrete[key]["filed"]:
                    discrete[key] = e
            if len(discrete) < MIN_QUARTERS_FOR_STD + 4:
                continue

            ordered = sorted(discrete.values(), key=lambda e: e["end"])
            by_fy_fp = {(e["fy"], e["fp"]): e for e in ordered}
            surprises = []  # (filed_date, surprise_val)
            sue_points = []
            for e in ordered:
                prior_key = (e["fy"] - 1, e["fp"])
                prior = by_fy_fp.get(prior_key)
                if prior is None:
                    continue
                surprise = e["val"] - prior["val"]
                recent = [s for _, s in surprises[-MAX_QUARTERS_FOR_STD:]]
                if len(recent) >= MIN_QUARTERS_FOR_STD:
                    std = float(np.std(recent))
                    if std > 1e-6:
                        sue = surprise / std
                        sue_points.append((e["filed"], sue))
                surprises.append((e["filed"], surprise))

            if sue_points:
                sue_points.sort()
                sue_by_ticker[row["ticker"]] = sue_points

    print(f"  SUE byggd for {len(sue_by_ticker)} av {n_tickers_total} tickers (kravde >= "
          f"{MIN_QUARTERS_FOR_STD} historiska kvartalsoverraskningar for en std-skattning).")
    return sue_by_ticker


def sue_asof(sue_by_ticker: dict, ticker: str, as_of_date_str: str):
    points = sue_by_ticker.get(ticker)
    if not points:
        return None
    dates = [p[0] for p in points]
    idx = bisect.bisect_left(dates, as_of_date_str) - 1
    if idx < 0:
        return None
    return points[idx][1]


# ════════════════════════════════════════════════════════════
#  NETTOEMISSION-DATA
# ════════════════════════════════════════════════════════════
def load_shares_matrix() -> pd.DataFrame:
    """Ticker x manad-matris av utestaende aktier, fran den redan
    look-ahead-sakra filed-date-varianten."""
    df = pd.read_csv(MARKETCAP_FILE, usecols=["ticker", "month", "shares"], parse_dates=["month"])
    df = df.dropna(subset=["shares"])
    piv = df.pivot_table(index="month", columns="ticker", values="shares", aggfunc="last")
    return piv.sort_index()


def issuance_growth_asof(shares_matrix: pd.DataFrame, ticker: str, as_of_date, lookback_months=12):
    if ticker not in shares_matrix.columns:
        return None
    col = shares_matrix[ticker].dropna()
    valid = col.loc[:as_of_date]
    if len(valid) < 2:
        return None
    now_date = valid.index[-1]
    now_val = valid.iloc[-1]
    target_date = now_date - pd.DateOffset(months=lookback_months)
    prior_valid = valid.loc[:target_date]
    if len(prior_valid) == 0:
        return None
    prior_val = prior_valid.iloc[-1]
    if prior_val <= 0:
        return None
    return now_val / prior_val - 1.0


# ════════════════════════════════════════════════════════════
#  GENERISK DOLLARNEUTRAL DECIL-L/S-MOTOR (samma som
#  diagnostic_hyp044_candidate_legs.py)
# ════════════════════════════════════════════════════════════
def run_ls_sleeve(name, close, daily_ret, universe_by_month, tidx, rebal_map, rebal_set,
                   start_idx, trade_dates, score_fn):
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
    print("Laddar universum + prismatriser...")
    tickers, universe_by_month = hyp037.load_universe()
    close, close_adj, high, low, volume = hyp037.load_price_matrices(tickers, hyp037.FULL_START, hyp037.FULL_END)
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

    print("Bygger SUE-serier (PEAD-kandidaten)...")
    sue_by_ticker = load_sue_series()

    print("Laddar aktieantal-matris (nettoemission-kandidaten)...")
    shares_matrix = load_shares_matrix()
    print(f"  {shares_matrix.shape[1]} tickers med aktieantalsdata.\n")

    tidx = {t: i for i, t in enumerate(close.columns)}
    calendar_dates = close.resample(REBAL_FREQ).last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[MIN_HISTORY_DAYS])
                                     & (calendar_dates <= close.index[-1])]
    snapped = snap_rebalance_dates(calendar_dates, close.index)
    rebal_map = dict(zip(snapped["execution_date"], snapped["calendar_label"]))
    rebal_set = set(snapped["execution_date"])
    start_idx = close.index.get_indexer([snapped["execution_date"].iloc[0]])[0]
    trade_dates = close.index[start_idx:]

    def pead_score_fn(date, date_i, eligible):
        as_of = date.strftime("%Y-%m-%d")
        out = {}
        for t in eligible:
            v = sue_asof(sue_by_ticker, t, as_of)
            if v is not None:
                out[t] = v
        return out

    def issuance_score_fn(date, date_i, eligible):
        out = {}
        for t in eligible:
            g = issuance_growth_asof(shares_matrix, t, date)
            if g is not None:
                out[t] = -g  # LAG tillvaxt (atekop) ska bli LONG -> negera
        return out

    print("=== Bygger PEAD/SUE L/S-sviten ===")
    pead_pv = run_ls_sleeve("PEAD/SUE", close, daily_ret, universe_by_month, tidx, rebal_map, rebal_set,
                             start_idx, trade_dates, pead_score_fn)

    print("=== Bygger NETTOEMISSION L/S-sviten ===")
    issuance_pv = run_ls_sleeve("nettoemission", close, daily_ret, universe_by_month, tidx, rebal_map, rebal_set,
                                 start_idx, trade_dates, issuance_score_fn)

    pead_pv.to_csv(CACHE_DIR / "diag_pead_sue_ls_sleeve_pv.csv", header=["portfolio_value"])
    issuance_pv.to_csv(CACHE_DIR / "diag_issuance_ls_sleeve_pv.csv", header=["portfolio_value"])

    print("\n=== EGEN PRESTANDA (2010-2024, isolerat ben) ===")
    for name, pv in [("PEAD/SUE L/S", pead_pv), ("Nettoemission L/S", issuance_pv)]:
        print(f"  {name:<20} Sharpe={sharpe(pv):.4f}  CAGR={cagr(pv):+.2%}  MaxDD={max_drawdown(pv):.2%}")

    print("\n=== KORRELATIONSMATRIS (dagliga avkastningar) ===")
    spy = hyp037.load_hedge(hyp037.FULL_START, hyp037.FULL_END)
    h37 = pd.read_csv(STRATEGIES_ROOT / "HYP-037" / "results" / "portfolio_value_100000.csv",
                       index_col=0, parse_dates=True).iloc[:, 0]
    mom_ls = pd.read_csv(STRATEGIES_ROOT / "HYP-043" / "results" / "momentum_ls_sleeve_pv.csv",
                          index_col=0, parse_dates=True).iloc[:, 0]
    combo43 = pd.read_csv(STRATEGIES_ROOT / "HYP-043" / "results" / "portfolio_value_combined_100000.csv",
                           index_col=0, parse_dates=True).iloc[:, 0]

    series = {
        "SPY": spy, "HYP037": h37, "MomentumLS": mom_ls, "HYP043_combo": combo43,
        "PEAD_SUE": pead_pv, "Nettoemission": issuance_pv,
    }
    rets = pd.concat({k: v.pct_change() for k, v in series.items()}, axis=1, join="inner").dropna()
    print(f"  ({len(rets)} overlappande dagar)\n")
    print(rets.corr().round(4).to_string())

    print(f"\nKLART, {time.time() - t0:.0f}s totalt. Sparat till data/cache/diag_pead_sue_ls_sleeve_pv.csv "
          f"och data/cache/diag_issuance_ls_sleeve_pv.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
