"""
Bygger om 2025-universum-utökningen med FAKTISKT filed-datum istället för
periodslut-datum (kodgranskning 2026-08-05 - samma bugg som huvudserien,
se data/rebuild_smallcap_classification_filed_date.py, men enklare fix
här: companyfacts-endpointen (till skillnad från frames) innehåller redan
ett 'filed'-fält per post - det lästes bara aldrig).

SEPARAT FIL - rör INTE data/sec_edgar_adapter.py eller
data/build_universe_2025.py (de ursprungliga används fortfarande av
rebuild_current_universe.py och andra anropare; ändras inte här för att
undvika oavsiktliga sidoeffekter någon annanstans).

Output: data/cache/smallcap_universe_2025_extension_filed_date.json
"""

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_universe_2025 import (  # noqa: E402
    BAND_HIGH, BAND_LOW, MONTH_ENDS_2025, load_buffer_candidates, load_cik_map, load_price_at_or_before,
)
from sec_edgar_adapter import CACHE_DIR, COMPANYFACTS_URL, REQUEST_DELAY, USER_AGENT, shares_outstanding_at  # noqa: E402

OUTPUT_FILE = CACHE_DIR / "smallcap_universe_2025_extension_filed_date.json"


def get_shares_outstanding_history_filed_date(cik: str) -> list:
    """
    Identisk till sec_edgar_adapter.py::get_shares_outstanding_history(),
    MED buggfixen: sparar e['filed'] (faktiskt känt datum) som 'date',
    inte e['end'] (periodslut). companyfacts-endpointen innehåller redan
    'filed' per post (till skillnad från frames-endpointen som huvudserien
    använder, som saknar det helt - se rebuild_smallcap_classification_filed_date.py
    för den mer omständiga lösningen där).
    """
    headers = {"User-Agent": USER_AGENT}
    url = COMPANYFACTS_URL.format(cik=cik)
    resp = requests.get(url, headers=headers, timeout=30)
    time.sleep(REQUEST_DELAY)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    data = resp.json()

    facts = data.get("facts", {})
    for namespace, tag in (("dei", "EntityCommonStockSharesOutstanding"),
                           ("us-gaap", "CommonStockSharesOutstanding")):
        entries = facts.get(namespace, {}).get(tag, {}).get("units", {}).get("shares")
        if entries:
            history = sorted(
                ({"date": e["filed"], "period_end": e["end"], "shares": e["val"]}
                 for e in entries if e.get("filed") and e.get("end") and e.get("val")),
                key=lambda x: x["date"],
            )
            if history:
                return history
    return []


def main() -> int:
    print("Laddar kandidater (december 2024-marknadsvärde $20M-$10B)...")
    candidates = load_buffer_candidates()
    ticker_cik = load_cik_map(candidates)
    print(f"  {len(candidates)} kandidater, {len(ticker_cik)} med CIK.\n")

    print("Hämtar aktieantal-historik per bolag (SEC EDGAR companyfacts, MED filed-datum)...")
    shares_history = {}
    for i, (ticker, cik) in enumerate(sorted(ticker_cik.items()), 1):
        if i % 50 == 0 or i == len(ticker_cik):
            print(f"  ... {i}/{len(ticker_cik)}")
        try:
            hist = get_shares_outstanding_history_filed_date(cik)
        except Exception:
            hist = []
        if hist:
            shares_history[ticker] = hist
    print(f"  {len(shares_history)} bolag med användbar aktieantal-historik.\n")

    universe_by_month = {}
    for month_end in MONTH_ENDS_2025:
        eligible = []
        for ticker, hist in shares_history.items():
            entry = shares_outstanding_at(hist, month_end)
            if entry is None:
                continue
            price_date, price = load_price_at_or_before(ticker, month_end)
            if price is None:
                continue
            try:
                market_cap = float(price) * float(entry["shares"])
            except (TypeError, ValueError):
                continue
            if BAND_LOW <= market_cap <= BAND_HIGH:
                eligible.append(ticker)
        universe_by_month[month_end] = sorted(eligible)
        print(f"  {month_end}: {len(eligible)} bolag i $100M-$2B-bandet (filed-datum-korrigerat)")

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(universe_by_month, f, indent=2, ensure_ascii=False)

    print(f"\nKLART. Sparat till {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
