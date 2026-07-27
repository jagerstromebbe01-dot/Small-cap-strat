"""
STEG 1 (CEO-plan 2026-07-27): hämtar EODHD daglig OHLCV, 2010-01-01 till
2024-12-31, för alla tickers med status "ok" i
smallcap_classification.jsonl (~9 300 st - CIK och aktieantal redan
verifierat via SEC, se build_smallcap_classification.py).

Körs PARALLELLT med den separata SEC submissions.json-körningen
(fetch_last_activity_for_no_shares_group.py) - olika API (EODHD vs
SEC), ingen konflikt, ingen delad hastighetsspärr behövs mellan dem.

PARALLELLISERAD (2026-07-27, ombyggd): den ursprungliga sekventiella
versionen tog ~4h trots att EODHD tillåter 1000 anrop/minut - flaskhalsen
var ren nätverks-/serverlatens per anrop (~1.5-2s), inte en medveten
fördröjning. Denna version kör MAX_WORKERS trådar parallellt, med en
delad, trådsäker hastighetsspärr på TARGET_RATE anrop/sek (klar
säkerhetsmarginal under EODHD:s 1000/min ≈ 16.7/sek).

Cache: en CSV-fil per ticker i data/cache/ohlcv/{ticker}.csv.
Återupptagningsbar - hoppar över tickers som redan har en cachad fil
(de ~1000 som redan hanns hämtas av den gamla sekventiella körningen
återanvänds, hämtas inte om).

Rör INTE smallcap_classification.jsonl, eodhd_adapter.py, eller SEC-
relaterade filer.
"""

import csv
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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

TARGET_RATE = 8.0  # anrop/sek = 480/min, ~48% av EODHD:s 1000/min-gräns
MAX_WORKERS = 16   # tillräckligt många samtidiga anrop för att mätta TARGET_RATE
                   # givet ~1.5-2s latens/anrop (16 / 1.75s ≈ 9/sek > 8/sek-målet)


class RateLimiter:
    """Delad, trådsäker hastighetsspärr - alla trådar delar samma
    minsta-mellanrum-klocka, så den verkliga sammanlagda takten aldrig
    överskrider TARGET_RATE oavsett hur många trådar som kör."""

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


def load_target_tickers() -> list:
    tickers = []
    with CLASSIFICATION_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("status") == "ok":
                tickers.append(rec["ticker"])
    return tickers


def fetch_one(ticker: str) -> dict:
    """Körs i en worker-tråd. Returnerar ett litet statusresultat -
    skriver ALDRIG till delade räknare direkt (det görs i main-tråden
    när resultatet kommer tillbaka), för att hålla trådsäkerheten enkel
    och tydlig."""
    rate_limiter.wait()
    try:
        rows = get_daily_ohlcv(ticker, START_DATE, END_DATE)
    except Exception as exc:  # robust: logga och fortsätt, krascha aldrig hela poolen
        return {"ticker": ticker, "status": "error", "error": f"{type(exc).__name__}: {exc}"}

    if not rows:
        return {"ticker": ticker, "status": "empty"}

    out_path = OHLCV_DIR / f"{ticker}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    return {"ticker": ticker, "status": "ok", "rows": len(rows)}


def main() -> int:
    OHLCV_DIR.mkdir(parents=True, exist_ok=True)

    print("Laddar tickerlista (status=ok i smallcap_classification.jsonl)...")
    tickers = load_target_tickers()
    print(f"  {len(tickers)} tickers.\n")

    already = {p.stem for p in OHLCV_DIR.glob("*.csv")}
    todo = [t for t in tickers if t not in already]
    print(f"  {len(already)} redan cachade sedan tidigare (återupptagning), {len(todo)} kvar.")
    print(f"  Hastighet: max {TARGET_RATE}/sek ({TARGET_RATE*60:.0f}/min, under EODHD:s 1000/min), {MAX_WORKERS} parallella trådar.\n")

    done = 0
    ok_count = 0
    empty_count = 0
    error_count = 0
    total_rows = 0
    t0 = time.time()

    with ERROR_LOG.open("a", encoding="utf-8") as errlog, ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_one, t): t for t in todo}
        for future in as_completed(futures):
            result = future.result()
            status = result["status"]

            if status == "ok":
                with _progress_lock:
                    ok_count += 1
                    total_rows += result["rows"]
            elif status == "empty":
                with _progress_lock:
                    empty_count += 1
            else:
                with _error_lock:
                    errlog.write(json.dumps({"ticker": result["ticker"], "error": result["error"]}, ensure_ascii=False) + "\n")
                    errlog.flush()
                with _progress_lock:
                    error_count += 1

            with _progress_lock:
                done += 1
                if done % 200 == 0:
                    elapsed = time.time() - t0
                    rate = done / elapsed
                    remaining = (len(todo) - done) / rate if rate > 0 else 0
                    print(
                        f"  ... {done}/{len(todo)} klara ({ok_count} ok, {empty_count} tomma, "
                        f"{error_count} fel, {rate:.1f}/sek, {elapsed/60:.1f} min, ~{remaining/60:.1f} min kvar)"
                    )

    print(f"\nKLART denna körning: {done} tickers behandlade.")
    print(f"  OK (fil skriven): {ok_count}, tomma: {empty_count}, fel: {error_count}")
    print(f"  Totalt antal rader skrivna: {total_rows}")
    print(f"  Cache-mapp: {OHLCV_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
