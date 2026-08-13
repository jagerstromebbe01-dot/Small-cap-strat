"""
Genuin OOS-validering av HYP-023 över 2025 (2026-07-31, CEO-beslut).

VARFÖR DETTA ÄR EN ÄKTA BLIND TEST, TILL SKILLNAD FRÅN ATT DELA UPP DEN
BEFINTLIGA 2011-2024-BACKTESTEN I "IS 2011-2014 / OOS 2014-2024": Claude
har redan sett vad som hände 2015-2024 (covidkraschen, 2022 räntehöjningar,
SVB-krisen) i sin träningsdata, oavsett vilket fönster som visas i en given
konversation - att dela upp REDAN KÄND historik löser inte det. 2025 ligger
delvis efter träningsgränsen (januari 2026), och även den del som ligger
före den gäller specifika, obskyra småbolags dagskurser - inte den typen av
fakta en språkmodell memorerar. HYP-023:s regler låstes dessutom helt innan
någon någonsin tittade på 2025-data.

METOD: kör HYP-023:s EGNA, OFÖRÄNDRADE funktioner (importerade direkt från
strategies/HYP-023/backtest.py - INTE kopierad eller omskriven kod) över en
UTÖKAD periods- och universumdefinition:
  - Pris: samma cache som redan finns, nu utökad till att innehålla 2025-data
    där tillgänglig (se data/update_ohlcv_current.py och
    data/rebuild_current_universe.py).
  - Universum: research/../smallcap_universe_by_month.json (2010-2024,
    ORÖRD - projektets grundsanning) SAMMANFOGAD med
    data/cache/smallcap_universe_2025_extension.json (byggd av
    data/build_universe_2025.py - samma $100M-$2B-bandlogik, men manatlig
    genom hela 2025, inte bara en "idag"-ögonblicksbild).

KÄND BEGRÄNSNING (INTE dold): universumets storlek i utökningen sjunker
INOM 2025 sjalvt (202 bolag i januari -> 66 i december) - detta ar en
konsekvens av att EODHD:s datatäckning tunnas ut mot slutet av perioden,
INTE ett verkligt marknadsfenomen. Tolka darfor senare delen av 2025 med
storre forsiktighet an den tidigare.

Rapporterar bade den FULLA kontinuerliga serien (for kontinuitetskoll mot
den redan kanda 2011-2024-backtesten) och metrics ISOLERADE till ENDAST
2025 (den faktiska OOS-perioden).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PAPER_DIR = Path(__file__).resolve().parent
CACHE_DIR = REPO_ROOT / "data" / "cache"
ORIGINAL_UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_by_month.json"
EXTENSION_UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_2025_extension.json"
HYP023_DIR = REPO_ROOT / "strategies" / "HYP-023"
RESULTS_DIR = PAPER_DIR / "oos_2025_results"

sys.path.insert(0, str(REPO_ROOT / "strategies" / "common"))
sys.path.insert(0, str(HYP023_DIR))
from data_hygiene import clean_price_matrix, flag_implausible_liquidity  # noqa: E402
from sector import load_bank_financial_flags  # noqa: E402
import backtest as hyp023  # noqa: E402 - source of truth, INTE omskriven

OOS_START = "2025-01-01"
FULL_END = "2025-12-31"


def sharpe(s, rf=0.02):
    r = s.pct_change().dropna()
    return float(np.sqrt(252) * (r - rf / 252).mean() / r.std()) if r.std() > 0 else 0.0


def max_drawdown(s):
    return float(((s - s.cummax()) / s.cummax()).min())


def cagr(s):
    if len(s) < 2:
        return None
    return float((s.iloc[-1] / s.iloc[0]) ** (252 / len(s)) - 1)


def main():
    print("Laddar och sammanfogar universum (2011-2024 grundsanning + 2025-utökning)...")
    with ORIGINAL_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_orig = json.load(f)
    with EXTENSION_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_2025 = json.load(f)
    universe_merged = {**universe_orig, **universe_2025}
    all_tickers = sorted({t for tickers in universe_merged.values() for t in tickers})
    print(f"  {len(universe_orig)} manader (grundsanning) + {len(universe_2025)} manader (2025) = "
          f"{len(universe_merged)} totalt. {len(all_tickers)} unika tickers.\n")

    print("Laddar prismatriser (2010-01-01 till 2025-12-31)...")
    close, close_adj, high, low, volume = hyp023.load_price_matrices(all_tickers, hyp023.FULL_START, FULL_END)
    hedge = hyp023.load_hedge(hyp023.FULL_START, FULL_END)
    print(f"  Prismatris: {close.shape}\n")

    print("Sanerar prisdata...")
    close, high, low = clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    implausible = flag_implausible_liquidity(close, volume, max_market_cap=hyp023.MAX_MARKET_CAP,
                                              window=hyp023.ADV_WINDOW, multiplier=1.0)
    close = close.mask(implausible)
    close_adj = close_adj.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)

    print("Beräknar beta, idiosynkratisk vol, spread, bank-/finanskomposit (HYP-023:s egna, OFÖRÄNDRADE funktioner)...")
    beta_df = hyp023.compute_beta(close_adj, hedge, hyp023.BETA_WINDOW)
    vol_df = hyp023.compute_idiosyncratic_vol(close_adj, hedge, beta_df, hyp023.VOL_LOOKBACK_DAYS)
    spread_df = hyp023.compute_spread_matrix(high, low)
    bank_flags = load_bank_financial_flags(all_tickers)

    RESULTS_DIR.mkdir(exist_ok=True)
    all_results = []
    for capital_level in [100_000, 1_000_000, 10_000_000]:
        print(f"\n--- Kapitalnivå: ${capital_level:,.0f} ---")
        pv, tl, stl = hyp023.run_backtest(close, close_adj, hedge, vol_df, beta_df, spread_df, volume,
                                           universe_merged, capital_level, bank_flags)

        oos_pv = pv.loc[OOS_START:]
        oos_tl = tl[tl["date"] >= OOS_START] if len(tl) else tl

        full_sharpe = sharpe(pv)
        oos_sharpe = sharpe(oos_pv)
        oos_cagr = cagr(oos_pv)
        oos_maxdd = max_drawdown(oos_pv)
        oos_total_return = float(oos_pv.iloc[-1] / oos_pv.iloc[0] - 1) if len(oos_pv) > 1 else None

        result = {
            "capital_level": capital_level,
            "full_series_sharpe_2011_2025": full_sharpe,
            "oos_2025_sharpe": oos_sharpe,
            "oos_2025_cagr": oos_cagr,
            "oos_2025_total_return": oos_total_return,
            "oos_2025_max_drawdown": oos_maxdd,
            "oos_2025_n_trades": int(len(oos_tl)),
            "oos_2025_trading_days": int(len(oos_pv)),
        }
        all_results.append(result)

        print(f"    Full serie (2011-2025) Sharpe: {full_sharpe:.3f}")
        print(f"    OOS 2025 ENDAST: Sharpe={oos_sharpe:.3f}  Totalavkastning={oos_total_return:+.2%}  "
              f"MaxDD={oos_maxdd:.1%}  Trades={len(oos_tl)}  Handelsdagar={len(oos_pv)}")

        pv.to_csv(RESULTS_DIR / f"portfolio_value_full_{capital_level}.csv", header=["portfolio_value"])
        oos_pv.to_csv(RESULTS_DIR / f"portfolio_value_oos_2025_{capital_level}.csv", header=["portfolio_value"])
        tl.to_csv(RESULTS_DIR / f"trade_log_full_{capital_level}.csv", index=False)

    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, default=str, ensure_ascii=False)

    print(f"\nKLART. Sammanfattning sparad till {RESULTS_DIR / 'summary.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
