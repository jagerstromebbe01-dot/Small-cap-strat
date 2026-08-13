"""
Gratis robusthetskontroll, uppfoljning (2026-08-13, CEO-begard, INGEN
K-kostnad, andrar INGET last resultat): kor SAMMA syntetiska scenarier
som diagnostic_hyp088_synthetic_stress_test.py, men over HELA den
redan testade havstangsskalan (1,5x/2,0x/2,5x/3,0x - samma nivaer som
HYP-087/088:s egna disclosure-niver) for att ge ett riktigt, jamforbart
underlag for var pa skalan risken blir acceptabel, istallet for en
gissning baserad pa bara 3,0x-resultatet.

Anvander den EXAKTA, redan lasta simulate_leverage_with_margin_calls-
funktionen (importerad ofrandrad fran strategies/HYP-088/backtest.py) -
ingen omimplementation.
"""

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "strategies" / "HYP-088"))

from backtest import (  # noqa: E402
    simulate_leverage_with_margin_calls,
    GATING_SPREAD,
    MARGIN_CALL_TRIGGER,
)

LEVELS = [1.5, 2.0, 2.5, 3.0]


def make_series(daily_returns, start="2020-01-01"):
    dates = pd.bdate_range(start, periods=len(daily_returns))
    return pd.Series(daily_returns, index=dates)


def max_dd(equity: pd.Series) -> float:
    return float(((equity - equity.cummax()) / equity.cummax()).min())


def scenario_1_single_crash():
    """Samma som scenario 1 i det forsta stresstestet: 50 dagar flat,
    15 dagar a -1,5%/dag (~-20% underliggande), 25 dagar aterhamtning,
    20 dagar flat."""
    r = [0.0] * 50 + [-0.015] * 15 + [0.010] * 25 + [0.0] * 20
    return make_series(r)


def scenario_4_worse_than_history():
    """Samma som scenario 4: -35% underliggande over 20 dagar, ingen
    omedelbar studs."""
    r = [0.0] * 30 + [-0.021] * 20 + [0.0] * 30
    return make_series(r)


def run_and_report(series, label):
    print(f"=== {label} ===")
    print(f"{'Havstang':>10} {'#Anrop':>8} {'VarstaDD':>12} {'Naiv-DD (utan skydd)':>22} {'Skillnad':>10}")
    for lev in LEVELS:
        result = simulate_leverage_with_margin_calls(series, lev, GATING_SPREAD)
        worst = max_dd(result["equity"])

        cost_daily = (0.02 + GATING_SPREAD) / 252
        naive_r = lev * series - (lev - 1) * cost_daily
        naive_equity = (1 + naive_r).cumprod()
        naive_worst = max_dd(naive_equity)

        print(f"{lev:>9.1f}x {result['n_margin_calls']:>8} {worst:>11.2%} {naive_worst:>21.2%} "
              f"{worst - naive_worst:>+9.2%}")
    print()


def main():
    print("=== HYP-087/088-FAMILJEN: STRESSTEST OVER HELA HAVSTANGSSKALAN ===")
    print(f"(MARGIN_CALL_TRIGGER={MARGIN_CALL_TRIGGER:.0%}, samma mekanism for alla nivaer)\n")

    run_and_report(scenario_1_single_crash(), "Scenario 1: ~-20% underliggande krasch + aterhamtning")
    run_and_report(scenario_4_worse_than_history(), "Scenario 4: -35% underliggande, VARRE AN 2010-2025, ingen studs")

    print("=== SLUTSATS ===")
    print("Jamforelsetabellerna ovan visar hur mycket 'Varsta DD' faktiskt vaxer med")
    print("havstangsgraden i samma extremscenario - anvand for att valja en niva som")
    print("kanns rimlig aven i ett scenario varre an nagot backtesten sjalv sag.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
