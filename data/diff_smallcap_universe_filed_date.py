"""
Jämför det ursprungliga (periodslut-daterade) small-cap-universumet mot
det filed-datum-korrigerade - kvantifierar exakt hur många ticker-månader
som faktiskt byter medlemskap. ÄNDRAR INGET, bara rapporterar (se
CLAUDE.md: registret/redan testade hypoteser rörs aldrig av detta skript).

Usage: python data/diff_smallcap_universe_filed_date.py
"""

import json
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent / "cache"
ORIGINAL = CACHE_DIR / "smallcap_universe_by_month.json"
CORRECTED = CACHE_DIR / "smallcap_universe_by_month_filed_date.json"


def main() -> int:
    orig = json.loads(ORIGINAL.read_text(encoding="utf-8"))
    corr = json.loads(CORRECTED.read_text(encoding="utf-8"))

    all_months = sorted(set(orig) | set(corr))
    total_added = 0
    total_removed = 0
    total_orig_membership = 0
    per_month_rows = []

    for m in all_months:
        o = set(orig.get(m, []))
        c = set(corr.get(m, []))
        added = c - o     # med i korrigerad, INTE med i ursprunglig
        removed = o - c   # med i ursprunglig, INTE med i korrigerad
        total_added += len(added)
        total_removed += len(removed)
        total_orig_membership += len(o)
        per_month_rows.append((m, len(o), len(c), len(added), len(removed)))

    print("=" * 90)
    print(f"Månader jämförda: {len(all_months)}")
    print(f"Total ticker-månads-medlemskap (ursprunglig fil): {total_orig_membership:,}")
    print(f"Ticker-månader TILLAGDA i korrigerad (var INTE med innan):    {total_added:,}")
    print(f"Ticker-månader BORTTAGNA i korrigerad (var med innan, nu ute): {total_removed:,}")
    total_change = total_added + total_removed
    pct = total_change / max(total_orig_membership, 1)
    print(f"Total förändring: {total_change:,} ({pct:.2%} av ursprunglig medlemskapsmängd)")
    print("=" * 90)

    print("\nStörsta månatliga förändringar (topp 15 efter |added|+|removed|):")
    per_month_rows.sort(key=lambda r: -(r[3] + r[4]))
    for m, no, nc, a, r in per_month_rows[:15]:
        print(f"  {m}:  ursprunglig={no:>4}  korrigerad={nc:>4}  +{a:<4} -{r:<4}")

    unique_orig = {t for v in orig.values() for t in v}
    unique_corr = {t for v in corr.values() for t in v}
    print(f"\nUnika tickers någonsin i bandet: ursprunglig={len(unique_orig)}  korrigerad={len(unique_corr)}")
    print(f"Tickers som ALDRIG är med i korrigerad men VAR med i ursprunglig: {len(unique_orig - unique_corr)}")
    print(f"Tickers som ALDRIG var med i ursprunglig men ÄR med i korrigerad: {len(unique_corr - unique_orig)}")

    return 0


if __name__ == "__main__":
    main()
