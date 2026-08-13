"""
Delad backtestmotor for BATCH-004:s fyra textlikhets-varianter (HYP-093
till HYP-096, se deras registerposter for de lasta kriterierna).
Ateranvander de delade, redan validerade lag-niva-funktionerna fran
accrual_engine.py (universum, prismatriser, hedge, beta, spread,
friktions-primitiv, baseline, metrik) - INTE en dubblett, bara
ateranvand direkt - och lagger till textlikhets-specifik
signalladdning + en egen backtest-loop (tredjedelsindelning istallet
for decil, tva olika portfoljkonstruktioner: eget long/short-ben eller
undvikande-filter).

Kopiera INTE per hypotes - samma delad-modul-princip som resten av
BATCH-004.
"""

import bisect
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

STRATEGIES_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = STRATEGIES_ROOT.parent / "data"
CACHE_DIR = DATA_DIR / "cache"
TEXT_SIMILARITY_FILE = CACHE_DIR / "text_similarity_by_ticker.jsonl"

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
import accrual_engine as ae  # noqa: E402 - ateranvander universum/pris/hedge/beta/spread/friktion/baseline/metrik rakt av
from friction import borrow_cost  # noqa: E402
from rebalancing import snap_rebalance_dates  # noqa: E402

REBAL_FREQ = ae.REBAL_FREQ
RF_ANNUAL = ae.RF_ANNUAL
BETA_WINDOW = ae.BETA_WINDOW
MIN_HISTORY_DAYS = ae.MIN_HISTORY_DAYS
MAX_ADV_PCT = ae.MAX_ADV_PCT
ADV_WINDOW = ae.ADV_WINDOW
BORROW_ANNUAL_RATE = ae.BORROW_ANNUAL_RATE
STALENESS_DAYS = ae.STALENESS_DAYS
TERTILE_FRACTION = 1.0 / 3.0


def load_text_similarity_data(metric: str) -> dict:
    """metric: 'jaccard' eller 'cosine'. Returnerar ticker -> sorterad
    lista av (filed_date, likhetsvarde) - 'filed_date' approximeras med
    filingDate for den YNGRE (aktuella) 10-K:n i varje jamforelsepar,
    eftersom det ar den dag signalen faktiskt blir kand."""
    out = {}
    if not TEXT_SIMILARITY_FILE.exists():
        return out
    with TEXT_SIMILARITY_FILE.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            obs = []
            for c in row.get("comparisons", []):
                val = c.get(metric)
                if val is None or not c.get("filing_date"):
                    continue
                obs.append((c["filing_date"], val))
            if obs:
                obs.sort()
                out[row["ticker"]] = obs
    return out


def similarity_asof(data: dict, ticker: str, as_of_date_str: str, staleness_days=STALENESS_DAYS):
    obs = data.get(ticker)
    if not obs:
        return None
    dates = [o[0] for o in obs]
    idx = bisect.bisect_left(dates, as_of_date_str) - 1
    if idx < 0:
        return None
    filed, val = obs[idx]
    age_days = (pd.Timestamp(as_of_date_str) - pd.Timestamp(filed)).days
    if age_days > staleness_days:
        return None
    return val


def score_universe(eligible, sim_data, as_of, prices_v, tidx):
    """Returnerar sorterad lista (likhetsvarde, ticker, close_price),
    LAGST likhet forst (mest FORANDRAT risksprak)."""
    scores = []
    for t in eligible:
        val = similarity_asof(sim_data, t, as_of)
        if val is None:
            continue
        cp = prices_v[tidx[t]]
        if np.isnan(cp) or cp <= 0:
            continue
        scores.append((val, t, cp))
    scores.sort()
    return scores


def run_backtest(close, close_adj, hedge, sim_data, construction,
                  beta_df, spread_df, volume, universe_by_month, capital_level: float):
    """construction: 'own_leg' (long ÖVRE tredjedelen/stabilast, short
    NEDRE/mest förändrat - eget dollar-neutralt ben, ingen SPY-hedge)
    eller 'avoidance_filter' (long-only, likaviktat över HELA
    universumet MINUS nedre tredjedelen, SPY-beta-hedgad som HYP-033)."""
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
    long_holdings, short_holdings = {}, {}
    pv_list = [float(capital_level)]
    trade_log = []
    beta_exposure_log = []

    for date_i in range(start_idx, len(close.index)):
        date = close.index[date_i]
        hr_raw = hedge_ret_v[date_i]
        hr = float(hr_raw) if not np.isnan(hr_raw) else 0.0
        cash += cash * (RF_ANNUAL / 252)

        if date in rebal_set:
            month_key = rebal_map[date].strftime("%Y-%m-%d")
            as_of = date.strftime("%Y-%m-%d")
            eligible = [t for t in universe_by_month.get(month_key, []) if t in tidx]
            scores = score_universe(eligible, sim_data, as_of, prices_v[date_i], tidx)
            n = len(scores)
            n_third = max(1, int(n * TERTILE_FRACTION)) if n >= 6 else 0

            if construction == "own_leg":
                short_targets = {t for _, t, _ in scores[:n_third]} if n_third else set()   # lagst likhet
                long_targets = {t for _, t, _ in scores[-n_third:]} if n_third else set()   # hogst likhet
            else:  # avoidance_filter: long-only, hela universumet MINUS nedre tredjedelen
                excluded = {t for _, t, _ in scores[:n_third]} if n_third else set()
                long_targets = {t for _, t, _ in scores} - excluded
                short_targets = set()

            for t in list(long_holdings.keys()):
                if t not in long_targets:
                    ti = tidx[t]
                    cp = prices_v[date_i, ti]
                    if np.isnan(cp):
                        cp = long_holdings[t]["last_price"]
                    proceeds = long_holdings[t]["shares"] * cp
                    exit_spread = spread_v[date_i, ti]
                    if not np.isnan(exit_spread):
                        proceeds -= proceeds * (exit_spread / 2)
                    cash += proceeds
                    ret = proceeds / long_holdings[t]["cost"] - 1
                    trade_log.append({"date": date, "ticker": t, "side": "long", "ret": ret, "type": "rebalance_exit"})
                    del long_holdings[t]

            new_longs = [t for t in long_targets if t not in long_holdings]
            if new_longs:
                target_dollar = cash / len(new_longs) if len(new_longs) > 0 else 0.0
                for t in new_longs:
                    ti = tidx[t]
                    cp = prices_v[date_i, ti]
                    if np.isnan(cp) or cp <= 0:
                        continue
                    adv = dollar_volume.values[date_i, ti]
                    cap_dollar = adv * MAX_ADV_PCT if not np.isnan(adv) else target_dollar
                    sz = min(target_dollar, cap_dollar, cash)
                    if sz <= 0:
                        continue
                    entry_spread = spread_v[date_i, ti]
                    effective_entry = cp * (1 + entry_spread / 2) if not np.isnan(entry_spread) else cp
                    shares = sz / effective_entry
                    cash -= sz
                    long_holdings[t] = {"shares": shares, "entry": effective_entry, "cost": sz, "last_price": cp}

            if construction == "own_leg":
                for t in list(short_holdings.keys()):
                    if t not in short_targets:
                        ti = tidx[t]
                        cp = prices_v[date_i, ti]
                        if np.isnan(cp):
                            cp = short_holdings[t]["last_price"]
                        cover_cost = short_holdings[t]["shares"] * cp
                        exit_spread = spread_v[date_i, ti]
                        if not np.isnan(exit_spread):
                            cover_cost += cover_cost * (exit_spread / 2)
                        pnl = short_holdings[t]["proceeds"] - cover_cost
                        cash += pnl
                        ret = pnl / short_holdings[t]["proceeds"] if short_holdings[t]["proceeds"] else 0.0
                        trade_log.append({"date": date, "ticker": t, "side": "short", "ret": ret, "type": "rebalance_exit"})
                        del short_holdings[t]

                new_shorts = [t for t in short_targets if t not in short_holdings]
                if new_shorts:
                    target_dollar = capital_level / max(len(long_targets), 1)
                    for t in new_shorts:
                        ti = tidx[t]
                        cp = prices_v[date_i, ti]
                        if np.isnan(cp) or cp <= 0:
                            continue
                        adv = dollar_volume.values[date_i, ti]
                        cap_dollar = adv * MAX_ADV_PCT if not np.isnan(adv) else target_dollar
                        sz = min(target_dollar, cap_dollar)
                        if sz <= 0:
                            continue
                        entry_spread = spread_v[date_i, ti]
                        effective_entry = cp * (1 - entry_spread / 2) if not np.isnan(entry_spread) else cp
                        shares = sz / effective_entry
                        short_holdings[t] = {"shares": shares, "entry": effective_entry, "proceeds": sz, "last_price": cp}

        # KORT-BEN STOP-LOSS (DAGLIG) - se accrual_engine.py::run_backtest
        # för fullständig motivering (upptäckt 2026-08-13, HYP-098,
        # samma fix återanvänd här eftersom own_leg-konstruktionen har
        # identisk kort-ben-redovisning).
        if construction == "own_leg":
            for t in list(short_holdings.keys()):
                ti = tidx[t]
                cp = prices_v[date_i, ti]
                if np.isnan(cp):
                    continue
                h = short_holdings[t]
                paper_loss_ratio = (cp - h["entry"]) / h["entry"] if h["entry"] > 0 else 0.0
                if paper_loss_ratio > ae.SHORT_STOP_LOSS_THRESHOLD:
                    cover_cost = h["shares"] * cp
                    exit_spread = spread_v[date_i, ti]
                    if not np.isnan(exit_spread):
                        cover_cost += cover_cost * (exit_spread / 2)
                    pnl = h["proceeds"] - cover_cost
                    cash += pnl
                    ret = pnl / h["proceeds"] if h["proceeds"] else 0.0
                    trade_log.append({"date": date, "ticker": t, "side": "short", "ret": ret, "type": "stop_loss"})
                    del short_holdings[t]

        long_val, long_beta = 0.0, 0.0
        for t, h in long_holdings.items():
            ti = tidx[t]
            cp = float(prices_v[date_i, ti])
            if np.isnan(cp):
                cp = h["last_price"]
            else:
                h["last_price"] = cp
            val = h["shares"] * cp
            long_val += val
            long_beta += val * float(beta_v[date_i, ti])

        short_val, short_beta = 0.0, 0.0
        for t, h in short_holdings.items():
            ti = tidx[t]
            cp = float(prices_v[date_i, ti])
            if np.isnan(cp):
                cp = h["last_price"]
            else:
                h["last_price"] = cp
            mtm = h["shares"] * cp
            short_val += mtm
            short_beta += mtm * float(beta_v[date_i, ti])

        if construction == "avoidance_filter":
            daily_borrow = borrow_cost(position_value=abs(long_beta), holding_days=1, annual_rate=BORROW_ANNUAL_RATE)
            hedge_pnl = -long_beta * hr - long_beta * (RF_ANNUAL / 2 / 252) - daily_borrow
            pv_list.append(cash + long_val + hedge_pnl)
            beta_exposure_log.append({"date": date, "net_beta_dollar": 0.0})
        else:
            daily_short_borrow = borrow_cost(position_value=short_val, holding_days=1, annual_rate=BORROW_ANNUAL_RATE)
            pv_today = cash + long_val - short_val - daily_short_borrow
            # KONKURSGOLV - se accrual_engine.py::run_backtest för
            # fullständig motivering (upptäckt 2026-08-13, HYP-098, samma
            # fix återanvänd här).
            if pv_today <= 0:
                pv_today = 1e-6 * capital_level
            pv_list.append(pv_today)
            beta_exposure_log.append({"date": date, "net_beta_dollar": long_beta - short_beta})

    pv = pd.Series(pv_list[1:], index=trade_dates)
    tl = pd.DataFrame(trade_log)
    beta_log = pd.DataFrame(beta_exposure_log)
    return pv, tl, beta_log
