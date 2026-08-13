"""
HYP-020 (PEAD via SUE) - datahamtning: EPS-historik MED filingsdatum per
ticker, via SEC EDGAR companyfacts-API:et.

VARFOR INTE frames-API:et (som redan anvands for aktieantal i
build_smallcap_classification.py): testat 2026-07-30 - frames-svaret for
en resultatmatt (t.ex. EarningsPerShareBasic) innehaller INGET
filingsdatum, bara periodens start/slutdatum. For PEAD racker inte det -
hela poangen ar att handla vid det datum marknaden FICK VETA resultatet
(rapportdatum), inte periodens slutdatum (som ofta ligger 4-8 veckor
tidigare). companyfacts-API:et (per-CIK) HAR ett "filed"-falt, verifierat
mot AAPL:s riktiga data - men kraver ETT anrop per bolag, inte bulk.

Aterananvander den redan byggda och verifierade ticker->CIK-mappningen
(data/cache/smallcap_classification.jsonl, 19 032 av 32 371 EODHD-tickers
har en CIK) - loser INTE om CIK-matchning fran grunden. Hamtar bara for
tickers som NAGON GANG varit i small-cap-universumet
(smallcap_universe_by_month.json), inte alla 19 032 - onodigt for de
~14 000 som aldrig var i $100M-$2B-bandet.

Samma hastighetsspärr-monster (8 anrop/sek, delad RateLimiter) och samma
"skriv lopande" -monster (INTE allt i minnet, skrivet vid slutet) som
build_smallcap_classification.py - ett avbrott forlorar inte redan klart
arbete.

Output: data/cache/eps_by_ticker.jsonl - en rad JSON per ticker:
  {"ticker": ..., "cik": ..., "entries": [{"start":.., "end":.., "val":..,
   "filed":.., "fy":.., "fp":.., "form":..}, ...]}
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
OUTPUT_FILE = CACHE_DIR / "eps_by_ticker.jsonl"

USER_AGENT = "Kebbe Research jagerstromebbe01@gmail.com"
HEADERS = {"User-Agent": USER_AGENT}
COMPANYFACTS_URL_TMPL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

EPS_TAGS = ["EarningsPerShareBasic", "EarningsPerShareDiluted"]


class RateLimiter:
    """Samma monster som build_smallcap_classification.py - delad,
    tradsaker hastighetsspärr, max N anrop/sekund globalt."""

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
N_WORKERS = 8  # parallella arbetare - RateLimiter begransar fortfarande NYA anrop till 8/sek totalt, delat over alla


def sec_get(url: str, timeout: int = 30):
    sec_rate_limiter.wait()
    return requests.get(url, headers=HEADERS, timeout=timeout)


def load_universe_tickers() -> set:
    with UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_by_month = json.load(f)
    return {t for tickers in universe_by_month.values() for t in tickers}


def load_ticker_cik_map(universe_tickers: set) -> dict:
    """Filtrerar den redan byggda klassificeringsfilen till bara tickers
    som nagon gang varit i small-cap-universumet OCH har en CIK."""
    mapping = {}
    with CLASSIFICATION_FILE.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            ticker = row.get("ticker")
            cik = row.get("cik")
            if ticker in universe_tickers and cik:
                mapping[ticker] = cik
    return mapping


def fetch_eps_for_cik(cik: str) -> list:
    """Hamtar EPS-historik (bada taggarna, forsta som ger traffar vinner
    - samma fallback-monster som get_shares_outstanding_history) for en
    CIK. Returnerar ravarden (start/end/val/filed/fy/fp/form), en per
    rapporterad observation - SUE-berakningen (senare skript) avgor vilken
    som ar den URSPRUNGLIGA rapporten per kvartal."""
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
    for tag in EPS_TAGS:
        units = facts.get(tag, {}).get("units", {})
        entries = units.get("USD/shares") or units.get("USD-per-shares")
        if entries:
            cleaned = [
                {"start": e.get("start"), "end": e.get("end"), "val": e.get("val"),
                 "filed": e.get("filed"), "fy": e.get("fy"), "fp": e.get("fp"),
                 "form": e.get("form"), "tag": tag}
                for e in entries
                if e.get("end") and e.get("val") is not None and e.get("filed") and e.get("fp") != "FY"
            ]
            # fp != "FY" utesluter helarsrapporter (10-K:s EPS-varde tacker
            # 12 manader, inte ett enskilt kvartal - SUE ska jamfora
            # kvartal mot samma kvartal foregaende ar, inte blanda in
            # helarsvarden i samma serie).
            if cleaned:
                return {"entries": cleaned}
    return {"error": "ingen EPS-data i nagon tagg"}


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
    print(f"Hamtar EPS-historik for {total} tickers "
          f"({N_WORKERS} parallella arbetare, delad hastighetsspärr pa 8 NYA anrop/sek totalt)...\n")
    # VIKTIGT (upptackt 2026-07-30): varje companyfacts-svar tar ~1s att
    # ladda ner (1-4 MB, hela bolagets XBRL-fakta, inte bara EPS) - en
    # sekventiell loop ger darfor bara ~1 anrop/sek i praktiken oavsett
    # hastighetsspärrens 8/sek-tak, eftersom flaskhalsen ar svarstiden,
    # inte anropsfrekvensen. En liten tradpool later flera anrop vara
    # "i flykten" samtidigt - RateLimiter.wait() ar tradsaker (Lock) och
    # begransar fortfarande NYA anrop till 8/sek totalt, over alla
    # trådar - respekterar SEC:s gräns identiskt, bara utan att sitta
    # och vanta i onodan mellan varje.

    n_ok, n_err = 0, 0
    with OUTPUT_FILE.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=N_WORKERS) as executor:
            futures = {executor.submit(fetch_eps_for_cik, cik): (ticker, cik) for ticker, cik in remaining}
            for i, future in enumerate(as_completed(futures), 1):
                ticker, cik = futures[future]
                result = future.result()
                row = {"ticker": ticker, "cik": cik}
                if "entries" in result:
                    row["entries"] = result["entries"]
                    n_ok += 1
                else:
                    row["entries"] = []
                    row["error"] = result["error"]
                    n_err += 1
                out.write(json.dumps(row) + "\n")
                out.flush()

                if i % 200 == 0 or i == total:
                    print(f"  [{i}/{total}] klara ({n_ok} med data, {n_err} utan/fel)")

    print(f"\nKLART. {n_ok} tickers med EPS-data, {n_err} utan. Sparat till {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
