#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes - ingen K-kostnad, inget last kriterium):
kalibrerar ett SNABBT, pristrosel-triggat nedskalningsmekanism pa
BASELINE_BASKET (samma 5-coin likaviktade, friktionsjusterade korg som
HYP-061/062/063 anvander), som uppfoljning pa HYP-061:s FAILADE resultat
(razor-thin miss mot baseline-Sharpen, MaxDD-forbattring men INTE battre
Calmar an att bara halla korgen).

MOTIVERING: HYP-061:s volatilitetsmalsattning (60-dagars rullande vol)
ar STRUKTURELLT LANGSAM - skavde bara 10.6pp av MaxDD. Denna diagnostik
testar om en SNABBARE, pris-drawdown-triggad mekanism (samma familj som
bear catcher/krasch-overlayn pa aktiesidan, reagerar SAMMA DAG) kan gora
battre ifran sig, INNAN nagot las.

RISK ATT KALIBRERA FEL: crypto har ofta -30-40% korrigeringar MITT I en
fortsatt bullmarknad - en for grund troskel whipsawar och ater upp
avkastningen. Testar darfor ett GRID av trosklar x haircut-nivaer for
att se var avvagningen faktiskt ligger innan ett kriterium foreslas.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "strategies" / "common"))
import crypto_data as cd  # noqa: E402

TRIGGER_THRESHOLDS = [-0.25, -0.35, -0.45, -0.55]
HAIRCUT_LEVELS = [0.0, 0.25]  # 0.0 = full kontant vid triggning, 0.25 = 25% kvarvarande exponering
RE_ENTRY = -0.10  # aterinträde vid full exponering nar drawdown fran samma HWM battre an detta


def simulate_drawdown_trigger(basket: pd.Series, trigger: float, haircut: float) -> dict:
    raw_ret = basket.pct_change().fillna(0.0)
    equity = 1.0
    hwm = 1.0
    exposure = 1.0
    values, dates = [], []
    n_triggers = 0
    days_defensive = 0

    for date, r in raw_ret.items():
        port_ret = exposure * r + (1 - exposure) * (cd.RF_ANNUAL / cd.ANNUALIZATION_DAYS)
        equity *= (1 + port_ret)
        hwm = max(hwm, equity)
        drawdown = (equity - hwm) / hwm

        if exposure == 1.0 and drawdown <= trigger:
            exposure = haircut
            n_triggers += 1
        elif exposure < 1.0 and drawdown > RE_ENTRY:
            exposure = 1.0

        if exposure < 1.0:
            days_defensive += 1

        values.append(equity)
        dates.append(date)

    eq = pd.Series(values, index=dates)
    return {
        "equity": eq,
        "sharpe": cd.sharpe(eq),
        "cagr": cd.cagr(eq),
        "max_drawdown": cd.max_drawdown(eq),
        "calmar": cd.calmar(eq),
        "n_triggers": n_triggers,
        "pct_days_defensive": days_defensive / len(eq),
    }


def main():
    price_data = {t: cd.load_crypto(t) for t in cd.TICKERS}
    basket = cd.build_baseline_basket(price_data)

    boundary = pd.Timestamp(cd.OOS_START)
    basket_main = basket.loc[basket.index < boundary]

    base_sh, base_cagr, base_md, base_cal = (
        cd.sharpe(basket_main), cd.cagr(basket_main), cd.max_drawdown(basket_main), cd.calmar(basket_main))
    print(f"=== BASELINE_BASKET (huvudperiod, ingen overlay) ===")
    print(f"Sharpe={base_sh:.4f}  CAGR={base_cagr:+.2%}  MaxDD={base_md:.2%}  Calmar={base_cal:.3f}\n")

    print(f"{'Troskel':<10} {'Haircut':<9} {'Sharpe':>8} {'CAGR':>9} {'MaxDD':>9} {'Calmar':>8} {'#Triggers':>10} {'%dagar_def':>11}")
    for trigger in TRIGGER_THRESHOLDS:
        for haircut in HAIRCUT_LEVELS:
            res = simulate_drawdown_trigger(basket_main, trigger, haircut)
            flag = " <-- Calmar>baseline" if res["calmar"] > base_cal else ""
            print(f"{trigger:<10.2f} {haircut:<9.2f} {res['sharpe']:>8.4f} {res['cagr']:>9.2%} "
                  f"{res['max_drawdown']:>9.2%} {res['calmar']:>8.3f} {res['n_triggers']:>10d} "
                  f"{res['pct_days_defensive']:>10.1%}{flag}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
