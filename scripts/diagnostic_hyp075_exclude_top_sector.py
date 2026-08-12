"""
Gratis robusthetskontroll (2026-08-12, CEO-begärd, INGEN K-kostnad,
ändrar INGET låst resultat) - identisk princip som HYP-072:s tidigare
winsoriserings-/ex-2020-kontroller: kör HYP-075:s redan låsta motor
oförändrad, men med den mest bidragande SIC-2-siffer-branschen (funnen
via trade_log-analys: SIC 60, "State Commercial Banks", 803 trades,
störst summerad avkastning av alla branschgrupper) helt exkluderad ur
eligible-universumet. Konvergerande förslag fran tre externa AI-källor
(Grok/ChatGPT/Gemini, 2026-08-12) - se
research/CANDIDATE_BRAINSTORM_PROMPT_HYP075_UTVECKLING_2026-08-12.md.

Endast $100k (den avgörande nivån) körs - detta är en diagnostisk
kontroll, inte en ny hypotes.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "strategies" / "HYP-075"))
sys.path.insert(0, str(REPO_ROOT / "strategies" / "common"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import backtest as hyp075  # noqa: E402
from data_hygiene import (  # noqa: E402
    clean_price_matrix,
    flag_implausible_liquidity,
    mask_unrecovered_price_breaks,
    mask_implausible_adjusted_close_ratio,
)
from deflated_sharpe_ratio import kurtosis as sample_kurtosis  # noqa: E402

import json

SIC_FILE = REPO_ROOT / "data" / "cache" / "sic_classification.jsonl"
EXCLUDE_SIC2 = "60"  # State Commercial Banks - storst summerad avkastning i trade_log


def load_sic_map():
    m = {}
    with SIC_FILE.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            s = row.get("sic") or ""
            m[row["ticker"]] = s[:2] if s else "UNK"
    return m


def main():
    sic_map = load_sic_map()
    excluded_tickers = {t for t, s in sic_map.items() if s == EXCLUDE_SIC2}
    print(f"Exkluderar SIC {EXCLUDE_SIC2} (State Commercial Banks): {len(excluded_tickers)} tickers ur universumet.\n")

    print("Laddar universum...")
    tickers, universe_by_month = hyp075.load_universe()

    # Filtrera bort den exkluderade branschens tickers ur VARJE manads
    # eligible-lista (ren universumsfiltrering, ror inte signalen sjalv).
    universe_by_month_filtered = {
        month: [t for t in tks if t not in excluded_tickers]
        for month, tks in universe_by_month.items()
    }

    print(f"Laddar prismatriser...")
    close, close_adj, high, low, volume = hyp075.load_price_matrices(
        tickers, hyp075.FULL_START, hyp075.FULL_END)

    print("Sanerar prisdata...")
    close, high, low = clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    close_adj = mask_implausible_adjusted_close_ratio(close, close_adj)
    implausible = flag_implausible_liquidity(close, volume, max_market_cap=hyp075.MAX_MARKET_CAP,
                                              window=hyp075.ADV_WINDOW, multiplier=1.0)
    close = close.mask(implausible)
    close_adj = close_adj.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)
    close = mask_unrecovered_price_breaks(close)
    close_adj = close_adj.where(close.notna())
    high = high.where(close.notna())
    low = low.where(close.notna())

    print("Berknar Corwin-Schultz-spread...")
    spread_df = hyp075.compute_spread_matrix(high, low)

    print("Laddar SEC filings-index...\n")
    filing_index = hyp075.load_filing_index()

    level = 100_000
    print(f"--- Kör HYP-075 UTAN SIC {EXCLUDE_SIC2}, ${level:,.0f} ---")
    pv, tl, trl = hyp075.run_backtest(close, close_adj, spread_df, volume, filing_index,
                                       universe_by_month_filtered, level)
    main_pv = pv.loc[pv.index < hyp075.OOS_START]
    r_main = main_pv.pct_change().dropna()
    r_ex2020 = r_main[r_main.index.year != 2020]

    sh = hyp075.sharpe(main_pv)
    mdd = hyp075.max_drawdown(main_pv)
    sh_ex2020 = float(np.sqrt(252) * (r_ex2020 - 0.02 / 252).mean() / r_ex2020.std()) if r_ex2020.std() > 0 else 0.0
    kurt = float(sample_kurtosis(r_main.values))

    print(f"\nUTAN SIC {EXCLUDE_SIC2}: Sharpe={sh:.4f}  MaxDD={mdd:.2%}  Sharpe(ex-2020)={sh_ex2020:.4f}  Kurtosis={kurt:.1f}  n_trims={len(trl)}")
    print(f"HYP-075 ORIGINAL (för jämförelse): Sharpe=0.8065  MaxDD=-6.05%  Sharpe(ex-2020)=0.7737  Kurtosis=7.7")

    cond1 = sh >= 0.55
    cond2 = mdd >= -0.50
    cond3 = sh_ex2020 >= 0.4894
    cond4 = kurt < 366.2
    print(f"\nSamma villkor som HYP-075:s egna lasta kriterium, tillampade har rent diagnostiskt (ingen ny hypotes, ingen K-kostnad):")
    print(f"  Sharpe >= 0.55: {'PASS' if cond1 else 'FAIL'}")
    print(f"  MaxDD >= -50%: {'PASS' if cond2 else 'FAIL'}")
    print(f"  Sharpe ex-2020 >= 0.4894: {'PASS' if cond3 else 'FAIL'}")
    print(f"  Kurtosis < 366.2: {'PASS' if cond4 else 'FAIL'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
