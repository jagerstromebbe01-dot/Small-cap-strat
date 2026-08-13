"""
Bygger OM smallcap_classification.jsonl med FAKTISKT filed-datum istället
för periodslut-datum för varje aktieantal-datapunkt (kodgranskning
2026-08-05 - se data/sec_filed_dates.py för metoden och
data/test_sec_filed_date_feasibility.py för valideringen).

SEPARAT FIL - rör INTE data/cache/smallcap_classification.jsonl (den
ursprungliga förblir grundsanningen tills ett explicit CEO-beslut om att
byta, efter att diff_smallcap_universe_filed_date.py visat omfattningen).

Output: data/cache/smallcap_classification_filed_date.jsonl
"""

import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_smallcap_classification import (  # noqa: E402
    FRAMES_URL_TMPL, QUARTERS, SHARES_TAGS, fetch_company_tickers, resolve_cik, sec_get,
)
from eodhd_adapter import get_us_tickers  # noqa: E402
from sec_edgar_adapter import CACHE_DIR, load_cik_lookup  # noqa: E402
from sec_filed_dates import build_lookup  # noqa: E402

OUTPUT_FILE = CACHE_DIR / "smallcap_classification_filed_date.jsonl"


def fetch_all_frames_with_accn() -> dict:
    """Identisk till build_smallcap_classification.py::fetch_all_frames(),
    MED tillägget att 'accn' (accession-nummer) sparas per datapunkt -
    krävs för filed-datum-matchningen. Kopierad, INTE importerad+patchad,
    för att aldrig riskera att påverka den ursprungliga funktionen."""
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
                continue
            if resp.status_code != 200:
                print(f"  [{call_n}/{total_calls}] {taxonomy}:{tag} {period}: HTTP {resp.status_code}, hoppar över")
                continue
            try:
                rows = resp.json().get("data", [])
            except ValueError:
                continue

            for row in rows:
                cik = str(row.get("cik", "")).zfill(10)
                end = row.get("end")
                val = row.get("val")
                accn = row.get("accn")
                if not cik or not end or val is None:
                    continue
                by_cik.setdefault(cik, []).append({"date": end, "shares": val, "tag": taxonomy, "accn": accn})

            if call_n % 20 == 0:
                print(f"  [{call_n}/{total_calls}] frames hämtade, {len(by_cik)} unika CIK:er hittills")

    for cik in by_cik:
        by_cik[cik] = sorted(by_cik[cik], key=lambda r: r["date"])
    return by_cik


def correct_dates_with_filed(by_cik: dict, accn_to_filed: dict) -> tuple:
    """
    Ersätter 'date' (periodslut) med det matchade filed-datumet. Datapunkter
    UTAN matchning UTESLUTS helt - hellre mindre data än data med känd fel
    (look-ahead-biasad) tidsstämpel. Behåller period_end separat för
    spårbarhet/felsökning.
    """
    matched, unmatched = 0, 0
    corrected: dict = {}
    for cik, points in by_cik.items():
        new_points = []
        for p in points:
            filed = accn_to_filed.get(p.get("accn"))
            if filed is None:
                unmatched += 1
                continue
            matched += 1
            new_points.append({"date": filed, "period_end": p["date"], "shares": p["shares"], "tag": p["tag"]})
        if new_points:
            corrected[cik] = sorted(new_points, key=lambda r: r["date"])
    return corrected, {"matched": matched, "unmatched": unmatched}


def main() -> int:
    CACHE_DIR.mkdir(exist_ok=True)
    print("--- Ombyggnad: small-cap-klassificering med FAKTISKT filed-datum ---\n")

    print("1) Hämtar EODHD-tickerlista...")
    tickers = get_us_tickers(include_delisted=True)
    print(f"   {len(tickers)} tickers.\n")

    print("2) Hämtar company_tickers.json...")
    exact_ticker_lookup = fetch_company_tickers()
    print(f"   {len(exact_ticker_lookup)} tickers.\n")

    print("3) Laddar cik-lookup-data.txt (redan cachad lokalt)...")
    name_lookup = load_cik_lookup()
    print(f"   {sum(len(v) for v in name_lookup.values())} bolagsposter.\n")

    print(f"4) Hämtar frames-data MED accession-nummer ({len(QUARTERS) * len(SHARES_TAGS)} anrop)...")
    frames_by_cik = fetch_all_frames_with_accn()
    print(f"   Klart: {len(frames_by_cik)} unika CIK:er.\n")

    print("5) Bygger/läser accn->filed_date-uppslagning (SEC form.idx, cachas)...")
    accn_to_filed = build_lookup()
    print(f"   {len(accn_to_filed):,} accession-nummer i uppslagningen.\n")

    print("6) Korrigerar varje datapunkt till faktiskt filed-datum...")
    corrected_by_cik, stats = correct_dates_with_filed(frames_by_cik, accn_to_filed)
    total = stats["matched"] + stats["unmatched"]
    print(f"   {stats['matched']:,}/{total:,} matchade ({stats['matched']/max(total,1):.1%}), "
          f"{stats['unmatched']:,} exkluderade (inget filed-datum hittat i fönstret).\n")

    print("7) Klassificerar alla tickers (samma CIK-matchningslogik som originalskriptet)...\n")
    error_counts: dict = {}
    resolved_count = 0
    shares_found_count = 0

    with OUTPUT_FILE.open("w", encoding="utf-8") as out:
        for i, row in enumerate(tickers, start=1):
            code = row.get("Code", "")
            name = row.get("Name", "")
            record = {"ticker": code, "name": name}
            try:
                # Disambiguering använder ORIGINAL frames_by_cik (oberoende av
                # filed-datum-matchning) - identisk semantik som originalskriptet.
                match = resolve_cik(code, name, exact_ticker_lookup, name_lookup, frames_by_cik)
                record.update(match)

                if match["cik"] is None:
                    record["status"] = f"no_cik:{match['source']}"
                    error_counts[record["status"]] = error_counts.get(record["status"], 0) + 1
                else:
                    resolved_count += 1
                    shares_history = corrected_by_cik.get(match["cik"], [])
                    if shares_history:
                        shares_found_count += 1
                        record["shares_outstanding_history"] = shares_history
                        record["status"] = "ok"
                    else:
                        record["shares_outstanding_history"] = []
                        record["status"] = "cik_found_no_shares_data"
                        error_counts[record["status"]] = error_counts.get(record["status"], 0) + 1
            except Exception as exc:
                record["status"] = f"unexpected_error:{type(exc).__name__}"
                record["error_detail"] = str(exc)
                error_counts[record["status"]] = error_counts.get(record["status"], 0) + 1

            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            if i % 2000 == 0:
                print(f"   ... {i}/{len(tickers)} klassificerade ({resolved_count} med CIK, {shares_found_count} med aktiedata)")

    print(f"\n--- KLART: {len(tickers)} tickers klassificerade ---")
    print(f"Output: {OUTPUT_FILE}\n")
    print(f"CIK hittad:                          {resolved_count}/{len(tickers)} ({resolved_count/len(tickers)*100:.1f}%)")
    print(f"CIK + aktiedata (filed-datum-korrigerad): {shares_found_count}/{len(tickers)} ({shares_found_count/len(tickers)*100:.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
