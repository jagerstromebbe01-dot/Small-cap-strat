"""
HYP-042: Kortsiktig reversal (10-dagars trailing avkastning, veckovis
ombalansering, 10 dagars hallperiod, SPY-beta-hedge).

Se research/hypothesis_registry/HYP-042-kortsiktig-reversal.yaml for
det lasta kriteriet. Forsta genuint NYA aktiesignalen sedan HYP-035
(insiderkop) - HELT ANNAN ekonomisk mekanism (kortsiktig overreaktion)
an registrets befintliga edge (idiosynkratisk lagvolatilitet).

MEKANISM: varje VECKA (fredag, snappad till narmaste faktiska
handelsdag <= fredag), rangordnas hela det eligible small-cap-
universumet efter trailing 10-dagars avkastning. LONG botten-decilen
(samst presterande - reversal-tesen). Kop NASTA handelsdags oppning
(undviker framatblick). Salj efter EXAKT 10 handelsdagar (matchar
signalens egen horisont). SPY-beta-hedge, samma metod som HYP-037.
"""

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

STRATEGY_DIR = Path(__file__).resolve().parent
STRATEGIES_ROOT = STRATEGY_DIR.parent
DATA_DIR = STRATEGIES_ROOT.parent / "data"
CACHE_DIR = DATA_DIR / "cache"
OHLCV_DIR = CACHE_DIR / "ohlcv"
UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_by_month.json"
RESULTS_DIR = STRATEGY_DIR / "results"

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
from friction import borrow_cost, corwin_schultz_spread  # noqa: E402
from data_hygiene import clean_price_matrix, flag_implausible_liquidity  # noqa: E402
from rebalancing import snap_rebalance_dates  # noqa: E402

FULL_START = "2010-01-01"
FULL_END = "2024-12-31"

SIGNAL_LOOKBACK_DAYS = 10
HOLD_DAYS = 10
DECILE_FRACTION = 0.10
SELECTION_FREQ = "W-FRI"

BETA_WINDOW = 126
MAX_MARKET_CAP = 2_000_000_000
BORROW_ANNUAL_RATE = 0.03
MAX_ADV_PCT = 0.10
ADV_WINDOW = 20
RF_ANNUAL = 0.02
HEDGE = "SPY"


def load_universe():
    with UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_by_month = json.load(f)
    all_tickers = sorted({t for tickers in universe_by_month.values() for t in tickers})
    return all_tickers, universe_by_month


def trading_calendar(start, end):
    path = OHLCV_DIR / f"{HEDGE}.csv"
    df = pd.read_csv(path, usecols=["date"], parse_dates=["date"])
    dates = df["date"].drop_duplicates().sort_values()
    return pd.DatetimeIndex(dates[(dates >= start) & (dates <= end)])


def load_price_matrices(tickers, start, end):
    date_index = trading_calendar(start, end)
    open_s, close_s, adj_s, high_s, low_s, vol_s = {}, {}, {}, {}, {}, {}
    for t in tickers:
        path = OHLCV_DIR / f"{t}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path, usecols=["date", "open", "close", "adjusted_close", "high", "low", "volume"],
                          parse_dates=["date"])
        df = df.drop_duplicates(subset="date", keep="last").set_index("date").sort_index()
        open_s[t] = df["open"].astype("float32")
        close_s[t] = df["close"].astype("float32")
        adj_s[t] = df["adjusted_close"].astype("float32")
        high_s[t] = df["high"].astype("float32")
        low_s[t] = df["low"].astype("float32")
        vol_s[t] = df["volume"].astype("float32")

    open_ = pd.DataFrame(open_s).reindex(date_index)
    close = pd.DataFrame(close_s).reindex(date_index)
    close_adj = pd.DataFrame(adj_s).reindex(date_index)
    high = pd.DataFrame(high_s).reindex(date_index)
    low = pd.DataFrame(low_s).reindex(date_index)
    volume = pd.DataFrame(vol_s).reindex(date_index)
    return open_, close, close_adj, high, low, volume


def load_hedge(start, end):
    path = OHLCV_DIR / f"{HEDGE}.csv"
    df = pd.read_csv(path, usecols=["date", "adjusted_close"], parse_dates=["date"])
    df = df.drop_duplicates(subset="date", keep="last").set_index("date").sort_index()
    date_index = trading_calendar(start, end)
    return df["adjusted_close"].reindex(date_index)


def compute_beta(prices, hedge, beta_window):
    """Identisk till HYP-037/backtest.py::compute_beta()."""
    hedge_ret = hedge.pct_change()
    stock_ret = prices.pct_change()

    valid = stock_ret.notna() & hedge_ret.notna().values[:, None]
    x0 = stock_ret.where(valid, 0.0)
    y0 = pd.DataFrame(
        np.where(valid.values, np.broadcast_to(hedge_ret.values[:, None], valid.shape), 0.0),
        index=prices.index, columns=prices.columns,
    )

    n = valid.rolling(beta_window).sum().shift(1)
    sum_x = x0.rolling(beta_window).sum().shift(1)
    sum_y = y0.rolling(beta_window).sum().shift(1)
    sum_xy = (x0 * y0).rolling(beta_window).sum().shift(1)
    sum_y2 = (y0 * y0).rolling(beta_window).sum().shift(1)

    with np.errstate(invalid="ignore", divide="ignore"):
        mean_x = sum_x / n
        mean_y = sum_y / n
        cov = (sum_xy - n * mean_x * mean_y) / (n - 1)
        var_y = (sum_y2 - n * mean_y * mean_y) / (n - 1)
        beta_raw = cov / var_y

    enough_obs = (n >= 20).values
    valid_var = (var_y > 1e-8).values
    beta_arr = np.where(enough_obs & valid_var, beta_raw.values, 1.0).astype("float32")
    beta_arr = np.clip(beta_arr, -5.0, 5.0)
    return pd.DataFrame(beta_arr, index=prices.index, columns=prices.columns)


def compute_spread_matrix(high, low):
    spread = {}
    for t in high.columns:
        spread[t] = corwin_schultz_spread(high[t].values, low[t].values)
    return pd.DataFrame(spread, index=high.index)


# ════════════════════════════════════════════════════════════
#  BACKTEST-MOTOR
# ════════════════════════════════════════════════════════════
def adjusted_open(open_, close, close_adj):
    """
    BUGGFIX (motorfix 2-monstret, upptackt vid smoke-test 2026-08-06,
    ticker ACRX): entry MASTE anvanda ett split-justerat oppningspris,
    INTE ra open - annars berknas aktieantalet fran ett ojusterat pris
    men varderas sedan (vid exit/daglig vardering) mot close_adj, vilket
    over en RIKTIG split (t.ex. ACRX:s troliga omvanda split, ~20x)
    skapar en helt fiktiv vinst. Exakt samma buggklass som redan
    dokumenterad och fixad i HYP-037 (COL/ESSA/ARDMQ-fallen) och i
    HYP-040 (adjusted_ohlc()) - samma losning har: skala ra open med
    dagens close_adj/close-kvot.
    """
    ratio = (close_adj / close).replace([np.inf, -np.inf], np.nan)
    return open_ * ratio


def run_backtest(open_, close, close_adj, hedge, beta_df, spread_df, volume, universe_by_month, capital_level):
    tickers = list(close.columns)
    tidx = {t: i for i, t in enumerate(tickers)}
    hedge_ret = hedge.pct_change()
    dollar_volume = (close * volume).rolling(ADV_WINDOW).mean()

    signal = close_adj.pct_change(SIGNAL_LOOKBACK_DAYS)

    calendar_dates = close.resample(SELECTION_FREQ).last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[SIGNAL_LOOKBACK_DAYS + BETA_WINDOW])
                                     & (calendar_dates <= close.index[-1])]
    snapped = snap_rebalance_dates(calendar_dates, close.index)
    selection_dates = set(snapped["execution_date"])

    # Manads-nyckel per handelsdag: SAMMA monster som HYP-037:s
    # compute_universe_avg_spread/compute_bank_composite_returns - INTE
    # HYP-037:s egen rebal_map/calendar_label-genvag, som bara funkar
    # nar ombalanseringsfrekvensen redan AR manads-/kvartalsslut (var
    # veckovisa urvalsdatum ar det INTE, sa calendar_label skulle aldrig
    # matcha nagon nyckel i universe_by_month - upptackt och fixat innan
    # forsta korningen).
    month_keys = sorted(universe_by_month.keys())
    month_dates = pd.to_datetime(month_keys)
    day_month_idx = month_dates.searchsorted(close.index, side="right") - 1
    day_month_idx = np.clip(day_month_idx, 0, len(month_dates) - 1)

    start_idx = close.index.get_indexer([snapped["execution_date"].iloc[0]])[0]
    trade_dates = close.index[start_idx:]

    open_v = adjusted_open(open_, close, close_adj).values
    close_v = close.values
    prices_v = close_adj.values
    beta_v = beta_df.values
    spread_v = spread_df.reindex(columns=tickers).values
    hedge_ret_v = hedge_ret.values
    signal_v = signal.values

    cash = float(capital_level)
    holdings = {}
    trade_log = []
    pv_list = [float(capital_level)]

    pending_entries = []  # lista av tickers valda IGAR (eller senast), att kopa till OPPNING idag

    for date_i in range(start_idx, len(close.index)):
        date = close.index[date_i]
        hr_raw = hedge_ret_v[date_i]
        hr = float(hr_raw) if not np.isnan(hr_raw) else 0.0
        cash += cash * (RF_ANNUAL / 252)

        # ── EXEKVERA GARDAGENS URVAL PA DAGENS OPPNING ──
        if pending_entries:
            new_names = [t for t in pending_entries if t not in holdings]
            if new_names:
                target_dollar_per_name = cash / len(new_names)
                for t in new_names:
                    ti = tidx[t]
                    op = open_v[date_i, ti]
                    if np.isnan(op) or op <= 0:
                        continue
                    adv = dollar_volume.values[date_i, ti]
                    cap_dollar = adv * MAX_ADV_PCT if not np.isnan(adv) else target_dollar_per_name
                    sz = min(target_dollar_per_name, cap_dollar, cash)
                    if sz < capital_level * 0.0001 or sz <= 0:
                        continue
                    entry_spread = spread_v[date_i, ti]
                    effective_entry = op * (1 + entry_spread / 2) if not np.isnan(entry_spread) else op
                    shares = sz / effective_entry
                    cash -= sz
                    holdings[t] = {"shares": shares, "entry": effective_entry, "cost": sz,
                                   "last_price": op, "entry_date_i": date_i}
            pending_entries = []

        # ── EXITS: exakt HOLD_DAYS handelsdagar efter entry ──
        for t in list(holdings.keys()):
            h = holdings[t]
            if date_i - h["entry_date_i"] < HOLD_DAYS:
                continue
            ti = tidx[t]
            cp = prices_v[date_i, ti]
            if np.isnan(cp):
                cp = h["last_price"]
            proceeds = h["shares"] * cp
            exit_spread = spread_v[date_i, ti]
            if not np.isnan(exit_spread):
                proceeds -= proceeds * (exit_spread / 2)
            cash += proceeds
            ret = proceeds / h["cost"] - 1 if h["cost"] > 0 else 0.0
            trade_log.append({"date": date, "ticker": t, "ret": ret,
                               "gross_ret": cp / h["entry"] - 1, "type": "time_exit", "cost": h["cost"]})
            del holdings[t]

        # ── VALJ NYA NAMN (om idag ar en urvalsdag) - kops NASTA dags oppning ──
        if date in selection_dates:
            month_key = month_keys[day_month_idx[date_i]]
            eligible = [t for t in universe_by_month.get(month_key, []) if t in tidx]
            scores = []
            for t in eligible:
                sig = signal_v[date_i, tidx[t]]
                cp = prices_v[date_i, tidx[t]]
                if not np.isnan(sig) and not np.isnan(cp) and cp > 0:
                    scores.append((sig, t))
            scores.sort()  # LAGST (samst) avkastning forst - reversal-tesen
            n_top = max(1, int(len(scores) * DECILE_FRACTION)) if scores else 0
            pending_entries = [t for _, t in scores[:n_top]]

        # ── VARDERING + HEDGE ──
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

        daily_borrow = borrow_cost(position_value=abs(long_beta), holding_days=1, annual_rate=BORROW_ANNUAL_RATE)
        hedge_pnl = -long_beta * hr - long_beta * (RF_ANNUAL / 2 / 252) - daily_borrow

        pv_list.append(cash + long_val + hedge_pnl)

    pv = pd.Series(pv_list[1:], index=trade_dates)
    tl = pd.DataFrame(trade_log)
    return pv, tl


# ════════════════════════════════════════════════════════════
#  METRICS
# ════════════════════════════════════════════════════════════
def sharpe(s, rf=RF_ANNUAL):
    r = s.pct_change().dropna()
    return float(np.sqrt(252) * (r - rf / 252).mean() / r.std()) if r.std() > 0 else 0.0


def max_drawdown(s):
    return float(((s - s.cummax()) / s.cummax()).min())


def cagr(s):
    return float((s.iloc[-1] / s.iloc[0]) ** (252 / len(s)) - 1)


def calmar(s):
    md = abs(max_drawdown(s))
    return cagr(s) / md if md > 0 else 0.0


def run_for_capital_level(capital_level, open_, close, close_adj, hedge, beta_df, spread_df, volume, universe_by_month):
    pv, tl = run_backtest(open_, close, close_adj, hedge, beta_df, spread_df, volume, universe_by_month, capital_level)

    RESULTS_DIR.mkdir(exist_ok=True)
    pv.to_csv(RESULTS_DIR / f"portfolio_value_{int(capital_level)}.csv", header=["portfolio_value"])
    tl.to_csv(RESULTS_DIR / f"trade_log_{int(capital_level)}.csv", index=False)

    win_rate = float((tl["ret"] > 0).mean()) if len(tl) else float("nan")
    gains = tl.loc[tl["ret"] > 0, "ret"].sum() if len(tl) else 0.0
    losses = -tl.loc[tl["ret"] < 0, "ret"].sum() if len(tl) else 0.0
    pf = float(gains / losses) if losses > 0 else float("nan")

    return {
        "capital_level": capital_level,
        "sharpe": sharpe(pv),
        "cagr": cagr(pv),
        "max_drawdown": max_drawdown(pv),
        "calmar": calmar(pv),
        "n_trades": int(len(tl)),
        "win_rate": win_rate,
        "profit_factor": pf,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capital", type=float, default=None)
    parser.add_argument("--all-levels", action="store_true")
    args = parser.parse_args()
    levels = [100_000, 1_000_000, 10_000_000] if args.all_levels else [args.capital or 100_000]

    print("Laddar universum...")
    tickers, universe_by_month = load_universe()
    print(f"  {len(tickers)} unika tickers.\n")

    print("Laddar prismatriser (open/close/adjusted_close/high/low/volume)...")
    open_, close, close_adj, high, low, volume = load_price_matrices(tickers, FULL_START, FULL_END)
    hedge = load_hedge(FULL_START, FULL_END)
    print(f"  Prismatris: {close.shape}\n")

    print("Sanerar prisdata...")
    close, high, low = clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    open_ = open_.where(close.notna())
    implausible = flag_implausible_liquidity(close, volume, max_market_cap=MAX_MARKET_CAP,
                                              window=ADV_WINDOW, multiplier=1.0)
    close_adj = close_adj.mask(implausible)
    open_ = open_.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)

    # BUGGFIX (upptackt vid smoke-test 2026-08-06, ticker ABWND): en
    # KONSTANT, orimlig adjusted_close/close-kvot (~30 000x genom HELA
    # historiken, inte en enskild-dagshopp) - ett trasigt justeringstal
    # fran datakallan, INTE en riktig split. clean_price_matrix:s filter
    # fangar bara extrema ENSKILDA DAGARS avkastningar, inte en konstant
    # fel skalning som gor att varje enskild dags AVKASTNING ser normal
    # ut (kvoten ar ju konstant) - upptacktes har eftersom en reversal-
    # strategi som specifikt letar efter "storsta forlorare" ar sarskilt
    # exponerad for den har typen av fel (ett paverkat pris kan se ut
    # som en dramatisk "forlorare" och valjas rakt in). Generost, men
    # begransat: en riktig aktie splittas i praktiken aldrig >100x
    # kumulativt.
    ratio = (close_adj / close).replace([np.inf, -np.inf], np.nan)
    implausible_ratio = (ratio > 100) | (ratio < 0.01)
    if implausible_ratio.values.any():
        n_affected = int(implausible_ratio.any(axis=0).sum())
        print(f"  VARNING: {n_affected} tickers hade en orimlig adjusted_close/close-kvot "
              f"(>100x eller <0.01x) - maskade till NaN.")
    close_adj = close_adj.mask(implausible_ratio)
    open_ = open_.mask(implausible_ratio)

    print("Beräknar beta, Corwin-Schultz-spread...")
    beta_df = compute_beta(close_adj, hedge, BETA_WINDOW)
    spread_df = compute_spread_matrix(high, low)

    all_results = []
    for level in levels:
        print(f"\n--- Kapitalniva: ${level:,.0f} ---")
        r = run_for_capital_level(level, open_, close, close_adj, hedge, beta_df, spread_df, volume, universe_by_month)
        all_results.append(r)
        gate1 = "PASS" if r["sharpe"] >= 0.55 else "FAIL"
        print(f"  Sharpe={r['sharpe']:.4f} ({gate1}, kräver >=0.55)  CAGR={r['cagr']:+.2%}  "
              f"MaxDD={r['max_drawdown']:.2%}  Trades={r['n_trades']}  Winrate={r['win_rate']:.1%}  "
              f"PF={r['profit_factor']:.3f}")

    RESULTS_DIR.mkdir(exist_ok=True)
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, default=str)

    print("\nKLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
