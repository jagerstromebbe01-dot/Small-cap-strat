#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes - ingen K-kostnad, ingen pass_fail_criterion):
"lamna-en-kris-ute"-robusthetstest av HYP-017:s krasch-overlay.

Fraga: ar HYP-017:s PASS beroende av EN specifik episod (t.ex. covid), eller
haller resultatet ihop aven om overlayen fick INTE reagera pa en given
episod i taget? Overlayen triggade pa 5 oberoende episoder (se
trade_log_100000.csv, kolumn type=='crash_overlay_exit', grupperat per
datum): 2011-08-04, 2015-08-24, 2018-12-24, covid (2020-02-27 till
2020-03-16, flera triggningar), 2022 (2022-06-16 och 2022-09-26).

Metod: kor om HYP-017:s exakta backtest 5 ganger, en gang per episod -
varje korning stanger AV overlayens mojlighet att trigga bara under DEN
episodens datum (som om spy_10d_ret vore NaN just da), men lamnar den
aktiv for de andra 4 episoderna. Om Sharpe/MaxDD fortfarande haller ihop
nar en enskild episod plockas bort, ar resultatet inte beroende av just
den episoden. Detta ror INTE registrets redan sparade HYP-017-resultat -
bara en diagnostik ovanpa.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

STRATEGY_DIR = Path(__file__).resolve().parent.parent / "strategies" / "HYP-017"
sys.path.insert(0, str(STRATEGY_DIR))
import backtest as hyp017  # noqa: E402

EPISODES = {
    "2011 (skuldtakskrisen)": ["2011-08-04"],
    "2015 (Black Monday)": ["2015-08-24"],
    "2018 (julafton-massakern)": ["2018-12-24"],
    "2020 (covid)": ["2020-02-27", "2020-03-03", "2020-03-05", "2020-03-11", "2020-03-16"],
    "2022 (björnmarknad)": ["2022-06-16", "2022-09-26"],
}


def run_backtest_leave_out(close, close_adj, hedge, vol_df, beta_df, spread_df, volume,
                            universe_by_month, capital_level, excluded_dates: set):
    """Identisk kopia av hyp017.run_backtest(), MED ett tillagg: overlayen
    far inte trigga pa datum i excluded_dates (som om spy10 vore NaN da)."""
    tickers = list(close.columns)
    tidx = {t: i for i, t in enumerate(tickers)}
    hedge_ret = hedge.pct_change()
    dollar_volume = (close * volume).rolling(hyp017.ADV_WINDOW).mean()

    spy_10d_ret_v = hedge.pct_change(hyp017.CRASH_LOOKBACK_DAYS).values
    haircut_active = False

    calendar_dates = close.resample(hyp017.REBAL_FREQ).last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[hyp017.VOL_MIN_HISTORY]) & (calendar_dates <= close.index[-1])]
    snapped = hyp017.snap_rebalance_dates(calendar_dates, close.index)
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
        cash += cash * (hyp017.RF_ANNUAL / 252)

        if date in rebal_set:
            month_key = rebal_map[date].strftime("%Y-%m-%d")
            eligible = [t for t in universe_by_month.get(month_key, []) if t in tidx]
            vol_today = vol_df.loc[date]
            scores = []
            for t in eligible:
                v = vol_today[t]
                cp = prices_v[date_i, tidx[t]]
                if not np.isnan(v) and not np.isnan(cp) and cp > 0:
                    scores.append((v, t, cp))
            scores.sort()
            n_top = max(1, int(len(scores) * hyp017.DECILE_FRACTION)) if scores else 0
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
                    cap_dollar = adv * hyp017.MAX_ADV_PCT if not np.isnan(adv) else target_dollar_per_name
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

        # ── Krasch-overlay, MED lamna-ute-undantag ──
        date_str = date.strftime("%Y-%m-%d")
        spy10 = spy_10d_ret_v[date_i]
        if date_str in excluded_dates:
            haircut_active = False  # denna episod ska INTE fa trigga har
        elif not np.isnan(spy10) and spy10 < hyp017.CRASH_TRIGGER_RET and not haircut_active:
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

        daily_borrow = hyp017.borrow_cost(position_value=abs(long_beta), holding_days=1, annual_rate=hyp017.BORROW_ANNUAL_RATE)
        hedge_pnl = -long_beta * hr - long_beta * (hyp017.RF_ANNUAL / 2 / 252) - daily_borrow

        pv_list.append(cash + long_val + hedge_pnl)

    pv = pd.Series(pv_list[1:], index=trade_dates)
    return pv


def main():
    print("Laddar universum...")
    tickers, universe_by_month = hyp017.load_universe()

    print("Laddar prismatriser...")
    close, close_adj, high, low, volume = hyp017.load_price_matrices(tickers, hyp017.FULL_START, hyp017.FULL_END)
    hedge = hyp017.load_hedge(hyp017.FULL_START, hyp017.FULL_END)

    print("Sanerar prisdata...")
    close, high, low = hyp017.clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())

    print("Flaggar leverantors-datafel...")
    implausible = hyp017.flag_implausible_liquidity(close, volume, max_market_cap=hyp017.MAX_MARKET_CAP,
                                                     window=hyp017.ADV_WINDOW, multiplier=1.0)
    close = close.mask(implausible)
    close_adj = close_adj.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)

    print("Beräknar beta, idio-vol-signal, Corwin-Schultz-spread...\n")
    beta_df = hyp017.compute_beta(close_adj, hedge, hyp017.BETA_WINDOW)
    vol_df = hyp017.compute_idiosyncratic_vol(close_adj, hedge, beta_df, hyp017.VOL_LOOKBACK_DAYS)
    spread_df = hyp017.compute_spread_matrix(high, low)

    levels = [100_000, 1_000_000, 10_000_000]

    print("=" * 90)
    print(f"{'Scenario':<32}{'Nivå':<12}{'Sharpe':<10}{'MaxDD':<10}{'Calmar':<10}{'PASS?':<8}")
    print("=" * 90)

    def sharpe(s):
        return hyp017.sharpe(s)

    def maxdd(s):
        return hyp017.max_drawdown(s)

    def calmar(s):
        return hyp017.calmar(s)

    def passfail(sh, dd):
        return "JA" if (sh >= 0.55 and dd > -0.30) else "NEJ"

    # Full HYP-017 (referens, inget uteslutet)
    for level in levels:
        pv = run_backtest_leave_out(close, close_adj, hedge, vol_df, beta_df, spread_df, volume,
                                     universe_by_month, level, excluded_dates=set())
        sh, dd, cal = sharpe(pv), maxdd(pv), calmar(pv)
        print(f"{'FULL (referens)':<32}${level:<11,.0f}{sh:<10.3f}{dd:<10.2%}{cal:<10.3f}{passfail(sh, dd):<8}")
    print("-" * 90)

    results = {}
    for name, dates in EPISODES.items():
        excluded = set(dates)
        row = []
        for level in levels:
            pv = run_backtest_leave_out(close, close_adj, hedge, vol_df, beta_df, spread_df, volume,
                                         universe_by_month, level, excluded_dates=excluded)
            sh, dd, cal = sharpe(pv), maxdd(pv), calmar(pv)
            row.append((sh, dd, cal))
            print(f"{('utan ' + name):<32}${level:<11,.0f}{sh:<10.3f}{dd:<10.2%}{cal:<10.3f}{passfail(sh, dd):<8}")
        results[name] = row
        print("-" * 90)

    print("\nKLART.")


if __name__ == "__main__":
    sys.exit(main())
