"""
Genuin OOS-utökning (2026-07-31, CEO-beslut): eftersom "idag" (pappershandel)
visade sig blockerad av EODHD:s glesa realtidstäckning för small-cap, bygger
detta istället en MÅNATLIG universum-utökning för 2025 - ett fönster som
ligger EFTER HYP-023:s regler låstes (2026-07-30) och som jag (Claude) inte
har memorerat specifika dagskurser för (till skillnad från kända
makrohändelser). Detta ger en genuint blind OOS-test, körd som ett vanligt
backtest snarare än en känslig "vad gäller just idag"-ögonblicksbild.

METOD: samma logik som data/rebuild_current_universe.py men UPPREPAD per
manadsslut i 2025 istallet for en enda "idag"-punkt - shares_outstanding_at()
(SEC EDGAR, redan hamtad historik per CIK) x manadsslutets stangningskurs
(redan cachad/kompletterad OHLCV), filtrerat till $100M-$2B.

Kandidatpool: samma 383 tickers som rebuild_current_universe.py redan
identifierade (december 2024-marknadsvarde inom $20M-$10B-buffertbandet) -
FANGAR INTE bolag som var langt utanfor det bandet i december 2024 men som
skulle kunna ha rort sig in i $100M-$2B nagon gang under 2025 (samma kanda
begransning som tidigare, se moduldocstring i rebuild_current_universe.py).

Output: data/cache/smallcap_universe_2025_extension.json - SEPARAT fil,
HALLS ISOLERAD fran smallcap_universe_by_month.json (den ursprungliga
filen ar backtestens grundsanning for 2010-2024 och ANDRAS ALDRIG).
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sec_edgar_adapter import get_shares_outstanding_history, shares_outstanding_at  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent
CACHE_DIR = DATA_DIR / "cache"
CLASSIFICATION_FILE = CACHE_DIR / "smallcap_classification.jsonl"
MARKET_CAP_FILE = CACHE_DIR / "market_cap_by_ticker_month.csv"
OHLCV_DIR = CACHE_DIR / "ohlcv"
OUTPUT_FILE = CACHE_DIR / "smallcap_universe_2025_extension.json"

BUFFER_LOW = 20_000_000
BUFFER_HIGH = 10_000_000_000
BAND_LOW = 100_000_000
BAND_HIGH = 2_000_000_000

# BUGGFIX (kodgranskning 2026-08-05): data/build_smallcap_universe.py (huvudserien
# 2010-2024) kraver redan att aktieantalet inte ar aldre an 120 dagar relativt
# manadsslutet (merge_asof med tolerance=120 dagar) - denna 2025-gren hade INGEN
# sadan sparr alls, sa ett bolag som slutat rapportera regelbundet (sen filer,
# forestaende fusion, etc.) skulle kunna fa ett flera ar gammalt aktieantal
# tyst behandlat som aktuellt. Samma tolerans har, for konsekvens.
SHARES_STALENESS_TOLERANCE_DAYS = 120

MONTH_ENDS_2025 = [
    "2025-01-31", "2025-02-28", "2025-03-31", "2025-04-30", "2025-05-30",
    "2025-06-30", "2025-07-31", "2025-08-29", "2025-09-30", "2025-10-31",
    "2025-11-28", "2025-12-31",
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


def load_price_at_or_before(ticker: str, target_date: str):
    path = OHLCV_DIR / f"{ticker}.csv"
    if not path.exists():
        return None, None
    best_date, best_price = None, None
    with path.open(encoding="utf-8") as f:
        next(f, None)  # header
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 6 or not parts[0]:
                continue
            d = parts[0]
            if d > target_date:
                break
            # BUGGFIX (kodgranskning 2026-08-05): ra close (index 4), inte
            # adjusted_close (index 5) - borsvarde = aktier x FAKTISKT
            # handlat pris, split-/utdelningsjusterat pris missvisar borsvarde
            # runt en split/storutdelning. Samma fix som rebuild_current_universe.py.
            best_date, best_price = d, parts[4]
    if best_date is None:
        return None, None
    # kraver rimlig narhet till manadsslutet (inom 10 dagar) for att undvika
    # att anvanda ett manader-gammalt varde som om det vore aktuellt
    from datetime import date
    if (date.fromisoformat(target_date) - date.fromisoformat(best_date)).days > 10:
        return None, None
    return best_date, best_price


def main():
    print("Laddar kandidater (december 2024-marknadsvarde $20M-$10B)...")
    candidates = load_buffer_candidates()
    ticker_cik = load_cik_map(candidates)
    print(f"  {len(candidates)} kandidater, {len(ticker_cik)} med CIK.\n")

    print("Hamtar aktieantal-historik per bolag (SEC EDGAR, sekventiellt)...")
    shares_history = {}
    for i, (ticker, cik) in enumerate(sorted(ticker_cik.items()), 1):
        if i % 50 == 0 or i == len(ticker_cik):
            print(f"  ... {i}/{len(ticker_cik)}")
        try:
            hist = get_shares_outstanding_history(cik)
        except Exception:
            hist = []
        if hist:
            shares_history[ticker] = hist
    print(f"  {len(shares_history)} bolag med anvandbar aktieantal-historik.\n")

    universe_by_month = {}
    for month_end in MONTH_ENDS_2025:
        eligible = []
        for ticker, hist in shares_history.items():
            entry = shares_outstanding_at(hist, month_end)
            if entry is None:
                continue
            # Staleness-sparr - se SHARES_STALENESS_TOLERANCE_DAYS-kommentaren ovan.
            from datetime import date as _date
            shares_age_days = (_date.fromisoformat(month_end) - _date.fromisoformat(entry["date"])).days
            if shares_age_days > SHARES_STALENESS_TOLERANCE_DAYS:
                continue
            price_date, price = load_price_at_or_before(ticker, month_end)
            if price is None:
                continue
            try:
                market_cap = float(price) * float(entry["shares"])
            except (TypeError, ValueError):
                continue
            if BAND_LOW <= market_cap <= BAND_HIGH:
                eligible.append(ticker)
        universe_by_month[month_end] = sorted(eligible)
        print(f"  {month_end}: {len(eligible)} bolag i $100M-$2B-bandet")

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(universe_by_month, f, indent=2, ensure_ascii=False)

    print(f"\nKLART. Sparat till {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
