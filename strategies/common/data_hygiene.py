"""
Delad datasanering for prismatriser - upptackt 2026-07-29 vid HYP-012/013.

Ägs inte av nagon enskild hypotes - detta ar en STRUKTURELL brist i
rå-cachen (data/cache/ohlcv/), inte nagot specifikt for en strategi.
En bred kontroll av hela cachen (9017 tickers) visade:
  - 1010 filer (11%) har minst en rad med close/high/low <= 0
  - 3070 filer (34%) har minst en enskild dag med >500% prisrorelse,
    inklusive orimligheter som en 135 769x-rorelse pa en dag och
    oandliga varden (division med en tidigare nollrad)

HYP-008/009/011 (par-baserade, valjer bara ett fatal narmast-korrelerade
kandidater per manad) rakade undvika att detta fick storre effekt.
HYP-012 (momentum, rankar HELA universumet) och HYP-013 (reversal,
rankar HELA universumet) exponerades direkt - HYP-012 fick ett
portfoljvarde som gick negativt (degenererad beta pa en tunt handlad
ticker), HYP-013 kraschade med ZeroDivisionError (ett pris exakt 0.0).

Detta ar INTE reverse-engineered fran nagot backtest-resultat - troskeln
(±80% enskild dag) ar vald for att den ar ekonomiskt orimlig for en
riktig handelsdag (en aktie kan definitionsmassigt inte tappa mer an
100% pa en dag; en genuin >5x-uppgang pa en enda dag ar extremt sallsynt
och nastan alltid en data-artefakt - trasig split-justering, dubblerad
rad, eller liknande - inte en riktig kursrorelse) snarare an nagot
kalibrerat mot en specifik strategis resultat.
"""

import numpy as np
import pandas as pd

MIN_DAILY_RETURN = -0.80   # en dag kan aldrig ge mer an -100%, men redan -80% pa EN dag ar extremt ovanligt for riktig handel
MAX_DAILY_RETURN = 5.00    # +500% pa en enda dag - nastan alltid en data-artefakt, inte en riktig rorelse


def clean_price_matrix(close: pd.DataFrame, high: pd.DataFrame = None, low: pd.DataFrame = None):
    """
    Rensar en (eller flera, om high/low ges) prismatris:
      1. close/high/low <= 0 -> NaN (ogiltigt pris, inte en riktig handelsdag)
      2. Dagar dar close/close.shift(1) implicerar en avkastning utanfor
         [MIN_DAILY_RETURN, MAX_DAILY_RETURN] -> close (och high/low samma
         dag) satts till NaN. Detta bryter EN dags falska datapunkt utan
         att kasta bort resten av tickerns historik - nasta giltiga dag
         rknar avkastning mot senaste GILTIGA close (pandas pct_change
         hoppar over NaN naturligt).
      3. Appliceras iterativt (tva pass) eftersom en enskild trasig rad
         annars kan ge TVA falska extremrorelser (en in, en ut ur den
         trasiga raden) - andra passet fangar det som blir kvar efter
         forsta passets NaN-sattning.

    Returnerar samma antal DataFrames som gavs in (1-3 stycken).
    """
    close = close.copy()
    if high is not None:
        high = high.copy()
    if low is not None:
        low = low.copy()

    close = close.where(close > 0)
    if high is not None:
        high = high.where(high > 0)
    if low is not None:
        low = low.where(low > 0)

    for _pass in range(2):
        ret = close.pct_change()
        bad = (ret < MIN_DAILY_RETURN) | (ret > MAX_DAILY_RETURN)
        if not bad.values.any():
            break
        close = close.mask(bad)
        if high is not None:
            high = high.mask(bad)
        if low is not None:
            low = low.mask(bad)

    results = [close]
    if high is not None:
        results.append(high)
    if low is not None:
        results.append(low)
    return tuple(results) if len(results) > 1 else results[0]


if __name__ == "__main__":
    # Sanity-check med SYNTETISK data.
    dates = pd.date_range("2020-01-01", periods=10)
    df = pd.DataFrame({
        "A": [10, 10.1, 0.0, 10.3, 10.2, 10.4, 10.5, 10.3, 10.6, 10.7],  # en trasig nollrad
        "B": [5, 5.1, 5.2, 700.0, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8],          # en orimlig spike
    }, index=dates)
    print("Fore:")
    print(df)
    cleaned = clean_price_matrix(df)
    print("\nEfter:")
    print(cleaned)
    print("\nFörvantat: A-radens 0.0 -> NaN, B-radens 700.0 -> NaN, allt annat orort.")
