"""
Pappershandel-forberedelse, andra forsoket (2026-07-31): den frusna
december 2024-listan visade sig ha 83% av sina 222 tickers utan handel
pa >120 dagar (bekraftat mot EODHD direkt - inte ett cache-fel, riktig
avnotering/tystnad). En "frusen lista, uppdatera bara priser"-genvag
racker alltsa INTE for ett meningsfullt nulage.

DENNA VERSION bygger om det AKTUELLA ($100M-$2B) universumet istallet
for att bara aterananvanda december 2024:s medlemskap:

1. Utgar fran ALLA tickers vars marknadsvarde i december 2024 (redan
   cachat i data/cache/market_cap_by_ticker_month.csv) lag inom ett
   BRETT buffertband ($20M-$10B) runt malbandet - motiveringen ar att
   ett bolag i praktiken aldrig hoppar fran langt utanfor $100M-$2B till
   innanfor det pa 19 manader, sa detta fangar praktiskt taget alla
   rimliga kandidater utan att behova skanna om HELA det ursprungliga
   ~32 000-tickers-universumet.
2. For varje kandidat: hamtar SENASTE utestaende aktieantal via SEC
   EDGAR companyfacts (samma redan byggda infrastruktur som
   build_smallcap_classification.py anvande, sekventiell, redan
   hastighetsbegransad i sec_edgar_adapter.py).
3. Uppdaterar/aterananvander aktuella priser (samma monster som
   data/update_ohlcv_current.py).
4. Berknar AKTUELLT marknadsvarde = senaste aktieantal * senaste pris,
   filtrerar till $100M-$2B.

Output: data/cache/current_universe.json - {"as_of": "...",
"tickers": [...], "excluded_stale_price": [...], "excluded_no_shares": [...],
"excluded_out_of_band": [...]} - HALLS SEPARAT fran
smallcap_universe_by_month.json (den filen ar backtestens grundsanning,
rors ALDRIG av detta skript).
"""

import csv
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from eodhd_adapter import get_daily_ohlcv
from sec_edgar_adapter import get_shares_outstanding_history

DATA_DIR = Path(__file__).resolve().parent
CACHE_DIR = DATA_DIR / "cache"
CLASSIFICATION_FILE = CACHE_DIR / "smallcap_classification.jsonl"
MARKET_CAP_FILE = CACHE_DIR / "market_cap_by_ticker_month.csv"
OHLCV_DIR = CACHE_DIR / "ohlcv"
OUTPUT_FILE = CACHE_DIR / "current_universe.json"

BUFFER_LOW = 20_000_000
BUFFER_HIGH = 10_000_000_000
BAND_LOW = 100_000_000
BAND_HIGH = 2_000_000_000

TODAY = date.today().isoformat()
STALENESS_LIMIT_DAYS = 60  # pris fran senast inom 60 kalenderdagar accepteras som "aktuellt"

FIELDNAMES = [
    "date", "open", "high", "low", "close", "adjusted_close", "volume",
    "borrow_cost", "borrow_available", "bid_ask_spread",
]


def load_buffer_candidates() -> set:
    candidates = set()
    with MARKET_CAP_FILE.open(encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            if row["month"] != "2024-12-31":
                continue
            mc = row.get("market_cap")
            if not mc:
                continue
            try:
                mc = float(mc)
            except ValueError:
                continue
            if BUFFER_LOW <= mc <= BUFFER_HIGH:
                candidates.add(row["ticker"])
    return candidates


def load_cik_map(tickers: set) -> dict:
    mapping = {}
    with CLASSIFICATION_FILE.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            t = row.get("ticker")
            cik = row.get("cik")
            if t in tickers and cik:
                mapping[t] = cik
    return mapping


def get_current_price(ticker: str):
    """Aterananvander cache om fardan tillrackligt aktuell, annars
    hamtar fram till idag och appendar (samma monster som
    update_ohlcv_current.py)."""
    path = OHLCV_DIR / f"{ticker}.csv"
    last_date = None
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last_date = line.split(",")[0]

    if last_date is None:
        try:
            rows = get_daily_ohlcv(ticker, "2024-06-01", TODAY)
        except Exception:
            return None, None
        if not rows:
            return None, None
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
        last_row = rows[-1]
        # BUGGFIX (kodgranskning 2026-08-05): borsvarde = aktier x PRIS SOM DET
        # FAKTISKT HANDLADES FOR, inte split-/utdelningsjusterat pris - adjusted_close
        # kan missvisa historiskt/aktuellt borsvarde runt en split/storutdelning.
        # build_smallcap_universe.py (huvudserien 2010-2024) anvander redan ra close
        # korrekt av samma skal - denna gren gjorde det inte, nu konsekvent.
        return last_row["date"], last_row["close"]

    start = (date.fromisoformat(last_date) + timedelta(days=1)).isoformat()
    if start <= TODAY:
        try:
            rows = get_daily_ohlcv(ticker, start, TODAY)
        except Exception:
            rows = []
        if rows:
            with path.open("a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                writer.writerows(rows)
            last_date = rows[-1]["date"]
            last_price = rows[-1]["close"]  # buggfix - se ovan, ra close inte adjusted_close
            return last_date, last_price

    # ingen ny rad - las senaste befintliga raden ur filen
    with path.open(encoding="utf-8") as f:
        last_line = None
        for line in f:
            if line.strip():
                last_line = line
    if last_line is None:
        return None, None
    parts = last_line.strip().split(",")
    return parts[0], parts[4]  # date, close (buggfix - se ovan, ra close inte adjusted_close)


def main():
    print(f"Idag: {TODAY}\n")
    print("Laddar kandidater fran december 2024 (brett buffertband $20M-$10B)...")
    candidates = load_buffer_candidates()
    print(f"  {len(candidates)} kandidater.\n")

    print("Slar upp CIK for kandidaterna...")
    ticker_cik = load_cik_map(candidates)
    print(f"  {len(ticker_cik)} av dem har en CIK.\n")

    result_tickers = []
    excluded_no_shares = []
    excluded_stale_price = []
    excluded_out_of_band = []
    excluded_no_cik = sorted(candidates - set(ticker_cik.keys()))

    total = len(ticker_cik)
    for i, (ticker, cik) in enumerate(sorted(ticker_cik.items()), 1):
        if i % 50 == 0 or i == total:
            print(f"  ... {i}/{total}")

        try:
            history = get_shares_outstanding_history(cik)
        except Exception as exc:
            excluded_no_shares.append({"ticker": ticker, "reason": f"SEC-fel: {exc}"})
            continue
        if not history:
            excluded_no_shares.append({"ticker": ticker, "reason": "ingen aktieantal-historik"})
            continue
        latest = history[-1]
        shares = latest["shares"]
        shares_date = latest["date"]

        price_date, price = get_current_price(ticker)
        if price_date is None or price is None:
            excluded_stale_price.append({"ticker": ticker, "reason": "ingen prisdata"})
            continue

        staleness = (date.fromisoformat(TODAY) - date.fromisoformat(price_date)).days
        if staleness > STALENESS_LIMIT_DAYS:
            excluded_stale_price.append({"ticker": ticker, "last_price_date": price_date, "staleness_days": staleness})
            continue

        try:
            market_cap = float(price) * float(shares)
        except (TypeError, ValueError):
            excluded_no_shares.append({"ticker": ticker, "reason": "ogiltigt pris/aktieantal"})
            continue

        if BAND_LOW <= market_cap <= BAND_HIGH:
            result_tickers.append({
                "ticker": ticker, "market_cap": market_cap, "price": float(price),
                "price_date": price_date, "shares": shares, "shares_date": shares_date,
            })
        else:
            excluded_out_of_band.append({"ticker": ticker, "market_cap": market_cap})

    output = {
        "as_of": TODAY,
        "method": "buffer-band rebuild (2024-12-31 market cap $20M-$10B) + current SEC shares + current price",
        "known_limitation": "Fångar INTE bolag som var utanför $20M-$10B-buffertbandet i december 2024 men "
                             "som skulle kunna ha rört sig in i $100M-$2B-bandet sedan dess - bedömt osannolikt "
                             "men inte formellt uteslutet.",
        "band": [BAND_LOW, BAND_HIGH],
        "staleness_limit_days": STALENESS_LIMIT_DAYS,
        "n_in_band": len(result_tickers),
        "tickers": sorted(t["ticker"] for t in result_tickers),
        "details": result_tickers,
        "excluded_no_cik": excluded_no_cik,
        "excluded_no_shares": excluded_no_shares,
        "excluded_stale_price": excluded_stale_price,
        "excluded_out_of_band": excluded_out_of_band,
    }
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nKLART. {len(result_tickers)} tickers i dagens $100M-$2B-band.")
    print(f"  Uteslutna: {len(excluded_no_cik)} utan CIK, {len(excluded_no_shares)} utan aktieantal, "
          f"{len(excluded_stale_price)} inaktuellt pris, {len(excluded_out_of_band)} utanfor bandet.")
    print(f"  Sparat till {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
