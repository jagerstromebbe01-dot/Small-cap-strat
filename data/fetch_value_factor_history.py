"""
Book-to-Market-hypotesen (HYP-033) - datahamtning: arliga
StockholdersEquity OCH aktieantal per ticker, via SEC EDGAR
companyfacts-API:et (samma monster som fetch_profitability_history.py,
HYP-024).

VARFOR BADA fran SAMMA companyfacts-svar: Book-to-Market = StockholdersEquity
/ Marknadsvarde, dar Marknadsvarde = Pris x Aktieantal - VIKTIGT att
aktieantalet racknas fran SAMMA 10-K:s balansrakningsdatum som eget
kapitalet, inte ett senare/tidigare varde, for att undvika en falsk
"kvot" av tva icke-samtidiga matt.

VARFOR ARSVIS (10-K, fp="FY") och INTE kvartalsvis: samma motivering
som HYP-024 - Book-to-Market ar en NIVA-signal, akademisk praxis
(Fama-French HML) anvander arliga bokslutsdata.

Aterananvander samma ticker->CIK-mappning som EPS-/lonsamhet-pipen
(data/cache/smallcap_classification.jsonl).

Output: data/cache/value_factor_by_ticker.jsonl - en rad JSON per
ticker:
  {"ticker":.., "cik":.., "stockholders_equity":[{"end":.., "val":..,
   "filed":.., "fy":..}], "shares_outstanding":[{"end":.., "val":..,
   "filed":.., "fy":..}]}
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
OUTPUT_FILE = CACHE_DIR / "value_factor_by_ticker.jsonl"

USER_AGENT = "Kebbe Research jagerstromebbe01@gmail.com"
HEADERS = {"User-Agent": USER_AGENT}
COMPANYFACTS_URL_TMPL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

EQUITY_TAGS = ["StockholdersEquity"]
SHARES_TAGS = ["EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"]
SHARES_NAMESPACES = {"EntityCommonStockSharesOutstanding": "dei", "CommonStockSharesOutstanding": "us-gaap"}


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


def _extract_annual_equity(facts: dict) -> list:
    for tag in EQUITY_TAGS:
        units = facts.get("us-gaap", {}).get(tag, {}).get("units", {})
        entries = units.get("USD")
        if not entries:
            continue
        cleaned = [
            {"end": e.get("end"), "val": e.get("val"), "filed": e.get("filed"), "fy": e.get("fy")}
            for e in entries
            if e.get("end") and e.get("val") is not None and e.get("filed")
            and e.get("fp") == "FY" and e.get("form") in ("10-K", "10-K/A")
        ]
        if cleaned:
            return cleaned
    return []


def _extract_annual_shares(facts: dict) -> list:
    for tag in SHARES_TAGS:
        ns = SHARES_NAMESPACES[tag]
        units = facts.get(ns, {}).get(tag, {}).get("units", {})
        entries = units.get("shares")
        if not entries:
            continue
        cleaned = [
            {"end": e.get("end"), "val": e.get("val"), "filed": e.get("filed"), "fy": e.get("fy")}
            for e in entries
            if e.get("end") and e.get("val") is not None and e.get("filed")
            and e.get("form") in ("10-K", "10-K/A")
        ]
        if cleaned:
            return cleaned
    return []


def fetch_value_factor_for_cik(cik: str) -> dict:
    url = COMPANYFACTS_URL_TMPL.format(cik=cik)
    try:
        resp = sec_get(url)
    except requests.RequestException as exc:
        return {"error": f"natverksfel: {exc}"}

    if resp.status_code == 404:
        return {"error": "404: ingen companyfacts-data"}
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}"}

    try:
        data = resp.json()
    except ValueError:
        return {"error": "ogiltigt JSON-svar"}

    facts = data.get("facts", {})
    equity = _extract_annual_equity(facts)
    shares = _extract_annual_shares(facts)

    if not equity or not shares:
        return {"error": f"saknar data (equity={bool(equity)}, shares={bool(shares)})"}

    return {"stockholders_equity": equity, "shares_outstanding": shares}


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
    print(f"Hamtar vardefaktor-data for {total} tickers "
          f"({N_WORKERS} parallella arbetare, delad hastighetsspärr pa 8 NYA anrop/sek totalt)...\n")

    n_ok, n_err = 0, 0
    with OUTPUT_FILE.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=N_WORKERS) as executor:
            futures = {executor.submit(fetch_value_factor_for_cik, cik): (ticker, cik) for ticker, cik in remaining}
            for i, future in enumerate(as_completed(futures), 1):
                ticker, cik = futures[future]
                result = future.result()
                row = {"ticker": ticker, "cik": cik}
                if "stockholders_equity" in result:
                    row["stockholders_equity"] = result["stockholders_equity"]
                    row["shares_outstanding"] = result["shares_outstanding"]
                    n_ok += 1
                else:
                    row["stockholders_equity"] = []
                    row["shares_outstanding"] = []
                    row["error"] = result["error"]
                    n_err += 1
                out.write(json.dumps(row) + "\n")
                out.flush()

                if i % 200 == 0 or i == total:
                    print(f"  [{i}/{total}] klara ({n_ok} med data, {n_err} utan/fel)")

    print(f"\nKLART. {n_ok} tickers med vardefaktor-data, {n_err} utan. Sparat till {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
