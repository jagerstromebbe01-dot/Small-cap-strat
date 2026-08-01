"""
HYP-035 - datahamtning: insiderkop (SEC Form 4, oppna marknadskop) per
ticker och filningsdatum, 2010q1-2024q4 (tacker FULL_START="2010-01-01"
som redan anvands av HYP-008/015/017/023/034).

KALLA: SEC:s kvartalsvisa strukturerade Form 3/4/5-dataset
(https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets)
- EN ANNAN endpoint an companyfacts-XBRL:n som redan anvands for
lonsamhet/varde/EPS (det var den ursprungliga blockeraren for
insiderhypotesen, se CLAUDE.md). Gratis, ingen API-nyckel. Se
data/test_sec_form4_feasibility.py for feasibility-verifieringen som
gjordes fore denna pipeline byggdes.

FILTER (laste i HYP-035:s pass_fail_criterion, INTE fritt):
  TRANS_CODE == 'P'              (oppet marknads-/privatkop)
  TRANS_FORM_TYPE == 4           (Form 4, INTE Form 5 - haller signalen
                                   snabb/aktuell, inte forsenad arsrapportering)
  TRANS_ACQUIRED_DISP_CD == 'A'  (bekraftar forvarv, inte avyttring -
                                   nagra fa TRANS_CODE=='P'-rader ar
                                   felkodade 'D', se feasibility-checken)
  TRANS_PRICEPERSHARE notna       (kan inte varderas annars)
  ISSUERTRADINGSYMBOL i small-cap-universumet (nagon gang)

LASER BARA SUBMISSION.tsv + NONDERIV_TRANS.tsv direkt ur varje ZIP (INTE
FOOTNOTES.tsv/DERIV_*.tsv/OWNER_SIGNATURE.tsv - onodiga for denna
signal, sparar bade tid och disk).

Output: data/cache/insider_purchases_p_code.csv - en rad per
kvalificerande transaktion:
  ticker, filing_date, trans_date, dollar_value, accession_number
FILING_DATE (INTE TRANS_DATE) ar det look-ahead-sakra datumet -
backtest-motorn far ALDRIG anvanda TRANS_DATE for att avgora synlighet.
"""

import io
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).resolve().parent
CACHE_DIR = DATA_DIR / "cache"
UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_by_month.json"
OUTPUT_FILE = CACHE_DIR / "insider_purchases_p_code.csv"
DONE_QUARTERS_FILE = CACHE_DIR / "insider_purchases_quarters_done.txt"

USER_AGENT = "smallcap-edge-lab research echo.officialproject@gmail.com"
BASE_URL = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{q}_form345.zip"
REQUEST_DELAY = 0.3

START_YEAR, END_YEAR = 2010, 2024


def quarters():
    for year in range(START_YEAR, END_YEAR + 1):
        for q in range(1, 5):
            yield f"{year}q{q}"


def load_universe_tickers() -> set:
    import json
    with UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_by_month = json.load(f)
    return {t for tickers in universe_by_month.values() for t in tickers}


def load_done_quarters() -> set:
    if not DONE_QUARTERS_FILE.exists():
        return set()
    return set(DONE_QUARTERS_FILE.read_text(encoding="utf-8").split())


def mark_quarter_done(q: str):
    with DONE_QUARTERS_FILE.open("a", encoding="utf-8") as f:
        f.write(q + "\n")


def process_quarter(q: str, universe_tickers: set) -> pd.DataFrame:
    resp = requests.get(BASE_URL.format(q=q), headers={"User-Agent": USER_AGENT}, timeout=180)
    time.sleep(REQUEST_DELAY)
    if resp.status_code == 404:
        print(f"  {q}: 404 (finns inte, hoppar over)")
        return pd.DataFrame()
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        with z.open("SUBMISSION.tsv") as f:
            sub = pd.read_csv(f, sep="\t", usecols=["ACCESSION_NUMBER", "FILING_DATE", "ISSUERTRADINGSYMBOL"])
        with z.open("NONDERIV_TRANS.tsv") as f:
            nd = pd.read_csv(f, sep="\t", usecols=["ACCESSION_NUMBER", "TRANS_CODE", "TRANS_DATE",
                                                     "TRANS_FORM_TYPE", "TRANS_ACQUIRED_DISP_CD",
                                                     "TRANS_SHARES", "TRANS_PRICEPERSHARE"])

    p = nd[(nd["TRANS_CODE"] == "P") & (nd["TRANS_FORM_TYPE"] == 4) &
           (nd["TRANS_ACQUIRED_DISP_CD"] == "A") & nd["TRANS_PRICEPERSHARE"].notna()]
    if p.empty:
        return pd.DataFrame()

    merged = p.merge(sub, on="ACCESSION_NUMBER", how="left")
    merged = merged[merged["ISSUERTRADINGSYMBOL"].isin(universe_tickers)]
    if merged.empty:
        return pd.DataFrame()

    merged["dollar_value"] = merged["TRANS_SHARES"] * merged["TRANS_PRICEPERSHARE"]
    out = merged.rename(columns={"ISSUERTRADINGSYMBOL": "ticker", "FILING_DATE": "filing_date",
                                  "TRANS_DATE": "trans_date", "ACCESSION_NUMBER": "accession_number"})
    return out[["ticker", "filing_date", "trans_date", "dollar_value", "accession_number"]]


def main():
    print("Laddar universum-tickers...")
    universe_tickers = load_universe_tickers()
    print(f"  {len(universe_tickers)} unika tickers.\n")

    CACHE_DIR.mkdir(exist_ok=True)
    done = load_done_quarters()
    all_quarters = list(quarters())
    remaining = [q for q in all_quarters if q not in done]
    print(f"{len(done)}/{len(all_quarters)} kvartal redan hamtade tidigare. "
          f"{len(remaining)} kvar ({START_YEAR}q1-{END_YEAR}q4).\n")

    file_exists = OUTPUT_FILE.exists()
    total_rows = 0
    for i, q in enumerate(remaining, 1):
        print(f"[{i}/{len(remaining)}] {q}...", end=" ")
        try:
            df = process_quarter(q, universe_tickers)
        except requests.RequestException as exc:
            print(f"NATVERKSFEL: {exc} - avbryter, kor om senare for att aterupptaga")
            break
        if not df.empty:
            df.to_csv(OUTPUT_FILE, mode="a", header=not file_exists, index=False)
            file_exists = True
            total_rows += len(df)
        print(f"{len(df)} kvalificerande rader inom universumet")
        mark_quarter_done(q)

    print(f"\nKLART denna korning. {total_rows} nya rader tillagda i {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
