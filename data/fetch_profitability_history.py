"""
Kvalitet/lönsamhet-hypotesen - datahamtning: arliga OperatingIncomeLoss
och Assets per ticker, via SEC EDGAR companyfacts-API:et (samma monster
som fetch_eps_history.py, HYP-020).

VARFOR OperatingIncomeLoss/Assets och INTE Novy-Marx bruttovinst
(GrossProfit/Assets): genomlyst 2026-07-31 pa ett stickprov av 40
tickers - GrossProfit-taggen finns direkt hos bara 25% av bolagen, och
att rekonstruera den via Revenues-COGS raddar den inte (COGS-varianter
lika glest taggade). OperatingIncomeLoss har 75% tacking, Assets 90% -
tillrackligt praktiskt anvandbart, och nara Fama-French RMW-metodiken
(rorelselonsamhet), inte en urvattnad kompromiss.

VARFOR ARSVIS (10-K, fp="FY") och INTE kvartalsvis som EPS/SUE-pipen:
kvalitet/lonsamhet ar en NIVA-signal (hur lonsamt ar bolaget i grunden),
inte en overraskningssignal som SUE - akademisk praxis (Novy-Marx,
Fama-French) anvander arliga bokslutsdata. Enklare an att rekonstruera
TTM fran kvartalsdata, och undviker sasongsmonster i kvartalsvisa
rorelseresultat.

Aterananvander samma ticker->CIK-mappning som EPS-pipen
(data/cache/smallcap_classification.jsonl). Ett API-anrop per bolag
hamtar BADA taggarna samtidigt (samma companyfacts-svar).

Output: data/cache/profitability_by_ticker.jsonl - en rad JSON per
ticker:
  {"ticker":.., "cik":.., "operating_income":[{"end":.., "val":..,
   "filed":.., "fy":..}], "assets":[{"end":.., "val":.., "filed":..,
   "fy":..}]}
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
OUTPUT_FILE = CACHE_DIR / "profitability_by_ticker.jsonl"

USER_AGENT = "Kebbe Research jagerstromebbe01@gmail.com"
HEADERS = {"User-Agent": USER_AGENT}
COMPANYFACTS_URL_TMPL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

OPINC_TAGS = ["OperatingIncomeLoss"]
ASSETS_TAGS = ["Assets"]


class RateLimiter:
    """Samma monster som fetch_eps_history.py - delad, tradsaker
    hastighetsspärr, max N anrop/sekund globalt."""

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
    """Filtrerar till 10-K/fp=FY-observationer (arliga bokslutsvarden,
    INTE kvartalsdata) - se moduldocstring for motivering. En rad per
    fiskalar, med filingsdatum for att undvika framatblick."""
    for tag in tags:
        units = facts.get(tag, {}).get("units", {})
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


def fetch_profitability_for_cik(cik: str) -> dict:
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

    facts = data.get("facts", {}).get("us-gaap", {})
    operating_income = _extract_annual(facts, OPINC_TAGS)
    assets = _extract_annual(facts, ASSETS_TAGS)

    if not operating_income or not assets:
        return {"error": f"saknar data (opinc={bool(operating_income)}, assets={bool(assets)})"}

    return {"operating_income": operating_income, "assets": assets}


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
    print(f"Hamtar lonsamhetsdata for {total} tickers "
          f"({N_WORKERS} parallella arbetare, delad hastighetsspärr pa 8 NYA anrop/sek totalt)...\n")

    n_ok, n_err = 0, 0
    with OUTPUT_FILE.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=N_WORKERS) as executor:
            futures = {executor.submit(fetch_profitability_for_cik, cik): (ticker, cik) for ticker, cik in remaining}
            for i, future in enumerate(as_completed(futures), 1):
                ticker, cik = futures[future]
                result = future.result()
                row = {"ticker": ticker, "cik": cik}
                if "operating_income" in result:
                    row["operating_income"] = result["operating_income"]
                    row["assets"] = result["assets"]
                    n_ok += 1
                else:
                    row["operating_income"] = []
                    row["assets"] = []
                    row["error"] = result["error"]
                    n_err += 1
                out.write(json.dumps(row) + "\n")
                out.flush()

                if i % 200 == 0 or i == total:
                    print(f"  [{i}/{total}] klara ({n_ok} med data, {n_err} utan/fel)")

    print(f"\nKLART. {n_ok} tickers med lonsamhetsdata, {n_err} utan. Sparat till {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
