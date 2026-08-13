"""
HYP-076: Vinsthemtagning pa HYP-072:s langben - engangsdelforsaljning vid
dubblering. Se
research/hypothesis_registry/HYP-076-vinsthemtagning-hyp072.yaml for det
lasta kriteriet.

Identisk signal/klassificering och manatlig ombalansering som HYP-072:s
deltest A (full_ls). Kortbenet HELT OFORANDRAT. NY REGEL (endast
LONG-benet): forsta gangen en positions varde nar >= 2,0x dess varde
vid entry/senaste ombalansering, salj EXAKT 50% av kvarvarande aktier
nasta handelsdag - en engangshandelse per hallperiod, ingen upprepning.
"""

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
RESULTS_DIR = STRATEGY_DIR / "results"

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
sys.path.insert(0, str(STRATEGIES_ROOT.parent / "scripts"))
from friction import borrow_cost, corwin_schultz_spread  # noqa: E402
from data_hygiene import (  # noqa: E402
    clean_price_matrix,
    flag_implausible_liquidity,
    mask_unrecovered_price_breaks,
    mask_implausible_adjusted_close_ratio,
)
from rebalancing import snap_rebalance_dates  # noqa: E402
from sec_filing_index import load_filing_index, S3_FAMILY_FORMS  # noqa: E402
from deflated_sharpe_ratio import kurtosis as sample_kurtosis  # noqa: E402

# ════════════════════════════════════════════════════════════
#  PARAMETRAR
# ════════════════════════════════════════════════════════════
FULL_START = "2010-01-01"
FULL_END = "2025-12-31"
OOS_START = "2025-01-01"

MIN_HISTORY_DAYS = 130
REBAL_FREQ = "ME"
RF_ANNUAL = 0.02
BORROW_ANNUAL_RATE = 0.03
MAX_ADV_PCT = 0.10
ADV_WINDOW = 20
MAX_MARKET_CAP = 2_000_000_000

ACTIVE_12M_MIN_COUNT = 2
ACTIVE_6M_MIN_COUNT = 1
CLEAN_LOOKBACK_DAYS = 730
ACTIVE_12M_DAYS = 365
ACTIVE_6M_DAYS = 182

PROFIT_TAKE_MULTIPLE = 2.0
PROFIT_TAKE_FRACTION = 0.5

HYP072_SHARPE_EX2020_100K = 0.4894
HYP072_KURTOSIS_100K = 366.2


# ════════════════════════════════════════════════════════════
#  DATA (identisk med HYP-072)
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
    path = OHLCV_DIR / "SPY.csv"
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


def compute_spread_matrix(high, low):
    spread = {}
    for t in high.columns:
        spread[t] = corwin_schultz_spread(high[t].values, low[t].values)
    return pd.DataFrame(spread, index=high.index)


# ════════════════════════════════════════════════════════════
#  SHELF-SIGNAL (identisk med HYP-072)
# ════════════════════════════════════════════════════════════
def shelf_counts_asof(filings, as_of_ts):
    c12 = c6 = c24 = 0
    for f in filings:
        if f["form"] not in S3_FAMILY_FORMS:
            continue
        fdate = f.get("filingDate")
        if not fdate:
            continue
        fts = pd.Timestamp(fdate)
        if fts >= as_of_ts:
            continue
        delta = (as_of_ts - fts).days
        if delta <= ACTIVE_12M_DAYS:
            c12 += 1
        if delta <= ACTIVE_6M_DAYS:
            c6 += 1
        if delta <= CLEAN_LOOKBACK_DAYS:
            c24 += 1
    return c12, c6, c24


def classify_ticker(filing_index, ticker, as_of_ts):
    filings = filing_index.get(ticker, [])
    c12, c6, c24 = shelf_counts_asof(filings, as_of_ts)
    if c12 >= ACTIVE_12M_MIN_COUNT and c6 >= ACTIVE_6M_MIN_COUNT:
        return "active"
    if c24 == 0:
        return "clean"
    return None


# ════════════════════════════════════════════════════════════
#  MOTOR (HYP-072:s full_ls-lage + engangs-vinsthemtagning pa langbenet)
# ════════════════════════════════════════════════════════════
def run_backtest(close, close_adj, spread_df, volume, filing_index, universe_by_month, capital_level: float):
    tickers = list(close.columns)
    tidx = {t: i for i, t in enumerate(tickers)}
    dollar_volume = (close * volume).rolling(ADV_WINDOW).mean()

    calendar_dates = close.resample(REBAL_FREQ).last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[MIN_HISTORY_DAYS]) & (calendar_dates <= close.index[-1])]
    snapped = snap_rebalance_dates(calendar_dates, close.index)
    rebal_map = dict(zip(snapped["execution_date"], snapped["calendar_label"]))
    rebal_set = set(snapped["execution_date"])

    start_idx = close.index.get_indexer([snapped["execution_date"].iloc[0]])[0]
    trade_dates = close.index[start_idx:]

    prices_v = close_adj.values
    spread_v = spread_df.reindex(columns=tickers).values

    cash = float(capital_level)
    holdings = {}
    pending_profit_take = set()
    pv_list = [float(capital_level)]
    trade_log = []
    profit_take_log = []

    for date_i in range(start_idx, len(close.index)):
        date = close.index[date_i]
        cash += cash * (RF_ANNUAL / 252)

        # STEG 1: exekvera vinsthemtagningar upptackta igar (en dags fordrojning).
        for t in list(pending_profit_take):
            pending_profit_take.discard(t)
            if t not in holdings:
                continue
            h = holdings[t]
            if h["side"] != "long" or h.get("profit_taken", False):
                continue
            ti = tidx[t]
            cp = prices_v[date_i, ti]
            if np.isnan(cp) or cp <= 0:
                continue
            sell_shares = h["shares"] * PROFIT_TAKE_FRACTION
            tr_spread = spread_v[date_i, ti]
            tr_spread = 0.0 if np.isnan(tr_spread) else tr_spread
            proceeds = sell_shares * cp * (1 - tr_spread / 2)
            cash += proceeds
            h["shares"] -= sell_shares
            h["profit_taken"] = True
            profit_take_log.append({"date": date, "ticker": t, "price": cp, "entry_price": h["entry_price"]})

        # STEG 2: manatlig ombalansering (identisk med HYP-072:s full_ls).
        if date in rebal_set:
            month_key = rebal_map[date].strftime("%Y-%m-%d")
            as_of = date
            eligible = [t for t in universe_by_month.get(month_key, []) if t in tidx]

            active_names, clean_names = [], []
            for t in eligible:
                ti = tidx[t]
                cp = prices_v[date_i, ti]
                if np.isnan(cp) or cp <= 0:
                    continue
                cls = classify_ticker(filing_index, t, as_of)
                if cls == "active":
                    active_names.append(t)
                elif cls == "clean":
                    clean_names.append(t)

            target_long, target_short = set(clean_names), set(active_names)
            target_all = target_long | target_short

            for t in list(holdings.keys()):
                if t not in target_all:
                    h = holdings[t]
                    ti = tidx[t]
                    cp = prices_v[date_i, ti]
                    if np.isnan(cp):
                        cp = h["last_price"]
                    ex_spread = spread_v[date_i, ti]
                    ex_spread = 0.0 if np.isnan(ex_spread) else ex_spread
                    if h["side"] == "long":
                        proceeds = h["shares"] * cp * (1 - ex_spread / 2)
                        cash += proceeds
                        ret = proceeds / h["cost"] - 1
                    else:
                        buyback = h["shares"] * cp * (1 + ex_spread / 2)
                        cash -= buyback
                        ret = (h["entry_price"] - cp * (1 + ex_spread / 2)) / h["entry_price"]
                    trade_log.append({"date": date, "ticker": t, "side": h["side"], "ret": ret})
                    del holdings[t]
                    pending_profit_take.discard(t)

            current_long_value = sum(h["shares"] * h.get("last_price", h["entry_price"])
                                      for h in holdings.values() if h["side"] == "long")
            current_short_liability = sum(h["shares"] * h.get("last_price", h["entry_price"])
                                           for h in holdings.values() if h["side"] == "short")
            total_alloc_long = capital_level * (0.5 if target_short else 1.0)
            total_alloc_short = capital_level * 0.5 if target_short else 0.0
            long_pool = max(0.0, total_alloc_long - current_long_value)
            short_pool = max(0.0, total_alloc_short - current_short_liability)

            new_long = [t for t in target_long if t not in holdings]
            if new_long:
                dollar_per_name = long_pool / len(new_long)
                for t in new_long:
                    ti = tidx[t]
                    cp = prices_v[date_i, ti]
                    if np.isnan(cp) or cp <= 0:
                        continue
                    adv = dollar_volume.values[date_i, ti]
                    cap_dollar = adv * MAX_ADV_PCT if not np.isnan(adv) else dollar_per_name
                    sz = min(dollar_per_name, cap_dollar, cash)
                    if sz <= 0:
                        continue
                    en_spread = spread_v[date_i, ti]
                    en_spread = 0.0 if np.isnan(en_spread) else en_spread
                    eff = cp * (1 + en_spread / 2)
                    shares = sz / eff
                    cash -= sz
                    holdings[t] = {"side": "long", "shares": shares, "entry_price": eff, "cost": sz,
                                   "last_price": cp, "profit_taken": False}

            new_short = [t for t in target_short if t not in holdings]
            if new_short:
                dollar_per_name = short_pool / len(new_short)
                for t in new_short:
                    ti = tidx[t]
                    cp = prices_v[date_i, ti]
                    if np.isnan(cp) or cp <= 0:
                        continue
                    adv = dollar_volume.values[date_i, ti]
                    cap_dollar = adv * MAX_ADV_PCT if not np.isnan(adv) else dollar_per_name
                    sz = min(dollar_per_name, cap_dollar)
                    if sz <= 0:
                        continue
                    en_spread = spread_v[date_i, ti]
                    en_spread = 0.0 if np.isnan(en_spread) else en_spread
                    eff = cp * (1 - en_spread / 2)
                    shares = sz / eff
                    cash += shares * eff
                    holdings[t] = {"side": "short", "shares": shares, "entry_price": eff, "cost": sz,
                                   "last_price": cp}

        # STEG 3: daglig vardering + upptackt av NY vinsthemtagningshandelse (for imorgon).
        long_val, short_liability, daily_borrow = 0.0, 0.0, 0.0
        for t, h in holdings.items():
            ti = tidx[t]
            cp = float(prices_v[date_i, ti])
            if np.isnan(cp):
                cp = h["last_price"]
            else:
                h["last_price"] = cp
            current_value = h["shares"] * cp
            if h["side"] == "long":
                if not h.get("profit_taken", False) and current_value >= PROFIT_TAKE_MULTIPLE * h["cost"]:
                    pending_profit_take.add(t)
                long_val += current_value
            else:
                short_liability += current_value
                daily_borrow += borrow_cost(position_value=current_value, holding_days=1,
                                             annual_rate=BORROW_ANNUAL_RATE)

        cash -= daily_borrow
        pv_list.append(cash + long_val - short_liability)

    pv = pd.Series(pv_list[1:], index=trade_dates)
    tl = pd.DataFrame(trade_log)
    ptl = pd.DataFrame(profit_take_log)
    return pv, tl, ptl


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


# ════════════════════════════════════════════════════════════
#  KÖRNING
# ════════════════════════════════════════════════════════════
def main():
    print("Laddar universum...")
    tickers, universe_by_month = load_universe()
    print(f"  {len(tickers)} unika tickers.\n")

    print(f"Laddar prismatriser ({FULL_START} till {FULL_END})...")
    close, close_adj, high, low, volume = load_price_matrices(tickers, FULL_START, FULL_END)
    print(f"  Prismatris: {close.shape}\n")

    print("Sanerar prisdata...")
    close, high, low = clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    close_adj = mask_implausible_adjusted_close_ratio(close, close_adj)
    implausible = flag_implausible_liquidity(close, volume, max_market_cap=MAX_MARKET_CAP,
                                              window=ADV_WINDOW, multiplier=1.0)
    close = close.mask(implausible)
    close_adj = close_adj.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)
    close = mask_unrecovered_price_breaks(close)
    close_adj = close_adj.where(close.notna())
    high = high.where(close.notna())
    low = low.where(close.notna())

    print("Berknar Corwin-Schultz-spread...")
    spread_df = compute_spread_matrix(high, low)

    print("Laddar SEC filings-index...")
    filing_index = load_filing_index()
    print(f"  {len(filing_index)} av {len(tickers)} tickers har relevanta filingar.\n")

    RESULTS_DIR.mkdir(exist_ok=True)
    main_results, oos_results = [], []
    kurt_100k, sharpe_ex2020_100k = None, None

    for level in [100_000, 1_000_000, 10_000_000]:
        print(f"--- Kapitalnivå: ${level:,.0f} ---")
        pv, tl, ptl = run_backtest(close, close_adj, spread_df, volume, filing_index, universe_by_month, level)
        main_pv = pv.loc[pv.index < OOS_START]
        oos_pv = pv.loc[pv.index >= OOS_START]
        r_main = main_pv.pct_change().dropna()

        m = {"capital_level": level, "cagr": cagr(main_pv), "sharpe": sharpe(main_pv),
             "max_drawdown": max_drawdown(main_pv), "n_profit_takes": len(ptl)}
        main_results.append(m)
        o = {"capital_level": level, "oos_2025_sharpe": sharpe(oos_pv) if len(oos_pv) > 2 else None,
             "oos_2025_max_drawdown": max_drawdown(oos_pv) if len(oos_pv) > 2 else None}
        oos_results.append(o)

        r_ex2020 = r_main[r_main.index.year != 2020]
        sharpe_ex2020 = float(np.sqrt(252) * (r_ex2020 - 0.02 / 252).mean() / r_ex2020.std()) if r_ex2020.std() > 0 else 0.0
        kurt = float(sample_kurtosis(r_main.values))
        m["sharpe_ex2020"] = sharpe_ex2020
        m["kurtosis"] = kurt
        if level == 100_000:
            kurt_100k, sharpe_ex2020_100k = kurt, sharpe_ex2020

        pv.to_csv(RESULTS_DIR / f"portfolio_value_{int(level)}.csv", header=["portfolio_value"])
        tl.to_csv(RESULTS_DIR / f"trade_log_{int(level)}.csv", index=False)
        ptl.to_csv(RESULTS_DIR / f"profit_take_log_{int(level)}.csv", index=False)

        print(f"    CAGR={m['cagr']:+.2%}  Sharpe={m['sharpe']:.4f}  MaxDD={m['max_drawdown']:.2%}  "
              f"n_profit_takes={len(ptl)}")
        print(f"    Sharpe(ex-2020)={sharpe_ex2020:.4f}  Kurtosis={kurt:.1f}")
        print(f"    OOS-2025: Sharpe={o['oos_2025_sharpe']}  MaxDD={o['oos_2025_max_drawdown']}\n")

    m100k = main_results[0]
    cond1 = m100k["sharpe"] >= 0.55
    cond2 = m100k["max_drawdown"] >= -0.50
    cond3 = sharpe_ex2020_100k >= HYP072_SHARPE_EX2020_100K
    cond4 = kurt_100k < HYP072_KURTOSIS_100K
    overall = "PASSED" if (cond1 and cond2 and cond3 and cond4) else "FAILED"

    print("=== SLUTBEDOMNING (avgorande $100k-niva) ===")
    print(f"  Villkor 1 (Sharpe >= 0,55): {m100k['sharpe']:.4f} -> {'PASS' if cond1 else 'FAIL'}")
    print(f"  Villkor 2 (MaxDD >= -50%): {m100k['max_drawdown']:.2%} -> {'PASS' if cond2 else 'FAIL'}")
    print(f"  Villkor 3 (Sharpe ex-2020 >= {HYP072_SHARPE_EX2020_100K}): {sharpe_ex2020_100k:.4f} -> {'PASS' if cond3 else 'FAIL'}")
    print(f"  Villkor 4 (Kurtosis < {HYP072_KURTOSIS_100K}): {kurt_100k:.1f} -> {'PASS' if cond4 else 'FAIL'}")
    print(f"  => {overall}\n")

    summary = {"main": main_results, "oos_2025": oos_results,
               "pass_fail": {"cond1_sharpe": bool(cond1), "cond2_maxdd": bool(cond2),
                             "cond3_sharpe_ex2020": bool(cond3), "cond4_kurtosis": bool(cond4)},
               "overall": overall}
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
