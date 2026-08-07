#!/usr/bin/env python3
"""
Snabb, riktad uppfoljning (2026-08-07) av det redan kanda EODHD-
tackningsproblemet (se data/rebuild_current_universe.py, senast kort
2026-07-31: 11/383 kandidater med pris inom 60 dagar). Denna gang: inte
en full universumombyggnad (dyr, redan gjord tva ganger med samma
slutsats), utan ett BILLIGT stickprov pa tickers fran den SENASTE
manaden i smallcap_universe_2025_extension.json (december 2025) - for
att se om nagot forandrats en vecka senare, och specifikt for att
informera om HYP-043 (som beror pa samma small-cap-tackning via
HYP-037-benet och momentum L/S-sviten) kan forward-papperhandlas idag.
"""

import sys
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
sys.path.insert(0, str(DATA_DIR))
from eodhd_adapter import get_daily_ohlcv  # noqa: E402

import json  # noqa: E402

TODAY = date.today()

with (DATA_DIR / "cache" / "smallcap_universe_2025_extension.json").open(encoding="utf-8") as f:
    ext = json.load(f)
latest_month = sorted(ext.keys())[-1]
sample = ext[latest_month][:25]

print(f"Stickprov: {len(sample)} tickers fran senaste manaden ({latest_month}) i 2025-utokningen.")
print(f"Dagens datum: {TODAY}\n")

stale_days = []
for t in sample:
    rows = get_daily_ohlcv(t, "2025-10-01", TODAY.isoformat())
    if not rows:
        print(f"  {t:<8} INGA RADER ALLS")
        stale_days.append((t, None))
        continue
    last_date = max(r["date"] for r in rows if r.get("date"))
    days_stale = (TODAY - date.fromisoformat(last_date)).days
    stale_days.append((t, days_stale))
    flag = "OK" if days_stale <= 5 else ("VARNING" if days_stale <= 60 else "STALE")
    print(f"  {t:<8} senaste pris: {last_date}  ({days_stale:>4} dagar sedan)  [{flag}]")

valid = [d for _, d in stale_days if d is not None]
n_fresh = sum(1 for d in valid if d <= 5)
n_ok60 = sum(1 for d in valid if d <= 60)
print(f"\n{n_fresh}/{len(sample)} med pris inom 5 dagar (genuint 'idag'-handlingsbart).")
print(f"{n_ok60}/{len(sample)} med pris inom 60 dagar (samma trosklar som 2026-07-31-koll).")
print(f"{len(sample) - len(valid)}/{len(sample)} helt utan data i fonstret.")
