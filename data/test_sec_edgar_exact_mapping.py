"""
Sanity-check, STEG 1: exakt ticker<->CIK-mappning via SEC:s
company_tickers.json (INGEN fuzzy-matchning) plus SEC:s XBRL "frames"-
API för utestående aktier - som en HELT SEPARAT väg från
sec_edgar_adapter.py:s fuzzy-matchning mot cik-lookup-data.txt (den
filen/koden rörs inte här, se den modulens egen docstring för det
tidigare, mer osäkra spåret).

Rör INTE eodhd_adapter.py eller cachad EODHD-data - importerar bara
get_daily_ohlcv() för att läsa pris, gör inga fler EODHD-anrop än de
5 som krävs för detta test (ingen cache fanns sedan innan, se
data/cache/ - bara SEC-lookupen låg där).

INTE en riktig körning mot HYP-008. Rör inte HYP-008-filen eller
validate_hypothesis.py.
"""

import sys

import requests

from eodhd_adapter import get_daily_ohlcv

USER_AGENT = "Kebbe Research jagerstromebbe01@gmail.com"
HEADERS = {"User-Agent": USER_AGENT}

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FRAMES_URL = (
    "https://data.sec.gov/api/xbrl/frames/us-gaap/"
    "CommonStockSharesOutstanding/shares/CY2015Q4I.json"
)

TARGET_DATE = "2015-12-31"

# RSH/EK: company_tickers.json täcker bara AKTIVA bolag (se steg 2 nedan
# där det bekräftas). CIK för dessa två är redan KÄNDA från tidigare,
# separat verifierat arbete denna session mot SEC:s fullständiga
# cik-lookup-data.txt (inte en gissning): RadioShack Corp -> 96289,
# Eastman Kodak Co -> 31235. Används här bara för att testa
# frames+market-cap-steget, inte för att lösa matchnings-problemet igen.
KNOWN_DELISTED_CIKS = {
    "RSH": ("RadioShack Corp", 96289),
    "EK": ("Eastman Kodak Co", 31235),
}


def fetch_company_tickers() -> dict:
    resp = requests.get(COMPANY_TICKERS_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return {v["ticker"]: v["cik_str"] for v in data.values()}


def fetch_frames_shares_outstanding() -> dict:
    """Ett enda anrop hämtar utestående aktier för ALLA bolag som
    rapporterade konceptet för CY2015Q4I - returnerar dict CIK -> val."""
    resp = requests.get(FRAMES_URL, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return {row["cik"]: row for row in data.get("data", [])}


def closest_price(ticker: str, target_date: str):
    from datetime import datetime, timedelta
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    start = (dt - timedelta(days=10)).strftime("%Y-%m-%d")
    end = (dt + timedelta(days=10)).strftime("%Y-%m-%d")
    rows = [r for r in get_daily_ohlcv(ticker, start, end) if r.get("close") is not None]
    if not rows:
        return None, None
    closest = min(rows, key=lambda r: abs(datetime.strptime(r["date"], "%Y-%m-%d") - dt))
    return closest["date"], closest["close"]


def main() -> int:
    print(f"User-Agent som används mot sec.gov: {USER_AGENT}\n")

    print("--- Steg 2a: exakt ticker->CIK via company_tickers.json (aktiva bolag) ---")
    ticker_to_cik = fetch_company_tickers()
    print(f"{len(ticker_to_cik)} tickers laddade.\n")

    active_tickers = ["AAPL", "JNJ", "BBW"]  # BBW = Build-A-Bear Workshop, vald mellanstor small-cap
    resolved = {}
    for t in active_tickers:
        cik = ticker_to_cik.get(t)
        print(f"  {t}: {'CIK ' + str(cik) if cik else 'SAKNAS i company_tickers.json'}")
        if cik:
            resolved[t] = cik
    print()

    print("--- Steg 2b: undersöker om AVLISTADE bolag finns i company_tickers.json ---")
    for t in ["RSH", "EK"]:
        cik = ticker_to_cik.get(t)
        print(f"  {t}: {'CIK ' + str(cik) + ' (oväntat - fanns trots allt)' if cik else 'SAKNAS - bekräftat, company_tickers.json täcker bara aktiva bolag'}")
    print(
        "\n  Konsekvens: för avlistade bolag krävs ett annat SEC-underlag. Detta test\n"
        "  använder redan verifierade CIK-nummer (RSH=96289, EK=31235) från tidigare\n"
        "  arbete mot SEC:s fullständiga cik-lookup-data.txt (se sec_edgar_adapter.py),\n"
        "  INTE en ny gissning.\n"
    )
    for t, (name, cik) in KNOWN_DELISTED_CIKS.items():
        resolved[t] = cik

    print("--- Steg 3: utestående aktier via XBRL frames-API (CY2015Q4I), ETT anrop ---")
    frames = fetch_frames_shares_outstanding()
    print(f"{len(frames)} bolag rapporterade konceptet för detta kvartal.\n")

    print("--- Steg 4: börsvärde = aktier (frames) x pris (EODHD, live-anrop) ---\n")
    known_approx = {
        "AAPL": "~$625 miljarder (dec 2015, allmänt känt ungefärligt värde)",
        "JNJ": "~$275 miljarder (dec 2015, allmänt känt ungefärligt värde)",
    }
    for t in ["AAPL", "JNJ", "BBW", "RSH", "EK"]:
        cik = resolved.get(t)
        if cik is None:
            print(f"{t}: ingen CIK, hoppar över\n")
            continue

        frame_row = frames.get(cik)
        if frame_row is None:
            print(f"{t} (CIK {cik}): fanns inte i frames-svaret för CY2015Q4I\n")
            continue
        shares = frame_row["val"]

        price_date, price = closest_price(t, TARGET_DATE)
        if price is None:
            print(f"{t} (CIK {cik}): {shares:,} aktier, men inget EODHD-pris hittades nära {TARGET_DATE}\n")
            continue

        market_cap = shares * price
        print(f"{t} (CIK {cik}):")
        print(f"  Utestående aktier (frames, {frame_row.get('end')}): {shares:,}")
        print(f"  EODHD close: {price} ({price_date})")
        print(f"  -> Beräknat börsvärde: ${market_cap:,.0f}")
        if t in known_approx:
            print(f"  Referens att jämföra mot: {known_approx[t]}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
