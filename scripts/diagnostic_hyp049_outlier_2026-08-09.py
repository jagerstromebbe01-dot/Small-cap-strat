"""
Engångsdiagnostik v2: HYP-049s $100k-backtest visade en enskild dags
portföljavkastning på +35354% (2017-11-27). v1 använde fel
ombalanseringsdatum (efterföljande kvartal i stället för föregående) -
denna version hittar rätt ombalanseringsdatum (senaste <= target) och
letar efter NaN-gap-mönster (stale last_price -> plötslig återkomst vid
ett helt annat pris) per innehavt namn.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "strategies" / "HYP-049"))
import backtest as b  # noqa: E402
import numpy as np
import pandas as pd


def main():
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
    implausible = b.flag_implausible_liquidity(close, volume, max_market_cap=b.MAX_MARKET_CAP,
                                                window=b.ADV_WINDOW, multiplier=1.0)
    close = close.mask(implausible)
    close_adj = close_adj.mask(implausible)
    open_ = open_.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)
    close_adj = b.mask_implausible_adjusted_close_ratio(close, close_adj)

    score = b.compute_score(open_, close, close_adj)

    tickers2 = list(close.columns)
    tidx = {t: i for i, t in enumerate(tickers2)}

    target_i = close.index.get_loc(pd.Timestamp("2017-11-27"))
    prices_v = close_adj.values

    calendar_dates = close.resample(b.REBAL_FREQ).last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[b.SIGNAL_WINDOW])
                                     & (calendar_dates <= close.index[-1])]
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "strategies" / "common"))
    from rebalancing import snap_rebalance_dates
    snapped = snap_rebalance_dates(calendar_dates, close.index)

    prior = snapped[snapped["execution_date"] <= "2017-11-27"]
    rebal_date = prior["execution_date"].iloc[-1]
    rebal_i = close.index.get_loc(rebal_date)
    month_key = prior["calendar_label"].iloc[-1].strftime("%Y-%m-%d")
    print(f"Ratt ombalanseringsdatum (senaste <= target): {rebal_date}, month_key={month_key}")

    eligible = [t for t in universe_merged.get(month_key, []) if t in tidx]
    idxs = [tidx[t] for t in eligible]
    sc = pd.Series(score.values[rebal_i, idxs], index=eligible).dropna()
    ranked = sc.sort_values()
    n_decile = max(1, int(len(ranked) * b.DECILE_FRACTION))
    short_names = list(ranked.index[:n_decile])
    long_names = list(ranked.index[-n_decile:])
    print(f"n_decile={n_decile}, {len(short_names)} short, {len(long_names)} long")

    all_names = short_names + long_names
    print(f"\nSoker NaN-gap-monster (senaste giltiga pris FORE target ligger >5 handelsdagar bak) bland de {len(all_names)} innehaven:")
    for t in all_names:
        ti = tidx[t]
        col = prices_v[:target_i, ti]
        valid_idx = np.where(~np.isnan(col))[0]
        if len(valid_idx) == 0:
            continue
        last_valid_i = valid_idx[-1]
        gap = target_i - 1 - last_valid_i
        target_price = prices_v[target_i, ti]
        if np.isnan(target_price):
            continue
        last_valid_price = col[last_valid_i]
        if gap > 5:
            implied_ret = target_price / last_valid_price - 1
            print(f"  {t}: senaste giltiga pris FORE target var {gap} handelsdagar bak "
                  f"(index {last_valid_i}, {close.index[last_valid_i].date()}) = {last_valid_price:.4f}, "
                  f"target({close.index[target_i].date()})={target_price:.4f}  implicerad avkastning om man "
                  f"naivt jamfor = {implied_ret:+.2%}")

    print("\nDirekt dag-till-dag (target vs target-1) for samtliga innehav, sorterat:")
    rows = []
    for t in all_names:
        ti = tidx[t]
        p0 = prices_v[target_i - 1, ti]
        p1 = prices_v[target_i, ti]
        if np.isnan(p0) or np.isnan(p1) or p0 == 0:
            continue
        rows.append((t, p0, p1, p1 / p0 - 1))
    rows.sort(key=lambda x: abs(x[3]), reverse=True)
    for t, p0, p1, ret in rows[:10]:
        print(f"  {t}: {p0:.4f} -> {p1:.4f}  ({ret:+.2%})")


if __name__ == "__main__":
    main()
