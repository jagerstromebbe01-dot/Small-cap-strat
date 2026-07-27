"""
Full-skalig CIK-matchning + aktieantal-hämtning för HELA EODHD-
tickeruniversumet (~32 000, inkl. avlistade), via SEC EDGAR - HELT
SEPARAT från EODHD-prishämtningen (rör inte eodhd_adapter.py, gör inga
EODHD-prisanrop alls i detta skript).

STEG SOM GENOMFÖRS HÄR (1, 2, 6 i CEO:s numrering 2026-07-27):
  1. CIK-matchning: company_tickers.json (exakt ticker) i första hand,
     cik-lookup-data.txt (namnmatchning, redan cachad lokalt) som
     fallback för de som saknas där (typiskt avlistade bolag).
  2. Utestående aktier via XBRL frames-API, BÅDA taggarna
     (us-gaap:CommonStockSharesOutstanding och
     dei:EntityCommonStockSharesOutstanding), hämtat EN gång per
     kvartal 2010-2024 (120 anrop totalt, inte per ticker - frames
     returnerar ALLA bolag som rapporterat för perioden i ett svar).
  6. Sammanfattning grupperad per feltyp.

STEG SOM MEDVETET SKJUTS UPP (INTE körda här - se rapport i chatten):
  3. formerNames via submissions.json - kräver ETT anrop PER matchad
     CIK. Att köra det för alla (potentiellt >20 000) matchade CIK:er
     nu, INNAN det är klart om/hur prissökning (steg 4) ens ska ske,
     vore 2-3 timmars SEC-anrop för data vi ännu inte kan använda.
     Funktionen är byggd (get_former_names nedan) men anropas inte i
     full skala i detta skript - körs separat när prismatchning
     faktiskt ska ske.
  4-5. Börsvärde = aktier x pris, och filtrering till $100M-$2B - kräver
     EODHD-prisdata som INTE finns cachad (kontrollerat: data/cache/
     innehåller bara SEC-lookupen). Se rapport i chatten för exakt
     antal tickers detta skulle beröra.

Hastighetsspärr: max 8 anrop/sekund till sec.gov/data.sec.gov, GLOBALT
över hela skriptet (en enda delad RateLimiter-instans, inte "8/sek per
funktion") - klart under SEC:s bekräftade gräns på 10/sek per IP.

Output: data/cache/smallcap_classification.jsonl - en rad JSON per
EODHD-ticker, skriven LÖPANDE (inte allt i minnet och skrivet på
slutet) så ett avbrott inte förlorar redan klart arbete.
"""

import json
import re
import sys
import threading
import time
from pathlib import Path

import requests

from eodhd_adapter import get_us_tickers
from sec_edgar_adapter import CACHE_DIR, _normalize, find_cik_candidates, load_cik_lookup

USER_AGENT = "Kebbe Research jagerstromebbe01@gmail.com"
HEADERS = {"User-Agent": USER_AGENT}

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FRAMES_URL_TMPL = "https://data.sec.gov/api/xbrl/frames/{taxonomy}/{tag}/shares/{period}.json"
SUBMISSIONS_URL_TMPL = "https://data.sec.gov/submissions/CIK{cik}.json"

SHARES_TAGS = [
    ("us-gaap", "CommonStockSharesOutstanding"),
    ("dei", "EntityCommonStockSharesOutstanding"),
]

QUARTERS = [f"CY{year}Q{q}I" for year in range(2010, 2025) for q in range(1, 5)]

OUTPUT_FILE = CACHE_DIR / "smallcap_classification.jsonl"


class RateLimiter:
    """Delad, trådsäker hastighetsspärr - max N anrop/sekund, GLOBALT
    över alla funktioner som pratar med sec.gov i detta skript."""

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


sec_rate_limiter = RateLimiter(8.0)  # klart under SEC:s 10/sek-gräns


def sec_get(url: str, timeout: int = 30):
    sec_rate_limiter.wait()
    return requests.get(url, headers=HEADERS, timeout=timeout)


def fetch_company_tickers() -> dict:
    resp = sec_get(COMPANY_TICKERS_URL)
    resp.raise_for_status()
    data = resp.json()
    return {v["ticker"]: str(v["cik_str"]).zfill(10) for v in data.values()}


def fetch_all_frames() -> dict:
    """
    Hämtar utestående aktier för ALLA bolag, alla kvartal 2010-2024,
    båda XBRL-taggarna. 120 anrop totalt (60 kvartal x 2 taggar), inte
    32 000 - frames returnerar hela universumet per anrop.

    Returnerar dict: cik (10 siffror, zero-padded) -> sorterad lista av
    {"date": ..., "shares": ..., "tag": "us-gaap"|"dei"}.
    """
    by_cik: dict = {}
    total_calls = len(QUARTERS) * len(SHARES_TAGS)
    call_n = 0

    for taxonomy, tag in SHARES_TAGS:
        for period in QUARTERS:
            call_n += 1
            url = FRAMES_URL_TMPL.format(taxonomy=taxonomy, tag=tag, period=period)
            try:
                resp = sec_get(url)
            except requests.RequestException as exc:
                print(f"  [{call_n}/{total_calls}] {taxonomy}:{tag} {period}: nätverksfel {exc}, hoppar över")
                continue
            if resp.status_code == 404:
                # Vanligt för tidiga kvartal/taggar utan rapporterade värden - inte ett fel
                continue
            if resp.status_code != 200:
                print(f"  [{call_n}/{total_calls}] {taxonomy}:{tag} {period}: HTTP {resp.status_code}, hoppar över")
                continue

            try:
                rows = resp.json().get("data", [])
            except ValueError:
                print(f"  [{call_n}/{total_calls}] {taxonomy}:{tag} {period}: ogiltigt JSON-svar, hoppar över")
                continue

            for row in rows:
                cik = str(row.get("cik", "")).zfill(10)
                end = row.get("end")
                val = row.get("val")
                if not cik or not end or val is None:
                    continue
                by_cik.setdefault(cik, []).append({"date": end, "shares": val, "tag": taxonomy})

            if call_n % 20 == 0:
                print(f"  [{call_n}/{total_calls}] frames hämtade, {len(by_cik)} unika CIK:er hittills")

    for cik in by_cik:
        by_cik[cik] = sorted(by_cik[cik], key=lambda r: r["date"])

    return by_cik


def get_former_names(cik: str) -> dict:
    """
    STEG 3 (medvetet EJ anropad i full skala i detta skript, se
    modul-docstring). Byggd och testbar separat: hämtar
    submissions.json för en CIK, returnerar aktuell(a) ticker(s) och
    formerNames med datumintervall.
    """
    url = SUBMISSIONS_URL_TMPL.format(cik=cik)
    resp = sec_get(url)
    if resp.status_code == 404:
        return {"tickers": [], "formerNames": []}
    resp.raise_for_status()
    data = resp.json()
    return {
        "tickers": data.get("tickers", []),
        "formerNames": data.get("formerNames", []),
    }


def resolve_cik(ticker: str, name: str, exact_ticker_lookup: dict, name_lookup: dict, frames_by_cik: dict) -> dict:
    """
    Robust CIK-matchning i tre steg, faller aldrig bakåt in i en
    exception - se try/except runt varje anrop i main().

    Returnerar {"cik": str|None, "source": str, "candidates": [...]}
    """
    cik = exact_ticker_lookup.get(ticker)
    if cik:
        return {"cik": cik, "source": "company_tickers.json (exakt ticker)", "candidates": []}

    key = _normalize(name)
    exact = name_lookup.get(key, [])

    if len(exact) == 1:
        return {"cik": exact[0][1], "source": "cik-lookup-data.txt (exakt namn)", "candidates": []}

    if len(exact) > 1:
        in_frames = [(raw, c) for raw, c in exact if c in frames_by_cik]
        if len(in_frames) == 1:
            return {
                "cik": in_frames[0][1],
                "source": "cik-lookup-data.txt (disambiguerad via frames-data)",
                "candidates": exact,
            }
        return {"cik": None, "source": "ambiguous_exact_name", "candidates": exact}

    substring = find_cik_candidates(name, name_lookup)
    if substring:
        return {"cik": None, "source": "ambiguous_substring", "candidates": substring}

    return {"cik": None, "source": "no_candidates", "candidates": []}


def main() -> int:
    CACHE_DIR.mkdir(exist_ok=True)

    print("--- Full-skalig SEC-klassificering av EODHD-universumet ---\n")

    print("1) Hämtar EODHD-tickerlista (ett anrop, inte prisdata)...")
    tickers = get_us_tickers(include_delisted=True)
    print(f"   {len(tickers)} tickers.\n")

    print("2) Hämtar company_tickers.json (exakt ticker->CIK, aktiva bolag)...")
    exact_ticker_lookup = fetch_company_tickers()
    print(f"   {len(exact_ticker_lookup)} tickers.\n")

    print("3) Laddar cik-lookup-data.txt (redan cachad lokalt, ingen ny nedladdning)...")
    name_lookup = load_cik_lookup()
    print(f"   {sum(len(v) for v in name_lookup.values())} bolagsposter.\n")

    print(f"4) Hämtar frames-data: {len(QUARTERS)} kvartal x {len(SHARES_TAGS)} taggar = {len(QUARTERS)*len(SHARES_TAGS)} anrop...")
    frames_by_cik = fetch_all_frames()
    print(f"   Klart: {len(frames_by_cik)} unika CIK:er med minst en aktieobservation 2010-2024.\n")

    print("5) Klassificerar alla tickers (CIK-matchning + aktieantal-koppling)...\n")

    error_counts: dict = {}
    resolved_count = 0
    shares_found_count = 0

    with OUTPUT_FILE.open("w", encoding="utf-8") as out:
        for i, row in enumerate(tickers, start=1):
            code = row.get("Code", "")
            name = row.get("Name", "")

            record = {"ticker": code, "name": name}
            try:
                match = resolve_cik(code, name, exact_ticker_lookup, name_lookup, frames_by_cik)
                record.update(match)

                if match["cik"] is None:
                    record["status"] = f"no_cik:{match['source']}"
                    error_counts[record["status"]] = error_counts.get(record["status"], 0) + 1
                else:
                    resolved_count += 1
                    shares_history = frames_by_cik.get(match["cik"], [])
                    if shares_history:
                        shares_found_count += 1
                        record["shares_outstanding_history"] = shares_history
                        record["status"] = "ok"
                    else:
                        record["shares_outstanding_history"] = []
                        record["status"] = "cik_found_no_shares_data"
                        error_counts[record["status"]] = error_counts.get(record["status"], 0) + 1
            except Exception as exc:  # robust: logga och fortsätt, stanna aldrig
                record["status"] = f"unexpected_error:{type(exc).__name__}"
                record["error_detail"] = str(exc)
                error_counts[record["status"]] = error_counts.get(record["status"], 0) + 1

            out.write(json.dumps(record, ensure_ascii=False) + "\n")

            if i % 2000 == 0:
                print(f"   ... {i}/{len(tickers)} klassificerade ({resolved_count} med CIK, {shares_found_count} med aktiedata)")

    print(f"\n--- KLART: {len(tickers)} tickers klassificerade ---")
    print(f"Output: {OUTPUT_FILE}\n")

    print(f"CIK hittad:                          {resolved_count}/{len(tickers)} ({resolved_count/len(tickers)*100:.1f}%)")
    print(f"CIK + aktiedata (redo för prissteg):  {shares_found_count}/{len(tickers)} ({shares_found_count/len(tickers)*100:.1f}%)")
    print(f"\nFelkategorier ({len(tickers) - shares_found_count} tickers som INTE fick fullständig klassificering):")
    for status, count in sorted(error_counts.items(), key=lambda x: -x[1]):
        print(f"  {status:45s}: {count:6d}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
