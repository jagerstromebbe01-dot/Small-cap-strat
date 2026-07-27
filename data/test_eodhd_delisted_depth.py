"""
Undersöker hur långt bak i tiden EODHD:s NUVARANDE (free-tier) nyckel
faktiskt ger historik för REDAN AVLISTADE bolag, specifikt från
2012-2015-perioden. Detta är en separat fråga från den generella
"1 års historik"-begränsningen som redan bekräftats för AKTIVA tickers
(se data/test_eodhd_connection.py och tidigare session-fynd mot AAPL) -
avlistad data skulle KUNNA vara arkiverad separat i EODHD:s system,
så det testas explicit här istället för att antas.

INTE en riktig körning mot HYP-008 - avgör bara om nuvarande nyckel
räcker för djupet, eller om en uppgradering (All-World) krävs innan
small-cap-backtesten kan köras med rätt historik.

Valda exempel (välkända, verifierbart avlistade bolag runt 2012-2015):
  - RadioShack (Chapter 11 feb 2015) - provar "RSH" och "RSHCQ"
    (bolag byter ofta till en Q-suffixad OTC-ticker efter konkursansökan,
    se SHLDQ-exemplet i test_eodhd_connection.py)
  - Eastman Kodak (avlistad från NYSE jan 2012 under Chapter 11,
    återlistades senare 2013 under en NY ticker KODK - den gamla
    identiteten testas här) - provar "EK"
  - Patriot Coal (Chapter 11 juli 2012) - provar "PCX" och "PCXCQ"

Exakt vilken symbolvariant EODHD faktiskt använder är INTE känt i förväg
- därför testas flera varianter per bolag, och skriptet rapporterar
tydligt vad som faktiskt fungerade snarare än att anta en symbol.
"""

import sys

from eodhd_adapter import EODHDError, get_daily_ohlcv

CANDIDATES = {
    "RadioShack (Chapter 11, feb 2015)": ["RSH", "RSHCQ"],
    "Eastman Kodak (delistad NYSE, jan 2012)": ["EK"],
    "Patriot Coal (Chapter 11, juli 2012)": ["PCX", "PCXCQ"],
}

TEST_START = "2010-01-01"
TEST_END = "2015-12-31"


def main() -> int:
    print("--- EODHD: djuptest för avlistad small/mid-cap-historik ---")
    print(f"Period som efterfrågas: {TEST_START} till {TEST_END}\n")

    any_real_data = False

    for company, tickers in CANDIDATES.items():
        print(f"## {company}")
        for ticker in tickers:
            try:
                rows = get_daily_ohlcv(ticker, TEST_START, TEST_END)
            except EODHDError as exc:
                print(f"  {ticker}: MISSLYCKADES - {exc}")
                continue

            if not rows:
                print(f"  {ticker}: tomt svar (ingen data alls)")
                continue

            dates = [r["date"] for r in rows if r.get("date")]
            if not dates:
                print(f"  {ticker}: fick {len(rows)} rader men utan datum - oväntat format")
                continue

            any_real_data = True
            print(
                f"  {ticker}: OK - {len(rows)} rader, "
                f"{min(dates)} till {max(dates)}"
            )
        print()

    print("--- Slutsats ---")
    if any_real_data:
        print(
            "Minst en avlistad ticker gav riktig historik på nuvarande "
            "nyckel - se datumintervallen ovan för hur långt bak "
            "täckningen faktiskt sträcker sig."
        )
    else:
        print(
            "INGEN av testtickers gav riktig historisk data på nuvarande "
            "nyckel - samma ~1-års-begränsning som redan sågs för aktiva "
            "tickers (t.ex. AAPL 2020) gäller sannolikt även avlistad data. "
            "En uppgradering till EODHD All-World (eller motsvarande) är "
            "sannolikt nödvändig innan HYP-008 kan köras mot 2010-2024."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
