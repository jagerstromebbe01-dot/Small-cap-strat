#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes - ingen K-kostnad, INGET last kriterium):
utforskar hur mattlig hävstang paverkar HYP-047:s Sharpe/CAGR/MaxDD-
profil. CEO bad uttryckligen om att undersoka detta "med odmjukhet"
INNAN forskningsrapporten - detta ar en fristaende utforskning, inte
ett forslag att las nagot.

METODOLOGISK DISCIPLIN: simulerar FAKTISK daglig hafstang (multiplicerar
den dagliga avkastningen, later den sedan compoundera naturligt) - INTE
en algebraisk skalning av redan berknade sammanfattningsmatt. Detta
fangar den valkanda "leverage decay"-effekten (volatilitetsutspädning
fran Jensens olikhet) som en naiv skalning skulle dolja. Lanekostnad
modelleras som en EXPLICIT spread over riskfri ranta (inte gratis
hafstang) - tva olika spread-antaganden testas for kanslighet.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
STRATEGIES_ROOT = REPO_ROOT / "strategies"

RF_ANNUAL = 0.02
BORROW_SPREADS = {
    "Konservativ spread (+1.5%/ar over RF)": 0.015,
    "Hogre spread (+3.0%/ar over RF, stressad finansiering)": 0.030,
}
LEVERAGE_LEVELS = [1.0, 1.25, 1.5, 1.75, 2.0]


def simulate_leverage(daily_ret: pd.Series, leverage: float, borrow_spread: float, rf_annual=RF_ANNUAL) -> pd.Series:
    """Faktisk daglig hafstang: portfoljens EGEN dagliga avkastning
    multipliceras med L, det extra lanade kapitalet (L-1) kostar
    rf + spread per ar. Compounderas dag for dag - ingen genvag."""
    rf_daily = rf_annual / 252
    cost_daily = (rf_annual + borrow_spread) / 252

    values = [1.0]
    for r in daily_ret:
        if np.isnan(r):
            r = 0.0
        levered_r = leverage * r - (leverage - 1) * cost_daily
        values.append(values[-1] * (1 + levered_r))
    return pd.Series(values[1:], index=daily_ret.index)


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
    level = 1_000_000  # representativ nivå
    pv = pd.read_csv(STRATEGIES_ROOT / "HYP-047" / "results" / f"portfolio_value_combined_{level}.csv",
                      index_col=0, parse_dates=True).iloc[:, 0]
    daily_ret = pv.pct_change().dropna()

    print(f"=== HYP-047 ({level:,.0f}-nivan) med hafstang - FAKTISK daglig compoundering ===\n")
    print(f"Ograterad baslinje: Sharpe={sharpe(pv):.4f}  CAGR={cagr(pv):+.2%}  "
          f"MaxDD={max_drawdown(pv):.2%}  Calmar={calmar(pv):.3f}\n")

    for spread_name, spread in BORROW_SPREADS.items():
        print(f"--- {spread_name} ---")
        print(f"{'Hafstang':<10} {'Sharpe':>8} {'CAGR':>9} {'MaxDD':>9} {'Calmar':>8}   Kommentar")
        for lev in LEVERAGE_LEVELS:
            levered = simulate_leverage(daily_ret, lev, spread)
            sh, cg, md, cm = sharpe(levered), cagr(levered), max_drawdown(levered), calmar(levered)
            note = "(baslinje)" if lev == 1.0 else ""
            print(f"{lev:<10.2f} {sh:>8.4f} {cg:>9.2%} {md:>9.2%} {cm:>8.3f}   {note}")
        print()

    print("=== Jamforelse: naiv (FELAKTIG) algebraisk skalning vs verklig compoundering ===")
    print("(visar HUR STOR skillnaden ar - detta ar poangen med att simulera pa riktigt)\n")
    base_sharpe = sharpe(pv)
    base_cagr = cagr(pv)
    base_md = max_drawdown(pv)
    for lev in [1.5, 2.0]:
        naive_cagr = base_cagr * lev  # FELAKTIG genvag, bara for jamforelse
        naive_md = base_md * lev
        real = simulate_leverage(daily_ret, lev, BORROW_SPREADS["Konservativ spread (+1.5%/ar over RF)"])
        print(f"Hafstang {lev}x:")
        print(f"  Naiv (felaktig) skalning:   CAGR={naive_cagr:+.2%}  MaxDD={naive_md:.2%}")
        print(f"  Verklig daglig compoundering: CAGR={cagr(real):+.2%}  MaxDD={max_drawdown(real):.2%}")
        print(f"  Differens (leverage decay): {cagr(real)-naive_cagr:+.2%} CAGR, {max_drawdown(real)-naive_md:+.2%} MaxDD\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
