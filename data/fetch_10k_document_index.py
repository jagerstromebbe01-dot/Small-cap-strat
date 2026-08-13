"""
Risk Factors-textlikhet (BATCH-004, HYP-093-096) - datahamtning steg 1/2:
INDEX over faktiska 10-K-DOKUMENT (accessionNumber + primaryDocument,
inte bara formtyp+datum som sec_filing_index.jsonl redan har) per
ticker, via SEC EDGAR submissions-API:et. Ren metadata, ingen
dokumenttext hamtas har - se fetch_10k_text_similarity.py for steg 2.

VARFOR EN NY FIL (till skillnad fran att aterananvanda
sec_filing_index.jsonl): den filen sparar bara RELEVANT_FORMS (S-3-
familjen, NT-formulär, 8-K, *-formulärens AMENDMENTS) - INTE bara
"10-K" (basformularet), och sparar inte accessionNumber/primaryDocument
(behovs for att bygga den faktiska dokument-URL:en). Samma
ticker->CIK-mappning, samma hastighetsspärr-monster som
fetch_sec_filing_index.py.

Output: data/cache/10k_document_index.jsonl - en rad JSON per ticker:
  {"ticker":.., "cik":.., "filings":[{"filingDate":.., "accessionNumber":..,
   "primaryDocument":..}, ...]} (endast form=="10-K", INTE 10-K/A -
  amendments kan ändra Item 1A pa satt som inte ar jamforbara ar-over-ar
  pa ett enkelt satt, exkluderas medvetet fran denna forsta version).
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
OUTPUT_FILE = CACHE_DIR / "10k_document_index.jsonl"

USER_AGENT = "Kebbe Research jagerstromebbe01@gmail.com"
HEADERS = {"User-Agent": USER_AGENT}
SUBMISSIONS_URL_TMPL = "https://data.sec.gov/submissions/CIK{cik}.json"
SUBMISSIONS_ARCHIVE_TMPL = "https://data.sec.gov/submissions/{name}"

FULL_START = "2010-01-01"


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


def _extract_10k(columnar: dict) -> list:
    forms = columnar.get("form", [])
    dates = columnar.get("filingDate", [])
    accns = columnar.get("accessionNumber", [])
    docs = columnar.get("primaryDocument", [])
    out = []
    for i in range(len(forms)):
        if forms[i] != "10-K":
            continue
        out.append({
            "filingDate": dates[i] if i < len(dates) else None,
            "accessionNumber": accns[i] if i < len(accns) else None,
            "primaryDocument": docs[i] if i < len(docs) else None,
        })
    return out


def _earliest_date(recent: dict) -> str:
    dates = [d for d in recent.get("filingDate", []) if d]
    return min(dates) if dates else "9999-99-99"


def fetch_10k_index_for_cik(cik: str) -> dict:
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
    all_10k = _extract_10k(recent)

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
            all_10k.extend(_extract_10k(adata))

    all_10k = [f for f in all_10k if f["filingDate"] and f["accessionNumber"] and f["primaryDocument"]]
    all_10k.sort(key=lambda f: f["filingDate"])
    return {"filings": all_10k}


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
    print(f"Hamtar 10-K-dokumentindex for {total} tickers "
          f"({N_WORKERS} parallella arbetare, delad hastighetsspärr pa 8 anrop/sek)...\n")

    n_ok, n_none, n_err = 0, 0, 0
    with OUTPUT_FILE.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=N_WORKERS) as executor:
            futures = {executor.submit(fetch_10k_index_for_cik, cik): (ticker, cik) for ticker, cik in remaining}
            for i, future in enumerate(as_completed(futures), 1):
                ticker, cik = futures[future]
                result = future.result()
                row = {"ticker": ticker, "cik": cik}
                if "filings" in result:
                    row["filings"] = result["filings"]
                    if len(result["filings"]) >= 2:
                        n_ok += 1
                    else:
                        n_none += 1
                else:
                    row["filings"] = []
                    row["error"] = result["error"]
                    n_err += 1
                out.write(json.dumps(row) + "\n")
                out.flush()

                if i % 200 == 0 or i == total:
                    print(f"  [{i}/{total}] klara ({n_ok} med >=2 10-K:or (jamforbara), "
                          f"{n_none} med <2, {n_err} fel)")

    print(f"\nKLART. {n_ok} tickers med minst tva 10-K:or (jamforbara ar-over-ar), "
          f"{n_none} med for fa, {n_err} fel. Sparat till {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
