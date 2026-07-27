"""
Sanity-check av corwin_schultz_spread() mot riktig prisdata för några
kända, likvida large-cap-tickers. INTE en riktig körning mot HYP-008 -
bara ett sätt för CEO att bedöma om skattningarna ser rimliga ut (några
tiondels procent för stora likvida bolag) innan samma funktion används
på small-cap.

Datakälla: yfinance (gratis, ingen kvotpåverkan på EODHD) - samma källa
som redan används av /reference_code/v6_core_large_cap.py. Hämtas i
minnet för detta test, sparas inte till disk.
"""

import sys

import numpy as np
import yfinance as yf

from friction import corwin_schultz_spread

TICKERS = ["AAPL", "MSFT", "JNJ"]
PERIOD = "1y"


def main() -> int:
    print("--- Corwin-Schultz sanity-check mot riktig large-cap-data ---")
    print(f"Tickers: {', '.join(TICKERS)}  Period: {PERIOD} (yfinance)\n")

    for ticker in TICKERS:
        data = yf.download(ticker, period=PERIOD, auto_adjust=True, progress=False)
        if data.empty:
            print(f"{ticker}: MISSLYCKADES - tomt svar från yfinance\n")
            continue

        high = data["High"].to_numpy().flatten()
        low = data["Low"].to_numpy().flatten()

        spread = corwin_schultz_spread(high, low)
        valid = spread[~np.isnan(spread)]

        if len(valid) == 0:
            print(f"{ticker}: inga giltiga spread-skattningar kunde beräknas\n")
            continue

        print(f"{ticker} ({len(data)} handelsdagar):")
        print(f"  Medel spread:   {valid.mean() * 100:.3f}%")
        print(f"  Median spread:  {np.median(valid) * 100:.3f}%")
        print(f"  Min / Max:      {valid.min() * 100:.3f}% / {valid.max() * 100:.3f}%")
        print(f"  Andel dagar med spread = 0 (clippad): {(valid == 0).mean() * 100:.1f}%")
        print()

    print(
        "Referens att bedöma mot: stora likvida large-cap-aktier brukar "
        "enligt litteraturen (inkl. Corwin & Schultz egen artikel) hamna "
        "runt några tiondels procent i genomsnittlig skattad spread. "
        "Small-cap-bolag förväntas ge klart högre och mer varierande "
        "skattningar - det är i sig ett rimlighetstest när samma funktion "
        "senare körs på HYP-008:s universum."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
