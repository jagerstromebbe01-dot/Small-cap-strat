"""
Bygger och cachar en accession-nummer -> faktiskt-inlämningsdatum-
uppslagning från SEC:s kvartalsvisa full-index-filer (form.idx).

BAKGRUND (kodgranskning 2026-08-05): data/build_smallcap_classification.py
och data/sec_edgar_adapter.py sparade tidigare periodSLUT-datum för varje
aktieantal-datapunkt, inte det datum bolaget FAKTISKT offentliggjorde det -
en look-ahead-bias (marknaden vet inte ett kvartalsslut-aktieantal förrän
veckor/månader senare). Se data/test_sec_filed_date_feasibility.py för den
bevisade metoden: SEC:s form.idx (en bulkfil per kvartal, CIK+formulärtyp+
Date Filed+filnamn för VARJE inlämning) ger filed-datum utan per-bolag-
anrop. Testat: ett enda nominellt kvartal gav bara 0.2% träffar (brutna
räkenskapsår gör att en datapunkts "frame"-kvartal ofta skiljer sig från
det kvartal den faktiskt lämnades in i) - med ett ±2-kvartals fönster steg
träffgraden till 85.8%, alla eftersläpningar positiva (inga look-ahead-
introducerande felmatchningar).

Denna modul bygger en STOR, engångs-cachad uppslagning över hela
2009-2025 (marginal runt 2010-2024-backtestperioden) - används av
data/rebuild_smallcap_classification_filed_date.py.
"""

import json
import re
import time
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent
CACHE_DIR = DATA_DIR / "cache"
LOOKUP_CACHE = CACHE_DIR / "sec_filed_dates_lookup.json"

USER_AGENT = "smallcap-edge-lab research echo.officialproject@gmail.com"
FORM_IDX_URL_TMPL = "https://www.sec.gov/Archives/edgar/full-index/{year}/{qtr}/form.idx"

FILENAME_RE = re.compile(r"edgar/data/(\d+)/([\d\-]+)\.txt")
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

START_YEAR = 2009  # marginal fore 2010, for brutna rakenskapsar som "lutar bakat"
END_YEAR = 2025    # marginal efter 2024, for sena Q4-rapporter som lamnas in in i 2025


def _quarters_range(start_year: int, end_year: int) -> list:
    return [(str(y), f"QTR{q}") for y in range(start_year, end_year + 1) for q in range(1, 5)]


def fetch_form_idx_filed_dates(year: str, qtr: str, max_retries: int = 4) -> dict:
    """Returnerar {accession_number: filed_date} för ETT kvartal - en enda
    bulknedladdning, ingen per-bolag-fråga.

    BUGGFIX (kodgranskning 2026-08-05): den ursprungliga versionen gjorde
    INGEN retry - en enda transient nätverksstörning (2013 QTR3 misslyckades
    med "Response ended prematurely" vid den första körningen) fick HELA det
    kvartalets ~150 000 filed-datum att saknas tyst, vilket i sin tur fick
    universum-diffen att visa ett kraftigt överdrivet medlemskapsbortfall
    just runt det kvartalet (bolag vars Q2-rapporter lämnades in då kunde
    inte matchas mot något filed-datum alls). Nu: exponentiell backoff,
    kastar vidare (stannar INTE tyst) om alla försök misslyckas - build_lookup
    nedan loggar då tydligt vilket kvartal som faktiskt saknas, istället för
    att bara fortsätta som om allt gick bra."""
    url = FORM_IDX_URL_TMPL.format(year=year, qtr=qtr)
    headers = {"User-Agent": USER_AGENT}

    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=120)
            resp.raise_for_status()
            text = resp.text
            break
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < max_retries:
                time.sleep(2 ** attempt)  # 2s, 4s, 8s
    else:
        raise RuntimeError(f"form.idx för {year} {qtr} misslyckades efter {max_retries} försök: {last_exc}")

    accn_to_filed = {}
    for line in text.splitlines():
        fname_match = FILENAME_RE.search(line)
        if not fname_match:
            continue
        accn = fname_match.group(2)
        date_match = DATE_RE.search(line)
        if not date_match:
            continue
        accn_to_filed[accn] = date_match.group(1)
    return accn_to_filed


def build_lookup(start_year: int = START_YEAR, end_year: int = END_YEAR, force_refresh: bool = False) -> dict:
    """Bygger (eller läser cachad) accn -> filed_date över hela intervallet.
    Cachas till disk eftersom detta är ~68 nedladdningar (några minuter) och
    inte behöver upprepas för varje körning av nedströms-skript."""
    if LOOKUP_CACHE.exists() and not force_refresh:
        with LOOKUP_CACHE.open("r", encoding="utf-8") as f:
            return json.load(f)

    lookup: dict = {}
    quarters = _quarters_range(start_year, end_year)
    failed_quarters = []
    print(f"  Bygger filed-datum-uppslagning: {len(quarters)} kvartal ({start_year}-{end_year})...")
    for i, (year, qtr) in enumerate(quarters, 1):
        t0 = time.time()
        try:
            d = fetch_form_idx_filed_dates(year, qtr)
            lookup.update(d)
        except (requests.RequestException, RuntimeError) as exc:
            # BUGGFIX (kodgranskning 2026-08-05): tidigare "hoppa över och
            # fortsätt" HÄR (utan retry på anropet ovan heller) lät en enda
            # transient nätverksstörning tyst radera ett helt kvartals
            # filed-datum - se fetch_form_idx_filed_dates ovan. Nu: retry
            # sker redan där, och om det ÄNDÅ misslyckas efter alla försök
            # är det inte längre "en förväntad enstaka lucka" - vi vägrar
            # cacha en ofullständig uppslagning tyst, se raise nedan.
            print(f"    [{i}/{len(quarters)}] {year} {qtr}: MISSLYCKADES efter retries ({exc})")
            failed_quarters.append(f"{year} {qtr}")
            continue
        print(f"    [{i}/{len(quarters)}] {year} {qtr}: {len(d):,} rader ({time.time()-t0:.1f}s, "
              f"{len(lookup):,} ackumulerat)")

    if failed_quarters:
        raise RuntimeError(
            f"build_lookup: {len(failed_quarters)} kvartal misslyckades även efter retries: "
            f"{failed_quarters} - vägrar cacha en ofullständig uppslagning tyst. Kör om, "
            f"eller undersök varför just dessa kvartal konsekvent felar."
        )

    CACHE_DIR.mkdir(exist_ok=True)
    with LOOKUP_CACHE.open("w", encoding="utf-8") as f:
        json.dump(lookup, f)
    print(f"  Klart: {len(lookup):,} accession-nummer, cachat till {LOOKUP_CACHE}")
    return lookup


if __name__ == "__main__":
    build_lookup(force_refresh=True)
