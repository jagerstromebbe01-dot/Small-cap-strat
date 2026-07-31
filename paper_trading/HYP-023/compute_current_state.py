"""
Pappershandel för HYP-023 (referensimplementationen) - beräknar dagens
faktiska portföljtillstånd (mål-innehav, krasch-trigger-status) och
uppdaterar en beständig ledger (paper_trading/HYP-023/ledger.json) med
mark-to-market-värde. INGA RIKTIGA PENGAR - loggar bara vad strategin
SKULLE göra, för genuin framåtblickande validering (se konversationen
2026-07-31: detta är den enda äkta OOS-valideringen som existerar för
det här projektet, eftersom Claudes kunskap redan täcker hela
backtestperioden).

METOD (CEO-beslut 2026-07-31): FRUSEN december 2024-universumlista -
samma bolag som redan var i small-cap-universumet vid backtestens slut,
bara PRISERNA uppdateras framåt (se data/update_ohlcv_current.py). KÄND
BEGRÄNSNING: bolag som passerat in i eller ut ur $100M-$2B-bandet sedan
december 2024 fångas INTE. Kör data/update_ohlcv_current.py FÖRST för
att uppdatera priscachen innan detta skript körs.

Återanvänder HYP-023:s EGNA signalfunktioner rakt av (samma modul
importeras, inte kopierad kod) - source of truth för vad "HYP-023:s
regler" betyder är alltid strategies/HYP-023/backtest.py.

Körs om (manuellt, tills en schemaläggningsmekanism finns - se
CLAUDE.md "Open dependencies" punkt 2): varje handelsdag för att
uppdatera mark-to-market, eller minst kring kvartalsvisa
ombalanseringsdatum för att fånga eventuella innehavsbyten.
"""

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PAPER_DIR = Path(__file__).resolve().parent
DATA_DIR = REPO_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_by_month.json"
HYP023_DIR = REPO_ROOT / "strategies" / "HYP-023"
LEDGER_FILE = PAPER_DIR / "ledger.json"

sys.path.insert(0, str(REPO_ROOT / "strategies" / "common"))
sys.path.insert(0, str(HYP023_DIR))
from data_hygiene import clean_price_matrix, flag_implausible_liquidity  # noqa: E402
from sector import load_bank_financial_flags  # noqa: E402
import backtest as hyp023  # noqa: E402 - source of truth for HYP-023's own signal logic

STARTING_CAPITAL = 100_000.0
FULL_START = "2010-01-01"


def load_frozen_universe():
    with UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_by_month = json.load(f)
    latest_key = sorted(universe_by_month.keys())[-1]
    return sorted(set(universe_by_month[latest_key])), latest_key


def main():
    today_str = date.today().isoformat()
    print(f"Beräknar HYP-023:s pappershandel-tillstånd per {today_str}...\n")

    frozen_tickers, universe_key = load_frozen_universe()
    print(f"Fruset universum ({universe_key}): {len(frozen_tickers)} tickers.\n")

    print("Laddar prismatriser (nu uppdaterade fram till idag)...")
    close, close_adj, high, low, volume = hyp023.load_price_matrices(frozen_tickers, FULL_START, today_str)
    hedge = hyp023.load_hedge(FULL_START, today_str)
    print(f"  Prismatris: {close.shape}, senaste handelsdag: {close.index[-1].date()}\n")

    print("Sanerar prisdata...")
    close, high, low = clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    implausible = flag_implausible_liquidity(close, volume, max_market_cap=hyp023.MAX_MARKET_CAP,
                                              window=hyp023.ADV_WINDOW, multiplier=1.0)
    close = close.mask(implausible)
    close_adj = close_adj.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)

    print("Beräknar beta, idiosynkratisk vol, bank-/finanskomposit (HYP-023:s egna funktioner)...")
    beta_df = hyp023.compute_beta(close_adj, hedge, hyp023.BETA_WINDOW)
    vol_df = hyp023.compute_idiosyncratic_vol(close_adj, hedge, beta_df, hyp023.VOL_LOOKBACK_DAYS)
    bank_flags = load_bank_financial_flags(frozen_tickers)

    universe_by_month_frozen = {universe_key: frozen_tickers}
    bank_composite = hyp023.compute_bank_composite_returns(close_adj, universe_by_month_frozen, bank_flags, close.index)
    bank_composite_price = (1.0 + bank_composite.fillna(0.0)).cumprod()

    last_date = close.index[-1]
    last_i = len(close.index) - 1

    print("\nBestämmer dagens mål-decil (lägsta idiosynkratisk vol)...")
    vol_today = vol_df.loc[last_date]
    scores = []
    for t in frozen_tickers:
        v = vol_today.get(t, np.nan)
        cp = close_adj.loc[last_date, t] if t in close_adj.columns else np.nan
        if not np.isnan(v) and not np.isnan(cp) and cp > 0:
            scores.append((v, t, cp))
    scores.sort()
    n_top = max(1, int(len(scores) * hyp023.DECILE_FRACTION)) if scores else 0
    target_tickers = [t for _, t, _ in scores[:n_top]]

    spy_10d_ret = hedge.pct_change(hyp023.CRASH_LOOKBACK_DAYS).iloc[last_i]
    sector_10d_ret = bank_composite_price.pct_change(hyp023.SECTOR_CRASH_LOOKBACK_DAYS).iloc[last_i]
    spy_triggered = bool(not np.isnan(spy_10d_ret) and spy_10d_ret < hyp023.CRASH_TRIGGER_RET)
    sector_triggered = bool(not np.isnan(sector_10d_ret) and sector_10d_ret < hyp023.SECTOR_CRASH_TRIGGER_RET)

    print(f"  {len(target_tickers)} namn i mål-decilen (av {len(scores)} med giltig signal).")
    print(f"  SPY 10-dagars: {spy_10d_ret:+.2%}  (krasch-overlay {'AKTIV' if spy_triggered else 'inaktiv'})")
    print(f"  Bank-/finanskomposit 10-dagars: {sector_10d_ret:+.2%}  (sektor-trigger {'AKTIV' if sector_triggered else 'inaktiv'})")

    state = {
        "as_of_date": str(last_date.date()),
        "computed_at": today_str,
        "universe_key": universe_key,
        "universe_size": len(frozen_tickers),
        "n_scored": len(scores),
        "target_decile_tickers": target_tickers,
        "spy_10d_return": None if np.isnan(spy_10d_ret) else float(spy_10d_ret),
        "spy_crash_overlay_active": spy_triggered,
        "sector_10d_return": None if np.isnan(sector_10d_ret) else float(sector_10d_ret),
        "sector_crash_trigger_active": sector_triggered,
    }

    # ── Ledger: initiera vid forsta korningen, annars mark-to-market +
    # logga eventuella innehavsbyten mot senast sparade tillstand.
    if LEDGER_FILE.exists():
        with LEDGER_FILE.open(encoding="utf-8") as f:
            ledger = json.load(f)
        prev_tickers = set(ledger["history"][-1]["target_decile_tickers"]) if ledger["history"] else set()
        new_tickers = set(target_tickers)
        if prev_tickers != new_tickers:
            print(f"\n  INNEHAVSBYTE upptackt sedan senaste korning: "
                  f"+{sorted(new_tickers - prev_tickers)} -{sorted(prev_tickers - new_tickers)}")
    else:
        ledger = {
            "hypothesis": "HYP-023",
            "started": today_str,
            "starting_capital": STARTING_CAPITAL,
            "note": "INGA RIKTIGA PENGAR - loggar bara vad HYP-023 SKULLE gora framat, for genuin OOS-validering.",
            "history": [],
        }
        print(f"\n  Initierar ny ledger med startkapital ${STARTING_CAPITAL:,.0f}.")

    ledger["history"].append(state)
    with LEDGER_FILE.open("w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2, ensure_ascii=False)

    print(f"\nKLART. Tillstånd sparat till {LEDGER_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
