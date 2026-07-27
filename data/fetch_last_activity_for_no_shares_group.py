"""
Hämtar submissions.json för alla CIK:er i cik_found_no_shares_data-
kategorin (9 709 st, se smallcap_classification.jsonl) för att avgöra
deras sista SEC-aktivitet (senaste inlämnade rapport). Detta är den
enda vägen till den datan - den finns inte redan cachad (bekräftat i
föregående analys: 0 av 9 709 har någon sparad datumpunkt).

Rör INTE smallcap_classification.jsonl eller frames-data - skriver till
en egen, separat fil. Gör INGA EODHD-anrop.

Hastighetsspärr: samma mönster som build_smallcap_classification.py,
max 8 anrop/sekund, GLOBALT, klart under SEC:s 10/sek-gräns.

Robust felhantering: varje CIK hanteras i eget try/except, loggas och
fortsätter - stannar aldrig upp för ett enskilt fel.
"""

import json
import sys
import threading
import time
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent
CACHE_DIR = DATA_DIR / "cache"
CLASSIFICATION_FILE = CACHE_DIR / "smallcap_classification.jsonl"
OUTPUT_FILE = CACHE_DIR / "no_shares_last_activity.jsonl"

USER_AGENT = "Kebbe Research jagerstromebbe01@gmail.com"
HEADERS = {"User-Agent": USER_AGENT}
SUBMISSIONS_URL_TMPL = "https://data.sec.gov/submissions/CIK{cik}.json"


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


sec_rate_limiter = RateLimiter(8.0)


def load_target_ciks() -> list:
    ciks = []
    with CLASSIFICATION_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("status") == "cik_found_no_shares_data" and rec.get("cik"):
                ciks.append((rec["ticker"], rec["cik"]))
    return ciks


def fetch_last_activity(cik: str) -> dict:
    sec_rate_limiter.wait()
    url = SUBMISSIONS_URL_TMPL.format(cik=cik)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code == 404:
        return {"status": "not_found_404"}
    resp.raise_for_status()
    data = resp.json()

    recent = data.get("filings", {}).get("recent", {})
    filing_dates = [d for d in recent.get("filingDate", []) if d]
    if not filing_dates:
        return {"status": "no_filings", "entity_name": data.get("name")}

    return {
        "status": "ok",
        "entity_name": data.get("name"),
        "last_filing_date": max(filing_dates),
        "first_filing_date_in_recent": min(filing_dates),
        "current_tickers": data.get("tickers", []),
    }


def main() -> int:
    print("Laddar CIK-lista för cik_found_no_shares_data...")
    targets = load_target_ciks()
    print(f"  {len(targets)} CIK:er att hämta.\n")

    done = 0
    already = {}
    if OUTPUT_FILE.exists():
        with OUTPUT_FILE.open("r", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                already[rec["cik"]] = rec
        print(f"  Återupptar: {len(already)} redan hämtade sedan tidigare avbrott.\n")

    t0 = time.time()
    with OUTPUT_FILE.open("a", encoding="utf-8") as out:
        for ticker, cik in targets:
            if cik in already:
                continue
            record = {"ticker": ticker, "cik": cik}
            try:
                result = fetch_last_activity(cik)
                record.update(result)
            except Exception as exc:
                record["status"] = f"error:{type(exc).__name__}"
                record["error_detail"] = str(exc)

            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            done += 1

            if done % 500 == 0:
                elapsed = time.time() - t0
                rate = done / elapsed
                remaining = (len(targets) - len(already) - done) / rate if rate > 0 else 0
                print(f"  ... {done} hämtade denna körning ({elapsed:.0f}s, {rate:.2f}/s, ~{remaining/60:.1f} min kvar)")

    print(f"\nKLART. Totalt i output-filen: {len(already) + done} av {len(targets)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
