"""
Pipeline-sanity-check för EODHD-adaptern. INTE en riktig körning mot
HYP-008 - bekräftar bara att nyckel, anslutning och avlistad-data
faktiskt fungerar.

Vald ticker: SHLDQ.US (Sears Holdings efter konkursen 2018) - ett
välkänt, redan avlistat bolag vars börsvärde hade fallit kraftigt vid
delistningen. Detta skript verifierar ENDAST att data kommer tillbaka
för en avlistad ticker, inte att just detta bolags historiska
börsvärde vid varje tidpunkt låg i HYP-008:s $100M-$2B-intervall.

Skriver ALDRIG ut API-nyckeln.
"""

import sys

from eodhd_adapter import EODHDError, get_daily_ohlcv, get_us_tickers

TEST_TICKER = "SHLDQ"  # bare code - adaptern lägger till .US internt
TEST_START = "2018-01-01"
TEST_END = "2018-12-31"


def main() -> int:
    print(f"--- EODHD pipeline-sanity-check ---")
    print(f"Ticker: {TEST_TICKER}  Period: {TEST_START} till {TEST_END}\n")

    try:
        print("1) Kontrollerar att avlistade tickers går att hämta (delisted=1)...")
        tickers = get_us_tickers(include_delisted=True)
        print(f"   OK: {len(tickers)} US common-stock-tickers hämtade.\n")
    except EODHDError as exc:
        print(f"   MISSLYCKADES: {exc}", file=sys.stderr)
        return 1

    try:
        print(f"2) Hämtar daglig OHLCV för {TEST_TICKER}...")
        rows = get_daily_ohlcv(TEST_TICKER, TEST_START, TEST_END)
    except EODHDError as exc:
        print(f"   MISSLYCKADES: {exc}", file=sys.stderr)
        print(
            "   Om felet beror på att exakt tickersymbolen inte finns i "
            "EODHD:s databas: sök upp rätt symbol för Sears Holdings "
            "post-konkurs i deras tickerlista och uppdatera TEST_TICKER.",
            file=sys.stderr,
        )
        return 1

    if not rows:
        print("   MISSLYCKADES: tomt svar, inga rader kom tillbaka.", file=sys.stderr)
        return 1

    print(f"   OK: {len(rows)} dagliga rader kom tillbaka.")
    print(f"   Första raden: {rows[0]}")
    print(f"   Sista raden:  {rows[-1]}")
    print("\n--- Sanity-check klar: EODHD-pipelinen (inkl. avlistad data) fungerar. ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
