"""
Engångsdiagnostik: HYP-057 (spegelvänd HYP-055) - sanity-check av det
extrema MaxDD-talet (-99.49% vid $100k) och verifiering av att
signalriktningen faktiskt ÄR omvänd mot HYP-055, inte en oavsiktlig
kopia. Samma disciplin som redan etablerad för HYP-049/050/055 idag
(2026-08-10).

Två saker undersöks:
  1. Triggerdiagnostiken (n_long_triggers/n_short_triggers) är EXAKT
     omkastad mot HYP-055:s motsvarande tal - bekräftar att mekanismen
     körs på samma underliggande veckor/korgar, bara med riktningen
     omvänd (inte en kopierings-bugg).
  2. Per-position nettoavkastning vid $100k: är förlusten bred och jämn
     (som HYP-055:s postmortem) eller domineras den av enstaka
     exploderade positioner?
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "strategies" / "HYP-057"))
import backtest as b  # noqa: E402


def instrumented_run_backtest(open_, close, close_adj, spread_df, adv_cap, weekly_signals, capital_level):
    """Kopia av b.run_backtest() men loggar varje avslutad positions
    entry/exit-varde och riktning, for postmortem-diagnostik."""
    tickers = list(close_adj.columns)
    tidx = {t: i for i, t in enumerate(tickers)}

    daily_ret_v = close_adj.pct_change().values
    open_adj = b.adjusted_open(open_, close, close_adj)
    entry_day_ret_v = (close_adj / open_adj - 1.0).values
    spread_v = spread_df.reindex(columns=tickers).values
    adv_cap_v = adv_cap.reindex(columns=tickers).values

    start_idx = min(weekly_signals.keys())
    cash = float(capital_level)
    positions = {}
    trade_log = []

    for date_i in range(start_idx, len(close_adj.index)):
        cash += cash * (b.RF_ANNUAL / 252)

        for g in list(positions.keys()):
            pos = positions[g]
            days_held = date_i - pos["entry_date_i"]
            if days_held < b.HOLD_DAYS:
                continue
            idxs = np.array([tidx[t] for t in pos["names"] if t in tidx])
            rets_today = daily_ret_v[date_i, idxs]
            valid = ~np.isnan(rets_today)
            basket_ret = float(rets_today[valid].mean()) if valid.any() else 0.0
            sign = 1.0 if pos["direction"] == "long" else -1.0
            pos["value"] *= (1.0 + sign * basket_ret)
            if pos["direction"] == "short":
                pos["value"] -= b.borrow_cost(position_value=max(pos["value"], 0.0), holding_days=1,
                                               annual_rate=b.BORROW_ANNUAL_RATE)
            ex_spreads = spread_v[date_i, idxs]
            valid_s = ~np.isnan(ex_spreads)
            avg_ex_spread = float(ex_spreads[valid_s].mean()) if valid_s.any() else 0.0
            pos["value"] *= (1.0 - avg_ex_spread / 2.0)
            cash += pos["value"]
            trade_log.append({
                "group": g, "direction": pos["direction"], "entry_date_i": pos["entry_date_i"],
                "exit_date_i": date_i, "entry_value": pos["entry_value"], "exit_value": pos["value"],
                "net_return": pos["value"] / pos["entry_value"] - 1.0 if pos["entry_value"] > 0 else 0.0,
                "n_names": len(pos["names"]),
            })
            del positions[g]

        todays_signals = weekly_signals.get(date_i, [])
        new_signals = [s for s in todays_signals if s["group"] not in positions]

        if new_signals:
            target_per_group = cash / len(new_signals)
            for sig in new_signals:
                g, direction, names = sig["group"], sig["direction"], sig["names"]
                idxs = np.array([tidx[t] for t in names if t in tidx])
                if len(idxs) == 0:
                    continue
                cap_row = adv_cap_v[date_i, idxs]
                cap_total = np.nansum(cap_row) if not np.all(np.isnan(cap_row)) else 0.0
                realized = min(target_per_group, cap_total, cash) if cap_total > 0 else 0.0
                if realized < capital_level * 0.0001 or realized <= 0:
                    continue

                en_spreads = spread_v[date_i, idxs]
                valid_s = ~np.isnan(en_spreads)
                avg_en_spread = float(en_spreads[valid_s].mean()) if valid_s.any() else 0.0
                value = realized * (1.0 - avg_en_spread / 2.0)

                rets0 = entry_day_ret_v[date_i, idxs]
                valid0 = ~np.isnan(rets0)
                basket_ret0 = float(rets0[valid0].mean()) if valid0.any() else 0.0
                sign = 1.0 if direction == "long" else -1.0
                value *= (1.0 + sign * basket_ret0)
                if direction == "short":
                    value -= b.borrow_cost(position_value=max(value, 0.0), holding_days=1,
                                            annual_rate=b.BORROW_ANNUAL_RATE)

                cash -= realized
                positions[g] = {"direction": direction, "names": names, "entry_date_i": date_i,
                                 "value": value, "entry_value": value}

        for g, pos in positions.items():
            if date_i - pos["entry_date_i"] == 0:
                continue
            idxs = np.array([tidx[t] for t in pos["names"] if t in tidx])
            rets_today = daily_ret_v[date_i, idxs]
            valid = ~np.isnan(rets_today)
            basket_ret = float(rets_today[valid].mean()) if valid.any() else 0.0
            sign = 1.0 if pos["direction"] == "long" else -1.0
            pos["value"] *= (1.0 + sign * basket_ret)
            if pos["direction"] == "short":
                pos["value"] -= b.borrow_cost(position_value=max(pos["value"], 0.0), holding_days=1,
                                               annual_rate=b.BORROW_ANNUAL_RATE)

    return trade_log


def main():
    print("Laddar universum + prisdata (samma pipeline som backtest.py main())...")
    with b.ORIGINAL_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_orig = json.load(f)
    with b.EXTENSION_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_2025 = json.load(f)
    universe_merged = {**universe_orig, **universe_2025}
    tickers = sorted({t for tks in universe_merged.values() for t in tks})

    open_, close, close_adj, high, low, volume = b.load_price_matrices(tickers, b.FULL_START, b.FULL_END)
    close, high, low = b.clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    open_ = open_.where(close.notna())
    close = b.mask_unrecovered_price_breaks(close)
    high = high.where(close.notna())
    low = low.where(close.notna())
    close_adj = close_adj.where(close.notna())
    open_ = open_.where(close.notna())
    implausible = b.flag_implausible_liquidity(close, volume, max_market_cap=b.MAX_MARKET_CAP,
                                                window=b.ADV_WINDOW, multiplier=1.0)
    close = close.mask(implausible)
    close_adj = close_adj.mask(implausible)
    open_ = open_.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)
    close_adj = b.mask_implausible_adjusted_close_ratio(close, close_adj)
    spread_df = b.compute_spread_matrix(high, low)
    major_group_map = b.load_ticker_major_group(list(close_adj.columns))
    dollar_vol_60 = (close_adj * volume).rolling(b.LIQUIDITY_WINDOW, min_periods=b.LIQUIDITY_WINDOW).mean()
    adv_cap = (close * volume).rolling(b.ADV_WINDOW, min_periods=b.ADV_WINDOW).mean() * b.MAX_ADV_PCT

    weekly_signals, diag = b.build_weekly_group_signals(close_adj, dollar_vol_60, universe_merged, major_group_map)

    print("\n--- Triggerdiagnostik (jamfor mot HYP-055) ---")
    print(f"HYP-057: n_long_triggers={diag['n_long_triggers']}  n_short_triggers={diag['n_short_triggers']}")
    print("HYP-055 (fran registrerat resultat): n_long_triggers=2886  n_short_triggers=2778")
    hyp055_long, hyp055_short = 2886, 2778
    ok_mirror = (diag["n_long_triggers"] == hyp055_short) and (diag["n_short_triggers"] == hyp055_long)
    print(f"EXAKT SPEGELVAND (057.long==055.short OCH 057.short==055.long)? {ok_mirror}")
    if not ok_mirror:
        print("  VARNING: riktningen verkar INTE vara en ren spegelvandning av HYP-055 - undersok vidare!")

    print("\nKor instrumenterad backtest ($100k, avgorande niva) for att logga alla avslutade positioner...")
    trade_log = instrumented_run_backtest(open_, close, close_adj, spread_df, adv_cap, weekly_signals, 100_000)
    n = len(trade_log)
    net_returns = np.array([t["net_return"] for t in trade_log])
    longs = [t for t in trade_log if t["direction"] == "long"]
    shorts = [t for t in trade_log if t["direction"] == "short"]

    print(f"\nTotalt avslutade positioner: {n}")
    print(f"  Andel forlorande (net_return < 0): {(net_returns < 0).mean():.1%}")
    print(f"  Snitt nettoavkastning long:  {np.mean([t['net_return'] for t in longs]):+.4%}  (n={len(longs)})")
    print(f"  Snitt nettoavkastning short: {np.mean([t['net_return'] for t in shorts]):+.4%}  (n={len(shorts)})")
    print(f"  Andel positioner med nettoforlust > 50% av egen notional: {(net_returns < -0.50).mean():.3%} "
          f"({(net_returns < -0.50).sum()} st)")
    print(f"  Varsta enskilda positionsforlust: {net_returns.min():+.2%}")
    print(f"  Basta enskilda positionsvinst: {net_returns.max():+.2%}")

    worst = sorted(trade_log, key=lambda t: t["net_return"])[:5]
    print("\nDe 5 varsta enskilda positionerna:")
    for t in worst:
        print(f"  group={t['group']}  dir={t['direction']}  entry_i={t['entry_date_i']}  "
              f"exit_i={t['exit_date_i']}  n_names={t['n_names']}  net_return={t['net_return']:+.2%}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
