"""
HYP-046: Krasch-overlay (HYP-045) + PEAD/SUE-ben (HYP-044) - fyrdelad
likaviktad kombination.

Se research/hypothesis_registry/HYP-046-overlay-plus-pead-fyrdelad.yaml
for det lasta kriteriet. Sjatte kombinationshypotesen i registret.

Ateranvander BADA byggstenarna OFORANDRADE:
  - HYP-045:s krasch-overlay-mekanism (compute_overlay_fraction_series,
    apply_overlay) - tillampad pa SPY- och momentum L/S-benen.
  - HYP-044:s PEAD/SUE-svitkonstruktion - OFORANDRAD, INGEN overlay
    (se motivering i registerpostens header).

Universum/prismatriser laddas EN gang och ateranvands for BADA
sviterna (momentum L/S och PEAD/SUE), samma effektivitetsprincip som
scripts/diagnostic_hyp044_pead_and_issuance.py.
"""

import bisect
import importlib.util
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
RESULTS_DIR = STRATEGY_DIR / "results"

HYP037_DIR = STRATEGIES_ROOT / "HYP-037"
HYP037_RESULTS = HYP037_DIR / "results"
HYP037_OOS_RESULTS = REPO_ROOT / "paper_trading" / "HYP-037" / "oos_2025_results"
HYP044_DIR = STRATEGIES_ROOT / "HYP-044"
HYP045_DIR = STRATEGIES_ROOT / "HYP-045"

ORIGINAL_UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_by_month.json"
EXTENSION_UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_2025_extension.json"
EPS_FILE = CACHE_DIR / "eps_by_ticker.jsonl"

sys.path.insert(0, str(HYP037_DIR))
import backtest as hyp037  # noqa: E402
from friction import borrow_cost, corwin_schultz_spread  # noqa: E402

# HYP-045:s modul laddas under ETT UNIKT modulnamn - annars kolliderar den
# med HYP-037:s redan importerade "backtest"-modul (bada filerna heter
# backtest.py, Python cachar pa modulnamn i sys.modules, inte pa sokvag
# eller lokalt alias - upptackt 2026-08-07 nar detta script forst kordes,
# fixat innan nagot resultat rapporterades).
sys.path.insert(0, str(HYP045_DIR))
_spec = importlib.util.spec_from_file_location("hyp045_backtest_module", HYP045_DIR / "backtest.py")
hyp045 = importlib.util.module_from_spec(_spec)
sys.modules["hyp045_backtest_module"] = hyp045
_spec.loader.exec_module(hyp045)  # compute_overlay_fraction_series, apply_overlay

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

OOS_START = "2025-01-01"
FULL_END_WITH_OOS = "2025-12-31"

HYP043_FRICTION_CORRECTED_REF = {
    100_000: {"sharpe": 0.8926, "max_drawdown": -0.1558},
    1_000_000: {"sharpe": 0.8940, "max_drawdown": -0.1568},
    10_000_000: {"sharpe": 0.8217, "max_drawdown": -0.1429},
}
HYP039_OOS_REF = {100_000: 0.9185, 1_000_000: 0.8116, 10_000_000: 0.7932}
HYP044_REF = {100_000: 1.0117, 1_000_000: 1.0135, 10_000_000: 0.9439}
HYP045_REF = {100_000: 0.9941, 1_000_000: 0.9989, 10_000_000: 0.9287}


def compute_spread_matrix(high, low):
    spread = {}
    for t in high.columns:
        spread[t] = corwin_schultz_spread(high[t].values, low[t].values)
    return pd.DataFrame(spread, index=high.index)


def load_sue_series() -> dict:
    """Identisk med HYP-044:s backtest.py:load_sue_series()."""
    sue_by_ticker = {}
    with EPS_FILE.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
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
                    continue
                key = (e["fy"], e["fp"])
                if key not in discrete or e["filed"] < discrete[key]["filed"]:
                    discrete[key] = e
            if len(discrete) < MIN_QUARTERS_FOR_STD + 4:
                continue
            ordered = sorted(discrete.values(), key=lambda e: e["end"])
            by_fy_fp = {(e["fy"], e["fp"]): e for e in ordered}
            surprises, sue_points = [], []
            for e in ordered:
                prior = by_fy_fp.get((e["fy"] - 1, e["fp"]))
                if prior is None:
                    continue
                surprise = e["val"] - prior["val"]
                recent = [s for _, s in surprises[-MAX_QUARTERS_FOR_STD:]]
                if len(recent) >= MIN_QUARTERS_FOR_STD:
                    std = float(np.std(recent))
                    if std > 1e-6:
                        sue_points.append((e["filed"], surprise / std))
                surprises.append((e["filed"], surprise))
            if sue_points:
                sue_points.sort()
                sue_by_ticker[row["ticker"]] = sue_points
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


def build_sleeves(universe_by_month: dict):
    """Bygger BADE momentum L/S (med spread) och PEAD/SUE (med spread)
    fran EN delad laddning av universum/prismatriser."""
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
    daily_ret = close_adj.pct_change()

    print("  Berknar Corwin-Schultz-spread-matris...")
    spread_df = compute_spread_matrix(high, low)

    print("  Bygger SUE-serier fran EPS-data...")
    sue_by_ticker = load_sue_series()

    momentum = close_adj.shift(MOM_SKIP_DAYS) / close_adj.shift(MOM_LOOKBACK_DAYS) - 1

    tidx = {t: i for i, t in enumerate(close.columns)}
    calendar_dates = close.resample(REBAL_FREQ).last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[MIN_HISTORY_DAYS])
                                     & (calendar_dates <= close.index[-1])]
    snapped = snap_rebalance_dates(calendar_dates, close.index)
    rebal_map = dict(zip(snapped["execution_date"], snapped["calendar_label"]))
    rebal_set = set(snapped["execution_date"])
    start_idx = close.index.get_indexer([snapped["execution_date"].iloc[0]])[0]
    trade_dates = close.index[start_idx:]

    def run_decile_sleeve(score_fn):
        long_names, short_names = [], []
        pv_list = [1.0]
        for date_i in range(start_idx, len(close.index)):
            date = close.index[date_i]
            rebalance_cost = 0.0
            if date in rebal_set:
                month_key = rebal_map[date].strftime("%Y-%m-%d")
                eligible = [t for t in universe_by_month.get(month_key, []) if t in tidx]
                scores = score_fn(date, eligible)
                if len(scores) >= 20:
                    ranked = sorted(scores.items(), key=lambda kv: kv[1])
                    n_decile = max(1, int(len(ranked) * DECILE_FRACTION))
                    new_short = [t for t, _ in ranked[:n_decile]]
                    new_long = [t for t, _ in ranked[-n_decile:]]

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

    def mom_score_fn(date, eligible):
        vals = momentum.loc[date, eligible].dropna()
        return dict(vals)

    def pead_score_fn(date, eligible):
        as_of = date.strftime("%Y-%m-%d")
        out = {}
        for t in eligible:
            v = sue_asof(sue_by_ticker, t, as_of)
            if v is not None:
                out[t] = v
        return out

    print("  Bygger momentum L/S-sviten...")
    mom_ls = run_decile_sleeve(mom_score_fn)
    print("  Bygger PEAD/SUE-sviten...")
    pead_sue = run_decile_sleeve(pead_score_fn)
    return mom_ls, pead_sue


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

    print("Bygger momentum L/S + PEAD/SUE (delad laddning, bada med spreadkostnad)...")
    mom_ls_raw, pead_sue_raw = build_sleeves(universe_merged)
    print(f"  momentum: {len(mom_ls_raw)} dagar, PEAD/SUE: {len(pead_sue_raw)} dagar\n")

    spy_raw = load_spy()
    print("Berknar krasch-overlay-fraction-serien (HYP-045:s parametrar)...")
    fraction = hyp045.compute_overlay_fraction_series(spy_raw)

    print("Tillampar overlay pa SPY- och momentum L/S-benen (INTE PEAD/SUE)...")
    spy_protected = hyp045.apply_overlay(spy_raw, fraction)
    mom_ls_protected = hyp045.apply_overlay(mom_ls_raw, fraction)
    RESULTS_DIR.mkdir(exist_ok=True)
    spy_protected.to_csv(RESULTS_DIR / "spy_protected_pv.csv", header=["portfolio_value"])
    mom_ls_protected.to_csv(RESULTS_DIR / "mom_ls_protected_pv.csv", header=["portfolio_value"])
    pead_sue_raw.to_csv(RESULTS_DIR / "pead_sue_unprotected_pv.csv", header=["portfolio_value"])

    levels = [100_000, 1_000_000, 10_000_000]
    print("\n=== HYP-046: huvudbacktest (2010-2024) ===")
    main_results = []
    for level in levels:
        hyp037_pv = pd.read_csv(HYP037_RESULTS / f"portfolio_value_{level}.csv",
                                 index_col=0, parse_dates=True)["portfolio_value"]
        combined = combine_quarters({"spy": spy_protected, "hyp037": hyp037_pv,
                                      "mom_ls": mom_ls_protected, "pead": pead_sue_raw})
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
              f"CAGR={r['cagr']:+.2%}  Calmar={r['calmar']:.3f}  "
              f"[HYP-044={HYP044_REF[level]:.4f} HYP-045={HYP045_REF[level]:.4f}]")

    print("\n=== HYP-046: OOS-2025 ===")
    oos_results = []
    spy_oos = spy_protected.loc[OOS_START:FULL_END_WITH_OOS]
    mom_ls_oos = mom_ls_protected.loc[OOS_START:FULL_END_WITH_OOS]
    pead_oos = pead_sue_raw.loc[OOS_START:FULL_END_WITH_OOS]
    for level in levels:
        hyp037_oos_pv = pd.read_csv(HYP037_OOS_RESULTS / f"portfolio_value_oos_2025_{level}.csv",
                                     index_col=0, parse_dates=True)["portfolio_value"]
        combined_oos = combine_quarters({"spy": spy_oos, "hyp037": hyp037_oos_pv,
                                          "mom_ls": mom_ls_oos, "pead": pead_oos})
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
