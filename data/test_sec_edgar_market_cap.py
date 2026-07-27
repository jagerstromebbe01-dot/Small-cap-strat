"""
Bevisar att SEC EDGAR (utestående aktier) + EODHD (pris) tillsammans kan
räkna ut ett rimligt, tidsriktigt börsvärde - för fyra kända bolag, ett
aktivt (AAPL) och tre redan avlistade (RadioShack, Eastman Kodak,
Patriot Coal), vid en specifik historisk tidpunkt nära respektive
bolags konkurs/avlistning.

INTE en riktig körning mot HYP-008 - en konceptbekräftelse innan
matchningen eventuellt skalas upp till hela small-cap-universumet.
"""

import sys
from datetime import datetime, timedelta

from eodhd_adapter import get_daily_ohlcv
from sec_edgar_adapter import (
    find_cik_candidates,
    get_shares_outstanding_history,
    load_cik_lookup,
    market_cap_at_date,
)

# (bolagsnamn att söka i SEC:s lookup, EODHD-ticker, datum att räkna börsvärde vid)
CASES = [
    ("Apple Inc", "AAPL", "2026-06-15"),
    ("RadioShack Corp", "RSH", "2014-06-30"),
    ("Eastman Kodak Co", "EK", "2011-06-30"),
    ("Patriot Coal Corp", "PCX", "2012-03-30"),
]


def closest_close_price(ticker: str, target_date: str):
    """Hämtar close-pris nära target_date (+/- 7 dagar, för att hantera
    helger/handelsfria dagar), väljer den handelsdag som ligger närmast."""
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    start = (dt - timedelta(days=7)).strftime("%Y-%m-%d")
    end = (dt + timedelta(days=7)).strftime("%Y-%m-%d")
    rows = get_daily_ohlcv(ticker, start, end)
    rows = [r for r in rows if r.get("close") is not None]
    if not rows:
        return None, None
    closest = min(rows, key=lambda r: abs(datetime.strptime(r["date"], "%Y-%m-%d") - dt))
    return closest["date"], closest["close"]


def main() -> int:
    print("--- SEC EDGAR + EODHD: börsvärde vid historisk tidpunkt ---\n")
    print("Laddar SEC:s CIK-lookup (cachas lokalt efter första körningen)...")
    lookup = load_cik_lookup()
    print(f"  {sum(len(v) for v in lookup.values())} bolagsposter laddade.\n")

    for company_name, ticker, target_date in CASES:
        print(f"## {company_name} ({ticker}), börsvärde ~{target_date}")

        candidates = find_cik_candidates(company_name, lookup)
        if not candidates:
            print("  Ingen CIK-kandidat hittad i SEC-lookupen.\n")
            continue
        if len(candidates) > 1:
            print(f"  {len(candidates)} kandidater hittade, använder första: {candidates[0]}")
        raw_name, cik = candidates[0]
        print(f"  CIK: {cik} ({raw_name})")

        history = get_shares_outstanding_history(cik)
        if not history:
            print("  Ingen aktiehistorik hittad i SEC companyfacts.\n")
            continue
        print(f"  {len(history)} rapporterade aktieantal, {history[0]['date']} till {history[-1]['date']}")

        price_date, price = closest_close_price(ticker, target_date)
        if price is None:
            print("  Inget pris hittat i EODHD nära måldatumet.\n")
            continue
        print(f"  EODHD close: {price} ({price_date})")

        cap = market_cap_at_date(history, price, target_date)
        if cap is None:
            print("  Kunde inte räkna ut börsvärde (saknar data).\n")
            continue
        print(f"  -> Uppskattat börsvärde: ${cap:,.0f}\n")

    print(
        "Bedöm rimligheten: AAPL ska ligga i biljon-dollar-intervallet. "
        "RadioShack/Eastman Kodak/Patriot Coal nära sina respektive "
        "konkurser förväntas ligga i small-cap/micro-cap-intervallet "
        "(betydligt under $2B, sannolikt under $100M för flera av dem "
        "vid just dessa datum - konkursnära bolag har ofta redan fallit "
        "under small-cap-golvet, vilket i så fall är ett korrekt resultat, "
        "inte ett fel)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
