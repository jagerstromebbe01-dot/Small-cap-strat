"""
HYP-101: Aktivistiskt ägande (Schedule 13D) - datahamtning. Fangar
ENDAST formtypen "SC 13D" (INTE SC 13D/A, SC 13G, SC 13G/A - se HYP-101s
lasta kriterium, punkt 1: bara initiala 13D raknas) per ticker, via SEC
EDGAR submissions-API:et. Ren strukturerad metadata (formtyp +
filingdatum) - INGEN dokumenttext behovs, till skillnad fran
textlikhets-sparet.

SAMMA MONSTER som fetch_10k_document_index.py (ateranvander samma
ticker->CIK-mappning, samma hastighetsspärr, samma submissions-API-
paginering for bolag med lang historik).

Output: data/cache/13d_filing_index.jsonl - en rad JSON per ticker:
  {"ticker":.., "cik":.., "filings":[{"filingDate":..}, ...]}
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
OUTPUT_FILE = CACHE_DIR / "13d_filing_index.jsonl"

USER_AGENT = "Kebbe Research jagerstromebbe01@gmail.com"
HEADERS = {"User-Agent": USER_AGENT}
SUBMISSIONS_URL_TMPL = "https://data.sec.gov/submissions/CIK{cik}.json"
SUBMISSIONS_ARCHIVE_TMPL = "https://data.sec.gov/submissions/{name}"

FULL_START = "2010-01-01"
TARGET_FORM = "SC 13D"


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
N_WORKERS = 8


def sec_get(url: str, timeout: int = 30):
    sec_rate_limiter.wait()
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


def _extract_13d(columnar: dict) -> list:
    forms = columnar.get("form", [])
    dates = columnar.get("filingDate", [])
    out = []
    for i in range(len(forms)):
        if forms[i] != TARGET_FORM:
            continue
        if i < len(dates) and dates[i]:
            out.append({"filingDate": dates[i]})
    return out


def _earliest_date(recent: dict) -> str:
    dates = [d for d in recent.get("filingDate", []) if d]
    return min(dates) if dates else "9999-99-99"


def fetch_13d_index_for_cik(cik: str) -> dict:
    url = SUBMISSIONS_URL_TMPL.format(cik=cik)
    try:
        resp = sec_get(url)
    except requests.RequestException as exc:
        return {"error": f"natverksfel: {exc}"}
    if resp.status_code == 404:
        return {"error": "404: ingen submissions-data"}
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}"}
    try:
        data = resp.json()
    except ValueError:
        return {"error": "ogiltigt JSON-svar"}

    filings = data.get("filings", {})
    recent = filings.get("recent", {})
    all_13d = _extract_13d(recent)

    if _earliest_date(recent) > FULL_START:
        for file_info in filings.get("files", []):
            name = file_info.get("name")
            if not name:
                continue
            archive_url = SUBMISSIONS_ARCHIVE_TMPL.format(name=name)
            try:
                aresp = sec_get(archive_url)
            except requests.RequestException:
                continue
            if aresp.status_code != 200:
                continue
            try:
                adata = aresp.json()
            except ValueError:
                continue
            all_13d.extend(_extract_13d(adata))

    all_13d.sort(key=lambda f: f["filingDate"])
    return {"filings": all_13d}


def main():
    print("Laddar universum-tickers...")
    universe_tickers = load_universe_tickers()
    print(f"  {len(universe_tickers)} unika tickers i small-cap-universumet.\n")

    print("Filtrerar mot redan byggd ticker->CIK-mappning...")
    ticker_cik = load_ticker_cik_map(universe_tickers)
    print(f"  {len(ticker_cik)} av dem har en matchad CIK.\n")

    already_done = set()
    if OUTPUT_FILE.exists():
        with OUTPUT_FILE.open(encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    already_done.add(row["ticker"])
                except (json.JSONDecodeError, KeyError):
                    continue
        print(f"Aterupptar - {len(already_done)} tickers redan hamtade tidigare.\n")

    remaining = [(t, cik) for t, cik in ticker_cik.items() if t not in already_done]
    total = len(remaining)
    print(f"Hamtar SC 13D-index for {total} tickers "
          f"({N_WORKERS} parallella arbetare, delad hastighetsspärr pa 8 anrop/sek)...\n")

    n_with, n_none, n_err = 0, 0, 0
    total_events = 0
    with OUTPUT_FILE.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=N_WORKERS) as executor:
            futures = {executor.submit(fetch_13d_index_for_cik, cik): (ticker, cik) for ticker, cik in remaining}
            for i, future in enumerate(as_completed(futures), 1):
                ticker, cik = futures[future]
                result = future.result()
                row = {"ticker": ticker, "cik": cik}
                if "filings" in result:
                    row["filings"] = result["filings"]
                    if result["filings"]:
                        n_with += 1
                        total_events += len(result["filings"])
                    else:
                        n_none += 1
                else:
                    row["filings"] = []
                    row["error"] = result["error"]
                    n_err += 1
                out.write(json.dumps(row) + "\n")
                out.flush()

                if i % 500 == 0 or i == total:
                    print(f"  [{i}/{total}] klara ({n_with} med minst ett SC 13D, "
                          f"{total_events} totala händelser hittills, {n_none} utan, {n_err} fel)")

    print(f"\nKLART. {n_with} tickers med minst ett SC 13D, {total_events} totala händelser, "
          f"{n_none} utan, {n_err} fel. Sparat till {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
