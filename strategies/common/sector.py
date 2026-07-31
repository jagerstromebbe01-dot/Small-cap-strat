"""
Bank-/finanssektor-klassificering, tva metoder:

1. load_bank_financial_flags() - grov, reproducerbar klassificering
   baserad pa ticker-namn (nyckelord). Samma metod som anvandes for att
   upptacka HYP-017:s 27.3%-mot-7.0%-branschkoncentrationsfynd (se
   research/hypothesis_registry/HYP-017-spy-krasch-overlay-idio-vol.yaml,
   "ALLVARLIGT NEGATIVT"-avsnittet). Anvands av HYP-022/023/030:s LASTA,
   redan rapporterade resultat - ANDRAS INTE.

2. load_bank_financial_flags_sic() - formell SEC-klassificering (SIC-kod,
   fran SEC EDGAR submissions-API:et, data/fetch_sic_classification.py).
   Tillagd 2026-07-31 som en robusthetskontroll (INGEN K-kostnad, andrar
   INGET last resultat) - haller HYP-023 om vi hade anvant SIC i stallet
   for nyckelord? SIC 6000-6799 = "Finance, Insurance, And Real Estate"
   (Division H) - samma BREDD som nyckelordslistan (bancorp/bank/savings/
   thrift/financial/trust tacker mer an bara rena banker).
"""

import json
from pathlib import Path

COMMON_DIR = Path(__file__).resolve().parent
DATA_DIR = COMMON_DIR.parent.parent / "data"
CLASSIFICATION_FILE = DATA_DIR / "cache" / "smallcap_classification.jsonl"
SIC_CLASSIFICATION_FILE = DATA_DIR / "cache" / "sic_classification.jsonl"

BANK_FINANCIAL_KEYWORDS = ("bancorp", "savings", "bank", "thrift", "financial", "trust")
SIC_FINANCE_RANGE = (6000, 6799)


def load_ticker_names() -> dict:
    """ticker -> bolagsnamn, fran data/cache/smallcap_classification.jsonl."""
    names = {}
    with CLASSIFICATION_FILE.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            names[d["ticker"]] = d.get("name", "")
    return names


def is_bank_financial_name(name: str) -> bool:
    n = (name or "").lower()
    return any(kw in n for kw in BANK_FINANCIAL_KEYWORDS)


def load_bank_financial_flags(tickers) -> dict:
    """ticker -> bool (True om bolagsnamnet matchar bank-/finansnyckelord).
    Tickers utan namn-entry i klassificeringsfilen klassas som False
    (samma begransning som redan galler for den ursprungliga
    27.3%-mot-7.0%-diagnosen - okand namn kan inte klassificeras)."""
    names = load_ticker_names()
    return {t: is_bank_financial_name(names.get(t, "")) for t in tickers}


def load_ticker_sic() -> dict:
    """ticker -> SIC-kod (int) eller None, fran
    data/cache/sic_classification.jsonl (SEC EDGAR submissions-API)."""
    sic_map = {}
    with SIC_CLASSIFICATION_FILE.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            sic = d.get("sic")
            sic_map[d["ticker"]] = int(sic) if sic else None
    return sic_map


def load_bank_financial_flags_sic(tickers) -> dict:
    """ticker -> bool, baserat pa formell SIC-kod (6000-6799, "Finance,
    Insurance, And Real Estate") i stallet for nyckelordsmatchning.
    Tickers utan kand SIC-kod klassas som False (samma begransning som
    nyckelordsmetoden)."""
    sic_map = load_ticker_sic()
    lo, hi = SIC_FINANCE_RANGE
    return {t: (sic_map.get(t) is not None and lo <= sic_map[t] <= hi) for t in tickers}
