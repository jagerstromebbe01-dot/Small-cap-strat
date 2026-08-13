"""
Aterkops-hypotesen (kandidat HYP-066) - datahamtning: arliga
PaymentsForRepurchaseOfCommonStock OCH aktieantal per ticker, via SEC
EDGAR companyfacts-API:et (samma monster som fetch_value_factor_history.py,
HYP-033).

VARFOR SAMMA XBRL-tagg-monster som B/M-faktorn: aterkopsintensitet
($ aterkopt / marknadsvarde, "buyback yield" - Boudoukh et al.
payout yield-traditionen) racker BADA aterkopsbelopp OCH aktieantal
fran SAMMA 10-K for att marknadsvardet ska raknas vid ratt tidpunkt,
samma princip som B/M-faktorns egen motivering.

VARFOR ARSVIS (10-K, fp="FY") och INTE kvartalsvis: undviker den kanda
XBRL-fallgropen att kvartalsvisa kassaflodesposter ofta rapporteras
KUMULATIVT (year-to-date) i 10-Q, inte som fristaende kvartalsvarden -
att decumulera korrekt for alla filers skulle vara ett eget, sarskilt
felkansligt delprojekt. Arsvarden (10-K) har inte denna tvetydighet.
Samma forenkling som HYP-024/033 redan valde av samma skal.

FLERA KANDIDATTAGGAR (till skillnad fran B/M-faktorns enda EQUITY_TAGS):
aterkop ar mindre standardiserat taggat an eget kapital - forsoker
PaymentsForRepurchaseOfCommonStock forst (vanligast, kassaflodesrakningen),
faller tillbaka pa StockRepurchasedAndRetiredDuringPeriodValue och
PaymentsForRepurchaseOfEquity om den forsta saknas.

Aterananvander samma ticker->CIK-mappning som EPS-/lonsamhet-/vardefaktor-
pipen (data/cache/smallcap_classification.jsonl).

Output: data/cache/buyback_by_ticker.jsonl - en rad JSON per ticker:
  {"ticker":.., "cik":.., "buybacks":[{"end":.., "val":.., "filed":..,
   "fy":.., "tag":..}], "shares_outstanding":[{"end":.., "val":..,
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
OUTPUT_FILE = CACHE_DIR / "buyback_by_ticker.jsonl"

USER_AGENT = "Kebbe Research jagerstromebbe01@gmail.com"
HEADERS = {"User-Agent": USER_AGENT}
COMPANYFACTS_URL_TMPL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

BUYBACK_TAGS = [
    "PaymentsForRepurchaseOfCommonStock",
    "StockRepurchasedAndRetiredDuringPeriodValue",
    "PaymentsForRepurchaseOfEquity",
]
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


def _extract_annual_buyback(facts: dict) -> list:
    for tag in BUYBACK_TAGS:
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


def fetch_buyback_for_cik(cik: str) -> dict:
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
    buybacks = _extract_annual_buyback(facts)
    shares = _extract_annual_shares(facts)

    if not shares:
        return {"error": f"saknar aktieantal (buybacks={bool(buybacks)})"}

    # OBS: tom buybacks-lista ar ett GILTIGT resultat (bolaget har aldrig
    # rapporterat aterkop under nagon 10-K) - INTE samma sak som ett fel.
    # Skiljs at har fran "saknar shares" (som AR ett datafel/otillrackligt).
    return {"buybacks": buybacks, "shares_outstanding": shares}


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
    print(f"Hamtar aterkopsdata for {total} tickers "
          f"({N_WORKERS} parallella arbetare, delad hastighetsspärr pa 8 NYA anrop/sek totalt)...\n")

    n_ok_with_buybacks, n_ok_no_buybacks, n_err = 0, 0, 0
    with OUTPUT_FILE.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=N_WORKERS) as executor:
            futures = {executor.submit(fetch_buyback_for_cik, cik): (ticker, cik) for ticker, cik in remaining}
            for i, future in enumerate(as_completed(futures), 1):
                ticker, cik = futures[future]
                result = future.result()
                row = {"ticker": ticker, "cik": cik}
                if "shares_outstanding" in result:
                    row["buybacks"] = result["buybacks"]
                    row["shares_outstanding"] = result["shares_outstanding"]
                    if result["buybacks"]:
                        n_ok_with_buybacks += 1
                    else:
                        n_ok_no_buybacks += 1
                else:
                    row["buybacks"] = []
                    row["shares_outstanding"] = []
                    row["error"] = result["error"]
                    n_err += 1
                out.write(json.dumps(row) + "\n")
                out.flush()

                if i % 200 == 0 or i == total:
                    print(f"  [{i}/{total}] klara ({n_ok_with_buybacks} med aterkop, "
                          f"{n_ok_no_buybacks} utan aterkop men med aktieantal, {n_err} fel/saknar data)")

    print(f"\nKLART. {n_ok_with_buybacks} tickers med minst ett rapporterat aterkop, "
          f"{n_ok_no_buybacks} utan aterkop (men med giltigt aktieantal), "
          f"{n_err} utan tillrackligt data. Sparat till {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
