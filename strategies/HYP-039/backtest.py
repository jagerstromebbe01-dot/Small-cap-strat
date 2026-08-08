"""
HYP-039: Naiv 50/50-kombination (kvartalsvis ombalanserad) - SPY + HYP-037.

Se research/hypothesis_registry/HYP-039-naiv-kombination-spy-hyp037.yaml
for det lasta kriteriet. Forsta kombinationshypotesen i projektet, per
spec §5b:s regler for legitim kombinationstestning.

INGEN ny backtest-motor, INGEN ny signal - ren portfoljmatematik pa tva
REDAN KANDA, REDAN INDIVIDUELLT TESTADE avkastningsserier:
  - SPY: adjusted_close, dagliga avkastningar, ra marknadspris.
  - HYP-037: redan sparad strategies/HYP-037/results/portfolio_value_<niva>.csv,
    ANVAND OFORANDRAD (redan inkluderar HYP-037:s egen kostnadsmodell).

Mekanism: 50% notional i vardera benet, ombalanserat till EXAKT 50/50
VARJE KVARTAL - samma snap_rebalance_dates-metod och samma REBAL_FREQ="QE"
som HYP-037 sjalv anvander, tillampad pa den HAR sammanslagna kalendern
(bada serierna maste finnas for att en dag ska raknas med).
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

# GRANSKNINGSFYND 2026-08-08: pekar nu pa HYP-037:s KORRIGERADE resultat
# (filed-datum-universum + maskad adjusted_close-kvot, se
# strategies/HYP-037/backtest.py). OOS-benet (HYP037_OOS_RESULTS) lamnas
# medvetet OKORRIGERAT i denna omkorning - se slutrapporten/tilläggsnoten
# for motivering (paper_trading/HYP-037/oos_backtest_2025.py rors inte
# har, huvudkriteriet avgors pa 2010-2024-perioden).
HYP037_RESULTS = STRATEGIES_ROOT / "HYP-037" / "results_corrected_2026-08-08"
HYP037_OOS_RESULTS = REPO_ROOT / "paper_trading" / "HYP-037" / "oos_2025_results"

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
from rebalancing import snap_rebalance_dates  # noqa: E402

REBAL_FREQ = "QE"          # samma frekvens som HYP-037 sjalv - ateranvand, ingen ny fri parameter
WEIGHT_SPY = 0.5
WEIGHT_HYP037 = 0.5
SPY_MAXDD_REF = -0.337     # SPY:s egen MaxDD 2011-2024, villkor 2:s jamforelsepunkt

# GRANSKNINGSFYND 2026-08-08: portfoljniva-ombalansering mellan benen
# (kvartalsvis, se combine_50_50 nedan) hade tidigare NOLL
# transaktionskostnad - bryter mot spec §2 princip 3 ("friktion fran dag
# ett"). Konservativ, enkel schablon (INTE per-ben-spread - benen ar
# redan diversifierade portfoljvarde-serier, inte enskilda tickers, sa
# en genuin blandad spread per ben ar inte meningsfullt definierad pa
# denna niva): 10 baspunkter av det OMALLOKERADE beloppet (|mal - nuvarande|
# per ben, summerat) vid varje kvartalsvis ombalansering. Samma konstant
# ateranvands identiskt i alla sju kombinationshypoteser (HYP-039/041/
# 043/044/045/046/047) for konsekvens.
REBALANCE_COST_BPS = 0.0010


def load_spy_prices(start=None, end=None):
    path = OHLCV_DIR / "SPY.csv"
    df = pd.read_csv(path, usecols=["date", "adjusted_close"], parse_dates=["date"])
    df = df.drop_duplicates(subset="date", keep="last").set_index("date").sort_index()
    s = df["adjusted_close"]
    if start is not None or end is not None:
        s = s.loc[start:end]
    return s


def combine_50_50(spy_price: pd.Series, hyp037_pv: pd.Series, start_capital: float = 1.0) -> pd.Series:
    """
    Kombinerar tva redan kanda avkastningsserier till en 50/50-portfolj,
    ombalanserad till exakt 50/50 pa varje snappat kvartalsdatum (samma
    metod som resten av projektet - snap_rebalance_dates). Returnerar
    portfoljvarde-serien (borjar pa start_capital).
    """
    df = pd.concat([spy_price.rename("spy"), hyp037_pv.rename("hyp037")], axis=1, join="inner").dropna()
    spy_ret = df["spy"].pct_change()
    hyp_ret = df["hyp037"].pct_change()

    calendar_dates = df.resample(REBAL_FREQ).last().index
    snapped = snap_rebalance_dates(calendar_dates, df.index)
    rebal_set = set(snapped["execution_date"])

    spy_leg = start_capital * WEIGHT_SPY
    hyp_leg = start_capital * WEIGHT_HYP037
    values, dates = [], []

    for i in range(1, len(df)):
        date = df.index[i]
        r_spy = spy_ret.iloc[i]
        r_hyp = hyp_ret.iloc[i]
        if not np.isnan(r_spy):
            spy_leg *= (1 + r_spy)
        if not np.isnan(r_hyp):
            hyp_leg *= (1 + r_hyp)
        total = spy_leg + hyp_leg
        if date in rebal_set:
            target_spy = total * WEIGHT_SPY
            target_hyp = total * WEIGHT_HYP037
            turnover = abs(target_spy - spy_leg) + abs(target_hyp - hyp_leg)
            total -= turnover * REBALANCE_COST_BPS
            spy_leg = total * WEIGHT_SPY
            hyp_leg = total * WEIGHT_HYP037
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
    spy_price = load_spy_prices()
    combined = combine_50_50(spy_price, hyp037_pv)

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
    spy_price_2025 = load_spy_prices(start="2025-01-01", end="2025-12-31")
    combined_oos = combine_50_50(spy_price_2025, hyp037_oos_pv)

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
    print("=== HYP-039: huvudbacktest (2011-2024) ===")
    main_results = []
    for level in levels:
        r = run_main_backtest(level)
        main_results.append(r)
        gate1 = "PASS" if r["sharpe"] >= 1.0 else "FAIL"
        gate2 = "PASS" if r["max_drawdown"] > SPY_MAXDD_REF else "FAIL"
        print(f"  ${level:>10,.0f}  Sharpe={r['sharpe']:.3f} ({gate1}, kräver >=1.0)  "
              f"MaxDD={r['max_drawdown']:.1%} ({gate2}, kräver bättre än {SPY_MAXDD_REF:.1%})  "
              f"CAGR={r['cagr']:+.2%}  Calmar={r['calmar']:.2f}")

    print("\n=== HYP-039: OOS-2025 ===")
    oos_results = []
    for level in levels:
        r = run_oos_2025(level)
        oos_results.append(r)
        gate3 = "PASS" if r["oos_2025_sharpe"] > 0 else "FAIL"
        print(f"  ${level:>10,.0f}  OOS-Sharpe={r['oos_2025_sharpe']:.3f} ({gate3}, kräver >0)  "
              f"OOS-avkastning={r['oos_2025_total_return']:+.2%}  OOS-MaxDD={r['oos_2025_max_drawdown']:.1%}  "
              f"({r['n_days']} dagar)")

    RESULTS_DIR.mkdir(exist_ok=True)
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump({"main": main_results, "oos_2025": oos_results}, f, indent=2, default=str)

    print("\nKLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
