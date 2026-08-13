"""
Risk Factors-textlikhet (BATCH-004, HYP-093-096) - datahamtning steg
2/2: hamtar FAKTISKA 10-K-dokument (via data/cache/10k_document_index.jsonl,
byggd av fetch_10k_document_index.py), extraherar Item 1A
(strategies/common/text_similarity.py, verifierad heuristik) och
beraknar bade Jaccard- och cosine/TF-IDF-likhet mellan varje bolags
PA VARANDRA FOLJANDE 10-K:or.

SKALA (disclosad, INTE dold): detta ar den tyngsta hamtningen i hela
BATCH-004 - varje dokument ar ~1-2MB HTML (mot companyfacts-anropens
nagra KB JSON). Varje dokument hamtas ENDAST EN GANG per ticker
(cachead under bearbetningen av den tickerns hela 10-K-svit, aldrig
tva ganger for samma accessionNumber) aven om den anvands i TVA
konsekutiva jamforelser (ar N mot N-1, ar N+1 mot N).

STICKPROVSVERIFIERING (kravd av HYP-093:s registerpost innan resultat
litas pa): skriver ut extraktionsframgangsgrad lopande - om andelen
misslyckade extraktioner (for kort/ej hittad Item 1A) overstiger 20%
flaggas detta EXPLICIT i slututskriften, inte tyst ignorerat.

Output: data/cache/text_similarity_by_ticker.jsonl - en rad JSON per
ticker: {"ticker":.., "cik":.., "comparisons":[{"filing_date":..,
"prior_filing_date":.., "jaccard":.., "cosine":.., "len_current":..,
"len_prior":..}, ...], "n_extraction_failures":..}
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
DOC_INDEX_FILE = CACHE_DIR / "10k_document_index.jsonl"
OUTPUT_FILE = CACHE_DIR / "text_similarity_by_ticker.jsonl"

sys.path.insert(0, str(DATA_DIR.parent / "strategies" / "common"))
from text_similarity import extract_item_1a, jaccard_similarity, cosine_similarity_tfidf  # noqa: E402

USER_AGENT = "Kebbe Research jagerstromebbe01@gmail.com"
HEADERS = {"User-Agent": USER_AGENT}
ARCHIVES_URL_TMPL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_nodash}/{doc}"


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


def sec_get(url: str, timeout: int = 60):
    sec_rate_limiter.wait()
    return requests.get(url, headers=HEADERS, timeout=timeout)


def fetch_document_text(cik: str, accession_number: str, primary_document: str):
    cik_int = str(int(cik))  # Archives-URL:en vill ha CIK UTAN inledande nollor
    accn_nodash = accession_number.replace("-", "")
    url = ARCHIVES_URL_TMPL.format(cik_int=cik_int, accn_nodash=accn_nodash, doc=primary_document)
    try:
        resp = sec_get(url)
    except requests.RequestException as exc:
        return {"error": f"natverksfel: {exc}"}
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}"}
    return {"html": resp.text}


def process_ticker(ticker: str, cik: str, filings: list) -> dict:
    """filings redan sorterade pa filingDate (fetch_10k_document_index.py:s
    kontrakt). Hamtar varje dokument EN gang, jamfor konsekutiva par."""
    if len(filings) < 2:
        return {"comparisons": [], "n_extraction_failures": 0, "n_fetch_errors": 0}

    extracted = {}  # accessionNumber -> Item 1A-text (eller None om misslyckad)
    fetch_errors = 0
    for f in filings:
        result = fetch_document_text(cik, f["accessionNumber"], f["primaryDocument"])
        if "html" in result:
            extracted[f["accessionNumber"]] = extract_item_1a(result["html"])
        else:
            extracted[f["accessionNumber"]] = None
            fetch_errors += 1

    comparisons = []
    n_extraction_failures = 0
    for i in range(1, len(filings)):
        cur, prior = filings[i], filings[i - 1]
        cur_text = extracted.get(cur["accessionNumber"])
        prior_text = extracted.get(prior["accessionNumber"])
        if cur_text is None:
            n_extraction_failures += 1
        if prior_text is None:
            n_extraction_failures += 1
        if cur_text is None or prior_text is None:
            continue
        comparisons.append({
            "filing_date": cur["filingDate"], "prior_filing_date": prior["filingDate"],
            "jaccard": jaccard_similarity(cur_text, prior_text),
            "cosine": cosine_similarity_tfidf(cur_text, prior_text),
            "len_current": len(cur_text), "len_prior": len(prior_text),
        })

    return {"comparisons": comparisons, "n_extraction_failures": n_extraction_failures, "n_fetch_errors": fetch_errors}


def main():
    if not DOC_INDEX_FILE.exists():
        print(f"FEL: {DOC_INDEX_FILE} finns inte - kör fetch_10k_document_index.py först.")
        return 1

    print("Laddar 10-K-dokumentindex...")
    tickers_filings = []
    with DOC_INDEX_FILE.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if len(row.get("filings", [])) >= 2:
                tickers_filings.append((row["ticker"], row["cik"], row["filings"]))
    print(f"  {len(tickers_filings)} tickers med minst 2 10-K:or (jämförbara).\n")

    total_docs = sum(len(f) for _, _, f in tickers_filings)
    est_seconds = total_docs / 8.0
    print(f"  Totalt {total_docs} dokument att hämta (~{est_seconds/60:.0f} minuter vid 8/sek "
          f"rate-limit, sannolikt LÄNGRE i praktiken pga dokumentstorlek/parsning).\n")

    already_done = set()
    if OUTPUT_FILE.exists():
        with OUTPUT_FILE.open(encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    already_done.add(row["ticker"])
                except (json.JSONDecodeError, KeyError):
                    continue
        print(f"Återupptar - {len(already_done)} tickers redan klara.\n")

    remaining = [(t, cik, filings) for t, cik, filings in tickers_filings if t not in already_done]
    total = len(remaining)
    print(f"Bearbetar {total} tickers ({N_WORKERS} parallella arbetare, delad hastighetsspärr 8/sek)...\n")

    n_ok, n_no_comparisons, total_comparisons, total_extraction_failures, total_fetch_errors = 0, 0, 0, 0, 0
    with OUTPUT_FILE.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=N_WORKERS) as executor:
            futures = {executor.submit(process_ticker, t, cik, filings): (t, cik)
                       for t, cik, filings in remaining}
            for i, future in enumerate(as_completed(futures), 1):
                ticker, cik = futures[future]
                result = future.result()
                row = {"ticker": ticker, "cik": cik, "comparisons": result["comparisons"],
                       "n_extraction_failures": result["n_extraction_failures"],
                       "n_fetch_errors": result["n_fetch_errors"]}
                out.write(json.dumps(row) + "\n")
                out.flush()

                if result["comparisons"]:
                    n_ok += 1
                else:
                    n_no_comparisons += 1
                total_comparisons += len(result["comparisons"])
                total_extraction_failures += result["n_extraction_failures"]
                total_fetch_errors += result["n_fetch_errors"]

                if i % 100 == 0 or i == total:
                    fail_rate = total_extraction_failures / max(total_comparisons + total_extraction_failures, 1)
                    print(f"  [{i}/{total}] klara ({n_ok} med >=1 jämförelse, {n_no_comparisons} utan, "
                          f"{total_comparisons} jämförelser hittills, "
                          f"extraktionsmisslyckandegrad={fail_rate:.1%})")

    fail_rate = total_extraction_failures / max(total_comparisons + total_extraction_failures, 1)
    print(f"\nKLART. {n_ok} tickers med minst en jämförelse, {total_comparisons} totala år-över-år-"
          f"jämförelser, extraktionsmisslyckandegrad={fail_rate:.1%}.")
    if fail_rate > 0.20:
        print(f"  VARNING: extraktionsmisslyckandegraden ({fail_rate:.1%}) överstiger 20% - "
              f"HYP-093:s registerpost kräver att detta flaggas explicit innan resultat litas på. "
              f"Extraktionsheuristiken (strategies/common/text_similarity.py) är bara verifierad mot "
              f"ETT dokumentformat (GameStop 2024/2025) - troligen INTE robust nog över hela "
              f"universumets varierande arkiveringsformat utan ytterligare arbete.")
    print(f"Sparat till {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
