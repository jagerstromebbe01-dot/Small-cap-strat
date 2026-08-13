"""
HYP-073: Filing Stress Cascade - organisatorisk rapporteringsfriktion som
andraordnings-eventsignal. Se
research/hypothesis_registry/HYP-073-filing-stress-cascade.yaml for det
lasta kriteriet.

Fyra strukturerade stress-handelsetyper (SEC submissions-API, INGEN NLP):
  1. NT 10-K/NT 10-Q (sen inlamning)
  2. 10-K/A eller 10-Q/A (omarbetning)
  3. 8-K med item 4.01 (revisorsbyte)
  4. 8-K med item 4.02 (non-reliance/omrakning)
Score = antal DISTINKTA typer inom rullande 12 manader (0-4). Trigger nar
score korsar fran <2 till >=2. SHORT-only, likaviktat over samma
kalendervecka, entry nasta handelsdag efter veckans sista trigger, 60
handelsdagars fast hallperiod.

Delar data/cache/sec_filing_index.jsonl med HYP-072 (samma nya
datamodul, data/fetch_sec_filing_index.py).
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
from friction import borrow_cost, corwin_schultz_spread  # noqa: E402
from data_hygiene import (  # noqa: E402
    clean_price_matrix,
    flag_implausible_liquidity,
    mask_unrecovered_price_breaks,
)
from sec_filing_index import load_filing_index, has_item, NT_FORMS, AMENDMENT_FORMS  # noqa: E402

# ════════════════════════════════════════════════════════════
#  PARAMETRAR (lasta i HYP-073:s pass_fail_criterion)
# ════════════════════════════════════════════════════════════
FULL_START = "2010-01-01"
FULL_END = "2025-12-31"
OOS_START = "2025-01-01"

SCORE_WINDOW = "365D"
TRIGGER_THRESHOLD = 2
HOLD_DAYS = 60

RF_ANNUAL = 0.02
BORROW_ANNUAL_RATE = 0.03
MAX_ADV_PCT = 0.10
ADV_WINDOW = 20
MAX_MARKET_CAP = 2_000_000_000


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
    close_s, high_s, low_s, vol_s = {}, {}, {}, {}
    for t in tickers:
        path = OHLCV_DIR / f"{t}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path, usecols=["date", "close", "high", "low", "volume"], parse_dates=["date"])
        df = df.drop_duplicates(subset="date", keep="last").set_index("date").sort_index()
        close_s[t] = df["close"].astype("float32")
        high_s[t] = df["high"].astype("float32")
        low_s[t] = df["low"].astype("float32")
        vol_s[t] = df["volume"].astype("float32")
    close = pd.DataFrame(close_s).reindex(date_index)
    high = pd.DataFrame(high_s).reindex(date_index)
    low = pd.DataFrame(low_s).reindex(date_index)
    volume = pd.DataFrame(vol_s).reindex(date_index)
    return close, high, low, volume


def compute_spread_matrix(high, low):
    spread = {}
    for t in high.columns:
        spread[t] = corwin_schultz_spread(high[t].values, low[t].values)
    return pd.DataFrame(spread, index=high.index)


def eligible_at(date_str, universe_by_month, month_keys_sorted):
    import bisect
    idx = bisect.bisect_right(month_keys_sorted, date_str) - 1
    if idx < 0:
        return set()
    return set(universe_by_month.get(month_keys_sorted[idx], []))


# ════════════════════════════════════════════════════════════
#  STRESS-SCORE (ny signal, HYP-073)
# ════════════════════════════════════════════════════════════
def build_event_matrix(filing_index: dict, tickers: list, date_index: pd.DatetimeIndex,
                       predicate) -> pd.DataFrame:
    """Bool-matris (dagar x tickers), True den handelsdag (narmast EFTER
    filingdatumet) som en filing matchande `predicate` intraffar."""
    n = len(date_index)
    data = {}
    for t in tickers:
        filings = filing_index.get(t)
        if not filings:
            continue
        arr = np.zeros(n, dtype=bool)
        hit = False
        for f in filings:
            if not predicate(f):
                continue
            fdate = f.get("filingDate")
            if not fdate:
                continue
            ts = pd.Timestamp(fdate)
            pos = date_index.searchsorted(ts, side="left")
            if pos < n:
                arr[pos] = True
                hit = True
        if hit:
            data[t] = arr
    return pd.DataFrame(data, index=date_index)


def compute_score_and_triggers(filing_index: dict, tickers: list, date_index: pd.DatetimeIndex):
    nt_today = build_event_matrix(filing_index, tickers, date_index, lambda f: f["form"] in NT_FORMS)
    amend_today = build_event_matrix(filing_index, tickers, date_index, lambda f: f["form"] in AMENDMENT_FORMS)
    item401_today = build_event_matrix(filing_index, tickers, date_index,
                                        lambda f: f["form"] == "8-K" and has_item(f, "4.01"))
    item402_today = build_event_matrix(filing_index, tickers, date_index,
                                        lambda f: f["form"] == "8-K" and has_item(f, "4.02"))

    all_tickers = sorted(set(nt_today.columns) | set(amend_today.columns) |
                          set(item401_today.columns) | set(item402_today.columns))
    if not all_tickers:
        return pd.DataFrame(), []

    def in_window(df):
        df = df.reindex(columns=all_tickers, fill_value=False)
        return df.rolling(SCORE_WINDOW, min_periods=1).max().astype(bool)

    w_nt = in_window(nt_today)
    w_amend = in_window(amend_today)
    w_401 = in_window(item401_today)
    w_402 = in_window(item402_today)

    score = w_nt.astype(int) + w_amend.astype(int) + w_401.astype(int) + w_402.astype(int)
    prev_score = score.shift(1).fillna(0)
    trigger = (score >= TRIGGER_THRESHOLD) & (prev_score < TRIGGER_THRESHOLD)

    events = []
    for t in all_tickers:
        col = trigger[t]
        trig_dates = date_index[col.values]
        for d in trig_dates:
            events.append((t, d, int(score.loc[d, t])))
    return score, events


def group_by_week_and_size_entries(events, date_index):
    """Grupperar handelser per (ar, ISO-vecka) av trigger-datum. Entry for
    HELA veckans kohort = nasta handelsdag efter veckans SENASTE
    trigger-datum (look-ahead-sakert)."""
    by_week = {}
    for t, trig_date, score_val in events:
        iso = trig_date.isocalendar()
        key = (iso[0], iso[1])
        by_week.setdefault(key, []).append((t, trig_date, score_val))

    entries_by_date = {}
    score_at_trigger = {}
    for key, members in by_week.items():
        last_trig = max(m[1] for m in members)
        pos = date_index.searchsorted(last_trig, side="right")
        if pos >= len(date_index):
            continue
        entry_date = date_index[pos]
        for t, trig_date, score_val in members:
            entries_by_date.setdefault(entry_date, []).append(t)
            score_at_trigger[(t, entry_date)] = score_val
    return entries_by_date, score_at_trigger


# ════════════════════════════════════════════════════════════
#  SHORT-ONLY EVENTPORTFOLJ
# ════════════════════════════════════════════════════════════
def run_short_portfolio(close, spread_df, volume, universe_by_month, month_keys_sorted,
                        entries_by_date, capital_level):
    tickers = list(close.columns)
    tidx = {t: i for i, t in enumerate(tickers)}
    dollar_volume = (close * volume).rolling(ADV_WINDOW).mean()
    date_index = close.index
    prices_v = close.values
    spread_v = spread_df.reindex(columns=tickers).values

    filtered_entries = {}
    n_events_used = 0
    for d, names in entries_by_date.items():
        pos = date_index.get_indexer([d])[0]
        if pos < 0:
            continue
        valid_names = []
        for t in names:
            if t not in tidx:
                continue
            cp = prices_v[pos, tidx[t]]
            if np.isnan(cp) or cp <= 0:
                continue
            elig = eligible_at(d.strftime("%Y-%m-%d"), universe_by_month, month_keys_sorted)
            if t not in elig:
                continue
            valid_names.append(t)
        if valid_names:
            filtered_entries[d] = valid_names
            n_events_used += len(valid_names)

    if n_events_used == 0:
        return None, 0

    start_date = min(filtered_entries.keys())
    start_idx = date_index.get_indexer([start_date])[0]
    trade_dates = date_index[start_idx:]

    cash = float(capital_level)
    holdings = {}
    pv_list = []
    trade_log = []

    for date_i in range(start_idx, len(date_index)):
        date = date_index[date_i]
        cash += cash * (RF_ANNUAL / 252)

        for t in list(holdings.keys()):
            h = holdings[t]
            if h["exit_pos"] != date_i:
                continue
            ti = tidx[t]
            cp = prices_v[date_i, ti]
            if np.isnan(cp):
                cp = h["last_price"]
            exit_spread = spread_v[date_i, ti]
            exit_spread = 0.0 if np.isnan(exit_spread) else exit_spread
            buyback_cost = h["shares"] * cp * (1 + exit_spread / 2)
            cash -= buyback_cost
            ret = (h["entry_price"] - cp * (1 + exit_spread / 2)) / h["entry_price"]
            trade_log.append({"date": date, "ticker": t, "ret": ret})
            del holdings[t]

        new_names = [t for t in filtered_entries.get(date, []) if t not in holdings]
        if new_names:
            # VIKTIGT (bugg upptackt 2026-08-12): `cash` ar INTE
            # tillgangligt kapital for ett kort ben - blankningslikvider
            # banka in i cash men motsvarande skuld tracks separat, sa
            # cash/len(new_names) later obegransat med antalet samtidiga
            # positioner. Storleksatt mot AVSTAENDE kapacitet av
            # capital_level istallet.
            current_liability = sum(hh["shares"] * hh["last_price"] for hh in holdings.values())
            pool = max(0.0, capital_level - current_liability)
            target_dollar_per_name = pool / len(new_names)
            for t in new_names:
                ti = tidx[t]
                cp = prices_v[date_i, ti]
                if np.isnan(cp) or cp <= 0:
                    continue
                adv = dollar_volume.values[date_i, ti]
                cap_dollar = adv * MAX_ADV_PCT if not np.isnan(adv) else target_dollar_per_name
                sz = min(target_dollar_per_name, cap_dollar)
                if sz <= 0:
                    continue
                entry_spread = spread_v[date_i, ti]
                entry_spread = 0.0 if np.isnan(entry_spread) else entry_spread
                effective_entry = cp * (1 - entry_spread / 2)
                shares = sz / effective_entry
                cash += shares * effective_entry
                exit_pos = min(date_i + HOLD_DAYS, len(date_index) - 1)
                holdings[t] = {"shares": shares, "entry_price": effective_entry,
                               "last_price": cp, "exit_pos": exit_pos}

        short_liability = 0.0
        daily_borrow_total = 0.0
        for t, h in holdings.items():
            ti = tidx[t]
            cp = float(prices_v[date_i, ti])
            if np.isnan(cp):
                cp = h["last_price"]
            else:
                h["last_price"] = cp
            liability = h["shares"] * cp
            short_liability += liability
            daily_borrow_total += borrow_cost(position_value=liability, holding_days=1,
                                               annual_rate=BORROW_ANNUAL_RATE)

        cash -= daily_borrow_total
        pv_list.append(cash - short_liability)

    pv = pd.Series(pv_list, index=trade_dates)
    tl = pd.DataFrame(trade_log)
    return (pv, tl), n_events_used


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


# ════════════════════════════════════════════════════════════
#  KÖRNING
# ════════════════════════════════════════════════════════════
def main():
    print("Laddar universum...")
    tickers, universe_by_month = load_universe()
    month_keys_sorted = sorted(universe_by_month.keys())
    print(f"  {len(tickers)} unika tickers.\n")

    print(f"Laddar prismatriser ({FULL_START} till {FULL_END})...")
    close, high, low, volume = load_price_matrices(tickers, FULL_START, FULL_END)
    print(f"  Prismatris: {close.shape}\n")

    print("Sanerar prisdata...")
    close, high, low = clean_price_matrix(close, high, low, volume=volume)
    implausible = flag_implausible_liquidity(close, volume, max_market_cap=MAX_MARKET_CAP,
                                              window=ADV_WINDOW, multiplier=1.0)
    close = close.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)
    close = mask_unrecovered_price_breaks(close)
    high = high.where(close.notna())
    low = low.where(close.notna())

    print("Berknar Corwin-Schultz-spread...")
    spread_df = compute_spread_matrix(high, low)

    print("Laddar SEC filings-index (data/cache/sec_filing_index.jsonl)...")
    filing_index = load_filing_index()
    print(f"  {len(filing_index)} av {len(tickers)} tickers har relevanta filingar.\n")

    print("Beräknar stress-score och triggers...")
    score, events = compute_score_and_triggers(filing_index, tickers, close.index)
    print(f"  {len(events)} rakandelar (korsningshandelser score>=2) innan universums-/prisfilter.\n")

    entries_by_date, score_at_trigger = group_by_week_and_size_entries(events, close.index)

    RESULTS_DIR.mkdir(exist_ok=True)
    main_results, oos_results = [], []
    n_events_final = None

    for level in [100_000, 1_000_000, 10_000_000]:
        print(f"--- Kapitalnivå: ${level:,.0f} ---")
        res, n_events = run_short_portfolio(close, spread_df, volume, universe_by_month, month_keys_sorted,
                                            entries_by_date, level)
        n_events_final = n_events
        if res is None:
            print("    Inga giltiga handelser. Avbryter.\n")
            main_results.append({"capital_level": level, "sharpe": None, "cagr": None, "max_drawdown": None})
            oos_results.append({"capital_level": level, "oos_2025_sharpe": None, "oos_2025_max_drawdown": None})
            continue

        pv, tl = res
        main_pv = pv.loc[pv.index < OOS_START]
        oos_pv = pv.loc[pv.index >= OOS_START]

        m = {"capital_level": level, "cagr": cagr(main_pv), "sharpe": sharpe(main_pv),
             "calmar": calmar(main_pv), "max_drawdown": max_drawdown(main_pv), "n_events": n_events}
        main_results.append(m)
        o = {"capital_level": level, "oos_2025_sharpe": sharpe(oos_pv) if len(oos_pv) > 2 else None,
             "oos_2025_max_drawdown": max_drawdown(oos_pv) if len(oos_pv) > 2 else None,
             "n_days_oos": len(oos_pv)}
        oos_results.append(o)

        pv.to_csv(RESULTS_DIR / f"portfolio_value_{int(level)}.csv", header=["portfolio_value"])
        tl.to_csv(RESULTS_DIR / f"trade_log_{int(level)}.csv", index=False)

        print(f"    n_events={n_events}  CAGR={m['cagr']:+.2%}  Sharpe={m['sharpe']:.4f}  "
              f"MaxDD={m['max_drawdown']:.2%}")
        print(f"    OOS-2025: Sharpe={o['oos_2025_sharpe']}  MaxDD={o['oos_2025_max_drawdown']}\n")

    # Disclosure: fordelning av score vid triggertillfallet.
    score_dist = {}
    for (_t, _d), sv in score_at_trigger.items():
        score_dist[sv] = score_dist.get(sv, 0) + 1

    m100k = main_results[0]
    if m100k["sharpe"] is None:
        overall = "FEASIBILITY-FAIL"
    else:
        cond1 = m100k["sharpe"] >= 0.55
        cond2 = m100k["max_drawdown"] >= -0.50
        overall = "PASSED" if (cond1 and cond2) else "FAILED"
        print(f"=== SLUTBEDOMNING (avgorande $100k-niva) ===")
        print(f"  Villkor 1 (Sharpe >= 0,55): {m100k['sharpe']:.4f} -> {'PASS' if cond1 else 'FAIL'}")
        print(f"  Villkor 2 (MaxDD >= -50%): {m100k['max_drawdown']:.2%} -> {'PASS' if cond2 else 'FAIL'}")
        print(f"  => {overall}\n")

    summary = {"main": main_results, "oos_2025": oos_results, "overall": overall,
               "n_events_final": n_events_final, "score_distribution_at_trigger": score_dist}
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
