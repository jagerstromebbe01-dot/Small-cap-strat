"""
HYP-072: Dilution Pipeline / shelf-registration overhang. Se
research/hypothesis_registry/HYP-072-dilution-pipeline-shelf-overhang.yaml
for det lasta kriteriet.

TRE SEPARATA MANATLIGA PORTFOLJER (samma motor, tre lagen "mode"):
  full_ls          : deltest A - LONG "rena" namn / SHORT "aktiva shelf-
                      anvandare", 50/50 dollarneutralt, med borrow_cost+spread.
  avoid_long_only   : deltest B - LONG enbart "rena" namn (samma LONG-ben
                      som ovan), ingen kort sida.
  baseline_long_only: deltest B:s jamforelsepunkt - LONG HELA eligible-
                      universumet, ingen signal.

Delar data/cache/sec_filing_index.jsonl med HYP-073.
"""

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
RESULTS_DIR = STRATEGY_DIR / "results"

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
from friction import borrow_cost, corwin_schultz_spread  # noqa: E402
from data_hygiene import (  # noqa: E402
    clean_price_matrix,
    flag_implausible_liquidity,
    mask_unrecovered_price_breaks,
    mask_implausible_adjusted_close_ratio,
)
from rebalancing import snap_rebalance_dates  # noqa: E402
from sec_filing_index import load_filing_index, S3_FAMILY_FORMS  # noqa: E402

# ════════════════════════════════════════════════════════════
#  PARAMETRAR (lasta i HYP-072:s pass_fail_criterion)
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
#  SHELF-SIGNAL (ny i HYP-072)
# ════════════════════════════════════════════════════════════
def shelf_counts_asof(filings, as_of_ts):
    """(count_12m, count_6m, count_24m) S-3-familjefilingar STRIKT FORE as_of_ts."""
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
    """Returnerar "active", "clean", eller None (varken/eller)."""
    filings = filing_index.get(ticker, [])
    c12, c6, c24 = shelf_counts_asof(filings, as_of_ts)
    if c12 >= ACTIVE_12M_MIN_COUNT and c6 >= ACTIVE_6M_MIN_COUNT:
        return "active"
    if c24 == 0:
        return "clean"
    return None


# ════════════════════════════════════════════════════════════
#  MOTOR (delad for alla tre lagen)
# ════════════════════════════════════════════════════════════
def run_backtest(close, close_adj, spread_df, volume, filing_index, universe_by_month,
                 capital_level: float, mode: str):
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
    holdings = {}  # ticker -> {side, shares, entry_price, cost}
    pv_list = [float(capital_level)]
    trade_log = []
    monthly_disclosure = []

    for date_i in range(start_idx, len(close.index)):
        date = close.index[date_i]
        cash += cash * (RF_ANNUAL / 252)

        if date in rebal_set:
            month_key = rebal_map[date].strftime("%Y-%m-%d")
            as_of = date
            eligible = [t for t in universe_by_month.get(month_key, []) if t in tidx]

            active_names, clean_names, excluded = [], [], 0
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
                else:
                    excluded += 1

            if mode == "full_ls":
                target_long, target_short = set(clean_names), set(active_names)
            elif mode == "avoid_long_only":
                target_long, target_short = set(clean_names), set()
            elif mode == "baseline_long_only":
                target_long = {t for t in eligible if t in tidx and not np.isnan(prices_v[date_i, tidx[t]])
                               and prices_v[date_i, tidx[t]] > 0}
                target_short = set()
            else:
                raise ValueError(mode)

            n_elig = len(eligible)
            monthly_disclosure.append({"date": str(date.date()), "n_eligible": n_elig,
                                        "n_active": len(active_names), "n_clean": len(clean_names),
                                        "n_excluded": excluded})

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

            # VIKTIGT (bugg upptackt 2026-08-12, HYP-073-korningen): `cash`
            # ar INTE tillgangligt kapital for det korta benet -
            # blankningslikvider banka in i cash men motsvarande skuld
            # tracks separat (short_liability i vardering nedan), sa
            # cash-baserad storlekssattning later obegransat over manader
            # da en position hålls kvar. Storleksatt istallet mot
            # AVSTAENDE kapacitet av capital_level (redan hallna
            # positioners varde subtraheras forst).
            current_long_value = sum(
                h["shares"] * h.get("last_price", h["entry_price"])
                for h in holdings.values() if h["side"] == "long"
            )
            current_short_liability = sum(
                h["shares"] * h.get("last_price", h["entry_price"])
                for h in holdings.values() if h["side"] == "short"
            )
            total_alloc_long = capital_level * (0.5 if target_short else 1.0) if mode == "full_ls" else capital_level
            total_alloc_short = capital_level * 0.5 if (mode == "full_ls" and target_short) else 0.0
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
                                   "last_price": cp}

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

        long_val, short_liability, daily_borrow = 0.0, 0.0, 0.0
        for t, h in holdings.items():
            ti = tidx[t]
            cp = float(prices_v[date_i, ti])
            if np.isnan(cp):
                cp = h["last_price"]
            else:
                h["last_price"] = cp
            if h["side"] == "long":
                long_val += h["shares"] * cp
            else:
                liab = h["shares"] * cp
                short_liability += liab
                daily_borrow += borrow_cost(position_value=liab, holding_days=1, annual_rate=BORROW_ANNUAL_RATE)

        cash -= daily_borrow
        pv_list.append(cash + long_val - short_liability)

    pv = pd.Series(pv_list[1:], index=trade_dates)
    tl = pd.DataFrame(trade_log)
    return pv, tl, monthly_disclosure


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
    all_results = {}

    for mode in ["full_ls", "avoid_long_only", "baseline_long_only"]:
        print(f"==== LAGE: {mode} ====")
        mode_main, mode_oos = [], []
        for level in [100_000, 1_000_000, 10_000_000]:
            print(f"--- Kapitalnivå: ${level:,.0f} ---")
            pv, tl, disclosure = run_backtest(close, close_adj, spread_df, volume, filing_index,
                                              universe_by_month, level, mode)
            main_pv = pv.loc[pv.index < OOS_START]
            oos_pv = pv.loc[pv.index >= OOS_START]
            m = {"capital_level": level, "cagr": cagr(main_pv), "sharpe": sharpe(main_pv),
                 "max_drawdown": max_drawdown(main_pv)}
            mode_main.append(m)
            o = {"capital_level": level, "oos_2025_sharpe": sharpe(oos_pv) if len(oos_pv) > 2 else None,
                 "oos_2025_max_drawdown": max_drawdown(oos_pv) if len(oos_pv) > 2 else None}
            mode_oos.append(o)
            pv.to_csv(RESULTS_DIR / f"portfolio_value_{mode}_{int(level)}.csv", header=["portfolio_value"])
            tl.to_csv(RESULTS_DIR / f"trade_log_{mode}_{int(level)}.csv", index=False)
            if mode == "full_ls" and level == 100_000:
                with (RESULTS_DIR / "monthly_disclosure.json").open("w", encoding="utf-8") as f:
                    json.dump(disclosure, f, indent=2)
            print(f"    CAGR={m['cagr']:+.2%}  Sharpe={m['sharpe']:.4f}  MaxDD={m['max_drawdown']:.2%}")
            print(f"    OOS-2025: Sharpe={o['oos_2025_sharpe']}  MaxDD={o['oos_2025_max_drawdown']}\n")
        all_results[mode] = {"main": mode_main, "oos_2025": mode_oos}

    m100k_a = all_results["full_ls"]["main"][0]
    m100k_avoid = all_results["avoid_long_only"]["main"][0]
    m100k_base = all_results["baseline_long_only"]["main"][0]

    cond1 = m100k_a["sharpe"] >= 0.55
    cond2 = m100k_a["max_drawdown"] >= -0.50
    cond3 = m100k_avoid["sharpe"] >= m100k_base["sharpe"]
    overall = "PASSED" if (cond1 and cond2 and cond3) else "FAILED"

    print("=== SLUTBEDOMNING (avgorande $100k-niva) ===")
    print(f"  Villkor 1 (Deltest A Sharpe >= 0,55): {m100k_a['sharpe']:.4f} -> {'PASS' if cond1 else 'FAIL'}")
    print(f"  Villkor 2 (Deltest A MaxDD >= -50%): {m100k_a['max_drawdown']:.2%} -> {'PASS' if cond2 else 'FAIL'}")
    print(f"  Villkor 3 (Deltest B avoid >= baseline): {m100k_avoid['sharpe']:.4f} >= {m100k_base['sharpe']:.4f} "
          f"-> {'PASS' if cond3 else 'FAIL'}")
    print(f"  => {overall}\n")

    summary = {"modes": all_results, "pass_fail": {"cond1_sharpe": bool(cond1), "cond2_maxdd": bool(cond2),
                                                    "cond3_avoid_vs_baseline": bool(cond3)},
               "overall": overall}
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
