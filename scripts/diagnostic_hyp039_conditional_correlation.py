#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes - ingen K-kostnad, rör INTE
research/hypothesis_registry/HYP-039...yaml eller dess sparade resultat):
undersöker om SPY vs HYP-037:s dagliga avkastningskorrelation stiger
specifikt UNDER stress - inte bara helperiodssnittet (-0.003, redan
beräknat FÖRE HYP-039:s vikt låstes, se registerposten).

Motiv: den klassiska diversifieringsrisken är att korrelationer stiger
just när man behöver diversifieringen som mest (stress-korrelation >>
lugn-korrelation). Helperiodssnittet döljer detta om det inträffar.
HYP-039:s registerpost undersökte ALDRIG detta - bara helperiodssnittet.

Tre oberoende mått, ingen cherry-picking:
  1. Rullande 63-dagars korrelation över hela perioden - fördelning
     (min/max/percentiler), ingen förvald "stress-period".
  2. MEKANISKT definierad stress-regim: dagar där SPY:s eget 20-dagars
     trailing-avkastning ligger i sin egen bottenkvintil (5 lika stora
     bins baserat på SPY:s egen fördelning) - definierad av SPY:s
     rörelse, INTE valda i efterhand utifrån kända kriser.
  3. De 5 redan etablerade kris-episoderna i projektet (samma fönster
     som scripts/diagnostic_hyp037_leave_one_crisis_out.py använder som
     trigger-datum, här utvidgade till kalenderfönster runt varje
     episod för att korrelation ska vara meningsfull över fler än en dag)
     - rapporterade för jämförbarhet med tidigare diagnostik, inte som
     huvudmåttet (då de VALDES utifrån kända kriser, till skillnad från 1-2).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
STRATEGIES_ROOT = REPO_ROOT / "strategies"
HYP037_RESULTS = STRATEGIES_ROOT / "HYP-037" / "results"

sys.path.insert(0, str(STRATEGIES_ROOT / "HYP-039"))
import backtest as hyp039  # noqa: E402

CRISIS_WINDOWS = {
    "2011 (skuldtakskrisen)": ("2011-07-01", "2011-10-04"),
    "2015 (Black Monday)": ("2015-08-17", "2015-08-28"),
    "2018 (julafton-massakern)": ("2018-12-01", "2018-12-26"),
    "2020 (covid)": ("2020-02-19", "2020-04-30"),
    "2022 (björnmarknad)": ("2022-01-03", "2022-10-13"),
}

ROLLING_WINDOW = 63  # ~1 handelskvartal, samma storleksordning som ombalanseringsfrekvensen


def load_returns(level: int) -> pd.DataFrame:
    hyp037_pv = pd.read_csv(HYP037_RESULTS / f"portfolio_value_{level}.csv", index_col=0, parse_dates=True)["portfolio_value"]
    spy_price = hyp039.load_spy_prices()
    df = pd.concat([spy_price.rename("spy"), hyp037_pv.rename("hyp037")], axis=1, join="inner").dropna()
    ret = pd.DataFrame({
        "spy_ret": df["spy"].pct_change(),
        "hyp037_ret": df["hyp037"].pct_change(),
    }).dropna()
    return ret


def main():
    level = 100_000  # avgörande nivå, se registerposten
    ret = load_returns(level)

    full_corr = ret["spy_ret"].corr(ret["hyp037_ret"])
    print("=" * 90)
    print(f"HELPERIODSKORRELATION (2011-2024, ${level:,.0f}-nivå): {full_corr:+.4f}")
    print("(sanity-check mot registrets redan kända -0.003 - beräknad på samma serier)")
    print("=" * 90)

    # ── 1. Rullande korrelation, ingen förvald period ──
    roll_corr = ret["spy_ret"].rolling(ROLLING_WINDOW).corr(ret["hyp037_ret"]).dropna()
    print(f"\n--- 1. RULLANDE {ROLLING_WINDOW}-DAGARS KORRELATION (hela perioden, ingen cherry-picking) ---")
    print(f"  Min:            {roll_corr.min():+.3f}  (datum: {roll_corr.idxmin().date()})")
    print(f"  Max:            {roll_corr.max():+.3f}  (datum: {roll_corr.idxmax().date()})")
    print(f"  Median:         {roll_corr.median():+.3f}")
    print(f"  5:e percentil:  {roll_corr.quantile(0.05):+.3f}")
    print(f"  95:e percentil: {roll_corr.quantile(0.95):+.3f}")
    print(f"  Andel dagar med rullande korr > 0.3:  {(roll_corr > 0.3).mean():.1%}")
    print(f"  Andel dagar med rullande korr > 0.5:  {(roll_corr > 0.5).mean():.1%}")

    # ── 2. Mekanisk stress-regim: SPY:s egen 20d trailing-avkastning, bottenkvintil ──
    spy_20d = ret["spy_ret"].rolling(20).sum()
    quintile = pd.qcut(spy_20d.dropna(), 5, labels=False)  # 0 = sämsta kvintilen
    aligned = ret.loc[quintile.index]

    print("\n--- 2. KORRELATION BETINGAD PÅ SPY:s EGEN 20-DAGARS TRAILING-AVKASTNING (kvintiler, 0=sämst) ---")
    for q in range(5):
        mask = quintile == q
        n = mask.sum()
        c = aligned.loc[mask, "spy_ret"].corr(aligned.loc[mask, "hyp037_ret"])
        tag = "  <- STRESS (sämsta 20%)" if q == 0 else ("  <- BÄSTA 20%" if q == 4 else "")
        print(f"  Kvintil {q}  (n={n:>4} dagar):  korr = {c:+.4f}{tag}")

    # ── 3. Etablerade kris-episoder (jämförbarhet med tidigare diagnostik) ──
    print("\n--- 3. KÄNDA KRIS-EPISODER (fönster runt de 5 redan etablerade episoderna) ---")
    for name, (start, end) in CRISIS_WINDOWS.items():
        window = ret.loc[start:end]
        if len(window) < 5:
            print(f"  {name:<28} n={len(window)} dagar - för få datapunkter för meningsfull korrelation, hoppar över")
            continue
        c = window["spy_ret"].corr(window["hyp037_ret"])
        spy_ret_window = float((1 + window["spy_ret"]).prod() - 1)
        print(f"  {name:<28} n={len(window):>3} dagar  korr={c:+.4f}  SPY-avkastning i fönstret={spy_ret_window:+.1%}")

    print("\n" + "=" * 90)
    print("SLUTSATS (diagnostik, ändrar INGET i registret):")
    print("Om stress-korrelationerna ovan (mått 2 kvintil 0, och mått 3) ligger klart över")
    print("helperiodssnittet och/eller den rullande maxen är hög under just dessa perioder,")
    print("är det ett tecken på att diversifieringen är svagare precis när den behövs mest -")
    print("relevant kontext för HYP-039:s redan PASSADE MaxDD-villkor, men ändrar inte")
    print("det låsta resultatet. Ingen ny K-kostnad, inget nytt pass/fail-villkor.")
    print("=" * 90)


if __name__ == "__main__":
    sys.exit(main() or 0)
