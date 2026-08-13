#!/usr/bin/env python3
"""
Engangsscript: hamtar OHLCV for det breddade CTA-trendkorgens nya
tillgangar (utover TLT/GLD/DBC som redan finns cachade) - CEO-lasat
sokrymd 2026-08-07 (se chattsession), del av HYP-044-kandidatarbetet.

IEF/SHY (rantekurva utover TLT), HYG (kredit), EFA/EEM (internationella
aktier - INTE SPY, redan ett eget ben i portfoljen), UUP (dollar),
SLV (rravarubredd utover GLD/DBC).

Sparar i samma schema/format som ovrig data/cache/ohlcv/*.csv
(eodhd_adapter.get_daily_ohlcv()'s kolumner).
"""

import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OHLCV_DIR = DATA_DIR / "cache" / "ohlcv"

sys.path.insert(0, str(DATA_DIR))
from eodhd_adapter import get_daily_ohlcv  # noqa: E402

NEW_TICKERS = ["IEF", "SHY", "HYG", "EFA", "EEM", "UUP", "SLV"]
START = "2005-01-01"
END = "2025-12-31"


def main():
    for t in NEW_TICKERS:
        out_path = OHLCV_DIR / f"{t}.csv"
        if out_path.exists():
            print(f"{t}: redan cachad, hoppar over.")
            continue
        print(f"Hamtar {t}...")
        rows = get_daily_ohlcv(t, START, END)
        if not rows:
            print(f"  VARNING: inga rader for {t}!")
            continue
        df = pd.DataFrame(rows)
        df.to_csv(out_path, index=False)
        print(f"  {len(df)} rader, {df['date'].min()} till {df['date'].max()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
