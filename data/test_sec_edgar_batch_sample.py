"""
Kör resolve_cik() mot ett SLUMPMÄSSIGT urval av riktiga EODHD-tickers
(inte handplockade kända bolag) för att få verkliga siffror på:
- träffsäkerhet (confident / resolved_by_data / ambiguous / no_candidates)
- tidsåtgång, för att extrapolera kostnaden av en full körning mot alla
  ~32 000 tickers innan vi committar till det

INTE en riktig körning mot HYP-008 - ett representativt stickprov för
att bedöma om skalningen är rimlig, per CEO:s "så länge det inte blir
för omständigt"-gräns (2026-07-27).
"""

import random
import sys
import time

from eodhd_adapter import get_us_tickers
from sec_edgar_adapter import load_cik_lookup, resolve_cik

SAMPLE_SIZE = 100
SEED = 42


def main() -> int:
    print("--- SEC EDGAR-matchning: slumpmässigt stickprov ---\n")

    print("Hämtar full EODHD-tickerlista...")
    all_tickers = get_us_tickers(include_delisted=True)
    random.seed(SEED)
    sample = random.sample(all_tickers, SAMPLE_SIZE)
    print(f"Stickprov: {SAMPLE_SIZE} av {len(all_tickers)} tickers (seed={SEED})\n")

    print("Laddar SEC:s CIK-lookup (cachad lokalt)...")
    lookup = load_cik_lookup()
    print()

    counts = {"confident": 0, "resolved_by_data": 0, "ambiguous": 0, "no_candidates": 0}
    t0 = time.time()

    for i, row in enumerate(sample, start=1):
        name = row.get("Name", "")
        result = resolve_cik(name, lookup)
        counts[result["status"]] += 1
        if i % 20 == 0:
            elapsed = time.time() - t0
            print(f"  ... {i}/{SAMPLE_SIZE} klara ({elapsed:.0f}s hittills)")

    elapsed = time.time() - t0
    per_ticker = elapsed / SAMPLE_SIZE

    print(f"\n--- Resultat ({SAMPLE_SIZE} tickers, {elapsed:.0f}s totalt, {per_ticker:.2f}s/ticker) ---")
    for status, count in counts.items():
        pct = count / SAMPLE_SIZE * 100
        print(f"  {status:20s}: {count:4d}  ({pct:.0f}%)")

    resolved = counts["confident"] + counts["resolved_by_data"]
    print(f"\nAutomatiskt lösta (confident + resolved_by_data): {resolved}/{SAMPLE_SIZE} ({resolved/SAMPLE_SIZE*100:.0f}%)")
    print(f"Kräver manuell granskning (ambiguous + no_candidates): {SAMPLE_SIZE - resolved}/{SAMPLE_SIZE} ({(SAMPLE_SIZE-resolved)/SAMPLE_SIZE*100:.0f}%)")

    full_universe = len(all_tickers)
    est_seconds = per_ticker * full_universe
    print(
        f"\nExtrapolerat till hela universumet ({full_universe} tickers): "
        f"~{est_seconds/3600:.1f} timmar vid samma takt."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
