"""
Feasibility-/tackningskontroll for SEC Form 4-insiderdata (2026-08-01),
FORE nagon hypotes skrivs - samma disciplin som tidigare pivot-checkar
denna sasong (lonsamhets-/vardefaktor-feasibility).

FRAGA: kan vi bygga "nettoinsiderkop (kod P), trailing 60-90 dagar,
normaliserat pa borsvarde, topp-decilen" for vart small-cap-universum?

KALLA: SEC:s kvartalsvisa strukturerade Form 3/4/5-dataset (INTE samma
endpoint som companyfacts XBRL som redan anvands for lonsamhet/varde -
det var ursprungliga blockeraren, se CLAUDE.md/minnesanteckning
2026-07-31). Gratis, ingen API-nyckel, samma User-Agent-konvention som
sec_edgar_adapter.py. Kvartalsvisa ZIP-filer fran 2006q1 till idag -
https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets

Detta ar ENDAST en feasibility-check - INGEN hypotes, INGEN
pass_fail_criterion, INGEN K-kostnad, skriver INGET till
research/hypothesis_registry/. Testar tva kvartal som spanner
projektets 2011-2024-fonster: ett tidigt (2012q2, stort universum) och
ett sent (2023q1, tunnare universum efter kand datatunning).
"""

import zipfile
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).resolve().parent
CACHE_DIR = DATA_DIR / "cache"
UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_by_month.json"
SCRATCH_DIR = DATA_DIR / "cache" / "form4_feasibility_scratch"

USER_AGENT = "smallcap-edge-lab research echo.officialproject@gmail.com"
BASE_URL = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{q}_form345.zip"

TEST_QUARTERS = [
    ("2012q2", "2012-06-30"),  # tidigt, stort universum (kand datatunning senare)
    ("2023q1", "2023-03-31"),  # sent, tunnare universum
]


def download_quarter(q: str) -> Path:
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = SCRATCH_DIR / f"{q}_form345.zip"
    extract_dir = SCRATCH_DIR / q
    if extract_dir.exists():
        return extract_dir
    resp = requests.get(BASE_URL.format(q=q), headers={"User-Agent": USER_AGENT}, timeout=120)
    resp.raise_for_status()
    zip_path.write_bytes(resp.content)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(extract_dir)
    return extract_dir


def check_quarter(q: str, universe_month_key: str, universe_by_month: dict) -> dict:
    extract_dir = download_quarter(q)

    sub = pd.read_csv(extract_dir / "SUBMISSION.tsv", sep="\t",
                       usecols=["ACCESSION_NUMBER", "ISSUERTRADINGSYMBOL"])
    nd = pd.read_csv(extract_dir / "NONDERIV_TRANS.tsv", sep="\t",
                      usecols=["ACCESSION_NUMBER", "TRANS_CODE", "TRANS_FORM_TYPE",
                               "TRANS_ACQUIRED_DISP_CD", "TRANS_PRICEPERSHARE", "TRANS_SHARES"])

    p = nd[(nd["TRANS_CODE"] == "P") & (nd["TRANS_FORM_TYPE"] == 4)]
    merged = p.merge(sub, on="ACCESSION_NUMBER", how="left")

    universe = set(universe_by_month.get(universe_month_key, []))
    merged_tickers = set(merged["ISSUERTRADINGSYMBOL"].dropna().unique())
    overlap = merged_tickers & universe
    in_universe = merged[merged["ISSUERTRADINGSYMBOL"].isin(universe)]

    return {
        "quarter": q,
        "universe_month": universe_month_key,
        "universe_size": len(universe),
        "total_p_transactions_all_issuers": len(p),
        "n_universe_tickers_with_p_txn": len(overlap),
        "pct_universe_with_p_txn": len(overlap) / len(universe) if universe else None,
        "n_p_txn_rows_in_universe": len(in_universe),
        "null_ticker_rows": int(merged["ISSUERTRADINGSYMBOL"].isna().sum()),
        "null_price_rows": int(p["TRANS_PRICEPERSHARE"].isna().sum()),
        "acquired_disp_code_check": p["TRANS_ACQUIRED_DISP_CD"].value_counts().to_dict(),
    }


def main():
    import json
    with UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_by_month = json.load(f)

    print("SEC Form 4 (öppna marknadsköp, kod P) - feasibility mot small-cap-universumet\n")
    results = []
    for q, month_key in TEST_QUARTERS:
        print(f"--- {q} (universum {month_key}) ---")
        r = check_quarter(q, month_key, universe_by_month)
        results.append(r)
        print(f"  Universumstorlek: {r['universe_size']}")
        print(f"  Totalt P-transaktioner (alla emittenter, hela SEC): {r['total_p_transactions_all_issuers']}")
        print(f"  Universum-tickers med >=1 P-transaktion: {r['n_universe_tickers_with_p_txn']} "
              f"({r['pct_universe_with_p_txn']:.1%})")
        print(f"  P-transaktions-RADER inom universumet: {r['n_p_txn_rows_in_universe']}")
        print(f"  Null ticker/pris-rader (dataglapp): {r['null_ticker_rows']}/{r['null_price_rows']}")
        print(f"  TRANS_ACQUIRED_DISP_CD-koll (ska vara ~allt 'A'): {r['acquired_disp_code_check']}\n")

    return results


if __name__ == "__main__":
    main()
