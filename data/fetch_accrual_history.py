"""
Accrual-anomalin (BATCH-004, HYP-097-100) - datahamtning: arliga
NetIncomeLoss, NetCashProvidedByUsedInOperatingActivities OCH Assets
per ticker, via SEC EDGAR companyfacts-API:et.

SAMMA MONSTER som fetch_issuance_history.py/fetch_buyback_history.py
(redan korda mot hela small-cap-universumet, 5162 tickers med matchad
CIK) - ateranvander samma ticker->CIK-mappning, samma hastighetsspärr,
samma arsvis/FY-filtrering (undviker XBRL:s kumulativa-kvartalsvarde-
fallgrop, samma motivering som redan etablerad).

Assets-taggens tackning ar EJ verifierad i forvag (flaggat i HYP-097s
registerpost) - denna korning rapporterar tackningsgraden explicit i
slututskriften istallet for att tyst anta den ar bra.

Output: data/cache/accrual_by_ticker.jsonl - en rad JSON per ticker:
  {"ticker":.., "cik":.., "income":[...], "cfo":[...], "assets":[...]}
  varje lista: {"end":.., "val":.., "filed":.., "fy":.., "tag":..}
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
OUTPUT_FILE = CACHE_DIR / "accrual_by_ticker.jsonl"

USER_AGENT = "Kebbe Research jagerstromebbe01@gmail.com"
HEADERS = {"User-Agent": USER_AGENT}
COMPANYFACTS_URL_TMPL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

INCOME_TAGS = ["NetIncomeLoss"]
CFO_TAGS = ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]
ASSETS_TAGS = ["Assets"]


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


def _extract_annual(facts: dict, tags: list) -> list:
    for tag in tags:
        units = facts.get("us-gaap", {}).get(tag, {}).get("units", {})
        entries = units.get("USD")
        if not entries:
            continue
        cleaned = [
            {"end": e.get("end"), "val": e.get("val"), "filed": e.get("filed"), "fy": e.get("fy"), "tag": tag}
            for e in entries
            if e.get("end") and e.get("val") is not None and e.get("filed")
            and e.get("fp") == "FY" and e.get("form") in ("10-K", "10-K/A")
        ]
        if cleaned:
            return cleaned
    return []


def _extract_assets_instant(facts: dict, tags: list) -> list:
    """Assets ar en INSTANT-tagg (balansräkningspost, inget 'start'-fält,
    till skillnad fran NetIncomeLoss/CFO som ar DURATION-taggar over ett
    räkenskapsår) - filtreras pa fp=='FY' + form men INTE pa samma
    start/end-par-logik."""
    for tag in tags:
        units = facts.get("us-gaap", {}).get(tag, {}).get("units", {})
        entries = units.get("USD")
        if not entries:
            continue
        cleaned = [
            {"end": e.get("end"), "val": e.get("val"), "filed": e.get("filed"), "fy": e.get("fy"), "tag": tag}
            for e in entries
            if e.get("end") and e.get("val") is not None and e.get("filed")
            and e.get("fp") == "FY" and e.get("form") in ("10-K", "10-K/A")
        ]
        if cleaned:
            return cleaned
    return []


def fetch_accrual_for_cik(cik: str) -> dict:
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
    income = _extract_annual(facts, INCOME_TAGS)
    cfo = _extract_annual(facts, CFO_TAGS)
    assets = _extract_assets_instant(facts, ASSETS_TAGS)
    return {"income": income, "cfo": cfo, "assets": assets}


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
    print(f"Hamtar accrual-data for {total} tickers "
          f"({N_WORKERS} parallella arbetare, delad hastighetsspärr pa 8 anrop/sek)...\n")

    n_ok_all3, n_ok_partial, n_no_data, n_err = 0, 0, 0, 0
    with OUTPUT_FILE.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=N_WORKERS) as executor:
            futures = {executor.submit(fetch_accrual_for_cik, cik): (ticker, cik) for ticker, cik in remaining}
            for i, future in enumerate(as_completed(futures), 1):
                ticker, cik = futures[future]
                result = future.result()
                row = {"ticker": ticker, "cik": cik}
                if "income" in result:
                    row["income"] = result["income"]
                    row["cfo"] = result["cfo"]
                    row["assets"] = result["assets"]
                    if result["income"] and result["cfo"] and result["assets"]:
                        n_ok_all3 += 1
                    elif result["income"] and result["cfo"]:
                        n_ok_partial += 1
                    else:
                        n_no_data += 1
                else:
                    row["income"], row["cfo"], row["assets"] = [], [], []
                    row["error"] = result["error"]
                    n_err += 1
                out.write(json.dumps(row) + "\n")
                out.flush()

                if i % 200 == 0 or i == total:
                    print(f"  [{i}/{total}] klara ({n_ok_all3} med income+cfo+assets, "
                          f"{n_ok_partial} med income+cfo men ej assets, "
                          f"{n_no_data} utan tillrackligt, {n_err} fel)")

    print(f"\nKLART. {n_ok_all3} tickers med full data (income+cfo+assets), "
          f"{n_ok_partial} med income+cfo men INTE assets (paverkar HYP-097/098:s "
          f"tillgangs-skalning, INTE HYP-099/100:s marknadsvarde-skalning), "
          f"{n_no_data} utan tillrackligt, {n_err} fel. Sparat till {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
