"""
STEG 1 (CEO-plan 2026-07-27): hämtar EODHD daglig OHLCV, 2010-01-01 till
2024-12-31, för alla tickers med status "ok" i
smallcap_classification.jsonl (~9 300 st - CIK och aktieantal redan
verifierat via SEC, se build_smallcap_classification.py).

Körs PARALLELLT med den separata SEC submissions.json-körningen
(fetch_last_activity_for_no_shares_group.py) - olika API (EODHD vs
SEC), ingen konflikt, ingen delad hastighetsspärr behövs mellan dem.

Cache: en CSV-fil per ticker i data/cache/ohlcv/{ticker}.csv.
Återupptagningsbar - hoppar över tickers som redan har en cachad fil.

Rör INTE smallcap_classification.jsonl, eodhd_adapter.py, eller SEC-
relaterade filer.
"""

import csv
import json
import sys
import time
from pathlib import Path

from eodhd_adapter import EODHDError, get_daily_ohlcv

DATA_DIR = Path(__file__).resolve().parent
CACHE_DIR = DATA_DIR / "cache"
CLASSIFICATION_FILE = CACHE_DIR / "smallcap_classification.jsonl"
OHLCV_DIR = CACHE_DIR / "ohlcv"
ERROR_LOG = CACHE_DIR / "ohlcv_fetch_errors.jsonl"

START_DATE = "2010-01-01"
END_DATE = "2024-12-31"

FIELDNAMES = [
    "date", "open", "high", "low", "close", "adjusted_close", "volume",
    "borrow_cost", "borrow_available", "bid_ask_spread",
]


def load_target_tickers() -> list:
    tickers = []
    with CLASSIFICATION_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("status") == "ok":
                tickers.append(rec["ticker"])
    return tickers


def main() -> int:
    OHLCV_DIR.mkdir(parents=True, exist_ok=True)

    print("Laddar tickerlista (status=ok i smallcap_classification.jsonl)...")
    tickers = load_target_tickers()
    print(f"  {len(tickers)} tickers.\n")

    already = {p.stem for p in OHLCV_DIR.glob("*.csv")}
    todo = [t for t in tickers if t not in already]
    print(f"  {len(already)} redan cachade sedan tidigare, {len(todo)} kvar.\n")

    done = 0
    ok_count = 0
    empty_count = 0
    error_count = 0
    total_rows = 0
    t0 = time.time()

    with ERROR_LOG.open("a", encoding="utf-8") as errlog:
        for ticker in todo:
            try:
                rows = get_daily_ohlcv(ticker, START_DATE, END_DATE)
            except EODHDError as exc:
                error_count += 1
                errlog.write(json.dumps({"ticker": ticker, "error": str(exc)}, ensure_ascii=False) + "\n")
                errlog.flush()
                done += 1
                continue
            except Exception as exc:  # robust: logga och fortsätt
                error_count += 1
                errlog.write(json.dumps({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False) + "\n")
                errlog.flush()
                done += 1
                continue

            if not rows:
                empty_count += 1
                done += 1
                continue

            out_path = OHLCV_DIR / f"{ticker}.csv"
            with out_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                writer.writeheader()
                writer.writerows(rows)

            ok_count += 1
            total_rows += len(rows)
            done += 1

            if done % 200 == 0:
                elapsed = time.time() - t0
                rate = done / elapsed
                remaining = (len(todo) - done) / rate if rate > 0 else 0
                print(
                    f"  ... {done}/{len(todo)} klara ({ok_count} ok, {empty_count} tomma, "
                    f"{error_count} fel, {elapsed/60:.0f} min, ~{remaining/60:.0f} min kvar)"
                )

    print(f"\nKLART denna körning: {done} tickers behandlade.")
    print(f"  OK (fil skriven): {ok_count}, tomma: {empty_count}, fel: {error_count}")
    print(f"  Totalt antal rader skrivna: {total_rows}")
    print(f"  Cache-mapp: {OHLCV_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
