#!/usr/bin/env python3
"""
Numerisk validering: jamfor den vektoriserade compute_beta() i
strategies/HYP-009/backtest_optimized.py mot den ORIGINALA,
loop-baserade compute_beta() i strategies/HYP-009/backtest.py (ej
rord), pa en delmangd av riktiga tickers - inte hela universumet, for
att den langsamma originalversionen ska hinna kora klart pa rimlig tid
i ett valideringssteg.

Om detta INTE visar identiska (inom floating-point-tolerans) resultat:
den optimerade versionen far ALDRIG anvandas for en riktig hypotes-
korning, oavsett hur mycket snabbare den ar.
"""

import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "strategies" / "HYP-009"))

import backtest as orig  # noqa: E402
import backtest_optimized as opt  # noqa: E402

N_TICKERS_TO_TEST = 40


def main() -> int:
    print("Laddar universum...")
    tickers, universe_by_month = orig.load_universe()

    subset = tickers[:N_TICKERS_TO_TEST]
    print(f"Testar pa {len(subset)} tickers (av {len(tickers)} totalt) for snabb validering.\n")

    print("Laddar prismatriser...")
    close, high, low, volume = orig.load_price_matrices(subset, orig.FULL_START, orig.FULL_END)
    hedge = orig.load_hedge(orig.FULL_START, orig.FULL_END)
    print(f"  Prismatris: {close.shape}\n")

    print("Kor ORIGINAL compute_beta (loop-baserad, kan ta en stund pa detta antal tickers)...")
    t0 = time.time()
    beta_orig = orig.compute_beta(close, hedge, orig.BETA_WINDOW)
    t_orig = time.time() - t0
    print(f"  Klar pa {t_orig:.1f}s\n")

    print("Kor OPTIMERAD compute_beta (vektoriserad)...")
    t0 = time.time()
    beta_opt = opt.compute_beta(close, hedge, opt.BETA_WINDOW)
    t_opt = time.time() - t0
    print(f"  Klar pa {t_opt:.2f}s\n")

    if beta_orig.shape != beta_opt.shape:
        print(f"FEL: olika shape! orig={beta_orig.shape} opt={beta_opt.shape}")
        return 1

    a = beta_orig.values
    b = beta_opt.values
    both_nan = np.isnan(a) & np.isnan(b)
    diff = np.abs(a - b)
    diff[both_nan] = 0.0
    max_diff = np.nanmax(diff)
    n_mismatch = np.sum(diff > 1e-4)

    print("=" * 60)
    print(f"Max absolut skillnad:     {max_diff:.8f}")
    print(f"Antal celler som skiljer (>1e-4): {n_mismatch} av {a.size}")
    print(f"Tidsvinst pa {len(subset)} tickers: {t_orig / t_opt:.1f}x snabbare")
    print("=" * 60)

    if max_diff > 1e-4:
        print("\nFEL: DEN OPTIMERADE VERSIONEN GER ANDRA RESULTAT. Anvand INTE den.")
        # Visa nagra konkreta avvikande celler for felsokning
        idx = np.argwhere(diff > 1e-4)[:10]
        for r, c in idx:
            print(f"  rad {r} ({close.index[r].date()}), ticker {close.columns[c]}: "
                  f"orig={a[r, c]:.6f} opt={b[r, c]:.6f}")
        return 1

    print("\nOK: identiska resultat (inom floating-point-tolerans). Optimeringen ar korrekt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
