#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes an - ingen K-kostnad): DAGLIGT sparad
version av momentum long/short-sviten (se
diagnostic_momentum_long_short_sleeve.py for den forsta, kvartalsvisa
versionen) - byggd efter att den kvartalsvisa korrelationsberakningen
visade sig vila pa for fa datapunkter (57 kvartal) for att lita pa med
sakerhet, upptackt via en oberoende dubbelkoll mot den redan kanda
SPY/HYP-037-korrelationen (som visade sig vara -0.003 dagligen men
0.67 kvartalsvis - en verklig, inte felaktig, skillnad).

Samma mekanism som forsta versionen (12-1-manaders momentum, kvartalsvis
ombalansering, long topp-decil / kort botten-decil, dollar-neutralt),
men portfoljvardet sparas DAGLIGEN mellan ombalanseringarna (samma
princip som HYP-037:s egen dagliga vardering) - ger ~3500 datapunkter
istallet for 57, statistiskt mycket mer tillforlitligt for
korrelationsberakningen.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

STRATEGY_DIR = Path(__file__).resolve().parent.parent / "strategies" / "HYP-037"
sys.path.insert(0, str(STRATEGY_DIR))
import backtest as hyp037  # noqa: E402
from friction import borrow_cost  # noqa: E402

MOM_LOOKBACK_DAYS = 252
MOM_SKIP_DAYS = 21
DECILE_FRACTION = 0.10
REBAL_FREQ = "QE"
BORROW_ANNUAL_RATE = 0.03
RF_ANNUAL = 0.02


def main():
    print("Laddar universum, prismatriser (samma pipeline, aterananvander redan cachad data)...")
    tickers, universe_by_month = hyp037.load_universe()
    close, close_adj, high, low, volume = hyp037.load_price_matrices(tickers, hyp037.FULL_START, hyp037.FULL_END)

    print("Sanerar prisdata (standardfilter + konstant-kvot-sarhet)...")
    close, high, low = hyp037.clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    implausible = hyp037.flag_implausible_liquidity(close, volume, max_market_cap=hyp037.MAX_MARKET_CAP,
                                                      window=hyp037.ADV_WINDOW, multiplier=1.0)
    close_adj = close_adj.mask(implausible)
    ratio = (close_adj / close).replace([np.inf, -np.inf], np.nan)
    implausible_ratio = (ratio > 100) | (ratio < 0.01)
    n_affected = int(implausible_ratio.any(axis=0).sum())
    print(f"  {n_affected} tickers med orimlig kvot - maskade.")
    close_adj = close_adj.mask(implausible_ratio)

    print("Beräknar 12-1-manaders momentumsignal...")
    momentum = close_adj.shift(MOM_SKIP_DAYS) / close_adj.shift(MOM_LOOKBACK_DAYS) - 1
    daily_ret = close_adj.pct_change()

    tidx = {t: i for i, t in enumerate(close.columns)}
    calendar_dates = close.resample(REBAL_FREQ).last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[MOM_LOOKBACK_DAYS])
                                     & (calendar_dates <= close.index[-1])]
    snapped = hyp037.snap_rebalance_dates(calendar_dates, close.index)
    rebal_map = dict(zip(snapped["execution_date"], snapped["calendar_label"]))
    rebal_set = set(snapped["execution_date"])

    start_idx = close.index.get_indexer([snapped["execution_date"].iloc[0]])[0]
    trade_dates = close.index[start_idx:]

    long_names, short_names = [], []
    pv_list = [1.0]

    for date_i in range(start_idx, len(close.index)):
        date = close.index[date_i]

        if date in rebal_set:
            month_key = rebal_map[date].strftime("%Y-%m-%d")
            eligible = [t for t in universe_by_month.get(month_key, []) if t in tidx]
            mom_today = momentum.loc[date, eligible].dropna()
            if len(mom_today) >= 20:
                ranked = mom_today.sort_values()
                n_decile = max(1, int(len(ranked) * DECILE_FRACTION))
                short_names = list(ranked.index[:n_decile])
                long_names = list(ranked.index[-n_decile:])

        if date_i > start_idx and (long_names or short_names):
            long_r = daily_ret.loc[date, long_names].mean() if long_names else 0.0
            short_r = daily_ret.loc[date, short_names].mean() if short_names else 0.0
            long_r = 0.0 if np.isnan(long_r) else long_r
            short_r = 0.0 if np.isnan(short_r) else short_r

            daily_borrow = borrow_cost(position_value=0.5, holding_days=1, annual_rate=BORROW_ANNUAL_RATE)
            period_ret = 0.5 * long_r - 0.5 * short_r - daily_borrow + (RF_ANNUAL / 252)
            pv_list.append(pv_list[-1] * (1 + period_ret))
        else:
            pv_list.append(pv_list[-1])

    ls_pv = pd.Series(pv_list[1:], index=trade_dates)

    def sharpe(s, rf=RF_ANNUAL):
        r = s.pct_change().dropna()
        return float(np.sqrt(252) * (r - rf / 252).mean() / r.std()) if r.std() > 0 else 0.0

    def max_drawdown(s):
        return float(((s - s.cummax()) / s.cummax()).min())

    def cagr(s):
        return float((s.iloc[-1] / s.iloc[0]) ** (252 / len(s)) - 1)

    print(f"\nDaglig L/S-svit: {len(ls_pv)} dagar")
    print(f"Sharpe={sharpe(ls_pv):.4f}  CAGR={cagr(ls_pv):+.2%}  MaxDD={max_drawdown(ls_pv):.2%}\n")

    spy = hyp037.load_hedge(hyp037.FULL_START, hyp037.FULL_END)
    h37 = pd.read_csv(STRATEGY_DIR / "results" / "portfolio_value_100000.csv",
                       index_col=0, parse_dates=True)["portfolio_value"]

    ls_ret = ls_pv.pct_change().dropna()
    spy_ret = spy.pct_change().dropna()
    h37_ret = h37.pct_change().dropna()
    df = pd.concat([ls_ret.rename("Momentum_LS"), spy_ret.rename("SPY"), h37_ret.rename("HYP037")],
                    axis=1, join="inner").dropna()
    print(f"Overlappande DAGAR: {len(df)} (jamfor mot 57 kvartal i forra versionen)\n")
    print("Korrelationsmatris (DAGLIGA avkastningar):")
    print(df.corr().round(4))

    ls_pv.to_csv(Path(__file__).resolve().parent.parent / "data" / "cache" / "momentum_ls_sleeve_daily_pv.csv",
                 header=["portfolio_value"])
    print("\nSparad till data/cache/momentum_ls_sleeve_daily_pv.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
