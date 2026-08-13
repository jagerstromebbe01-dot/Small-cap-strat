"""
Kvalitetskontroll (2026-07-31, CEO-beslut, "gratis kontroll" - INGEN
K-kostnad, andrar INGET last resultat): kor HYP-023:s OFORANDRADE motor
med SIC-baserad bank-/finansklassificering (strategies/common/sector.py
::load_bank_financial_flags_sic) i stallet for nyckelordsmatchning, for
att se om det last resultatet haller.

FYND INNAN denna kordes: SIC flaggar 18.3% av universumet som bank/finans
mot nyckelordsmetodens 6.5% - en betydande UNDERSKATTNING i den
ursprungliga metoden (622 tickers ar finans enligt SIC men missas av
nyckelord, t.ex. "Bancshares" matchar inte "bancorp"-substrangen).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HYP023_DIR = REPO_ROOT / "strategies" / "HYP-023"
CACHE_DIR = REPO_ROOT / "data" / "cache"
UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_by_month.json"

sys.path.insert(0, str(REPO_ROOT / "strategies" / "common"))
sys.path.insert(0, str(HYP023_DIR))
from data_hygiene import clean_price_matrix, flag_implausible_liquidity  # noqa: E402
from sector import load_bank_financial_flags_sic  # noqa: E402
import backtest as hyp023  # noqa: E402


def sharpe(s, rf=0.02):
    r = s.pct_change().dropna()
    return float(np.sqrt(252) * (r - rf / 252).mean() / r.std()) if r.std() > 0 else 0.0


def max_drawdown(s):
    return float(((s - s.cummax()) / s.cummax()).min())


def main():
    with UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_by_month = json.load(f)
    tickers = sorted({t for tk in universe_by_month.values() for t in tk})

    print("Laddar prismatriser (identiskt med HYP-023:s officiella korning)...")
    close, close_adj, high, low, volume = hyp023.load_price_matrices(tickers, hyp023.FULL_START, hyp023.FULL_END)
    hedge = hyp023.load_hedge(hyp023.FULL_START, hyp023.FULL_END)

    close, high, low = clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    implausible = flag_implausible_liquidity(close, volume, max_market_cap=hyp023.MAX_MARKET_CAP,
                                              window=hyp023.ADV_WINDOW, multiplier=1.0)
    close = close.mask(implausible)
    close_adj = close_adj.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)

    beta_df = hyp023.compute_beta(close_adj, hedge, hyp023.BETA_WINDOW)
    vol_df = hyp023.compute_idiosyncratic_vol(close_adj, hedge, beta_df, hyp023.VOL_LOOKBACK_DAYS)
    spread_df = hyp023.compute_spread_matrix(high, low)

    print("Klassificerar bank-/finansnamn via SIC (INTE nyckelord)...")
    bank_flags_sic = load_bank_financial_flags_sic(tickers)
    print(f"  {sum(bank_flags_sic.values())} av {len(tickers)} klassade som bank/finans (SIC 6000-6799).\n")

    print("Officiella lasta resultat (nyckelordsklassificering, for jamforelse):")
    print("  100k: Sharpe 0.7174, MaxDD -0.2546")
    print("  1M:   Sharpe 0.7536, MaxDD -0.1929")
    print("  10M:  Sharpe 0.7227, MaxDD -0.1316\n")

    print("Kör om med SIC-klassificering...")
    for level in [100_000, 1_000_000, 10_000_000]:
        pv, tl, stl = hyp023.run_backtest(close, close_adj, hedge, vol_df, beta_df, spread_df, volume,
                                           universe_by_month, level, bank_flags_sic)
        sh = sharpe(pv)
        dd = max_drawdown(pv)
        print(f"  ${level:,.0f}: Sharpe={sh:.4f}  MaxDD={dd:.4f}  SektorTriggers={len(stl)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
