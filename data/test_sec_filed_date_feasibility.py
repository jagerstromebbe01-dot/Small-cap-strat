"""
Feasibility-test (2026-08-05, INGEN pipeline-andring har - se
research/hypothesis_registry-diskussionen om look-ahead-risken i
build_smallcap_classification.py/build_universe_2025.py): kan vi hamta
det FAKTISKA filed-datumet for varje aktieantal-datapunkt utan att offra
frames-API:ets skalbarhet (120 bulkanrop for hela 2010-2024 istallet for
tusentals per-bolag-anrop)?

IDE: SEC:s kvartalsvisa "full-index"-filer (form.idx) listar VARJE
inlamning ett kvartal - CIK, formulartyp, Date Filed, och filnamnet
(som innehaller accession-numret i SAMMA format som frames-API:ets
"accn"-falt). En bulknedladdning per kvartal (~60 totalt for 2010-2024,
samma storleksordning som de 120 befintliga frames-anropen) racker for
att bygga en accn -> filed_date-uppslagning, UTAN per-bolag-anrop.

Detta skript testar BARA metoden pa ETT kvartal - bygger inget, andrar
inget i cachen. Om detta fungerar ar nasta steg (INTE gjort har) att
utoka fetch_all_frames() i build_smallcap_classification.py till att
ocksa spara "accn" per datapunkt, och lagga till motsvarande
form.idx-uppslagning.

Usage:
    python data/test_sec_filed_date_feasibility.py
"""

import re
import sys
import time
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent
USER_AGENT = "smallcap-edge-lab research echo.officialproject@gmail.com"

TEST_QUARTER = ("2015", "QTR1")
FRAMES_URL = "https://data.sec.gov/api/xbrl/frames/us-gaap/CommonStockSharesOutstanding/shares/CY2015Q1I.json"
FORM_IDX_URL_TMPL = "https://www.sec.gov/Archives/edgar/full-index/{year}/{qtr}/form.idx"

# Matchar "edgar/data/<cik>/<accession-med-bindestreck>.txt" i filnamns-kolumnen
FILENAME_RE = re.compile(r"edgar/data/(\d+)/([\d\-]+)\.txt")
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def fetch_form_idx_filed_dates(year: str, qtr: str) -> dict:
    """Returnerar {accession_number: filed_date} for ETT kvartal, byggt fran
    en enda bulknedladdning av form.idx - ingen per-bolag-fraga."""
    url = FORM_IDX_URL_TMPL.format(year=year, qtr=qtr)
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=120)
    resp.raise_for_status()

    accn_to_filed = {}
    for line in resp.text.splitlines():
        fname_match = FILENAME_RE.search(line)
        if not fname_match:
            continue
        accn = fname_match.group(2)
        date_match = DATE_RE.search(line)
        if not date_match:
            continue
        accn_to_filed[accn] = date_match.group(1)
    return accn_to_filed


def fetch_frames_sample(url: str) -> list:
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json().get("data", [])


def main():
    print(f"Steg 1: hamtar form.idx for {TEST_QUARTER[0]} {TEST_QUARTER[1]} (EN bulknedladdning)...")
    t0 = time.time()
    accn_to_filed = fetch_form_idx_filed_dates(*TEST_QUARTER)
    print(f"  {len(accn_to_filed):,} accession-nummer -> filed-datum extraherade pa {time.time()-t0:.1f}s\n")

    print("Steg 2: hamtar ett urval aktieantal-datapunkter (samma frames-endpoint "
          "som redan anvands i build_smallcap_classification.py)...")
    rows = fetch_frames_sample(FRAMES_URL)
    print(f"  {len(rows):,} datapunkter i CY2015Q1I (us-gaap:CommonStockSharesOutstanding)\n")

    print("Steg 3: matchar varje datapunkts accn mot form.idx-uppslagningen och "
          "jamfor mot period-slutdatumet (den siffra som anvands IDAG, buggen "
          "under diskussion)...\n")

    matched = 0
    unmatched = 0
    lags = []
    examples = []
    for row in rows:
        accn = row.get("accn")
        end = row.get("end")
        if not accn or not end:
            continue
        filed = accn_to_filed.get(accn)
        if filed is None:
            unmatched += 1
            continue
        matched += 1
        from datetime import date
        lag_days = (date.fromisoformat(filed) - date.fromisoformat(end)).days
        lags.append(lag_days)
        if len(examples) < 5:
            examples.append((row.get("entityName", "?"), end, filed, lag_days))

    print(f"RESULTAT: {matched:,} matchade, {unmatched:,} omatchade "
          f"({matched/(matched+unmatched):.1%} matchningsgrad)\n")

    if lags:
        lags.sort()
        n = len(lags)
        print(f"Eftersläpning (filed - periodslut), dagar:")
        print(f"  Min: {lags[0]}  Median: {lags[n//2]}  Max: {lags[-1]}  "
              f"Negativa (filed FORE periodslut, skulle vara konstigt): {sum(1 for x in lags if x < 0)}")
        print(f"\nExempel:")
        for name, end, filed, lag in examples:
            print(f"  {name[:40]:40s}  periodslut={end}  filed={filed}  eftersläpning={lag}d")

    print("\n" + "=" * 90)
    if matched / max(matched + unmatched, 1) > 0.8:
        print("SLUTSATS: METODEN AR GENOMFORBAR. Hog matchningsgrad, rimliga (positiva, "
              "typiska 10-Q/10-K-eftersläpningar pa nagra veckor-manader) tidsskillnader.")
        print("Nasta steg (KRAVER separat CEO-beslut om scope innan det byggs): utoka "
              "fetch_all_frames() att ocksa spara 'accn', ladda ner ~60 kvartalsvisa "
              "form.idx-filer for hela 2010-2024, bygga en fullstandig accn->filed_date-"
              "uppslagning, och bygga om smallcap_classification.jsonl/smallcap_universe_by_month.json "
              "med filed-datum istallet for periodslut. Detta paverkar universum-medlemskap "
              "for alla 39 redan testade hypoteser - kraver ett separat beslut om vilka (om "
              "nagra) som ska koras om.")
    else:
        print("SLUTSATS: LAG MATCHNINGSGRAD - metoden fungerar inte tillforlitligt som den "
              "star. Behover felsokas innan den byggs ut.")
    print("=" * 90)
    return 0


if __name__ == "__main__":
    sys.exit(main())
