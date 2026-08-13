#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes - ingen K-kostnad, inget last kriterium):
samma marginalanrops-mekanism som scripts/diagnostic_hyp047_leverage_margin_calls.py
(och det senare lasta HYP-059), men applicerad pa HYP-056 istallet for
HYP-047 som bas.

MOTIVERING: HYP-056 har mycket lagre egen MaxDD an HYP-047 (-5.9% till
-6.0% mot -8.2% till -8.7%, se dess lasta capital_level_results) tack
vare volatilitetsmalsattnings-overlayn. Lagre bas-risk borde ge mer
"headroom" for hafstang innan marginalanropen borjar bita och Sharpen
kryper ner - denna diagnostik testar OM det stammer, INNAN nagot
kriterium foreslas/las.

Samma mekanism/parametrar som HYP-059 (INGEN ny kalibrering annu - det
ar poangen med att forst testa om samma installningar ger battre
resultat pa en lagre-risk bas): drawdown-triggad (-15% fran egen HWM),
delever till 1.0x, 0.5% forced-sale-slippage, 0.05x/vecka aterlaning,
gated pa -5% aterhamtning. Testar BREDARE hafstangsintervall (upp till
3.0x) eftersom lagre bas-risk kan mojliggora det.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
STRATEGIES_ROOT = REPO_ROOT / "strategies"
RESULTS_DIR = STRATEGIES_ROOT / "HYP-056" / "results"

RF_ANNUAL = 0.02
BORROW_SPREADS = {
    "Konservativ spread (+1.5%/ar over RF)": 0.015,
    "Hogre spread (+3.0%/ar over RF, stressad finansiering)": 0.030,
}
LEVERAGE_LEVELS = [1.25, 1.5, 1.75, 2.0, 2.5, 3.0]

MARGIN_CALL_TRIGGER = -0.15
DELEVER_FLOOR = 1.0
FORCED_SALE_SLIPPAGE = 0.005
RELEVER_STEP_PER_WEEK = 0.05
RELEVER_GATE = -0.05
TRADING_DAYS_PER_WEEK = 5


def simulate_static_spread(daily_ret: pd.Series, leverage: float, borrow_spread: float, rf_annual=RF_ANNUAL) -> pd.Series:
    cost_daily = (rf_annual + borrow_spread) / 252
    values = [1.0]
    for r in daily_ret:
        if np.isnan(r):
            r = 0.0
        levered_r = leverage * r - (leverage - 1) * cost_daily
        values.append(values[-1] * (1 + levered_r))
    return pd.Series(values[1:], index=daily_ret.index)


def simulate_with_margin_calls(daily_ret: pd.Series, leverage_target: float, borrow_spread: float,
                                rf_annual=RF_ANNUAL) -> dict:
    cost_daily = (rf_annual + borrow_spread) / 252
    equity = 1.0
    hwm = 1.0
    L_current = leverage_target
    values = []
    leverage_path = []
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
            margin_call_dates.append(date)
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
        leverage_path.append(L_current)

    equity_series = pd.Series(values, index=daily_ret.index)
    leverage_series = pd.Series(leverage_path, index=daily_ret.index)
    return {
        "equity": equity_series,
        "margin_calls": margin_call_dates,
        "pct_days_delevered": float((leverage_series < leverage_target - 1e-9).mean()),
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


def load_returns(level: int, include_oos: bool) -> pd.Series:
    main = pd.read_csv(RESULTS_DIR / f"portfolio_value_combined_scaled_{level}.csv", index_col=0, parse_dates=True).iloc[:, 0]
    if not include_oos:
        return main.pct_change().dropna()
    oos = pd.read_csv(RESULTS_DIR / f"portfolio_value_oos2025_combined_scaled_{level}.csv", index_col=0, parse_dates=True).iloc[:, 0]
    main_norm = main / main.iloc[0]
    oos_norm = (oos / oos.iloc[0]) * main_norm.iloc[-1]
    chained = pd.concat([main_norm, oos_norm])
    return chained.pct_change().dropna()


def run_block(daily_ret: pd.Series, label: str):
    baseline_static = simulate_static_spread(daily_ret, 1.0, 0.0)
    print(f"\nOgraterad baslinje ({label}): Sharpe={sharpe(baseline_static):.4f}  "
          f"CAGR={cagr(baseline_static):+.2%}  MaxDD={max_drawdown(baseline_static):.2%}  "
          f"Calmar={calmar(baseline_static):.3f}\n")

    for spread_name, spread in BORROW_SPREADS.items():
        print(f"--- {spread_name} ---")
        header = (f"{'Hafstang':<9} {'Sharpe(statisk)':>16} {'Sharpe(marginal)':>17} "
                  f"{'CAGR(statisk)':>14} {'CAGR(marginal)':>15} {'MaxDD(statisk)':>15} "
                  f"{'MaxDD(marginal)':>16} {'#Anrop':>7} {'%dagar<mal':>11}")
        print(header)
        for lev in LEVERAGE_LEVELS:
            static = simulate_static_spread(daily_ret, lev, spread)
            mc = simulate_with_margin_calls(daily_ret, lev, spread)
            eq = mc["equity"]
            print(f"{lev:<9.2f} {sharpe(static):>16.4f} {sharpe(eq):>17.4f} "
                  f"{cagr(static):>14.2%} {cagr(eq):>15.2%} "
                  f"{max_drawdown(static):>15.2%} {max_drawdown(eq):>16.2%} "
                  f"{len(mc['margin_calls']):>7d} {mc['pct_days_delevered']:>10.1%}")
        print()


def main():
    print("=" * 78)
    print("DEL A: Huvudperiod (2010-2024), ALLA TRE KAPITALNIVAER - HYP-056 som bas")
    print("=" * 78)
    for level in (100_000, 1_000_000, 10_000_000):
        daily_ret_main = load_returns(level, include_oos=False)
        run_block(daily_ret_main, f"huvudperiod, {level:,.0f}")

    print()
    print("=" * 78)
    print("DEL B: Huvudperiod + OOS-2025 kedjad ($1M representativ niva, informativt)")
    print("=" * 78)
    daily_ret_full = load_returns(1_000_000, include_oos=True)
    run_block(daily_ret_full, "huvudperiod+OOS-2025, 1,000,000")

    return 0


if __name__ == "__main__":
    sys.exit(main())
