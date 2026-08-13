"""
HYP-066: Aterkopsintensitet ($ aterkopt / marknadsvarde), toppdecilen,
ra signal. Genuint ny mekanismtyp - aldrig testad i registret tidigare
(skiljer sig fran insiderkop/HYP-035, som ar en HELT annan signal).

Se research/hypothesis_registry/HYP-066-aterkopsintensitet-decil.yaml
for det lasta kriteriet.

Aterananvander HYP-024:s redan validerade motor (SPY-beta-hedge, friktion,
kapacitetsspärr, snappade ombalanseringsdatum, adjusted_close genomgaende,
flag_implausible_liquidity) - ren signalersattning. TILL SKILLNAD FRAN
HYP-024: INGEN bank-/finansexklusion (medvetet, redovisat i det lasta
kriteriet - $ aterkopt/marknadsvarde ar en jamforbar kvot aven for
banker/REITs, till skillnad fran HYP-024:s rorelsemarginal-signal).

DATA: data/cache/buyback_by_ticker.jsonl (byggd av data/fetch_buyback_history.py,
verifierad feasibility 2026-08-11: 45.3% av 5162 tickers har rapporterat
minst ett aterkop, 117-434 kvalificerande namn/ar i stickprovet).

OOS-2025: koras i SAMMA sammanhangande backtest (2010-01-01 till
2025-12-31, sammanslaget grund-/2025-utokningsuniversum) - samma monster
som paper_trading/HYP-034/oos_backtest_2025.py, men konsoliderat i EN
fil istallet for tva eftersom denna hypotes fran borjan kraver OOS
enligt sitt eget lasta kriterium (inte ett separat diagnostiskt tillagg).
"""

import argparse
import bisect
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
UNIVERSE_2025_FILE = CACHE_DIR / "smallcap_universe_2025_extension.json"
BUYBACK_FILE = CACHE_DIR / "buyback_by_ticker.jsonl"
RESULTS_DIR = STRATEGY_DIR / "results"

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
from friction import borrow_cost, corwin_schultz_spread  # noqa: E402
from data_hygiene import clean_price_matrix, flag_implausible_liquidity  # noqa: E402
from rebalancing import snap_rebalance_dates  # noqa: E402

# ════════════════════════════════════════════════════════════
#  PARAMETRAR
# ════════════════════════════════════════════════════════════
FULL_START = "2010-01-01"
FULL_END = "2025-12-31"   # inkluderar OOS-2025, slicas senare
OOS_START = "2025-01-01"

MIN_HISTORY_DAYS = 130
DECILE_FRACTION = 0.10
REBAL_FREQ = "QE"
RF_ANNUAL = 0.02
BETA_WINDOW = 126

BORROW_ANNUAL_RATE = 0.03
MAX_ADV_PCT = 0.10
ADV_WINDOW = 20

MAX_MARKET_CAP = 2_000_000_000
HEDGE = "SPY"


# ════════════════════════════════════════════════════════════
#  DATA
# ════════════════════════════════════════════════════════════
def load_universe():
    with UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_orig = json.load(f)
    with UNIVERSE_2025_FILE.open(encoding="utf-8") as f:
        universe_2025 = json.load(f)
    universe_by_month = {**universe_orig, **universe_2025}
    all_tickers = sorted({t for tickers in universe_by_month.values() for t in tickers})
    return all_tickers, universe_by_month


def trading_calendar(start, end):
    path = OHLCV_DIR / f"{HEDGE}.csv"
    df = pd.read_csv(path, usecols=["date"], parse_dates=["date"])
    dates = df["date"].drop_duplicates().sort_values()
    return pd.DatetimeIndex(dates[(dates >= start) & (dates <= end)])


def load_price_matrices(tickers, start, end):
    date_index = trading_calendar(start, end)
    close_s, adj_s, high_s, low_s, vol_s = {}, {}, {}, {}, {}

    for t in tickers:
        path = OHLCV_DIR / f"{t}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path, usecols=["date", "close", "adjusted_close", "high", "low", "volume"],
                          parse_dates=["date"])
        df = df.drop_duplicates(subset="date", keep="last").set_index("date").sort_index()
        close_s[t] = df["close"].astype("float32")
        adj_s[t] = df["adjusted_close"].astype("float32")
        high_s[t] = df["high"].astype("float32")
        low_s[t] = df["low"].astype("float32")
        vol_s[t] = df["volume"].astype("float32")

    close = pd.DataFrame(close_s).reindex(date_index)
    close_adj = pd.DataFrame(adj_s).reindex(date_index)
    high = pd.DataFrame(high_s).reindex(date_index)
    low = pd.DataFrame(low_s).reindex(date_index)
    volume = pd.DataFrame(vol_s).reindex(date_index)
    return close, close_adj, high, low, volume


def load_hedge(start, end):
    path = OHLCV_DIR / f"{HEDGE}.csv"
    df = pd.read_csv(path, usecols=["date", "adjusted_close"], parse_dates=["date"])
    df = df.drop_duplicates(subset="date", keep="last").set_index("date").sort_index()
    date_index = trading_calendar(start, end)
    return df["adjusted_close"].reindex(date_index)


# ════════════════════════════════════════════════════════════
#  ATERKOPSSIGNAL (ny i HYP-066)
# ════════════════════════════════════════════════════════════
def load_buyback_data() -> dict:
    """Per ticker: {'buybacks': sorterad [(filed, val)], 'shares': sorterad
    [(filed, val)]} - bada as-of-uppslagna separat (aterkopsbelopp fran
    senaste FY-10-K, aktieantal fran senaste filade 10-K, INTE
    nodvandigtvis samma bokslut - marknadsvarde ska raknas med SENAST
    KANDA aktieantal, inte det historiska antalet vid just det aterkopet)."""
    out = {}
    if not BUYBACK_FILE.exists():
        return out
    with BUYBACK_FILE.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            bb = sorted([(e["filed"], e["val"]) for e in row.get("buybacks", []) if e.get("val") is not None])
            sh = sorted([(e["filed"], e["val"]) for e in row.get("shares_outstanding", [])
                         if e.get("val") not in (None, 0)])
            if bb and sh:
                out[row["ticker"]] = {"buybacks": bb, "shares": sh}
    return out


def _asof(sorted_pairs, as_of_date_str):
    """Senaste FILED varde strikt FORE as_of_date_str."""
    if not sorted_pairs:
        return None
    dates = [p[0] for p in sorted_pairs]
    idx = bisect.bisect_left(dates, as_of_date_str) - 1
    if idx < 0:
        return None
    return sorted_pairs[idx][1]


def buyback_intensity_asof(buyback_data: dict, ticker: str, as_of_date_str: str, current_price: float):
    rec = buyback_data.get(ticker)
    if not rec:
        return None
    bb_val = _asof(rec["buybacks"], as_of_date_str)
    shares_val = _asof(rec["shares"], as_of_date_str)
    if bb_val is None or shares_val is None or bb_val <= 0 or shares_val <= 0 or current_price <= 0:
        return None
    market_cap = current_price * shares_val
    return bb_val / market_cap


# ════════════════════════════════════════════════════════════
#  BETA (identisk med HYP-024)
# ════════════════════════════════════════════════════════════
def compute_beta(prices, hedge, beta_window):
    beta_window_i = int(beta_window)
    hedge_ret = hedge.pct_change()
    stock_ret = prices.pct_change()

    valid = stock_ret.notna() & hedge_ret.notna().values[:, None]
    x0 = stock_ret.where(valid, 0.0)
    y0 = pd.DataFrame(
        np.where(valid.values, np.broadcast_to(hedge_ret.values[:, None], valid.shape), 0.0),
        index=prices.index, columns=prices.columns,
    )

    n = valid.rolling(beta_window_i).sum().shift(1)
    sum_x = x0.rolling(beta_window_i).sum().shift(1)
    sum_y = y0.rolling(beta_window_i).sum().shift(1)
    sum_xy = (x0 * y0).rolling(beta_window_i).sum().shift(1)
    sum_y2 = (y0 * y0).rolling(beta_window_i).sum().shift(1)

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
#  BACKTEST-MOTOR (HYP-024:s struktur, INGEN bank-/finansexklusion)
# ════════════════════════════════════════════════════════════
def run_backtest(close, close_adj, hedge, buyback_data, beta_df, spread_df, volume,
                 universe_by_month, capital_level: float):
    tickers = list(close.columns)
    tidx = {t: i for i, t in enumerate(tickers)}
    hedge_ret = hedge.pct_change()
    dollar_volume = (close * volume).rolling(ADV_WINDOW).mean()

    calendar_dates = close.resample(REBAL_FREQ).last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[MIN_HISTORY_DAYS]) & (calendar_dates <= close.index[-1])]
    snapped = snap_rebalance_dates(calendar_dates, close.index)
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
        cash += cash * (RF_ANNUAL / 252)

        if date in rebal_set:
            month_key = rebal_map[date].strftime("%Y-%m-%d")
            as_of = date.strftime("%Y-%m-%d")
            eligible = [t for t in universe_by_month.get(month_key, []) if t in tidx]
            scores = []
            for t in eligible:
                ti = tidx[t]
                cp = prices_v[date_i, ti]
                raw_cp = close.values[date_i, ti] if not np.isnan(close.values[date_i, ti]) else cp
                if np.isnan(cp) or cp <= 0 or np.isnan(raw_cp) or raw_cp <= 0:
                    continue
                intensity = buyback_intensity_asof(buyback_data, t, as_of, float(raw_cp))
                if intensity is not None:
                    scores.append((intensity, t, cp))
            scores.sort(reverse=True)  # HOGST aterkopsintensitet forst
            n_top = max(1, int(len(scores) * DECILE_FRACTION)) if scores else 0
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
                    trade_log.append({"date": date, "ticker": t, "ret": ret,
                                       "gross_ret": cp / holdings[t]["entry"] - 1, "type": "rebalance_exit",
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
                    cap_dollar = adv * MAX_ADV_PCT if not np.isnan(adv) else target_dollar_per_name
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
def sharpe(s, rf=0.02):
    r = s.pct_change().dropna()
    return float(np.sqrt(252) * (r - rf / 252).mean() / r.std()) if r.std() > 0 else 0.0


def max_drawdown(s):
    return float(((s - s.cummax()) / s.cummax()).min())


def cagr(s):
    if len(s) < 2:
        return None
    return float((s.iloc[-1] / s.iloc[0]) ** (252 / len(s)) - 1)


def calmar(s):
    md = abs(max_drawdown(s))
    c = cagr(s)
    return c / md if (md > 0 and c is not None) else None


def trade_stats(tl):
    if len(tl) == 0:
        return dict(n=0, win_rate=0.0, avg_ret=0.0, pf=np.nan)
    wins = tl[tl["ret"] > 0]["ret"]
    losses = tl[tl["ret"] <= 0]["ret"]
    pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 and losses.sum() != 0 else np.nan
    return dict(n=len(tl), win_rate=len(wins) / len(tl), avg_ret=tl["ret"].mean(), pf=pf)


# ════════════════════════════════════════════════════════════
#  KÖRNING
# ════════════════════════════════════════════════════════════
def main():
    print("Laddar universum (grundsanning 2010-2024 + 2025-utokning)...")
    tickers, universe_by_month = load_universe()
    print(f"  {len(tickers)} unika tickers totalt.\n")

    print(f"Laddar prismatriser ({FULL_START} till {FULL_END})...")
    close, close_adj, high, low, volume = load_price_matrices(tickers, FULL_START, FULL_END)
    hedge = load_hedge(FULL_START, FULL_END)
    print(f"  Prismatris: {close.shape}\n")

    print("Sanerar prisdata...")
    close, high, low = clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())

    print("Flaggar leverantors-datafel...")
    implausible = flag_implausible_liquidity(close, volume, max_market_cap=MAX_MARKET_CAP,
                                              window=ADV_WINDOW, multiplier=1.0)
    close = close.mask(implausible)
    close_adj = close_adj.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)
    print(f"  {int(implausible.values.sum())} ticker-dagar maskade.\n")

    print("Estimerar beta...")
    beta_df = compute_beta(close_adj, hedge, BETA_WINDOW)

    print("Berknar Corwin-Schultz-spread...\n")
    spread_df = compute_spread_matrix(high, low)

    print("Laddar aterkopsdata (data/cache/buyback_by_ticker.jsonl)...")
    buyback_data = load_buyback_data()
    print(f"  {len(buyback_data)} av {len(tickers)} tickers har anvandbar aterkopsdata.\n")

    RESULTS_DIR.mkdir(exist_ok=True)
    main_results, oos_results = [], []

    for level in [100_000, 1_000_000, 10_000_000]:
        print(f"--- Kapitalnivå: ${level:,.0f} ---")
        pv, tl = run_backtest(close, close_adj, hedge, buyback_data, beta_df, spread_df, volume,
                              universe_by_month, level)

        main_pv = pv.loc[pv.index < OOS_START]
        oos_pv = pv.loc[pv.index >= OOS_START]
        main_tl = tl[tl["date"] < OOS_START] if len(tl) else tl

        m = {"capital_level": level, "cagr": cagr(main_pv), "sharpe": sharpe(main_pv),
             "calmar": calmar(main_pv), "max_drawdown": max_drawdown(main_pv),
             "trade_stats": trade_stats(main_tl)}
        main_results.append(m)

        o = {"capital_level": level, "oos_2025_sharpe": sharpe(oos_pv),
             "oos_2025_max_drawdown": max_drawdown(oos_pv),
             "oos_2025_total_return": float(oos_pv.iloc[-1] / oos_pv.iloc[0] - 1) if len(oos_pv) > 1 else None,
             "n_days": len(oos_pv)}
        oos_results.append(o)

        pv.to_csv(RESULTS_DIR / f"portfolio_value_full_{int(level)}.csv", header=["portfolio_value"])
        tl.to_csv(RESULTS_DIR / f"trade_log_{int(level)}.csv", index=False)

        print(f"    HUVUDPERIOD: CAGR={m['cagr']:+.2%}  Sharpe={m['sharpe']:.4f}  "
              f"Calmar={m['calmar']:.3f}  MaxDD={m['max_drawdown']:.2%}  Trades={m['trade_stats']['n']}")
        print(f"    OOS-2025:    Sharpe={o['oos_2025_sharpe']:.4f}  MaxDD={o['oos_2025_max_drawdown']:.2%}  "
              f"Avkastning={o['oos_2025_total_return']:+.2%}\n")

    lvl = 100_000
    m100k = main_results[0]
    cond1 = m100k["sharpe"] >= 0.55
    overall = "PASSED" if cond1 else "FAILED"

    print("=== SLUTBEDOMNING (avgorande $100k-niva) ===")
    print(f"  Villkor 1 (Sharpe >= 0,55): {m100k['sharpe']:.4f} -> {'PASS' if cond1 else 'FAIL'}")
    print(f"  => {overall}\n")

    summary = {"main": main_results, "oos_2025": oos_results,
               "pass_fail": {"condition_1_sharpe": bool(cond1), "overall": overall}}
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
