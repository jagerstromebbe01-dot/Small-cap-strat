"""
HYP-074: Utdelningsinitiering/-indragning - kapitalallokeringspolicy-chock.
Se research/hypothesis_registry/HYP-074-dividend-initiation-omission.yaml
for det lasta kriteriet.

INGEN NY EXTERN DATA - detekterar utdelningsjusteringsdagar via den redan
befintliga adjusted_close/close-kvoten (samma falt som redan anvands for
sanering, se mask_implausible_adjusted_close_ratio i data_hygiene.py).

TVA HELT OBEROENDE ENBENSPORTFOLJER (varje kapitalniva var for sig, ingen
delad kapitalpool mellan LONG och SHORT):
  LONG  (initiering): forsta utdelningsjusteringsdagen nagonsin per ticker,
        kraver >=36 manaders prishistorik innan handelsen.
  SHORT (indragning):  etablerad betalare (utdelning i >=3 av senaste 4
        kalenderkvartal) foljt av ETT FULLT kvartal (63 handelsdagar) utan
        utdelning.
Bada: entry nasta handelsdag efter handelsen, 120 handelsdagars fast
hallperiod, likaviktat over samtidiga positioner. Minimum-N-sparr (30
handelser) per ben, oberoende.
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
RESULTS_DIR = STRATEGY_DIR / "results"

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
from friction import borrow_cost, corwin_schultz_spread  # noqa: E402
from data_hygiene import (  # noqa: E402
    clean_price_matrix,
    flag_implausible_liquidity,
    mask_unrecovered_price_breaks,
    mask_implausible_adjusted_close_ratio,
)

# ════════════════════════════════════════════════════════════
#  PARAMETRAR (lasta i HYP-074:s pass_fail_criterion)
# ════════════════════════════════════════════════════════════
FULL_START = "2010-01-01"
FULL_END = "2025-12-31"
OOS_START = "2025-01-01"

MIN_HISTORY_MONTHS_INITIATION = 36
HOLD_DAYS = 120
OMISSION_WINDOW_DAYS = 63
ESTABLISHED_MIN_QUARTERS = 3
ESTABLISHED_WINDOW_QUARTERS = 4
MIN_N_EVENTS = 30

RATIO_CHANGE_LOW = -0.03
RATIO_CHANGE_HIGH = -0.0001

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
    month_keys_sorted = sorted(universe_by_month.keys())
    return all_tickers, universe_by_month, month_keys_sorted


def eligible_at(date_str: str, universe_by_month: dict, month_keys_sorted: list) -> set:
    """Senaste manadsnyckel <= date_str (samma 'as-of'-princip som resten av registret)."""
    idx = bisect.bisect_right(month_keys_sorted, date_str) - 1
    if idx < 0:
        return set()
    return set(universe_by_month.get(month_keys_sorted[idx], []))


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
#  UTDELNINGSJUSTERINGSDAGAR (ny signal, HYP-074)
# ════════════════════════════════════════════════════════════
def compute_dividend_day_matrix(close, close_adj):
    """True dar close_adj/close-kvotens dag-till-dag-forandring ligger
    strikt i (RATIO_CHANGE_LOW, RATIO_CHANGE_HIGH) - ett litet nedatgaende
    kvotsteg (utdelning), skilt fran splittar (mycket storre steg)."""
    ratio = (close_adj / close).replace([np.inf, -np.inf], np.nan)
    ratio_change = ratio.pct_change()
    return (ratio_change > RATIO_CHANGE_LOW) & (ratio_change < RATIO_CHANGE_HIGH)


def find_initiation_events(div_day: pd.DataFrame, close: pd.DataFrame) -> list:
    """[(ticker, trigger_date)] - forsta utdelningsjusteringsdagen nagonsin
    per ticker, med >=36 manaders giltig prishistorik dessforinnan."""
    events = []
    for t in div_day.columns:
        col = div_day[t]
        div_dates = col.index[col.values]
        if len(div_dates) == 0:
            continue
        first_div_date = div_dates[0]

        valid_close = close[t].notna()
        if not valid_close.any():
            continue
        first_valid_date = close.index[valid_close.values][0]

        if first_valid_date + pd.DateOffset(months=MIN_HISTORY_MONTHS_INITIATION) > first_div_date:
            continue
        events.append((t, first_div_date))
    return events


def find_omission_events(div_day: pd.DataFrame) -> list:
    """[(ticker, entry_trigger_date)] - kan intraffa flera ganger per
    ticker. entry_trigger_date ar den handelsdag DA fonstret utan
    utdelning lopte ut (entry sker "nasta handelsdag" i portfoljmotorn,
    dvs +1 handelsdag ytterligare, hanteras dar)."""
    quarterly = div_day.resample("QE").sum() > 0  # bool, index = kvartalsslut
    established = quarterly.rolling(ESTABLISHED_WINDOW_QUARTERS, min_periods=ESTABLISHED_WINDOW_QUARTERS).sum() >= ESTABLISHED_MIN_QUARTERS

    date_index = div_day.index
    events = []
    for t in div_day.columns:
        s = quarterly[t]
        est = established[t]
        quarters = s.index
        col = div_day[t].values
        for i in range(len(quarters) - 1):
            q = quarters[i]
            if not (bool(s.iloc[i]) and bool(est.iloc[i])):
                continue
            if bool(s.iloc[i + 1]):
                continue  # nasta kvartal HADE ocksa utdelning - inget indragningsfonster
            start_pos = date_index.searchsorted(q, side="right")
            end_pos = start_pos + OMISSION_WINDOW_DAYS
            if end_pos >= len(date_index):
                continue  # fonstret rymms inte inom tillgangliga dagar
            window_had_div = col[start_pos:end_pos].any()
            if window_had_div:
                continue
            entry_trigger_pos = end_pos - 1  # sista dagen i det tomma fonstret
            events.append((t, date_index[entry_trigger_pos]))
    return events


# ════════════════════════════════════════════════════════════
#  ENBENSPORTFOLJ (delad motor for LONG/initiering och SHORT/indragning)
# ════════════════════════════════════════════════════════════
def run_event_portfolio(close, close_adj, spread_df, volume, universe_by_month, month_keys_sorted,
                        events, side: str, capital_level: float):
    """side: 'long' eller 'short'. events: [(ticker, trigger_date)] -
    faktisk entry sker NASTA handelsdag efter trigger_date."""
    tickers = list(close.columns)
    tidx = {t: i for i, t in enumerate(tickers)}
    dollar_volume = (close * volume).rolling(ADV_WINDOW).mean()
    date_index = close.index

    # Mappa varje handelse till FAKTISK entry-handelsdag (+1 fran trigger),
    # filtrera pa universumsmedlemskap OCH giltigt pris den dagen.
    entries_by_date = {}
    n_events_used = 0
    for t, trigger_date in events:
        pos = date_index.searchsorted(trigger_date, side="right")
        if pos >= len(date_index):
            continue
        entry_date = date_index[pos]
        if t not in tidx:
            continue
        cp = close_adj.iloc[pos][t]
        if pd.isna(cp) or cp <= 0:
            continue
        elig = eligible_at(entry_date.strftime("%Y-%m-%d"), universe_by_month, month_keys_sorted)
        if t not in elig:
            continue
        entries_by_date.setdefault(entry_date, []).append(t)
        n_events_used += 1

    if n_events_used == 0:
        return None, n_events_used

    prices_v = close_adj.values
    spread_v = spread_df.reindex(columns=tickers).values

    cash = float(capital_level)
    holdings = {}  # ticker -> {shares, entry_pos, exit_pos, cost/proceeds}
    pv_list = []
    trade_log = []

    start_date = min(entries_by_date.keys())
    start_idx = date_index.get_indexer([start_date])[0]
    trade_dates = date_index[start_idx:]

    for date_i in range(start_idx, len(date_index)):
        date = date_index[date_i]
        cash += cash * (RF_ANNUAL / 252)

        # Stang positioner vars hallperiod loper ut idag.
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
            if side == "long":
                proceeds = h["shares"] * cp * (1 - exit_spread / 2)
                cash += proceeds
                ret = proceeds / h["cost"] - 1
            else:  # short: kop tillbaka (betala lite mer pga spread)
                buyback_cost = h["shares"] * cp * (1 + exit_spread / 2)
                cash -= buyback_cost
                ret = (h["entry_price"] - cp * (1 + exit_spread / 2)) / h["entry_price"]
            trade_log.append({"date": date, "ticker": t, "ret": ret, "side": side})
            del holdings[t]

        # Oppna dagens nya positioner (om nagra), likaviktat sinsemellan.
        new_names = entries_by_date.get(date, [])
        new_names = [t for t in new_names if t not in holdings]
        if new_names:
            if side == "long":
                pool = cash
            else:
                # VIKTIGT (bugg upptackt 2026-08-12, HYP-073-korningen):
                # `cash` ar INTE tillgangligt kapital for ett kort ben -
                # blankningslikvider banka in i cash men motsvarande
                # skuld tracks separat (short_liability nedan), sa
                # cash/len(new_names) later obegransat med antalet
                # samtidiga positioner (varje ny blankning "later" mer
                # kapital an det egentligen finns). Storleksatt istallet
                # mot AVSTAENDE kapacitet av capital_level, inte cash.
                current_liability = sum(
                    hh["shares"] * hh["last_price"] for hh in holdings.values()
                )
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
                if side == "long":
                    sz = min(sz, cash)
                if sz <= 0:
                    continue
                entry_spread = spread_v[date_i, ti]
                entry_spread = 0.0 if np.isnan(entry_spread) else entry_spread
                exit_pos = min(date_i + HOLD_DAYS, len(date_index) - 1)
                if side == "long":
                    effective_entry = cp * (1 + entry_spread / 2)
                    shares = sz / effective_entry
                    cash -= sz
                    holdings[t] = {"shares": shares, "entry_price": effective_entry, "cost": sz,
                                   "last_price": cp, "exit_pos": exit_pos}
                else:  # short: salj lant (fa lite mindre pga spread), banka in likviden
                    effective_entry = cp * (1 - entry_spread / 2)
                    shares = sz / effective_entry
                    cash += shares * effective_entry
                    holdings[t] = {"shares": shares, "entry_price": effective_entry, "cost": sz,
                                   "last_price": cp, "exit_pos": exit_pos}

        # Dagligt vardera oppna positioner.
        long_val = 0.0
        short_liability = 0.0
        daily_borrow_total = 0.0
        for t, h in holdings.items():
            ti = tidx[t]
            cp = float(prices_v[date_i, ti])
            if np.isnan(cp):
                cp = h["last_price"]
            else:
                h["last_price"] = cp
            if side == "long":
                long_val += h["shares"] * cp
            else:
                liability = h["shares"] * cp
                short_liability += liability
                daily_borrow_total += borrow_cost(position_value=liability, holding_days=1,
                                                   annual_rate=BORROW_ANNUAL_RATE)

        if side == "short":
            cash -= daily_borrow_total
            pv_list.append(cash - short_liability)
        else:
            pv_list.append(cash + long_val)

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
    print("Laddar universum (grundsanning 2010-2024 + 2025-utokning)...")
    tickers, universe_by_month, month_keys_sorted = load_universe()
    print(f"  {len(tickers)} unika tickers totalt.\n")

    print(f"Laddar prismatriser ({FULL_START} till {FULL_END})...")
    close, close_adj, high, low, volume = load_price_matrices(tickers, FULL_START, FULL_END)
    print(f"  Prismatris: {close.shape}\n")

    print("Sanerar prisdata...")
    close, high, low = clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    close_adj = mask_implausible_adjusted_close_ratio(close, close_adj)

    print("Flaggar leverantors-datafel (implausible liquidity)...")
    implausible = flag_implausible_liquidity(close, volume, max_market_cap=MAX_MARKET_CAP,
                                              window=ADV_WINDOW, multiplier=1.0)
    close = close.mask(implausible)
    close_adj = close_adj.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)

    print("Maskerar ej aterhamtade prisbrott (mask_unrecovered_price_breaks)...")
    close = mask_unrecovered_price_breaks(close)
    close_adj = close_adj.where(close.notna())
    high = high.where(close.notna())
    low = low.where(close.notna())
    print(f"  Klart.\n")

    print("Berknar Corwin-Schultz-spread...")
    spread_df = compute_spread_matrix(high, low)

    print("Detekterar utdelningsjusteringsdagar...")
    div_day = compute_dividend_day_matrix(close, close_adj)
    print(f"  {int(div_day.values.sum())} ticker-dagar klassade som utdelningsjustering.\n")

    print("Hittar initierings- och indragningshandelser...")
    initiation_events = find_initiation_events(div_day, close)
    omission_events = find_omission_events(div_day)
    print(f"  Initiering (rakandelar innan universums-/prisfilter): {len(initiation_events)}")
    print(f"  Indragning (rakandelar innan universums-/prisfilter): {len(omission_events)}\n")

    RESULTS_DIR.mkdir(exist_ok=True)
    summary = {"legs": {}}

    for leg_name, events, side in [("initiation_long", initiation_events, "long"),
                                    ("omission_short", omission_events, "short")]:
        print(f"==== BEN: {leg_name} ({side}) ====")
        leg_results_main, leg_results_oos = [], []
        n_events_final = None

        for level in [100_000, 1_000_000, 10_000_000]:
            print(f"--- Kapitalnivå: ${level:,.0f} ---")
            res, n_events = run_event_portfolio(close, close_adj, spread_df, volume,
                                                 universe_by_month, month_keys_sorted,
                                                 events, side, level)
            n_events_final = n_events
            if res is None:
                print(f"    Inga giltiga handelser (n={n_events}). Hoppar over.\n")
                leg_results_main.append({"capital_level": level, "sharpe": None, "cagr": None,
                                          "max_drawdown": None, "calmar": None})
                leg_results_oos.append({"capital_level": level, "oos_2025_sharpe": None,
                                         "oos_2025_max_drawdown": None})
                continue

            pv, tl = res
            main_pv = pv.loc[pv.index < OOS_START]
            oos_pv = pv.loc[pv.index >= OOS_START]

            m = {"capital_level": level, "cagr": cagr(main_pv), "sharpe": sharpe(main_pv),
                 "calmar": calmar(main_pv), "max_drawdown": max_drawdown(main_pv), "n_events": n_events}
            leg_results_main.append(m)

            o = {"capital_level": level, "oos_2025_sharpe": sharpe(oos_pv) if len(oos_pv) > 2 else None,
                 "oos_2025_max_drawdown": max_drawdown(oos_pv) if len(oos_pv) > 2 else None,
                 "n_days_oos": len(oos_pv)}
            leg_results_oos.append(o)

            pv.to_csv(RESULTS_DIR / f"portfolio_value_{leg_name}_{int(level)}.csv", header=["portfolio_value"])
            tl.to_csv(RESULTS_DIR / f"trade_log_{leg_name}_{int(level)}.csv", index=False)

            print(f"    n_events(giltiga)={n_events}  CAGR={m['cagr']:+.2%}  Sharpe={m['sharpe']:.4f}  "
                  f"MaxDD={m['max_drawdown']:.2%}")
            print(f"    OOS-2025: Sharpe={o['oos_2025_sharpe']}  MaxDD={o['oos_2025_max_drawdown']}\n")

        insufficient_n = (n_events_final is not None and n_events_final < MIN_N_EVENTS) or n_events_final in (0, None)
        m100k = leg_results_main[0]
        if insufficient_n:
            leg_pass = None
            print(f"  BEN {leg_name}: OTILLRACKLIGT N ({n_events_final} < {MIN_N_EVENTS}) - exkluderad fran PASS/FAIL.\n")
        else:
            cond1 = m100k["sharpe"] is not None and m100k["sharpe"] >= 0.55
            cond2 = m100k["max_drawdown"] is not None and m100k["max_drawdown"] >= -0.50
            leg_pass = bool(cond1 and cond2)
            print(f"  BEN {leg_name}: Sharpe>=0.55: {cond1}  MaxDD>=-50%: {cond2}  => {'PASS' if leg_pass else 'FAIL'}\n")

        summary["legs"][leg_name] = {
            "n_events_final": n_events_final,
            "insufficient_n": insufficient_n,
            "main": leg_results_main,
            "oos_2025": leg_results_oos,
            "leg_pass": leg_pass,
        }

    both_insufficient = all(v["insufficient_n"] for v in summary["legs"].values())
    if both_insufficient:
        overall = "FEASIBILITY-FAIL"
    else:
        valid_legs = [v["leg_pass"] for v in summary["legs"].values() if not v["insufficient_n"]]
        overall = "PASSED" if any(valid_legs) and all(v is not False for v in valid_legs) else (
            "FAILED" if any(v is False for v in valid_legs) else "FEASIBILITY-FAIL")
        # Enligt kriteriet: om ENDAST ett ben har tillrackligt N, avgor DET benet ensamt.
        if len(valid_legs) == 1:
            overall = "PASSED" if valid_legs[0] else "FAILED"
        elif len(valid_legs) == 2:
            overall = "PASSED" if all(valid_legs) else "FAILED"

    summary["overall"] = overall
    print(f"=== SLUTBEDOMNING ===\n  {overall}\n")

    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
