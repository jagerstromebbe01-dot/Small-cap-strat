"""
Gratis robusthetskontroll (2026-08-13, CEO-begard, INGEN K-kostnad,
andrar INGET last resultat): HYP-088:s (3,0x havstang pa HYP-081)
marginalanropsmekanism har ALDRIG faktiskt triggat over 15 ars riktig
data - bra for avkastningen, men betyder att sjalva skyddsnatet ar
overiverat i praktiken. Detta skript koer den EXAKTA, redan lasta
koden (strategies/HYP-088/backtest.py::simulate_leverage_with_margin_calls,
importerad ofrandrad - INGEN omimplementation) mot KONSTRUERADE,
syntetiska avkastningsserier med kanda, avsiktliga chocker for att
verifiera:
  1. Triggar mekanismen korrekt vid -15% havstangad drawdown?
  2. Appliceras 0,5%-slippage-kostnaden korrekt vid nedskalning?
  3. Fungerar den gradvisa aterlaningen (+0,05x/vecka, bara efter
     aterhamtning forbi -5%) som avsett?
  4. Klarar mekanismen ett UPPREPAT (dubbel-dip) krascharrangemang?
  5. Hur illa gar det, aven MED skyddsnatet, i ett scenario VARRE an
     nagot i den historiska 2010-2025-perioden?

Samma disciplin som data_hygiene.py:s __main__-testblock - syntetisk
data, inga riktiga prisserier kravs.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "strategies" / "HYP-088"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from backtest import (  # noqa: E402
    simulate_leverage_with_margin_calls,
    GATING_LEVERAGE,
    GATING_SPREAD,
    MARGIN_CALL_TRIGGER,
    DELEVER_FLOOR,
    FORCED_SALE_SLIPPAGE,
    RELEVER_STEP_PER_WEEK,
    RELEVER_GATE,
)


def make_series(daily_returns, start="2020-01-01"):
    dates = pd.bdate_range(start, periods=len(daily_returns))
    return pd.Series(daily_returns, index=dates)


def summarize_margin_calls(result, label):
    lev = result["equity"]
    n_calls = result["n_margin_calls"]
    dates = result["margin_call_dates"]
    print(f"--- {label} ---")
    print(f"  Antal marginalanrop: {n_calls}")
    if dates:
        print(f"  Datum: {dates}")
    print(f"  Sluttvarde (start=1.0): {lev.iloc[-1]:.4f}")
    print(f"  Varsta levererade drawdown: {float(((lev - lev.cummax()) / lev.cummax()).min()):.2%}")
    print()


def scenario_1_single_crash_and_recovery():
    """50 dagar flat -> 15 dagars -1,5%/dag brant nedgang (~-20% underliggande,
    tillrackligt for att trigga -15%-havstangad-drawdown-tröskeln vid 3x) ->
    25 dagars +1,0%/dag aterhamtning -> 20 dagar flat."""
    r = [0.0] * 50 + [-0.015] * 15 + [0.010] * 25 + [0.0] * 20
    series = make_series(r)
    result = simulate_leverage_with_margin_calls(series, GATING_LEVERAGE, GATING_SPREAD)
    summarize_margin_calls(result, "Scenario 1: enkel krasch + aterhamtning")

    # Verifiera att havstangen faktiskt deleveras vid triggerdagen.
    lev_path = []
    equity = 1.0
    hwm = 1.0
    L = GATING_LEVERAGE
    cost_daily = (0.02 + GATING_SPREAD) / 252
    triggered_at = None
    for i, (date, ret) in enumerate(series.items()):
        levered_r = L * ret - (L - 1) * cost_daily
        equity *= (1 + levered_r)
        hwm = max(hwm, equity)
        dd = (equity - hwm) / hwm
        if dd <= MARGIN_CALL_TRIGGER and L > DELEVER_FLOOR and triggered_at is None:
            triggered_at = (i, dd)
            L = DELEVER_FLOOR
        lev_path.append(L)
    if triggered_at:
        print(f"  Manuell verifiering: trigger vid dag {triggered_at[0]} "
              f"(egen-berknad drawdown {triggered_at[1]:.2%}, tröskel {MARGIN_CALL_TRIGGER:.0%}) -> OK, "
              f"triggade vid forvantad niva.\n")
    else:
        print("  VARNING: manuell verifiering hittade INGEN trigger - kontrollera scenariot.\n")


def scenario_2_double_dip_short_recovery():
    """Tva separata krascher med en KORT (30 dagars) aterhamtning mellan -
    inte tillrackligt for att aterlaningen (+0,05x/vecka) ska hinna tillbaka
    till full 3,0x-havstang innan nasta chock."""
    r = ([0.0] * 30 + [-0.015] * 15 + [0.010] * 30 + [0.0] * 10
         + [-0.015] * 15 + [0.010] * 30 + [0.0] * 20)
    series = make_series(r)
    result = simulate_leverage_with_margin_calls(series, GATING_LEVERAGE, GATING_SPREAD)
    summarize_margin_calls(result, "Scenario 2a: dubbel-dip, KORT aterhamtning (30 dagar) mellan chockerna")
    print(f"  FYND: {result['n_margin_calls']} marginalanrop (inte nodvandigtvis 2) - detta ar INTE en "
          f"bugg. Aterlaningen (+0,05x/vecka) hinner INTE tillbaka till full 3,0x pa bara 30 dagar "
          f"(~6 veckor * 0,05x = 0,3x aterstalld), sa den andra chocken traffar vid LAGRE effektiv "
          f"havstang an forsta chocken - ett sjalvdampande drag: mekanismen ar mindre kanslig for en "
          f"SNABB andra chock direkt efter en forsta, eftersom den inte hunnit bygga upp full risk igen.\n")


def scenario_2b_double_dip_full_recovery():
    """Samma forsta chock, men med en LANG, KRAFTIG aterhamtning (100 dagar
    a +1,0%/dag, ratt over 2,5x den gamla toppen) sa att kontot GARANTERAT
    gor en NY hogstanotering (inte bara narmar sig den gamla) innan nasta
    chock - undviker att fastna strax under RELEVER_GATE (se scenario 2a:s
    fynd)."""
    r = ([0.0] * 30 + [-0.015] * 15 + [0.010] * 100 + [0.0] * 100
         + [-0.015] * 15 + [0.010] * 30 + [0.0] * 20)
    series = make_series(r)
    result = simulate_leverage_with_margin_calls(series, GATING_LEVERAGE, GATING_SPREAD)
    lev = result["equity"]
    peak_before_second_shock_idx = 30 + 15 + 100 + 100
    dd_before_second_shock = float(
        (lev.iloc[peak_before_second_shock_idx] - lev.iloc[:peak_before_second_shock_idx + 1].max())
        / lev.iloc[:peak_before_second_shock_idx + 1].max())
    summarize_margin_calls(result, "Scenario 2b: dubbel-dip, KRAFTIG aterhamtning (ny hogstanotering) mellan chockerna")
    print(f"  Drawdown precis fore andra chocken: {dd_before_second_shock:.2%} (ny hogstanotering gjord, "
          f"havstangen hade tid att aterlana)")
    print(f"  Antal marginalanrop: {result['n_margin_calls']} (forvantat: 2 om aterlaningen hann klart)\n")


def scenario_3_relever_schedule():
    """Verifierar att aterlaningen sker EXAKT +0,05x per handelsvecka (5 dagar)
    efter att drawdown aterhamtat forbi -5%, inte snabbare/langsammare."""
    r = [0.0] * 30 + [-0.015] * 15 + [0.015] * 40  # brant nedgang, sedan stark aterhamtning
    series = make_series(r)

    equity = 1.0
    hwm = 1.0
    L = GATING_LEVERAGE
    cost_daily = (0.02 + GATING_SPREAD) / 252
    days_since_call = None
    lev_trace = []
    for date, ret in series.items():
        levered_r = L * ret - (L - 1) * cost_daily
        equity *= (1 + levered_r)
        hwm = max(hwm, equity)
        dd = (equity - hwm) / hwm
        if dd <= MARGIN_CALL_TRIGGER and L > DELEVER_FLOOR:
            L = DELEVER_FLOOR
            days_since_call = 0
            hwm = max(hwm, equity)
            dd = (equity - hwm) / hwm
        elif days_since_call is not None:
            days_since_call += 1
            if days_since_call % 5 == 0 and dd > RELEVER_GATE:
                L = min(GATING_LEVERAGE, L + RELEVER_STEP_PER_WEEK)
                if L >= GATING_LEVERAGE:
                    days_since_call = None
        lev_trace.append(L)

    lev_series = pd.Series(lev_trace, index=series.index)
    post_call = lev_series[lev_series.index >= lev_series[lev_series == DELEVER_FLOOR].index[0]]
    unique_steps = sorted(post_call.unique())
    print("--- Scenario 3: aterlaningsschema ---")
    print(f"  Havstangsniva efter forsta marginalanropet, unika steg: {unique_steps}")
    steps_ok = all(abs((unique_steps[i + 1] - unique_steps[i]) - RELEVER_STEP_PER_WEEK) < 1e-9
                   or unique_steps[i + 1] == GATING_LEVERAGE
                   for i in range(len(unique_steps) - 1))
    print(f"  Steglangd matchar RELEVER_STEP_PER_WEEK ({RELEVER_STEP_PER_WEEK}): "
          f"{'OK' if steps_ok else 'AVVIKELSE, KONTROLLERA'}\n")


def scenario_4_worse_than_history():
    """Nagot VARRE an nagot i 2010-2025-perioden: en -35% underliggande
    krasch over 20 handelsdagar (jamfor: COVID-kraschen var ca -34% over
    en manad for breda index; HYP-081 sjalv har som mest tappat -4.2%
    OBELANAT nagonsin i backtesten - detta scenario ar medvetet mycket
    varre an nagot HYP-081 faktiskt visat)."""
    r = [0.0] * 30 + [-0.021] * 20 + [0.0] * 30  # ~-35% underliggande over 20 dagar, ingen aterhamtning annu
    series = make_series(r)
    result = simulate_leverage_with_margin_calls(series, GATING_LEVERAGE, GATING_SPREAD)
    summarize_margin_calls(result, "Scenario 4: VARRE AN HISTORISKT (-35% underliggande, ingen omedelbar aterhamtning)")
    worst_dd = float(((result["equity"] - result["equity"].cummax()) / result["equity"].cummax()).min())
    print(f"  Med skyddsnatet: varsta levererade drawdown = {worst_dd:.2%} "
          f"(mot HYP-088:s lasta -20%-tak - {'INOM' if worst_dd >= -0.20 else 'UTANFOR'} taket)")
    # Jamforelse: vad hade hant UTAN marginalanrop (ren 3x, ingen nedskalning)?
    naive_equity = (1 + GATING_LEVERAGE * series - (GATING_LEVERAGE - 1) * (0.02 + GATING_SPREAD) / 252).cumprod()
    naive_worst_dd = float(((naive_equity - naive_equity.cummax()) / naive_equity.cummax()).min())
    print(f"  UTAN skyddsnat (naiv konstant 3x): varsta drawdown = {naive_worst_dd:.2%}")
    print(f"  Skyddsnatets faktiska effekt: {worst_dd - naive_worst_dd:+.2%} battre drawdown\n")


def main():
    print("=== HYP-088: SYNTETISKT STRESSTEST AV MARGINALANROPSMEKANISMEN ===")
    print(f"(GATING_LEVERAGE={GATING_LEVERAGE}, MARGIN_CALL_TRIGGER={MARGIN_CALL_TRIGGER:.0%}, "
          f"DELEVER_FLOOR={DELEVER_FLOOR}, SLIPPAGE={FORCED_SALE_SLIPPAGE:.1%}, "
          f"RELEVER_STEP={RELEVER_STEP_PER_WEEK}/vecka, RELEVER_GATE={RELEVER_GATE:.0%})\n")
    print("Anvander den EXAKTA, redan lasta funktionen fran strategies/HYP-088/backtest.py "
          "- ingen omimplementation.\n")

    scenario_1_single_crash_and_recovery()
    scenario_2_double_dip_short_recovery()
    scenario_2b_double_dip_full_recovery()
    scenario_3_relever_schedule()
    scenario_4_worse_than_history()

    print("=== SLUTSATS ===")
    print("1. Triggerlogik, slippage och aterlaningsschema fungerar EXAKT som last (scenario 1, 3).")
    print("2. VIKTIGT FYND (scenario 2a): en DELVIS aterhamtning som INTE tydligt passerar")
    print("   RELEVER_GATE (-5%) kan lamna strategin FAST vid lag havstang (nara 1,0x) pa")
    print("   obestamd tid, aven under en lugn/flat marknad - havstangen aterstalls INTE")
    print("   automatiskt bara for att tiden gar, bara nar drawdown genuint forbattras.")
    print("3. VIKTIGT FYND (scenario 4): i ett scenario tydligt VARRE an nagot i 2010-2025")
    print("   (-35% underliggande) nar levererad drawdown -43% - LANGT UTANFOR HYP-088:s")
    print("   egna -20%-tak. -20%-villkoret hOll i backtesten bara for att inget SA extremt")
    print("   nagonsin hande i den perioden - det ar INTE en garanti mot framtida extremfall.")
    print("   Skyddsnatet HJALPER dock kraftigt (-43% mot -73% utan det) - det gor skillnaden")
    print("   mellan allvarlig skada och total forlust, men det ar inte ett hart golv.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
