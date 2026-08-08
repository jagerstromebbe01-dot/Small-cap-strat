"""
HYP-041: Naiv tredelad kombination (kvartalsvis ombalanserad) - SPY +
HYP-037 + TLT.

Se research/hypothesis_registry/HYP-041-naiv-kombination-spy-hyp037-tlt.yaml
for det lasta kriteriet. Andra kombinationshypotesen i projektet (efter
HYP-039), per spec §5b:s regler for legitim kombinationstestning -
korrelationsmatris berknad FORE lasning, naiv (ej in-sample-optimerad)
vikt, egen K-kostnad.

INGEN ny backtest-motor, INGEN ny signal - ren portfoljmatematik pa TRE
redan kanda, redan individuellt testade avkastningsserier:
  - SPY: adjusted_close, dagliga avkastningar, ra marknadspris.
  - TLT: adjusted_close, dagliga avkastningar, ra marknadspris.
  - HYP-037: redan sparad strategies/HYP-037/results/portfolio_value_<niva>.csv,
    ANVAND OFORANDRAD (redan inkluderar HYP-037:s egen kostnadsmodell).

Mekanism: 1/3 notional i vardera benet, ombalanserat till EXAKT
tredjedelar VARJE KVARTAL - samma snap_rebalance_dates-metod och samma
REBAL_FREQ="QE" som HYP-037/HYP-039 sjalva anvander, tillampad pa den
HAR sammanslagna (tre-vags) kalendern.
"""

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
RESULTS_DIR = STRATEGY_DIR / "results_corrected_2026-08-08"

# GRANSKNINGSFYND 2026-08-08: HYP-037-benet ar nu det KORRIGERADE
# resultatet (filed-datum-universum + maskad adjusted_close-kvot). OOS-
# benet lamnas medvetet okorrigerat, se HYP-039:s motsvarande kommentar.
HYP037_RESULTS = STRATEGIES_ROOT / "HYP-037" / "results_corrected_2026-08-08"
HYP037_OOS_RESULTS = REPO_ROOT / "paper_trading" / "HYP-037" / "oos_2025_results"

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
from rebalancing import snap_rebalance_dates  # noqa: E402

REBAL_FREQ = "QE"  # samma frekvens som HYP-037/HYP-039 sjalva - ateranvand, ingen ny fri parameter
WEIGHT_SPY = 1.0 / 3.0
WEIGHT_HYP037 = 1.0 / 3.0
WEIGHT_TLT = 1.0 / 3.0

# GRANSKNINGSFYND 2026-08-08: se HYP-039:s identiska kommentar - samma
# 10bps-schablon pa omallokerat belopp, ateranvand konsekvent.
REBALANCE_COST_BPS = 0.0010

# HYP-039:s EGNA redan registrerade varden - jamforelsepunkten for villkor 2/3
# (se research/hypothesis_registry/HYP-039-naiv-kombination-spy-hyp037.yaml)
HYP039_REF = {
    100_000: {"sharpe": 1.0191, "max_drawdown": -0.2203, "oos_2025_sharpe": 0.9185},
    1_000_000: {"sharpe": 1.0300, "max_drawdown": -0.2216, "oos_2025_sharpe": 0.8116},
    10_000_000: {"sharpe": 0.9879, "max_drawdown": -0.2003, "oos_2025_sharpe": 0.7932},
}


def load_prices(ticker, start=None, end=None):
    path = OHLCV_DIR / f"{ticker}.csv"
    df = pd.read_csv(path, usecols=["date", "adjusted_close"], parse_dates=["date"])
    df = df.drop_duplicates(subset="date", keep="last").set_index("date").sort_index()
    s = df["adjusted_close"]
    if start is not None or end is not None:
        s = s.loc[start:end]
    return s


def combine_thirds(spy_price: pd.Series, hyp037_pv: pd.Series, tlt_price: pd.Series,
                    start_capital: float = 1.0) -> pd.Series:
    """Kombinerar tre redan kanda avkastningsserier till en likaviktad
    (1/3 vardera) portfolj, ombalanserad till exakt tredjedelar pa varje
    snappat kvartalsdatum - samma metod som HYP-039:s combine_50_50()."""
    df = pd.concat([spy_price.rename("spy"), hyp037_pv.rename("hyp037"), tlt_price.rename("tlt")],
                    axis=1, join="inner").dropna()
    spy_ret = df["spy"].pct_change()
    hyp_ret = df["hyp037"].pct_change()
    tlt_ret = df["tlt"].pct_change()

    calendar_dates = df.resample(REBAL_FREQ).last().index
    snapped = snap_rebalance_dates(calendar_dates, df.index)
    rebal_set = set(snapped["execution_date"])

    spy_leg = start_capital * WEIGHT_SPY
    hyp_leg = start_capital * WEIGHT_HYP037
    tlt_leg = start_capital * WEIGHT_TLT
    values, dates = [], []

    for i in range(1, len(df)):
        date = df.index[i]
        r_spy = spy_ret.iloc[i]
        r_hyp = hyp_ret.iloc[i]
        r_tlt = tlt_ret.iloc[i]
        if not np.isnan(r_spy):
            spy_leg *= (1 + r_spy)
        if not np.isnan(r_hyp):
            hyp_leg *= (1 + r_hyp)
        if not np.isnan(r_tlt):
            tlt_leg *= (1 + r_tlt)
        total = spy_leg + hyp_leg + tlt_leg
        if date in rebal_set:
            target_spy = total * WEIGHT_SPY
            target_hyp = total * WEIGHT_HYP037
            target_tlt = total * WEIGHT_TLT
            turnover = abs(target_spy - spy_leg) + abs(target_hyp - hyp_leg) + abs(target_tlt - tlt_leg)
            total -= turnover * REBALANCE_COST_BPS
            spy_leg = total * WEIGHT_SPY
            hyp_leg = total * WEIGHT_HYP037
            tlt_leg = total * WEIGHT_TLT
        values.append(total)
        dates.append(date)

    return pd.Series(values, index=dates)


# ════════════════════════════════════════════════════════════
#  METRICS (identiska definitioner mot resten av projektet)
# ════════════════════════════════════════════════════════════
def sharpe(s, rf=0.02):
    r = s.pct_change().dropna()
    return float(np.sqrt(252) * (r - rf / 252).mean() / r.std()) if r.std() > 0 else 0.0


def max_drawdown(s):
    return float(((s - s.cummax()) / s.cummax()).min())


def cagr(s):
    return float((s.iloc[-1] / s.iloc[0]) ** (252 / len(s)) - 1)


def calmar(s):
    md = abs(max_drawdown(s))
    return cagr(s) / md if md > 0 else 0.0


def run_main_backtest(level: int) -> dict:
    hyp037_pv = pd.read_csv(HYP037_RESULTS / f"portfolio_value_{level}.csv", index_col=0, parse_dates=True)["portfolio_value"]
    spy_price = load_prices("SPY")
    tlt_price = load_prices("TLT")
    combined = combine_thirds(spy_price, hyp037_pv, tlt_price)

    RESULTS_DIR.mkdir(exist_ok=True)
    combined.to_csv(RESULTS_DIR / f"portfolio_value_combined_{level}.csv", header=["portfolio_value"])

    return {
        "capital_level": level,
        "sharpe": sharpe(combined),
        "cagr": cagr(combined),
        "max_drawdown": max_drawdown(combined),
        "calmar": calmar(combined),
        "n_days": len(combined),
    }


def run_oos_2025(level: int) -> dict:
    hyp037_oos_pv = pd.read_csv(HYP037_OOS_RESULTS / f"portfolio_value_oos_2025_{level}.csv",
                                  index_col=0, parse_dates=True)["portfolio_value"]
    spy_price_2025 = load_prices("SPY", start="2025-01-01", end="2025-12-31")
    tlt_price_2025 = load_prices("TLT", start="2025-01-01", end="2025-12-31")
    combined_oos = combine_thirds(spy_price_2025, hyp037_oos_pv, tlt_price_2025)

    RESULTS_DIR.mkdir(exist_ok=True)
    combined_oos.to_csv(RESULTS_DIR / f"portfolio_value_oos2025_combined_{level}.csv", header=["portfolio_value"])

    return {
        "capital_level": level,
        "oos_2025_sharpe": sharpe(combined_oos),
        "oos_2025_cagr": cagr(combined_oos) if len(combined_oos) > 1 else None,
        "oos_2025_max_drawdown": max_drawdown(combined_oos),
        "oos_2025_total_return": float(combined_oos.iloc[-1] / combined_oos.iloc[0] - 1) if len(combined_oos) > 1 else None,
        "n_days": len(combined_oos),
    }


def main():
    levels = [100_000, 1_000_000, 10_000_000]
    print("=== HYP-041: huvudbacktest (2010-2024) ===")
    main_results = []
    for level in levels:
        r = run_main_backtest(level)
        main_results.append(r)
        ref = HYP039_REF[level]
        gate1 = "PASS" if r["sharpe"] >= 1.0 else "FAIL"
        gate2 = "PASS" if r["sharpe"] > ref["sharpe"] else "FAIL"
        gate3 = "PASS" if r["max_drawdown"] > ref["max_drawdown"] else "FAIL"
        print(f"  ${level:>10,.0f}  Sharpe={r['sharpe']:.4f} ({gate1}, kräver >=1.0; {gate2} mot HYP-039:s {ref['sharpe']:.4f})  "
              f"MaxDD={r['max_drawdown']:.2%} ({gate3} mot HYP-039:s {ref['max_drawdown']:.2%})  "
              f"CAGR={r['cagr']:+.2%}  Calmar={r['calmar']:.3f}")

    print("\n=== HYP-041: OOS-2025 ===")
    oos_results = []
    for level in levels:
        r = run_oos_2025(level)
        oos_results.append(r)
        ref = HYP039_REF[level]
        gate4 = "PASS" if r["oos_2025_sharpe"] > ref["oos_2025_sharpe"] else "FAIL"
        print(f"  ${level:>10,.0f}  OOS-Sharpe={r['oos_2025_sharpe']:.4f} ({gate4} mot HYP-039:s {ref['oos_2025_sharpe']:.4f})  "
              f"OOS-avkastning={r['oos_2025_total_return']:+.2%}  OOS-MaxDD={r['oos_2025_max_drawdown']:.2%}  "
              f"({r['n_days']} dagar)")

    RESULTS_DIR.mkdir(exist_ok=True)
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump({"main": main_results, "oos_2025": oos_results}, f, indent=2, default=str)

    print("\nKLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
