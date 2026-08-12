"""
Delad datamodul for HYP-072 (dilution pipeline) och HYP-073 (filing stress
cascade) - hamtar STRUKTURERAD filings-metadata (formtyp + filingdatum +
8-K-item-koder) via SEC EDGAR submissions-API:et, INGEN dokumenttext/NLP.

VARFOR EN NY MODUL (till skillnad fran sec_edgar_adapter.py/
fetch_buyback_history.py/fetch_issuance_history.py, som ALLA pratar mot
companyfacts-XBRL-API:et): companyfacts ger bara numeriska redovisnings-
taggar. submissions-API:et ger den fullstandiga filings-LISTAN (vilken
formtyp som lamnades in nar) - en annan endpoint, en annan datamodell.
Verifierad feasible via webbsokning 2026-08-12 (se
research/candidate_ideas.md, posten daterad 2026-08-12): svaret innehaller
ett `items`-falt for 8-K (t.ex. "4.01" = revisorsbyte, "4.02" =
non-reliance/omrakning) samt fullstandig `form`+`filingDate`-historik.

ENDPOINT: https://data.sec.gov/submissions/CIK##########.json
  - filings.recent: kolumnara arrayer (samma index i over alla falt) for
    de senaste filingarna (minst 1 ar eller 1000 filingar, vilket som ar
    mest).
  - filings.files: lista over YTTERLIGARE json-filer med aldre historik
    om bolaget har mer an det. Hamtas bara om recent-fonstret inte redan
    tacker tillbaka till FULL_START (se _covers_full_history()).

Aterananvander samma ticker->CIK-mappning som buyback-/issuance-
hamtarna (data/cache/smallcap_classification.jsonl).

Output: data/cache/sec_filing_index.jsonl - en rad JSON per ticker:
  {"ticker":.., "cik":.., "filings":[{"form":.., "filingDate":..,
   "items":..}, ...]}
Endast RELEVANTA formtyper sparas (se RELEVANT_FORMS) for att halla
filstorleken rimlig - vi bygger ingen generisk filings-arkivmodul, bara
det denna batch tvahypoteser faktiskt behover.
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
OUTPUT_FILE = CACHE_DIR / "sec_filing_index.jsonl"

USER_AGENT = "Kebbe Research jagerstromebbe01@gmail.com"
HEADERS = {"User-Agent": USER_AGENT}
SUBMISSIONS_URL_TMPL = "https://data.sec.gov/submissions/CIK{cik}.json"
SUBMISSIONS_ARCHIVE_TMPL = "https://data.sec.gov/submissions/{name}"

FULL_START = "2010-01-01"

# HYP-072 (S-3-familjen) + HYP-073 (sen/omarbetad/8-K-item) formtyper.
RELEVANT_FORMS = {
    "S-3", "S-3/A", "S-3ASR", "424B3", "424B5",
    "NT 10-K", "NT 10-K/A", "NT 10-Q", "NT 10-Q/A",
    "10-K/A", "10-Q/A", "8-K", "8-K/A",
}


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


def _extract_relevant(recent_or_columnar: dict) -> list:
    forms = recent_or_columnar.get("form", [])
    dates = recent_or_columnar.get("filingDate", [])
    items = recent_or_columnar.get("items", [])
    out = []
    for i in range(len(forms)):
        form = forms[i]
        if form not in RELEVANT_FORMS:
            continue
        out.append({
            "form": form,
            "filingDate": dates[i] if i < len(dates) else None,
            "items": items[i] if i < len(items) else "",
        })
    return out


def _earliest_date(recent: dict) -> str:
    dates = [d for d in recent.get("filingDate", []) if d]
    return min(dates) if dates else "9999-99-99"


def fetch_filing_index_for_cik(cik: str) -> dict:
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
    all_filings = _extract_relevant(recent)

    # Om recent-fonstret inte redan tacker tillbaka till FULL_START, hamta
    # aldre arkivfiler ocksa (filings.files - en per ytterligare tidsspann).
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
            all_filings.extend(_extract_relevant(adata))

    return {"filings": all_filings}


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
    print(f"Hamtar filings-index for {total} tickers "
          f"({N_WORKERS} parallella arbetare, delad hastighetsspärr pa 8 anrop/sek totalt)...\n")

    n_ok_with_filings, n_ok_none, n_err = 0, 0, 0
    with OUTPUT_FILE.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=N_WORKERS) as executor:
            futures = {executor.submit(fetch_filing_index_for_cik, cik): (ticker, cik) for ticker, cik in remaining}
            for i, future in enumerate(as_completed(futures), 1):
                ticker, cik = futures[future]
                result = future.result()
                row = {"ticker": ticker, "cik": cik}
                if "filings" in result:
                    row["filings"] = result["filings"]
                    if result["filings"]:
                        n_ok_with_filings += 1
                    else:
                        n_ok_none += 1
                else:
                    row["filings"] = []
                    row["error"] = result["error"]
                    n_err += 1
                out.write(json.dumps(row) + "\n")
                out.flush()

                if i % 200 == 0 or i == total:
                    print(f"  [{i}/{total}] klara ({n_ok_with_filings} med relevanta filingar, "
                          f"{n_ok_none} utan relevanta filingar, {n_err} fel/saknar data)")

    print(f"\nKLART. {n_ok_with_filings} tickers med minst en relevant filing, "
          f"{n_ok_none} utan (men CIK gav giltigt svar), "
          f"{n_err} utan tillrackligt data. Sparat till {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
