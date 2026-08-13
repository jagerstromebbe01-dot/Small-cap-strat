#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes - ingen K-kostnad, INGET last kriterium):
utokar scripts/diagnostic_hyp047_leverage_exploration.py med en verklig
marginalanrop/tvingad-nedskalning-mekanism, inte bara en statisk
lanekostnad-spread.

VARFOR DRAWDOWN-TRIGGAD, INTE KLASSISK REG-T-PROCENT:
HYP-047 ar en diversifierad, delvis hedgad portfolj med lag egen
volatilitet (implicerad arsvol ~5-6% vid Sharpe~1.1, CAGR~8.5%). Ett
klassiskt Reg-T-underhallskrav (25% av notional) skulle for denna bok
kreva en encardaglig rorelse pa cirka -33% vid L=2.0 for att overhuvudtaget
triggas - i praktiken ALDRIG for den har boken, vilket skulle gora
mekanismen till en icke-handelse och dolja precis den risk CEO bad om
att undersoka. Istallet anvands en HOGRE, riskskrivbord-liknande tröskel
pa EGEN (levererad) drawdown fran rullande hogsta-vattenmarke - detta
motsvarar hur en verklig prime broker/riskavdelning agerar LANGT innan
det lagstadgade minimikravet nas (interna limiter, inte bara Reg-T-golvet).

MEKANISM (mina diagnostiska antaganden - INTE lasta, oppna for CEO att
justera innan nagot kriterium las):
  1. Levererad daglig avkastning beraknas med AKTUELL hafstang L_t
     (borjar pa L_target), lanekostnad pa (L_t - 1) x notional.
  2. Drawdown fran den levererade equity-kurvans EGNA rullande
     hogsta-vattenmarke beraknas varje dag.
  3. Om drawdown <= MARGIN_CALL_TRIGGER (-15%): TVINGAD nedskalning till
     DELEVER_FLOOR (1.0x, dvs hela det lanade kapitalet loses in) SAMMA
     dag, plus en forced-sale-slippage-kostnad (utover normal spread)
     pa den notional-andel som tvingas salja.
  4. Aterhamtning ar INTE omedelbar: hafstangen tillats bara stiga
     RELEVER_STEP (0.05x) per handelsvecka, och BARA nar portfoljen
     inte langre ar i en aktiv drawdown vardare an RELEVER_GATE (-5%)
     fran samma hogsta-vattenmarke - modellerar att ingen
     riskavdelning aterlanar fullt omedelbart efter ett marginalanrop.

Samma FAKTISKA dagliga compoundering-disciplin som forsta diagnostiken
(ingen algebraisk genvag).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
STRATEGIES_ROOT = REPO_ROOT / "strategies"
RESULTS_DIR = STRATEGIES_ROOT / "HYP-047" / "results_corrected_2026-08-08"

RF_ANNUAL = 0.02
BORROW_SPREADS = {
    "Konservativ spread (+1.5%/ar over RF)": 0.015,
    "Hogre spread (+3.0%/ar over RF, stressad finansiering)": 0.030,
}
LEVERAGE_LEVELS = [1.25, 1.5, 1.75, 2.0]

MARGIN_CALL_TRIGGER = -0.15   # levererad egen drawdown fran HWM som triggar tvingad nedskalning
DELEVER_FLOOR = 1.0           # tvingas hela vagen till ohavstangad efter ett anrop
FORCED_SALE_SLIPPAGE = 0.005  # extra engangskostnad pa notional som tvingas salja (utover spread)
RELEVER_STEP_PER_WEEK = 0.05  # hur mycket hafstangen far aterhamta sig per handelsvecka
RELEVER_GATE = -0.05          # far bara aterlana medan drawdown fran HWM ar battre an detta
TRADING_DAYS_PER_WEEK = 5


def simulate_static_spread(daily_ret: pd.Series, leverage: float, borrow_spread: float, rf_annual=RF_ANNUAL) -> pd.Series:
    """Samma som forsta diagnostiken: konstant hafstang, ingen marginalanrop-mekanism."""
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
    """Verklig hafstang MED drawdown-triggad tvingad nedskalning och gradvis aterlaning."""
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
        "leverage_path": leverage_series,
        "margin_calls": margin_call_dates,
        "pct_days_delevered": float((leverage_series < leverage_target - 1e-9).mean()),
        "avg_leverage_realized": float(leverage_series.mean()),
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
    main = pd.read_csv(RESULTS_DIR / f"portfolio_value_combined_{level}.csv", index_col=0, parse_dates=True).iloc[:, 0]
    if not include_oos:
        return main.pct_change().dropna()
    oos = pd.read_csv(RESULTS_DIR / f"portfolio_value_oos2025_combined_{level}.csv", index_col=0, parse_dates=True).iloc[:, 0]
    main_norm = main / main.iloc[0]
    oos_norm = (oos / oos.iloc[0]) * main_norm.iloc[-1]
    chained = pd.concat([main_norm, oos_norm])
    return chained.pct_change().dropna()


def main():
    print("=" * 78)
    print("DEL A: Huvudperiod (2010-2024), ALLA TRE KAPITALNIVAER - matchar")
    print("registrets gating-konvention (spec kraver 100k/1M/10M for small-cap)")
    print("=" * 78)
    for level in (100_000, 1_000_000, 10_000_000):
        daily_ret_main = load_returns(level, include_oos=False)
        run_block(daily_ret_main, f"huvudperiod, {level:,.0f}")

    print()
    print("=" * 78)
    print("DEL B: Huvudperiod + OOS-2025 kedjad ($1M representativ niva,")
    print("informativt - fangar sent 2025-volatilitetsuppsving som HYP-056 redan")
    print("flaggade, testar marginalanrop-mekanismen mot mer nyligen data)")
    print("=" * 78)
    daily_ret_full = load_returns(1_000_000, include_oos=True)
    run_block(daily_ret_full, "huvudperiod+OOS-2025, 1,000,000")

    return 0


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


if __name__ == "__main__":
    sys.exit(main())
