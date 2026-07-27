"""
STEG 2 (CEO-plan 2026-07-27): bygger det TIDSRIKTIGA small-cap-
universumet för HYP-008 - vilka bolag som ligger i $100M-$2B-
intervallet vid varje månadsskifte 2010-2024 (ett bolag kan gå in/ut
ur intervallet över tid, hanteras explicit, inte en statisk lista).

Börsvärde = utestående aktier (SEC, senast kända VID varje månadsskifte,
look-ahead-fritt) x pris (EODHD, cachad lokalt i data/cache/ohlcv/).
Ingen ny hämtning - all indata är redan cachad från tidigare steg.

Rebalanseringsfrekvens: månadsvis, samma mönster som
identify_pairs() i reference_code/v6_core_large_cap.py
(prices.resample('M').last()) - för metodologisk konsekvens med
v6-kärnan som Coder ska återanvända.

Output:
- data/cache/smallcap_universe_by_month.json: {månad: [tickers]}
- data/cache/market_cap_by_ticker_month.csv: full tabell (för granskning/
  felsökning) - ticker, month, shares, price, market_cap, in_band
"""

import json
import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent
CACHE_DIR = DATA_DIR / "cache"
CLASSIFICATION_FILE = CACHE_DIR / "smallcap_classification.jsonl"
OHLCV_DIR = CACHE_DIR / "ohlcv"

UNIVERSE_OUTPUT = CACHE_DIR / "smallcap_universe_by_month.json"
MARKET_CAP_TABLE_OUTPUT = CACHE_DIR / "market_cap_by_ticker_month.csv"

MIN_CAP = 100_000_000
MAX_CAP = 2_000_000_000

START = "2010-01-01"
END = "2024-12-31"


def load_shares_histories() -> dict:
    histories = {}
    with CLASSIFICATION_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("status") == "ok" and rec.get("shares_outstanding_history"):
                histories[rec["ticker"]] = rec["shares_outstanding_history"]
    return histories


def month_end_dates() -> pd.DatetimeIndex:
    return pd.date_range(start=START, end=END, freq="ME")


def market_cap_series_for_ticker(ticker: str, shares_history: list, month_ends: pd.DatetimeIndex):
    """
    Returnerar en DataFrame med en rad per månadsskifte: date, shares,
    price, market_cap - eller None om ingen prisdata finns cachad för
    tickern.

    Look-ahead-fritt: shares tas från senast KÄNDA rapporten PÅ ELLER
    FÖRE månadsskiftet (merge_asof direction='backward'), aldrig en
    senare rapport. Pris är senaste handelsdagens close PÅ ELLER FÖRE
    månadsskiftet (samma logik, samma skäl).
    """
    csv_path = OHLCV_DIR / f"{ticker}.csv"
    if not csv_path.exists():
        return None

    prices = pd.read_csv(csv_path, parse_dates=["date"])
    prices = prices.dropna(subset=["date", "close"]).sort_values("date")
    if prices.empty:
        return None

    shares_df = pd.DataFrame(shares_history)
    shares_df["date"] = pd.to_datetime(shares_df["date"])
    shares_df = shares_df.sort_values("date")

    month_df = pd.DataFrame({"date": month_ends})

    # Pris: senaste handelsdagens close PÅ ELLER FÖRE varje månadsskifte.
    # TOLERANCE ÄR KRITISK: utan den skulle ett bolags SISTA pris innan
    # avlistning (t.ex. AACC, sista handelsdag 2013-06-13) tyst "leva
    # vidare" som om det vore aktuellt pris för långt senare månader
    # (t.ex. 2021-12-31) - upptäckt vid testning av backtest.py
    # 2026-07-27. 10 dagars tolerans - bortom det räknas ingen prisdata
    # som "aktuell" för det månadsskiftet.
    price_asof = pd.merge_asof(
        month_df, prices[["date", "close"]], on="date", direction="backward",
        tolerance=pd.Timedelta(days=10),
    )

    # Aktier: senast rapporterade PÅ ELLER FÖRE varje månadsskifte. Bolag
    # rapporterar kvartalsvis - 120 dagars tolerans (dryga kvartalet)
    # täcker normal rapporteringstakt utan att låta ett flera år gammalt
    # aktieantal räknas som aktuellt.
    combined = pd.merge_asof(
        price_asof, shares_df[["date", "shares"]], on="date", direction="backward",
        tolerance=pd.Timedelta(days=120),
    )

    combined["market_cap"] = combined["shares"] * combined["close"]
    combined["ticker"] = ticker
    return combined


def main() -> int:
    print("Laddar aktieantal-historik (redan cachad, SEC)...")
    shares_histories = load_shares_histories()
    print(f"  {len(shares_histories)} tickers med aktieantal.\n")

    month_ends = month_end_dates()
    print(f"Månadsskiften: {len(month_ends)} ({month_ends[0].date()} till {month_ends[-1].date()})\n")

    print("Beräknar börsvärde per ticker per månad...")
    all_frames = []
    no_price_count = 0
    processed = 0

    for ticker, hist in shares_histories.items():
        df = market_cap_series_for_ticker(ticker, hist, month_ends)
        processed += 1
        if df is None:
            no_price_count += 1
            continue
        all_frames.append(df)

        if processed % 1000 == 0:
            print(f"  ... {processed}/{len(shares_histories)} tickers behandlade")

    print(f"\nKlart: {len(all_frames)} tickers med både aktier och pris, {no_price_count} saknade cachad prisdata.\n")

    full_table = pd.concat(all_frames, ignore_index=True)
    full_table["month"] = full_table["date"].dt.strftime("%Y-%m-%d")
    full_table["in_band"] = full_table["market_cap"].between(MIN_CAP, MAX_CAP)

    print(f"Skriver fullständig tabell till {MARKET_CAP_TABLE_OUTPUT}...")
    full_table[["ticker", "month", "shares", "close", "market_cap", "in_band"]].rename(
        columns={"close": "price"}
    ).to_csv(MARKET_CAP_TABLE_OUTPUT, index=False)

    print("Bygger universum-per-månad (endast in_band=True)...")
    universe_by_month = {}
    in_band = full_table[full_table["in_band"]]
    for month, group in in_band.groupby("month"):
        universe_by_month[month] = sorted(group["ticker"].tolist())

    with UNIVERSE_OUTPUT.open("w", encoding="utf-8") as f:
        json.dump(universe_by_month, f, ensure_ascii=False, indent=1)

    sizes = [len(v) for v in universe_by_month.values()]
    print(f"\n--- KLART ---")
    print(f"Universum-fil: {UNIVERSE_OUTPUT}")
    print(f"Antal månader med >=1 bolag i intervallet: {len(universe_by_month)}/{len(month_ends)}")
    if sizes:
        print(f"Antal bolag i universumet per månad: min={min(sizes)}, max={max(sizes)}, snitt={sum(sizes)/len(sizes):.0f}")

    unique_tickers_ever = set()
    for v in universe_by_month.values():
        unique_tickers_ever.update(v)
    print(f"Unika tickers som NÅGONSIN varit i $100M-$2B-intervallet 2010-2024: {len(unique_tickers_ever)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
