"""
HYP-083: Naiv 50/50-kombination (kvartalsvis ombalanserad) - HYP-079 +
Leg 3 (HYP-043:s momentum L/S-svit, isolerad). Se
research/hypothesis_registry/HYP-083-naiv-kombination-hyp079-hyp043-sleeve.yaml
for det lasta kriteriet. Samma metod som HYP-039/078/081/082.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

STRATEGY_DIR = Path(__file__).resolve().parent
STRATEGIES_ROOT = STRATEGY_DIR.parent
RESULTS_DIR = STRATEGY_DIR / "results"

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
from rebalancing import snap_rebalance_dates  # noqa: E402

REBAL_FREQ = "QE"
WEIGHT_A = 0.5
WEIGHT_B = 0.5
REBALANCE_COST_BPS = 0.0010

HYP043_SLEEVE_FILE = STRATEGIES_ROOT / "HYP-043" / "results" / "momentum_ls_sleeve_pv.csv"
HYP079_RESULTS = STRATEGIES_ROOT / "HYP-079" / "results"

HYP043_SLEEVE_SHARPE = 0.4317
HYP043_SLEEVE_MAXDD = -0.5832
HYP079_SHARPE = {100_000: 0.8433, 1_000_000: 0.7498, 10_000_000: 0.6936}
HYP079_MAXDD = {100_000: -0.0582, 1_000_000: -0.0585, 10_000_000: -0.0690}


def combine_50_50(pv_a: pd.Series, pv_b: pd.Series, start_capital: float = 1.0) -> pd.Series:
    df = pd.concat([pv_a.rename("a"), pv_b.rename("b")], axis=1, join="inner").dropna()
    r_a = df["a"].pct_change()
    r_b = df["b"].pct_change()

    calendar_dates = df.resample(REBAL_FREQ).last().index
    snapped = snap_rebalance_dates(calendar_dates, df.index)
    rebal_set = set(snapped["execution_date"])

    leg_a = start_capital * WEIGHT_A
    leg_b = start_capital * WEIGHT_B
    values, dates = [], []

    for i in range(1, len(df)):
        date = df.index[i]
        ra, rb = r_a.iloc[i], r_b.iloc[i]
        if not np.isnan(ra):
            leg_a *= (1 + ra)
        if not np.isnan(rb):
            leg_b *= (1 + rb)
        total = leg_a + leg_b
        if date in rebal_set:
            target_a = total * WEIGHT_A
            target_b = total * WEIGHT_B
            turnover = abs(target_a - leg_a) + abs(target_b - leg_b)
            total -= turnover * REBALANCE_COST_BPS
            leg_a = total * WEIGHT_A
            leg_b = total * WEIGHT_B
        values.append(total)
        dates.append(date)

    return pd.Series(values, index=dates)


def sharpe(s, rf=0.02):
    r = s.pct_change().dropna()
    return float(np.sqrt(252) * (r - rf / 252).mean() / r.std()) if r.std() > 0 else 0.0


def max_drawdown(s):
    return float(((s - s.cummax()) / s.cummax()).min())


def cagr(s):
    if len(s) < 2:
        return None
    return float((s.iloc[-1] / s.iloc[0]) ** (252 / len(s)) - 1)


def main():
    levels = [100_000, 1_000_000, 10_000_000]
    RESULTS_DIR.mkdir(exist_ok=True)

    print("=== HYP-083: naiv 50/50 HYP-079 + Leg 3 (HYP-043 momentum L/S-svit) ===\n")
    main_results = []

    # Robust kolumnnamn-hantering (sviten kan ha ett annat kolumnnamn an "portfolio_value").
    raw = pd.read_csv(HYP043_SLEEVE_FILE, index_col=0, parse_dates=True)
    pv_sleeve = raw.iloc[:, 0]

    for level in levels:
        pv079 = pd.read_csv(HYP079_RESULTS / f"portfolio_value_{level}.csv",
                             index_col=0, parse_dates=True)["portfolio_value"]
        combined = combine_50_50(pv_sleeve, pv079)
        combined.to_csv(RESULTS_DIR / f"portfolio_value_combined_{level}.csv", header=["portfolio_value"])

        m = {"capital_level": level, "sharpe": sharpe(combined), "cagr": cagr(combined),
             "max_drawdown": max_drawdown(combined), "n_days": len(combined)}
        main_results.append(m)

        best_sharpe = max(HYP043_SLEEVE_SHARPE, HYP079_SHARPE[level])
        best_maxdd = max(HYP043_SLEEVE_MAXDD, HYP079_MAXDD[level])
        cond1 = m["sharpe"] >= best_sharpe
        cond2 = m["max_drawdown"] > best_maxdd
        print(f"  ${level:>10,.0f}  Sharpe={m['sharpe']:.4f} (bästa byggsten:{best_sharpe:.4f}) "
              f"-> {'PASS' if cond1 else 'FAIL'}")
        print(f"               MaxDD={m['max_drawdown']:.2%} (bästa byggsten:{best_maxdd:.2%}) "
              f"-> {'PASS' if cond2 else 'FAIL'}")
        print(f"               CAGR={m['cagr']:+.2%}\n")

    cond1_all = all(main_results[i]["sharpe"] >= max(HYP043_SLEEVE_SHARPE, HYP079_SHARPE[levels[i]]) for i in range(3))
    cond2_all = all(main_results[i]["max_drawdown"] > max(HYP043_SLEEVE_MAXDD, HYP079_MAXDD[levels[i]]) for i in range(3))
    overall = "PASSED" if (cond1_all and cond2_all) else "FAILED"

    print(f"=== SLUTBEDOMNING ===\n  Villkor 1: {'PASS' if cond1_all else 'FAIL'}")
    print(f"  Villkor 2: {'PASS' if cond2_all else 'FAIL'}")
    print(f"  => {overall}\n")

    summary = {"main": main_results, "pass_fail": {"cond1_sharpe": bool(cond1_all), "cond2_maxdd": bool(cond2_all)},
               "overall": overall}
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
