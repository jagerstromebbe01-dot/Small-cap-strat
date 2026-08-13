"""
HYP-078: Naiv 80/20-kombination (kvartalsvis ombalanserad) - HYP-056
(befintlig referensportfölj) + HYP-075 (femte ben).

Se research/hypothesis_registry/HYP-078-naiv-femte-ben-hyp075-hyp056.yaml
for det lasta kriteriet. Ingen ny backtest-motor, ingen ny signal - ren
portfoljmatematik pa tva REDAN KANDA, REDAN INDIVIDUELLT TESTADE
avkastningsserier, samma monster som HYP-039/041/043/044/045/046/047.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

STRATEGY_DIR = Path(__file__).resolve().parent
STRATEGIES_ROOT = STRATEGY_DIR.parent
REPO_ROOT = STRATEGIES_ROOT.parent
RESULTS_DIR = STRATEGY_DIR / "results"

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
from rebalancing import snap_rebalance_dates  # noqa: E402

REBAL_FREQ = "QE"
WEIGHT_HYP056 = 0.8
WEIGHT_HYP075 = 0.2
REBALANCE_COST_BPS = 0.0010

HYP056_RESULTS = STRATEGIES_ROOT / "HYP-056" / "results"
HYP075_RESULTS = STRATEGIES_ROOT / "HYP-075" / "results"

# HYP-056:s egna redan uppmatta jamforelsetal (fran dess registerpost,
# aterananvanda identiskt av HYP-071 tidigare - samma konvention har).
HYP056_SHARPE = {100_000: 1.2228, 1_000_000: 1.2177, 10_000_000: 1.1923}
HYP056_MAXDD = {100_000: -0.0592, 1_000_000: -0.0602, 10_000_000: -0.0564}
HYP056_OOS_SHARPE = {100_000: 1.7585, 1_000_000: 1.7379, 10_000_000: 1.7579}

OOS_START = "2025-01-01"


def combine_80_20(pv056: pd.Series, pv075: pd.Series, start_capital: float = 1.0) -> pd.Series:
    df = pd.concat([pv056.rename("hyp056"), pv075.rename("hyp075")], axis=1, join="inner").dropna()
    r056 = df["hyp056"].pct_change()
    r075 = df["hyp075"].pct_change()

    calendar_dates = df.resample(REBAL_FREQ).last().index
    snapped = snap_rebalance_dates(calendar_dates, df.index)
    rebal_set = set(snapped["execution_date"])

    leg056 = start_capital * WEIGHT_HYP056
    leg075 = start_capital * WEIGHT_HYP075
    values, dates = [], []

    for i in range(1, len(df)):
        date = df.index[i]
        r1, r2 = r056.iloc[i], r075.iloc[i]
        if not np.isnan(r1):
            leg056 *= (1 + r1)
        if not np.isnan(r2):
            leg075 *= (1 + r2)
        total = leg056 + leg075
        if date in rebal_set:
            target056 = total * WEIGHT_HYP056
            target075 = total * WEIGHT_HYP075
            turnover = abs(target056 - leg056) + abs(target075 - leg075)
            total -= turnover * REBALANCE_COST_BPS
            leg056 = total * WEIGHT_HYP056
            leg075 = total * WEIGHT_HYP075
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

    print("=== HYP-078: naiv 80/20 HYP-056 + HYP-075 ===\n")
    main_results, oos_results = [], []

    for level in levels:
        pv056 = pd.read_csv(HYP056_RESULTS / f"portfolio_value_combined_scaled_{level}.csv",
                             index_col=0, parse_dates=True)["portfolio_value"]
        pv075 = pd.read_csv(HYP075_RESULTS / f"portfolio_value_{level}.csv",
                             index_col=0, parse_dates=True)["portfolio_value"]
        main_pv = combine_80_20(pv056, pv075.loc[pv075.index < OOS_START])
        main_pv.to_csv(RESULTS_DIR / f"portfolio_value_combined_{level}.csv", header=["portfolio_value"])

        # HYP-056:s huvudserie sträcker sig inte in i OOS-2025 (separat fil,
        # samma äldre konvention som HYP-039) - kombinera OOS-2025 separat.
        pv056_oos = pd.read_csv(HYP056_RESULTS / f"portfolio_value_oos2025_combined_scaled_{level}.csv",
                                 index_col=0, parse_dates=True)["portfolio_value"]
        pv075_oos = pv075.loc[pv075.index >= OOS_START]
        oos_pv = combine_80_20(pv056_oos, pv075_oos)
        oos_pv.to_csv(RESULTS_DIR / f"portfolio_value_oos2025_combined_{level}.csv", header=["portfolio_value"])

        m = {"capital_level": level, "sharpe": sharpe(main_pv), "cagr": cagr(main_pv),
             "max_drawdown": max_drawdown(main_pv), "n_days": len(main_pv)}
        main_results.append(m)
        o = {"capital_level": level, "oos_2025_sharpe": sharpe(oos_pv) if len(oos_pv) > 2 else None,
             "oos_2025_max_drawdown": max_drawdown(oos_pv) if len(oos_pv) > 2 else None,
             "n_days_oos": len(oos_pv)}
        oos_results.append(o)

        cond1 = m["sharpe"] >= HYP056_SHARPE[level]
        cond2 = m["max_drawdown"] > HYP056_MAXDD[level]
        print(f"  ${level:>10,.0f}  Sharpe={m['sharpe']:.4f} (HYP-056:{HYP056_SHARPE[level]:.4f}) "
              f"-> {'PASS' if cond1 else 'FAIL'}")
        print(f"               MaxDD={m['max_drawdown']:.2%} (HYP-056:{HYP056_MAXDD[level]:.2%}) "
              f"-> {'PASS' if cond2 else 'FAIL'}")
        print(f"               CAGR={m['cagr']:+.2%}  OOS-2025 Sharpe={o['oos_2025_sharpe']} "
              f"(HYP-056 OOS:{HYP056_OOS_SHARPE[level]:.4f})\n")

    cond1_all = all(main_results[i]["sharpe"] >= HYP056_SHARPE[levels[i]] for i in range(3))
    cond2_all = all(main_results[i]["max_drawdown"] > HYP056_MAXDD[levels[i]] for i in range(3))
    overall = "PASSED" if (cond1_all and cond2_all) else "FAILED"

    print(f"=== SLUTBEDOMNING ===\n  Villkor 1 (Sharpe >= HYP-056 på alla nivåer): {'PASS' if cond1_all else 'FAIL'}")
    print(f"  Villkor 2 (MaxDD bättre än HYP-056 på alla nivåer): {'PASS' if cond2_all else 'FAIL'}")
    print(f"  => {overall}\n")

    summary = {"main": main_results, "oos_2025": oos_results,
               "pass_fail": {"cond1_sharpe": bool(cond1_all), "cond2_maxdd": bool(cond2_all)},
               "overall": overall}
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
