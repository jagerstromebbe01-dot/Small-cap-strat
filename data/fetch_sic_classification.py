"""
Kvalitetskontroll (2026-07-31, CEO-beslut, "gratis kontroll" - INGEN
K-kostnad, andrar INGET last resultat): HYP-022/023/030s bank-/finans-
klassificering bygger pa nyckelordsmatchning mot bolagsnamnet
(strategies/common/sector.py) - en grov men reproducerbar heuristik,
redan sjalv-flaggad som sadan i registret. Detta skript hamtar den
FORMELLA SEC-klassificeringen (SIC-kod) via SEC EDGAR submissions-API:et
for jamforelse - inte for att retroaktivt andra nagot last resultat,
utan som en robusthetskontroll: haller HYP-023:s resultat om vi hade
anvant SIC i stallet for nyckelord?

SIC-intervall for "Finance, Insurance, And Real Estate" (Division H):
  6000-6099 Depository institutions (banker)
  6100-6199 Non-depository credit institutions
  6200-6299 Security/commodity brokers
  6300-6499 Forsakring
  6500-6599 Real estate (inkl. REITs)
  6700-6799 Holding-/investeringsbolag (inkl. bankholdingbolag)
Anvander HELA 6000-6799 for att matcha den ursprungliga nyckelords-
klassificeringens BREDD (bancorp/bank/savings/thrift/financial/trust
tacker mer an bara rena banker).

Samma monster som ovriga fetch-skript: delad hastighetsspärr,
atertupptagningsbar, skriver lopande.
"""

import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent
CACHE_DIR = DATA_DIR / "cache"
CLASSIFICATION_FILE = CACHE_DIR / "smallcap_classification.jsonl"
UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_by_month.json"
OUTPUT_FILE = CACHE_DIR / "sic_classification.jsonl"

USER_AGENT = "Kebbe Research jagerstromebbe01@gmail.com"
HEADERS = {"User-Agent": USER_AGENT}
SUBMISSIONS_URL_TMPL = "https://data.sec.gov/submissions/CIK{cik}.json"

TARGET_RATE = 8.0
MAX_WORKERS = 8


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


def sec_get(url: str, timeout: int = 20):
    rate_limiter.wait()
    return requests.get(url, headers=HEADERS, timeout=timeout)


def load_universe_tickers() -> set:
    with UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_by_month = json.load(f)
    return {t for tickers in universe_by_month.values() for t in tickers}


def load_ticker_cik_map(universe_tickers: set) -> dict:
    mapping = {}
    with CLASSIFICATION_FILE.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            ticker = row.get("ticker")
            cik = row.get("cik")
            if ticker in universe_tickers and cik:
                mapping[ticker] = cik
    return mapping


def fetch_sic_for_cik(cik: str) -> dict:
    url = SUBMISSIONS_URL_TMPL.format(cik=cik)
    try:
        resp = sec_get(url)
    except requests.RequestException as exc:
        return {"error": f"natverksfel: {exc}"}
    if resp.status_code == 404:
        return {"error": "404"}
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}"}
    try:
        data = resp.json()
    except ValueError:
        return {"error": "ogiltigt JSON-svar"}
    sic = data.get("sic")
    if not sic:
        return {"error": "ingen SIC-kod"}
    return {"sic": sic, "sic_description": data.get("sicDescription")}


def main():
    print("Laddar universum-tickers...")
    universe_tickers = load_universe_tickers()
    print(f"  {len(universe_tickers)} unika tickers.\n")

    print("Slar upp CIK...")
    ticker_cik = load_ticker_cik_map(universe_tickers)
    print(f"  {len(ticker_cik)} med CIK.\n")

    already_done = set()
    if OUTPUT_FILE.exists():
        with OUTPUT_FILE.open(encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    already_done.add(row["ticker"])
                except (json.JSONDecodeError, KeyError):
                    continue
        print(f"Aterupptar - {len(already_done)} redan hamtade.\n")

    remaining = [(t, cik) for t, cik in ticker_cik.items() if t not in already_done]
    total = len(remaining)
    print(f"Hamtar SIC-koder for {total} tickers ({MAX_WORKERS} trådar, {TARGET_RATE}/sek)...\n")

    n_ok, n_err = 0, 0
    with OUTPUT_FILE.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(fetch_sic_for_cik, cik): (ticker, cik) for ticker, cik in remaining}
            for i, future in enumerate(as_completed(futures), 1):
                ticker, cik = futures[future]
                result = future.result()
                row = {"ticker": ticker, "cik": cik}
                if "sic" in result:
                    row["sic"] = result["sic"]
                    row["sic_description"] = result["sic_description"]
                    n_ok += 1
                else:
                    row["sic"] = None
                    row["error"] = result["error"]
                    n_err += 1
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                out.flush()

                if i % 200 == 0 or i == total:
                    print(f"  [{i}/{total}] klara ({n_ok} med SIC, {n_err} utan)")

    print(f"\nKLART. {n_ok} tickers med SIC-kod, {n_err} utan. Sparat till {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
