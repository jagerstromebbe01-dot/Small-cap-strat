"""
Delad laddare for data/cache/sec_filing_index.jsonl (byggd av
data/fetch_sec_filing_index.py) - anvands av HYP-072 (dilution pipeline)
och HYP-073 (filing stress cascade). Ren strukturerad formtyp+item-kod-
metadata fran SEC submissions-API:et, ingen NLP.

Kopiera INTE denna fil per hypotes (samma princip som friction.py/
data_hygiene.py) - delad, generisk laddningslogik.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
FILING_INDEX_FILE = DATA_DIR / "cache" / "sec_filing_index.jsonl"

S3_FAMILY_FORMS = {"S-3", "S-3/A", "S-3ASR", "424B3", "424B5"}
NT_FORMS = {"NT 10-K", "NT 10-K/A", "NT 10-Q", "NT 10-Q/A"}
AMENDMENT_FORMS = {"10-K/A", "10-Q/A"}


def load_filing_index() -> dict:
    """ticker -> lista av {"form":.., "filingDate":.., "items":..}."""
    out = {}
    if not FILING_INDEX_FILE.exists():
        return out
    with FILING_INDEX_FILE.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row.get("filings"):
                out[row["ticker"]] = row["filings"]
    return out


def has_item(filing: dict, item_code: str) -> bool:
    items = filing.get("items") or ""
    return item_code in {c.strip() for c in items.split(",") if c.strip()}
