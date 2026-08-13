"""
HYP-059: Havstang (1,5x) med marginalanrop/tvingad nedskalning som overlay
pa HYP-047:s redan kombinerade 25/25/25/25-portfolj.

Se research/hypothesis_registry/HYP-059-havstang-margin-anrop-hyp047.yaml
for det lasta kriteriet. Elfte kombinationshypotesen i registret.

MEKANISM (lockad, se kriteriet): FAST hafstang 1,5x pa HYP-047:s redan
berknade kombinerade avkastningsserie, FAKTISK daglig compoundering
(ingen algebraisk genvag). Lanekostnad pa det lanade kapitalet (0,5x):
RF (2%/ar) + KONSERVATIV spread (1,5%/ar) = 3,5%/ar totalt, primart
(gating) antagande.

MARGINALANROP (utover spreaden): om portfoljens EGEN levererade drawdown
fran rullande hogsta-vattenmarke nar -15%, tvingas hafstangen SAMMA dag
ner till 1,0x (hela lanat kapital loses in) + 0,5% forced-sale-slippage
pa den nedskalade notionalen. Aterlaning GRADVIS (+0,05x/handelsvecka),
ENDAST nar drawdown atehamtat sig forbi -5% fran samma hogsta-vattenmarke.

DRAWDOWN-TRIGGAD, INTE REG-T-PROCENT (se registerpostens egen motivering):
HYP-047:s laga egna volatilitet gor ett klassiskt 25%-underhallskrav till
en icke-handelse for den har boken (skulle kreva en encardaglig rorelse
pa ~-33% vid 2,0x). Drawdown-triggen efterliknar istallet ett internt
riskavdelning-limit, langt fore det lagstadgade Reg-T-golvet.

DISCLOSURE (icke-gating, alla nivaer): stressad spread (3,0%/ar over RF),
hafstangsnivaerna 1,25x/1,75x/2,0x.

INGEN NY BACKTEST-MOTOR: ren hafstangsmatematik ovanpa HYP-047:s redan
berknade, oforandrade kombinerade portfoljvardesserier (main 2010-2024,
OOS-2025) - ingen ny small-cap-signal, inget nytt handelsuniversum, ingen
ny prismatris laddas. small_cap_definition deklarerar N/A per
registerpostens egen text -> requires_friction_check i
scripts/hypothesis_gate.py returnerar False for denna fil (samma
undantag som HYP-039/041/043/044/045/046/047/048/056 redan fatt).

KALLOR (aterananvander direkt, ingen omberkning):
  strategies/HYP-047/results_corrected_2026-08-08/portfolio_value_combined_{level}.csv
  strategies/HYP-047/results_corrected_2026-08-08/portfolio_value_oos2025_combined_{level}.csv

Ingen spec-fil i research/strategy_specs/ skrevs for denna hypotes -
samma precedent som HYP-045/047/056 (overlayer utan ny backtest-motor
dokumenterar aterananvandningen direkt har i modulens docstring,
Strategy Builder-rollens "vilken befintlig kodmodul som ateranands" ar
sjalvklar/trivial for denna typ av portfoljniva-overlay).
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

HYP047_RESULTS = STRATEGIES_ROOT / "HYP-047" / "results_corrected_2026-08-08"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from deflated_sharpe_ratio import deflated_sharpe_ratio_from_returns  # noqa: E402

RF_ANNUAL = 0.02
GATING_LEVERAGE = 1.5
DISCLOSURE_LEVERAGES = [1.25, 1.75, 2.0]
GATING_SPREAD = 0.015   # konservativ, 1.5%/ar over RF - PRIMART (gating) antagande
DISCLOSURE_SPREAD = 0.030  # stressad, 3.0%/ar over RF - disclosure, ej gating

MARGIN_CALL_TRIGGER = -0.15
DELEVER_FLOOR = 1.0
FORCED_SALE_SLIPPAGE = 0.005
RELEVER_STEP_PER_WEEK = 0.05
RELEVER_GATE = -0.05
TRADING_DAYS_PER_WEEK = 5

# HYP-047:s egna lasta korrigerade referensvarden (jamforelsepunkten for
# villkor 2, se kriteriet).
HYP047_MAIN_REF_CAGR = {100_000: 0.0856, 1_000_000: 0.0852, 10_000_000: 0.0795}

DSR_N_TRIALS = 58  # k_total_hypotheses_before_this (57) + 1, per registerpostens egen K


def load_hyp047_combined(level: int) -> pd.Series:
    return pd.read_csv(HYP047_RESULTS / f"portfolio_value_combined_{level}.csv",
                        index_col=0, parse_dates=True)["portfolio_value"]


def load_hyp047_oos(level: int) -> pd.Series:
    return pd.read_csv(HYP047_RESULTS / f"portfolio_value_oos2025_combined_{level}.csv",
                        index_col=0, parse_dates=True)["portfolio_value"]


def simulate_leverage_with_margin_calls(daily_ret: pd.Series, leverage_target: float,
                                         borrow_spread: float, rf_annual=RF_ANNUAL) -> dict:
    """Verklig daglig hafstangscompoundering MED drawdown-triggad tvingad
    nedskalning och gradvis aterlaning. Identisk mekanism som diagnostiken
    (scripts/diagnostic_hyp047_leverage_margin_calls.py), nu formaliserad
    for det lasta kriteriet."""
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
        "leverage": leverage,
        "borrow_spread": spread,
        "sharpe": sharpe(eq_main),
        "cagr": cagr(eq_main),
        "max_drawdown": max_drawdown(eq_main),
        "calmar": calmar(eq_main),
        "n_margin_calls_main": main_result["n_margin_calls"],
        "margin_call_dates_main": main_result["margin_call_dates"],
        "pct_days_below_target_main": main_result["pct_days_below_target"],
        "oos_2025_sharpe": sharpe(eq_oos),
        "oos_2025_max_drawdown": max_drawdown(eq_oos),
        "oos_2025_total_return": float(eq_oos.iloc[-1] / eq_oos.iloc[0] - 1) if len(eq_oos) > 1 else None,
        "n_margin_calls_oos": oos_result["n_margin_calls"],
    }


def main():
    levels = [100_000, 1_000_000, 10_000_000]

    print("=== HYP-059: havstang 1,5x med marginalanrop-overlay pa HYP-047 ===\n")
    print(f"Laddar HYP-047:s redan berknade kombinerade portfoljvardesserier ({HYP047_RESULTS})...\n")

    all_results = {}

    for level in levels:
        pv_main = load_hyp047_combined(level)
        pv_oos = load_hyp047_oos(level)
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

        # Spara den gating-konfigurationens equity-kurva for revision
        eq_main_gating = simulate_leverage_with_margin_calls(r_main, GATING_LEVERAGE, GATING_SPREAD)["equity"]
        eq_main_gating.to_csv(RESULTS_DIR / f"portfolio_value_levered_{level}.csv", header=["portfolio_value"])

        dsr_info = deflated_sharpe_ratio_from_returns(
            eq_main_gating.pct_change().dropna().values, n_trials=DSR_N_TRIALS, risk_free_per_period=RF_ANNUAL / 252)
        gating["dsr"] = dsr_info["deflated_sharpe_ratio"]

        print(f"  ${level:>10,.0f}  [GATING 1,5x, konservativ spread] Sharpe={gating['sharpe']:.4f}  "
              f"CAGR={gating['cagr']:+.2%}  MaxDD={gating['max_drawdown']:.2%}  Calmar={gating['calmar']:.3f}  "
              f"DSR(K={DSR_N_TRIALS})={gating['dsr']:.4f}")
        print(f"              #marginalanrop(main)={gating['n_margin_calls_main']}  "
              f"andel_dagar_under_mal={gating['pct_days_below_target_main']:.1%}  "
              f"OOS-Sharpe={gating['oos_2025_sharpe']:.4f}  OOS-avkastning={gating['oos_2025_total_return']:+.2%}\n")

    # --- PASS/FAIL enligt det lasta kriteriet, AVGORANDE vid $100k, GATING-konfiguration ---
    lvl = 100_000
    gating_100k = next(r for r in all_results[lvl] if r["leverage"] == GATING_LEVERAGE and r["spread_label"] == "konservativ_gating")
    ref_cagr = HYP047_MAIN_REF_CAGR[lvl]

    cond1 = gating_100k["sharpe"] >= 1.0
    cond2 = gating_100k["cagr"] > (ref_cagr + 0.02)
    cond3 = gating_100k["max_drawdown"] >= -0.20
    overall = "PASSED" if (cond1 and cond2 and cond3) else "FAILED"

    print("=== SLUTBEDOMNING (avgorande $100k-niva, 1,5x hafstang, konservativ spread) ===")
    print(f"  Villkor 1 (Sharpe >= 1,0): {gating_100k['sharpe']:.4f} -> {'PASS' if cond1 else 'FAIL'}")
    print(f"  Villkor 2 (CAGR > HYP-047 {ref_cagr:.2%} + 2,0pp = {ref_cagr + 0.02:.2%}): "
          f"{gating_100k['cagr']:.2%} -> {'PASS' if cond2 else 'FAIL'}")
    print(f"  Villkor 3 (MaxDD >= -20%): {gating_100k['max_drawdown']:.2%} -> {'PASS' if cond3 else 'FAIL'}")
    print(f"  => {overall}\n")

    summary = {
        "gating_leverage": GATING_LEVERAGE,
        "gating_spread": GATING_SPREAD,
        "all_scenarios_by_level": all_results,
        "hyp047_main_ref_cagr": HYP047_MAIN_REF_CAGR,
        "dsr_n_trials": DSR_N_TRIALS,
        "pass_fail": {
            "condition_1_sharpe": bool(cond1), "condition_2_cagr": bool(cond2),
            "condition_3_maxdd": bool(cond3), "overall": overall,
        },
    }
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
