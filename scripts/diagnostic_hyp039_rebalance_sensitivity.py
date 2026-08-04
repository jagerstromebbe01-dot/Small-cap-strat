#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes - ingen K-kostnad, rör INTE
research/hypothesis_registry/HYP-039...yaml eller dess sparade resultat):
hur känsligt är HYP-039:s resultat för VAL av ombalanseringsfrekvens?

HYP-039:s låsta kriterium återanvänder HYP-037:s egen redan låsta
kvartalsfrekvens ("QE") - ett medvetet val för att undvika en ny fri
parameter (se registerposten och CLAUDE.md §5b). Detta skript testar
INTE om en annan frekvens ger ett "bättre" facit - det vore precis den
typ av facit-anpassning i efterhand som spec §5b förbjuder, och INGEN
av siffrorna här får användas för att byta låst frekvens utan ett nytt,
explicit CEO-beslut och en ny K-kostnad.

Syftet är enbart att förstå STORLEKSORDNINGEN på känsligheten: är
kvartalsvalet ett resultat som håller ihop över närliggande frekvenser,
eller ett skört val som bara råkar fungera vid exakt "QE"? Om resultaten
sprider sig kraftigt mellan näraliggande frekvenser är det ett tecken på
skörhet värt att känna till, oavsett vilken siffra som råkar vara högst.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
STRATEGIES_ROOT = REPO_ROOT / "strategies"
HYP037_RESULTS = STRATEGIES_ROOT / "HYP-037" / "results"

sys.path.insert(0, str(STRATEGIES_ROOT / "HYP-039"))
sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
import backtest as hyp039  # noqa: E402
from rebalancing import snap_rebalance_dates  # noqa: E402

WEIGHT_SPY = 0.5
WEIGHT_HYP037 = 0.5

FREQUENCIES = [
    ("W-FRI", "Veckovis (fredagar)"),
    ("ME", "Månadsvis"),
    ("QE", "Kvartalsvis (LÅST VAL)"),
    ("2QE", "Halvårsvis"),
    ("YE", "Årsvis"),
    (None, "Aldrig (köp-och-håll från start)"),
]


def combine_with_freq(spy_price: pd.Series, hyp037_pv: pd.Series, freq: str | None,
                       start_capital: float = 1.0) -> pd.Series:
    """Identisk till backtest.py::combine_50_50, men med parametriserad frekvens
    (None = aldrig ombalansera efter start) - enda skillnaden mot det låsta skriptet."""
    df = pd.concat([spy_price.rename("spy"), hyp037_pv.rename("hyp037")], axis=1, join="inner").dropna()
    spy_ret = df["spy"].pct_change()
    hyp_ret = df["hyp037"].pct_change()

    if freq is None:
        rebal_set = set()
    else:
        calendar_dates = df.resample(freq).last().index
        snapped = snap_rebalance_dates(calendar_dates, df.index)
        rebal_set = set(snapped["execution_date"])

    spy_leg = start_capital * WEIGHT_SPY
    hyp_leg = start_capital * WEIGHT_HYP037
    values, dates = [], []

    for i in range(1, len(df)):
        date = df.index[i]
        r_spy = spy_ret.iloc[i]
        r_hyp = hyp_ret.iloc[i]
        if not np.isnan(r_spy):
            spy_leg *= (1 + r_spy)
        if not np.isnan(r_hyp):
            hyp_leg *= (1 + r_hyp)
        total = spy_leg + hyp_leg
        if date in rebal_set:
            spy_leg = total * WEIGHT_SPY
            hyp_leg = total * WEIGHT_HYP037
        values.append(total)
        dates.append(date)

    return pd.Series(values, index=dates)


def n_rebalances(spy_price, hyp037_pv, freq):
    df = pd.concat([spy_price.rename("spy"), hyp037_pv.rename("hyp037")], axis=1, join="inner").dropna()
    if freq is None:
        return 0
    calendar_dates = df.resample(freq).last().index
    snapped = snap_rebalance_dates(calendar_dates, df.index)
    return len(snapped)


def main():
    level = 100_000  # avgörande nivå, se registerposten
    hyp037_pv = pd.read_csv(HYP037_RESULTS / f"portfolio_value_{level}.csv", index_col=0, parse_dates=True)["portfolio_value"]
    spy_price = hyp039.load_spy_prices()

    print("=" * 100)
    print(f"OMBALANSERINGSKÄNSLIGHET, ${level:,.0f}-nivå, 2011-2024 (diagnostik - ändrar inget låst)")
    print("=" * 100)
    print(f"{'Frekvens':<32}{'#ombalanseringar':<18}{'Sharpe':<10}{'MaxDD':<10}{'CAGR':<10}{'Calmar':<10}")
    print("-" * 100)

    results = []
    for freq, label in FREQUENCIES:
        combined = combine_with_freq(spy_price, hyp037_pv, freq)
        sh = hyp039.sharpe(combined)
        dd = hyp039.max_drawdown(combined)
        cg = hyp039.cagr(combined)
        cal = hyp039.calmar(combined)
        n = n_rebalances(spy_price, hyp037_pv, freq)
        results.append((label, freq, n, sh, dd, cg, cal))
        print(f"{label:<32}{n:<18}{sh:<10.3f}{dd:<10.2%}{cg:<10.2%}{cal:<10.3f}")

    sharpes = [r[3] for r in results]
    print("-" * 100)
    print(f"\nSharpe-spridning över alla testade frekvenser: {min(sharpes):.3f} - {max(sharpes):.3f} "
          f"(spann {max(sharpes) - min(sharpes):.3f})")
    locked = next(r for r in results if r[1] == "QE")
    print(f"Låst val (kvartalsvis): Sharpe={locked[3]:.3f} - "
          f"{'är HÖGST' if locked[3] == max(sharpes) else 'är INTE högst'} av de testade frekvenserna.")

    print("\n" + "=" * 90)
    print("VIKTIGT: detta är enbart en känslighetsanalys, INTE ett förslag att byta frekvens.")
    print("Att välja en annan frekvens här för att den råkar visa högre Sharpe vore exakt den")
    print("typ av facit-anpassning i efterhand spec §5b förbjuder. Kvartalsvis förblir det")
    print("låsta valet i HYP-039:s registerpost tills ett nytt, explicit CEO-beslut fattas -")
    print("och ett sådant beslut skulle i så fall utgöra en NY hypotes med egen K-kostnad,")
    print("inte en ändring av denna redan passerade.")
    print("=" * 90)


if __name__ == "__main__":
    sys.exit(main() or 0)
