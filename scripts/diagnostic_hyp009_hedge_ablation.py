#!/usr/bin/env python3
"""
DIAGNOSTIK, INTE en ny hypotes - ingen pass_fail_criterion, inget
K-bidrag, ror inte registret. Ren utforskande analys for att forsta
VARFOR HYP-009 (small-cap, friktion=0) fortfarande ger djupt negativ
Sharpe (-0.17 till -0.21) trots att trade_log visar en svagt POSITIV
aktieplocknings-edge (profit factor 1.19, 51.8% vinstandel).

Testar hypotesen: ar det SPY-betahedgen (inte sjalva parhandelssignalen)
som drar ner hela portfoljen? Kor run_backtest med hedge_pnl tvingad
till 0 (annars identisk kod) och jamfor Sharpe mot den riktiga,
hedgade versionen.
"""

import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "strategies" / "HYP-009"))

import backtest as bt  # noqa: E402


def run_backtest_no_hedge(prices, hedge, zscore_df, beta_df, spread_df, volume, capital_level):
    """Identisk kopia av bt.run_backtest(), MED ENDA SKILLNADEN att hedge_pnl tvingas till 0."""
    hedge_ret = hedge.pct_change()
    mom_3d = prices.pct_change(3)
    mom_10d = prices.pct_change(10)
    rf_daily = bt.RF_ANNUAL / 252
    tickers = list(prices.columns)
    tidx = {t: i for i, t in enumerate(tickers)}

    dollar_volume = (prices * volume).rolling(bt.ADV_WINDOW).mean()
    trade_state_vals = np.where(zscore_df.values < -bt.TRADE_Z_THRESH, 1,
                                 np.where(zscore_df.values > bt.TRADE_Z_THRESH, -1, 0))
    start_idx = max(bt.COINT_WINDOW, bt.BETA_WINDOW)

    prices_v = prices.values
    zscore_v = zscore_df.values
    mom3_v = mom_3d.values
    mom10_v = mom_10d.values
    dollar_volume_v = dollar_volume.values
    spread_v = spread_df.reindex(columns=tickers).values

    cash, positions, pv_list, trade_log = float(capital_level), {}, [float(capital_level)], []

    for date_i in range(start_idx, len(prices.index)):
        date = prices.index[date_i]
        cash += cash * rf_daily

        to_close = []
        for t, pos in positions.items():
            ti = tidx[t]
            cp = float(prices_v[date_i, ti])
            cz = float(zscore_v[date_i, ti])
            if np.isnan(cp):
                continue
            hit_stop = cp <= pos["stop"]
            hit_target = not np.isnan(cz) and abs(cz) < 0.3
            if hit_stop or hit_target:
                gross_ret = cp / pos["entry"] - 1
                proceeds = pos["size"] * (cp / pos["entry"])
                exit_spread = spread_v[date_i, ti]
                if not np.isnan(exit_spread):
                    proceeds -= proceeds * (exit_spread / 2) * bt.SPREAD_COST_MULTIPLIER
                cash += proceeds
                net_ret = proceeds / pos["size"] - 1
                to_close.append(t)
                trade_log.append({"date": date, "ticker": t, "ret": net_ret, "gross_ret": gross_ret,
                                   "type": "stop" if hit_stop else "target"})
        for t in to_close:
            del positions[t]

        if len(positions) < bt.MAX_POS:
            cands = []
            row_state = trade_state_vals[date_i]
            row_prices = prices_v[date_i]
            row_z = zscore_v[date_i]
            row_m3 = mom3_v[date_i]
            row_m10 = mom10_v[date_i]
            buy_signal = (row_state == 1) & (row_z < -bt.TRADE_Z_THRESH) & \
                         ~np.isnan(row_prices) & ~np.isnan(row_z)
            for ti in np.flatnonzero(buy_signal):
                t = tickers[ti]
                if t in positions:
                    continue
                cm3, cm10 = row_m3[ti], row_m10[ti]
                mom_ok = (not np.isnan(cm3) and cm3 > -0.04) or (not np.isnan(cm10) and cm10 > -0.06)
                if not mom_ok:
                    continue
                cands.append((abs(row_z[ti]), t, float(row_prices[ti])))
            cands.sort(reverse=True)
            slots = max(0, bt.MAX_POS - len(positions))
            for _, t, cp in cands[:slots]:
                ti = tidx[t]
                desired = bt.FIXED_FRAC * cash
                adv = dollar_volume_v[date_i, ti]
                cap = adv * bt.MAX_ADV_PCT if not np.isnan(adv) else desired
                sz = min(desired, cap)
                if sz < capital_level * 0.0001:
                    continue
                entry_spread = spread_v[date_i, ti]
                if not np.isnan(entry_spread):
                    effective_entry = cp * (1 + entry_spread / 2 * bt.SPREAD_COST_MULTIPLIER)
                else:
                    effective_entry = cp
                cash -= sz
                positions[t] = {"entry": effective_entry, "size": sz, "stop": effective_entry * (1 - bt.STOP_LOSS)}

        # ── ENDA SKILLNADEN mot originalet: ingen SPY-hedge, ingen borrow-kostnad ──
        long_val = 0.0
        for t, pos in positions.items():
            cp = float(prices_v[date_i, tidx[t]])
            if not np.isnan(cp):
                long_val += pos["size"] * cp / pos["entry"]
        pv_list.append(cash + long_val)  # hedge_pnl helt borttaget

    import pandas as pd
    pv = pd.Series(pv_list[1:], index=prices.index[start_idx:])
    tl = pd.DataFrame(trade_log)
    return pv, tl


def main():
    print("Laddar universum och data (delad, oforandrad kod - tar en stund pa full skala)...")
    tickers, universe_by_month = bt.load_universe()
    close, high, low, volume = bt.load_price_matrices(tickers, bt.FULL_START, bt.FULL_END)
    hedge = bt.load_hedge(bt.FULL_START, bt.FULL_END)
    tidx = {t: i for i, t in enumerate(close.columns)}
    log_ret = np.log(close).diff()
    log_p = np.log(close)

    print("Identifierar par...")
    pairs_by_date = bt.identify_pairs_dynamic(close, log_ret, universe_by_month, bt.COINT_WINDOW, bt.MIN_PAIRS, bt.CORR_THRESH, bt.MAX_PAIRS)
    print("Berknar z-score...")
    zscore_df = bt.compute_zscore(close, log_p, pairs_by_date, bt.COINT_WINDOW, bt.ZSCORE_WINDOW, tidx)
    print("Beraknar beta (optimerad)...")
    beta_df = bt.compute_beta(close, hedge, bt.BETA_WINDOW)
    print("Beraknar spread...")
    spread_df = bt.compute_spread_matrix(high, low)

    capital_level = 100_000.0

    print("\nKor MED SPY-hedge (riktiga HYP-009-metoden)...")
    t0 = time.time()
    pv_hedged, tl_hedged = bt.run_backtest(close, hedge, zscore_df, beta_df, spread_df, volume, capital_level)
    print(f"  Klar pa {time.time()-t0:.1f}s")

    print("Kor UTAN SPY-hedge (diagnostik)...")
    t0 = time.time()
    pv_unhedged, tl_unhedged = run_backtest_no_hedge(close, hedge, zscore_df, beta_df, spread_df, volume, capital_level)
    print(f"  Klar pa {time.time()-t0:.1f}s")

    print("\n" + "=" * 60)
    print(f"MED hedge:   Sharpe={bt.sharpe(pv_hedged):.3f}  CAGR={bt.cagr(pv_hedged):+.2%}  MaxDD={bt.max_drawdown(pv_hedged):.1%}  trades={len(tl_hedged)}")
    print(f"UTAN hedge:  Sharpe={bt.sharpe(pv_unhedged):.3f}  CAGR={bt.cagr(pv_unhedged):+.2%}  MaxDD={bt.max_drawdown(pv_unhedged):.1%}  trades={len(tl_unhedged)}")
    print("=" * 60)

    RESULTS_DIR = REPO_ROOT / "strategies" / "HYP-009" / "diagnostics"
    RESULTS_DIR.mkdir(exist_ok=True)
    pv_hedged.to_csv(RESULTS_DIR / "pv_hedged.csv", header=["portfolio_value"])
    pv_unhedged.to_csv(RESULTS_DIR / "pv_unhedged.csv", header=["portfolio_value"])
    print(f"\nSparat till {RESULTS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
