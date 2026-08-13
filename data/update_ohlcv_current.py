"""
Pappershandel-forberedelse (2026-07-31, CEO-plan): stanger prisdata-luckan
mellan backtestens slut (2024-12-31) och idag for HYP-023:s universum, sa
att en "skarp" (framatblickande, inga riktiga pengar) korning kan starta.

METOD (CEO-beslut 2026-07-31): FRUSEN december 2024-universum-lista -
samma bolag som redan var i small-cap-universumet vid backtestens slut,
bara PRISERNA uppdateras framat. Ingen ombyggnad av marknadsvarde/
aktieantal for 2025-2026 (det ar ett storre, separat jobb - se
data/build_smallcap_universe.py om det nagonsin görs). KAND BEGRANSNING,
INTE dold: bolag som passerat in i eller ut ur $100M-$2B-bandet sedan
december 2024 fangas INTE av denna uppdatering.

Inkrementell (INTE en fullstandig ombyggnad): laser sista datumet i
varje redan cachad CSV, hamtar bara raderna DAREFTER till idag, och
APPENDAR (skriver INTE om hela filen) - mycket snabbare an
fetch_ohlcv_for_smallcap_candidates.py:s fullstandiga hamtning.

Samma hastighetsspärr-/tradpool-monster som ovriga fetch-skript i denna
mapp (delad RateLimiter, atertupptagningsbar).
"""

import csv
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

from eodhd_adapter import get_daily_ohlcv

DATA_DIR = Path(__file__).resolve().parent
CACHE_DIR = DATA_DIR / "cache"
OHLCV_DIR = CACHE_DIR / "ohlcv"
UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_by_month.json"
ERROR_LOG = CACHE_DIR / "ohlcv_update_errors.jsonl"

FIELDNAMES = [
    "date", "open", "high", "low", "close", "adjusted_close", "volume",
    "borrow_cost", "borrow_available", "bid_ask_spread",
]

TODAY = date.today().isoformat()

TARGET_RATE = 8.0
MAX_WORKERS = 16


class RateLimiter:
    def __init__(self, max_per_second: float):
        self.min_interval = 1.0 / max_per_second
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last = time.monotonic()


rate_limiter = RateLimiter(TARGET_RATE)
_progress_lock = threading.Lock()
_error_lock = threading.Lock()


def load_frozen_universe_tickers() -> set:
    """December 2024-universum (senaste manadsnyckeln i den redan byggda
    filen) - se moduldocstring for motivering av den frusna metoden."""
    with UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_by_month = json.load(f)
    latest_key = sorted(universe_by_month.keys())[-1]
    tickers = set(universe_by_month[latest_key])
    return tickers, latest_key


def last_cached_date(ticker: str):
    path = OHLCV_DIR / f"{ticker}.csv"
    if not path.exists():
        return None, path
    last_line = None
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                last_line = line
    if last_line is None:
        return None, path
    return last_line.split(",")[0], path


def fetch_one(ticker: str) -> dict:
    last_date, path = last_cached_date(ticker)
    if last_date is None:
        return {"ticker": ticker, "status": "no_cache"}

    start = (date.fromisoformat(last_date) + timedelta(days=1)).isoformat()
    if start > TODAY:
        return {"ticker": ticker, "status": "already_current"}

    rate_limiter.wait()
    try:
        rows = get_daily_ohlcv(ticker, start, TODAY)
    except Exception as exc:
        return {"ticker": ticker, "status": "error", "error": f"{type(exc).__name__}: {exc}"}

    if not rows:
        return {"ticker": ticker, "status": "no_new_rows"}

    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerows(rows)

    return {"ticker": ticker, "status": "ok", "rows": len(rows)}


def main() -> int:
    print(f"Idag (enligt systemklockan): {TODAY}\n")

    print("Laddar frusen december 2024-universumlista...")
    tickers, latest_key = load_frozen_universe_tickers()
    tickers = sorted(tickers | {"SPY"})
    print(f"  {len(tickers)} tickers (universum-nyckel: {latest_key}, plus SPY).\n")

    done = ok_count = current_count = nocache_count = error_count = norows_count = 0
    total_rows = 0
    t0 = time.time()

    with ERROR_LOG.open("a", encoding="utf-8") as errlog, ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_one, t): t for t in tickers}
        for future in as_completed(futures):
            result = future.result()
            status = result["status"]

            with _progress_lock:
                done += 1
                if status == "ok":
                    ok_count += 1
                    total_rows += result["rows"]
                elif status == "already_current":
                    current_count += 1
                elif status == "no_cache":
                    nocache_count += 1
                elif status == "no_new_rows":
                    norows_count += 1
                else:
                    error_count += 1
                    with _error_lock:
                        errlog.write(json.dumps({"ticker": result["ticker"], "error": result.get("error")},
                                                 ensure_ascii=False) + "\n")
                        errlog.flush()

                if done % 200 == 0 or done == len(tickers):
                    elapsed = time.time() - t0
                    rate = done / elapsed if elapsed > 0 else 0
                    print(f"  ... {done}/{len(tickers)} ({ok_count} uppdaterade, {current_count} redan aktuella, "
                          f"{nocache_count} okanda, {error_count} fel, {rate:.1f}/sek)")

    print(f"\nKLART. {ok_count} tickers fick nya rader ({total_rows} rader totalt), "
          f"{current_count} redan aktuella, {nocache_count} saknade cache sedan tidigare, "
          f"{error_count} fel (se {ERROR_LOG}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
