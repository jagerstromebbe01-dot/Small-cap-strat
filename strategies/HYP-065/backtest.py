"""
HYP-065: Havstang (2,5x) med marginalanrop/tvingad nedskalning som overlay
pa HYP-056:s redan volatilitetsmalsatta portfolj.

Se research/hypothesis_registry/HYP-065-havstang-margin-anrop-hyp056.yaml
for det lasta kriteriet. IDENTISK marginalanrops-mekanism som HYP-059
(strategies/HYP-059/backtest.py) - ENDA skillnaderna: bas (HYP-056 istallet
for HYP-047) och havstangsniva (2,5x istallet for 1,5x), motiverat av
HYP-056:s lagre egen MaxDD (mer headroom).

KALLOR (aterananvander direkt, ingen omberkning):
  strategies/HYP-056/results/portfolio_value_combined_scaled_{level}.csv
  strategies/HYP-056/results/portfolio_value_oos2025_combined_scaled_{level}.csv
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

HYP056_RESULTS = STRATEGIES_ROOT / "HYP-056" / "results"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from deflated_sharpe_ratio import deflated_sharpe_ratio_from_returns  # noqa: E402

RF_ANNUAL = 0.02
GATING_LEVERAGE = 2.5
DISCLOSURE_LEVERAGES = [1.5, 2.0, 3.0]
GATING_SPREAD = 0.015
DISCLOSURE_SPREAD = 0.030

MARGIN_CALL_TRIGGER = -0.15
DELEVER_FLOOR = 1.0
FORCED_SALE_SLIPPAGE = 0.005
RELEVER_STEP_PER_WEEK = 0.05
RELEVER_GATE = -0.05
TRADING_DAYS_PER_WEEK = 5

# HYP-056:s egna lasta capital_level_results (CAGR vid $100k/$1M/$10M)
HYP056_MAIN_REF_CAGR = {100_000: 0.0831, 1_000_000: 0.0826, 10_000_000: 0.0780}

DSR_N_TRIALS = 64  # k_total_hypotheses_before_this (63) + 1


def load_hyp056_combined(level: int) -> pd.Series:
    return pd.read_csv(HYP056_RESULTS / f"portfolio_value_combined_scaled_{level}.csv",
                        index_col=0, parse_dates=True)["portfolio_value"]


def load_hyp056_oos(level: int) -> pd.Series:
    return pd.read_csv(HYP056_RESULTS / f"portfolio_value_oos2025_combined_scaled_{level}.csv",
                        index_col=0, parse_dates=True)["portfolio_value"]


def simulate_leverage_with_margin_calls(daily_ret: pd.Series, leverage_target: float,
                                         borrow_spread: float, rf_annual=RF_ANNUAL) -> dict:
    cost_daily = (rf_annual + borrow_spread) / 252
    equity = 1.0
    hwm = 1.0
    L_current = leverage_target
    values, dates, leverage_path = [], [], []
    margin_call_dates = []
    days_since_call = None

    for date, r in daily_ret.items():
        if np.isnan(r):
            r = 0.0
        levered_r = L_current * r - (L_current - 1) * cost_daily
        equity = equity * (1 + levered_r)
        hwm = max(hwm, equity)
        drawdown = (equity - hwm) / hwm

        if drawdown <= MARGIN_CALL_TRIGGER and L_current > DELEVER_FLOOR:
            forced_notional_fraction = (L_current - DELEVER_FLOOR) / L_current
            equity *= (1 - FORCED_SALE_SLIPPAGE * forced_notional_fraction)
            L_current = DELEVER_FLOOR
            margin_call_dates.append(str(date.date()))
            days_since_call = 0
            hwm = max(hwm, equity)
            drawdown = (equity - hwm) / hwm
        elif days_since_call is not None:
            days_since_call += 1
            if days_since_call % TRADING_DAYS_PER_WEEK == 0 and drawdown > RELEVER_GATE:
                L_current = min(leverage_target, L_current + RELEVER_STEP_PER_WEEK)
                if L_current >= leverage_target:
                    days_since_call = None

        values.append(equity)
        dates.append(date)
        leverage_path.append(L_current)

    equity_series = pd.Series(values, index=dates)
    leverage_series = pd.Series(leverage_path, index=dates)
    return {
        "equity": equity_series,
        "n_margin_calls": len(margin_call_dates),
        "margin_call_dates": margin_call_dates,
        "pct_days_below_target": float((leverage_series < leverage_target - 1e-9).mean()),
    }


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


def run_scenario(daily_ret_main: pd.Series, daily_ret_oos: pd.Series, leverage: float, spread: float) -> dict:
    main_result = simulate_leverage_with_margin_calls(daily_ret_main, leverage, spread)
    oos_result = simulate_leverage_with_margin_calls(daily_ret_oos, leverage, spread)
    eq_main = main_result["equity"]
    eq_oos = oos_result["equity"]
    return {
        "leverage": leverage, "borrow_spread": spread,
        "sharpe": sharpe(eq_main), "cagr": cagr(eq_main),
        "max_drawdown": max_drawdown(eq_main), "calmar": calmar(eq_main),
        "n_margin_calls_main": main_result["n_margin_calls"],
        "pct_days_below_target_main": main_result["pct_days_below_target"],
        "oos_2025_sharpe": sharpe(eq_oos), "oos_2025_max_drawdown": max_drawdown(eq_oos),
        "oos_2025_total_return": float(eq_oos.iloc[-1] / eq_oos.iloc[0] - 1) if len(eq_oos) > 1 else None,
        "n_margin_calls_oos": oos_result["n_margin_calls"],
    }


def main():
    levels = [100_000, 1_000_000, 10_000_000]
    print("=== HYP-065: havstang 2,5x med marginalanrop-overlay pa HYP-056 ===\n")

    all_results = {}
    for level in levels:
        pv_main = load_hyp056_combined(level)
        pv_oos = load_hyp056_oos(level)
        r_main = pv_main.pct_change().dropna()
        r_oos = pv_oos.pct_change().dropna()

        level_results = []
        for leverage in [GATING_LEVERAGE] + DISCLOSURE_LEVERAGES:
            for spread, spread_label in [(GATING_SPREAD, "konservativ_gating"), (DISCLOSURE_SPREAD, "stressad_disclosure")]:
                res = run_scenario(r_main, r_oos, leverage, spread)
                res["spread_label"] = spread_label
                level_results.append(res)
        all_results[level] = level_results

        gating = next(r for r in level_results if r["leverage"] == GATING_LEVERAGE and r["spread_label"] == "konservativ_gating")
        eq_main_gating = simulate_leverage_with_margin_calls(r_main, GATING_LEVERAGE, GATING_SPREAD)["equity"]
        eq_main_gating.to_csv(RESULTS_DIR / f"portfolio_value_levered_{level}.csv", header=["portfolio_value"])

        dsr_info = deflated_sharpe_ratio_from_returns(
            eq_main_gating.pct_change().dropna().values, n_trials=DSR_N_TRIALS, risk_free_per_period=RF_ANNUAL / 252)
        gating["dsr"] = dsr_info["deflated_sharpe_ratio"]

        print(f"  ${level:>10,.0f}  [GATING 2,5x, konservativ spread] Sharpe={gating['sharpe']:.4f}  "
              f"CAGR={gating['cagr']:+.2%}  MaxDD={gating['max_drawdown']:.2%}  Calmar={gating['calmar']:.3f}  "
              f"DSR(K={DSR_N_TRIALS})={gating['dsr']:.4f}")
        print(f"              #marginalanrop(main)={gating['n_margin_calls_main']}  "
              f"andel_dagar_under_mal={gating['pct_days_below_target_main']:.1%}  "
              f"Sharpe-marginal mot 1,0-golv={gating['sharpe']-1.0:+.4f}  "
              f"OOS-Sharpe={gating['oos_2025_sharpe']:.4f}  OOS-avkastning={gating['oos_2025_total_return']:+.2%}\n")

    lvl = 100_000
    gating_100k = next(r for r in all_results[lvl] if r["leverage"] == GATING_LEVERAGE and r["spread_label"] == "konservativ_gating")
    ref_cagr = HYP056_MAIN_REF_CAGR[lvl]

    cond1 = gating_100k["sharpe"] >= 1.0
    cond2 = gating_100k["cagr"] > (ref_cagr + 0.05)
    cond3 = gating_100k["max_drawdown"] >= -0.20
    overall = "PASSED" if (cond1 and cond2 and cond3) else "FAILED"

    print("=== SLUTBEDOMNING (avgorande $100k-niva, 2,5x hafstang, konservativ spread) ===")
    print(f"  Villkor 1 (Sharpe >= 1,0): {gating_100k['sharpe']:.4f} -> {'PASS' if cond1 else 'FAIL'}")
    print(f"  Villkor 2 (CAGR > HYP-056 {ref_cagr:.2%} + 5,0pp = {ref_cagr + 0.05:.2%}): "
          f"{gating_100k['cagr']:.2%} -> {'PASS' if cond2 else 'FAIL'}")
    print(f"  Villkor 3 (MaxDD >= -20%): {gating_100k['max_drawdown']:.2%} -> {'PASS' if cond3 else 'FAIL'}")
    print(f"  => {overall}\n")

    summary = {
        "gating_leverage": GATING_LEVERAGE, "gating_spread": GATING_SPREAD,
        "all_scenarios_by_level": all_results, "hyp056_main_ref_cagr": HYP056_MAIN_REF_CAGR,
        "dsr_n_trials": DSR_N_TRIALS,
        "pass_fail": {"condition_1_sharpe": bool(cond1), "condition_2_cagr": bool(cond2),
                       "condition_3_maxdd": bool(cond3), "overall": overall},
    }
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
