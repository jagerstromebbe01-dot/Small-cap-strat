#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes - ingen K-kostnad, ingen pass_fail_criterion):
testar om HYP-017:s krasch-overlay (SPY 10-dagars-avkastning < -10% ->
skar till 40%) OCKSA tamjer HYP-012/016:s momentum-signals MaxDD-problem,
eller om den bara fungerar for lagvol-signalen.

Fraga (fran konversationen 2026-07-30): ar krasch-overlayen en UNIVERSUM-
egenskap (small-cap paniksaljs i kris oavsett vilken signal man kor ovanpa)
eller en SIGNAL-specifik fix? HYP-016 visade att vol-skalning (Barroso &
Santa-Clara, literaturens standardrecept for just momentum) knappt rorde
momentums MaxDD. Detta testar en helt annan mekanism - samma overlay som
faktiskt fungerade for HYP-015/017 - pa momentum-signalen, for att se om
mekanismen generaliserar over signaltyper eller inte.

Bygger pa HYP-016:s OSKALADE baslinje-motor (dvs momentum utan vol-
skalning - vi vill isolera krasch-overlayens effekt separat fran
vol-skalningen som redan testats och FAILED), med krasch-overlayen
importerad rakt av fran HYP-017 (samma konstanter, samma mekanism -
inga nya parametrar hittade pa har).
"""

import sys
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

STRATEGIES_DIR = Path(__file__).resolve().parent.parent / "strategies"


def _load_module(name, path):
    """Bada HYP-016 och HYP-017 heter 'backtest.py' - laddas har med unika
    modulnamn via importlib sa de inte krockar i sys.modules."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hyp016 = _load_module("hyp016_backtest", STRATEGIES_DIR / "HYP-016" / "backtest.py")
hyp017 = _load_module("hyp017_backtest", STRATEGIES_DIR / "HYP-017" / "backtest.py")


def run_momentum_with_crash_overlay(close, close_adj, hedge, mom_df, beta_df, spread_df, volume,
                                     universe_by_month, capital_level):
    """HYP-016:s OSKALADE momentum-motor (exposure_scale=None-logiken,
    dvs identisk med HYP-012), MED HYP-017:s krasch-overlay tillagd
    (samma konstanter: CRASH_LOOKBACK_DAYS, CRASH_TRIGGER_RET,
    CRASH_HAIRCUT_FRACTION, importerade fran hyp017-modulen rakt av)."""
    tickers = list(close.columns)
    tidx = {t: i for i, t in enumerate(tickers)}
    hedge_ret = hedge.pct_change()
    dollar_volume = (close * volume).rolling(hyp016.ADV_WINDOW).mean()

    spy_10d_ret_v = hedge.pct_change(hyp017.CRASH_LOOKBACK_DAYS).values
    haircut_active = False

    calendar_dates = close.resample("ME").last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[hyp016.MOM_MIN_HISTORY]) & (calendar_dates <= close.index[-1])]
    snapped = hyp016.snap_rebalance_dates(calendar_dates, close.index)
    rebal_map = dict(zip(snapped["execution_date"], snapped["calendar_label"]))
    rebal_set = set(snapped["execution_date"])

    start_idx = close.index.get_indexer([snapped["execution_date"].iloc[0]])[0]
    trade_dates = close.index[start_idx:]

    prices_v = close_adj.values
    beta_v = beta_df.values
    spread_v = spread_df.reindex(columns=tickers).values
    hedge_ret_v = hedge_ret.values

    cash = float(capital_level)
    holdings = {}
    pv_list = [float(capital_level)]
    trade_log = []

    for date_i in range(start_idx, len(close.index)):
        date = close.index[date_i]
        hr_raw = hedge_ret_v[date_i]
        hr = float(hr_raw) if not np.isnan(hr_raw) else 0.0
        cash += cash * (hyp016.RF_ANNUAL / 252)

        if date in rebal_set:
            month_key = rebal_map[date].strftime("%Y-%m-%d")
            eligible = [t for t in universe_by_month.get(month_key, []) if t in tidx]
            mom_today = mom_df.loc[date]
            scores = []
            for t in eligible:
                m = mom_today[t]
                cp = prices_v[date_i, tidx[t]]
                if not np.isnan(m) and not np.isnan(cp) and cp > 0:
                    scores.append((m, t, cp))
            scores.sort(reverse=True)
            n_top = max(1, int(len(scores) * hyp016.DECILE_FRACTION)) if scores else 0
            target_tickers = {t for _, t, _ in scores[:n_top]}

            for t in list(holdings.keys()):
                if t not in target_tickers:
                    ti = tidx[t]
                    cp = prices_v[date_i, ti]
                    if np.isnan(cp):
                        cp = holdings[t]["last_price"]
                    proceeds = holdings[t]["shares"] * cp
                    exit_spread = spread_v[date_i, ti]
                    if not np.isnan(exit_spread):
                        proceeds -= proceeds * (exit_spread / 2)
                    cash += proceeds
                    ret = proceeds / holdings[t]["cost"] - 1
                    trade_log.append({"date": date, "ticker": t, "ret": ret, "type": "rebalance_exit",
                                       "cost": holdings[t]["cost"]})
                    del holdings[t]

            new_names = [t for t in target_tickers if t not in holdings]
            if new_names:
                target_dollar_per_name = cash / len(new_names) if len(new_names) > 0 else 0.0
                for t in new_names:
                    ti = tidx[t]
                    cp = prices_v[date_i, ti]
                    if np.isnan(cp) or cp <= 0:
                        continue
                    adv = dollar_volume.values[date_i, ti]
                    cap_dollar = adv * hyp016.MAX_ADV_PCT if not np.isnan(adv) else target_dollar_per_name
                    sz = min(target_dollar_per_name, cap_dollar)
                    if sz < capital_level * 0.0001 or sz > cash:
                        sz = min(sz, cash)
                    if sz <= 0:
                        continue
                    entry_spread = spread_v[date_i, ti]
                    effective_entry = cp * (1 + entry_spread / 2) if not np.isnan(entry_spread) else cp
                    shares = sz / effective_entry
                    cash -= sz
                    holdings[t] = {"shares": shares, "entry": effective_entry, "cost": sz, "last_price": cp}

        # ── Krasch-overlay, importerad rakt av fran HYP-017 (samma konstanter) ──
        spy10 = spy_10d_ret_v[date_i]
        if not np.isnan(spy10) and spy10 < hyp017.CRASH_TRIGGER_RET and not haircut_active:
            for t in list(holdings.keys()):
                ti = tidx[t]
                cp = prices_v[date_i, ti]
                if np.isnan(cp):
                    cp = holdings[t]["last_price"]
                shares_to_sell = holdings[t]["shares"] * (1 - hyp017.CRASH_HAIRCUT_FRACTION)
                proceeds = shares_to_sell * cp
                exit_spread = spread_v[date_i, ti]
                if not np.isnan(exit_spread):
                    proceeds -= proceeds * (exit_spread / 2)
                cash += proceeds
                sold_cost = holdings[t]["cost"] * (1 - hyp017.CRASH_HAIRCUT_FRACTION)
                trade_log.append({"date": date, "ticker": t,
                                   "ret": proceeds / sold_cost - 1 if sold_cost > 0 else 0.0,
                                   "type": "crash_overlay_exit", "cost": sold_cost})
                holdings[t]["shares"] -= shares_to_sell
                holdings[t]["cost"] -= sold_cost
            haircut_active = True
        elif not np.isnan(spy10) and spy10 >= hyp017.CRASH_TRIGGER_RET:
            haircut_active = False

        long_val = 0.0
        long_beta = 0.0
        for t, h in holdings.items():
            ti = tidx[t]
            cp = float(prices_v[date_i, ti])
            if np.isnan(cp):
                cp = h["last_price"]
            else:
                h["last_price"] = cp
            val = h["shares"] * cp
            long_val += val
            long_beta += val * float(beta_v[date_i, ti])

        daily_borrow = hyp016.borrow_cost(position_value=abs(long_beta), holding_days=1, annual_rate=hyp016.BORROW_ANNUAL_RATE)
        hedge_pnl = -long_beta * hr - long_beta * (hyp016.RF_ANNUAL / 2 / 252) - daily_borrow

        pv_list.append(cash + long_val + hedge_pnl)

    pv = pd.Series(pv_list[1:], index=trade_dates)
    tl = pd.DataFrame(trade_log)
    return pv, tl


def main():
    print("Laddar universum...")
    tickers, universe_by_month = hyp016.load_universe()

    print("Laddar prismatriser...")
    close, close_adj, high, low, volume = hyp016.load_price_matrices(tickers, hyp016.FULL_START, hyp016.FULL_END)
    hedge = hyp016.load_hedge(hyp016.FULL_START, hyp016.FULL_END)

    print("Sanerar prisdata...")
    close, high, low = hyp016.clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())

    print("Flaggar leverantors-datafel...")
    implausible = hyp016.flag_implausible_liquidity(close, volume, max_market_cap=hyp016.MAX_MARKET_CAP,
                                                     window=hyp016.ADV_WINDOW, multiplier=1.0)
    close = close.mask(implausible)
    close_adj = close_adj.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)

    print("Beräknar momentum-signal, beta, Corwin-Schultz-spread...\n")
    mom_df = hyp016.compute_momentum(close_adj)
    beta_df = hyp016.compute_beta(close_adj, hedge, hyp016.BETA_WINDOW)
    spread_df = hyp016.compute_spread_matrix(high, low)

    levels = [100_000, 1_000_000, 10_000_000]

    print("=" * 90)
    print(f"{'Scenario':<30}{'Nivå':<12}{'CAGR':<10}{'Sharpe':<10}{'Calmar':<10}{'MaxDD':<10}{'Trades':<8}")
    print("=" * 90)

    for level in levels:
        pv, tl = run_momentum_with_crash_overlay(close, close_adj, hedge, mom_df, beta_df, spread_df, volume,
                                                   universe_by_month, level)
        sh = hyp016.sharpe(pv)
        dd = hyp016.max_drawdown(pv)
        cal = hyp016.calmar(pv)
        cg = hyp016.cagr(pv)
        print(f"{'momentum + krasch-overlay':<30}${level:<11,.0f}{cg:<10.2%}{sh:<10.3f}{cal:<10.3f}{dd:<10.2%}{len(tl):<8}")

    print("-" * 90)
    print("Jamforelse (redan i registret, HYP-016):")
    print(f"{'momentum, oskalad baslinje':<30}$100,000    -3.4%     -0.045    -           -76.6%")
    print(f"{'momentum, vol-skalad (HYP-016)':<30}$100,000    -3.9%     -0.105    -0.051      -76.2%")
    print("\nKLART.")


if __name__ == "__main__":
    sys.exit(main())
