"""
Bygger om smallcap_universe_by_month.json med det filed-datum-korrigerade
klassificeringsunderlaget (data/cache/smallcap_classification_filed_date.jsonl,
se rebuild_smallcap_classification_filed_date.py). Identisk logik till
build_smallcap_universe.py i övrigt (samma toleranser, samma
$100M-$2B-band, samma månadsslut) - ENDA skillnaden är källfilen.

SEPARAT FIL - rör INTE data/cache/smallcap_universe_by_month.json (den
ursprungliga förblir grundsanningen tills ett explicit CEO-beslut).

Output:
- data/cache/smallcap_universe_by_month_filed_date.json
- data/cache/market_cap_by_ticker_month_filed_date.csv
"""

import json
import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent
CACHE_DIR = DATA_DIR / "cache"
CLASSIFICATION_FILE = CACHE_DIR / "smallcap_classification_filed_date.jsonl"
OHLCV_DIR = CACHE_DIR / "ohlcv"

UNIVERSE_OUTPUT = CACHE_DIR / "smallcap_universe_by_month_filed_date.json"
MARKET_CAP_TABLE_OUTPUT = CACHE_DIR / "market_cap_by_ticker_month_filed_date.csv"

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
    """Identisk logik till build_smallcap_universe.py - samma toleranser
    (10 dagar pris, 120 dagar aktier), samma look-ahead-fria merge_asof-
    riktning. shares_history's 'date' är nu filed-datum, inte periodslut."""
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

    price_asof = pd.merge_asof(
        month_df, prices[["date", "close"]], on="date", direction="backward",
        tolerance=pd.Timedelta(days=10),
    )

    combined = pd.merge_asof(
        price_asof, shares_df[["date", "shares"]], on="date", direction="backward",
        tolerance=pd.Timedelta(days=120),
    )

    combined["market_cap"] = combined["shares"] * combined["close"]
    combined["ticker"] = ticker
    return combined


def main() -> int:
    print("Laddar aktieantal-historik (filed-datum-korrigerad)...")
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
