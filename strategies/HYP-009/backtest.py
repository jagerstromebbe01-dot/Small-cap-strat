"""
HYP-009: ren friktionsablation av HYP-008 - INTE en ny strategi.

Kopierad ORÖRD från /strategies/HYP-008/backtest.py (som i sin tur
kopierade /reference_code/v6_core_large_cap.py) - universum, signaler,
par-identifiering, z-score, beta, entry/exit, position sizing och
kapacitetsspärren (MAX_ADV_PCT) är IDENTISKA. Se
research/strategy_specs/HYP-009-spec.md.

DEN ENDA TILLÅTNA SKILLNADEN mot HYP-008 (spec §3, kriteriet i
research/hypothesis_registry/HYP-009-friction-ablation.yaml):

1. Borrow-kostnad: BORROW_ANNUAL_RATE = 0.0 istället för 0.03.
   borrow_cost() anropas fortfarande, med annual_rate=0.0 - inte
   hoppas över.
2. Bid-ask-spread: corwin_schultz_spread() beräknas EXAKT som i
   HYP-008 (samma spread_df) - men kostnadseffekten (halva spreaden
   vid öppning, halva vid stängning) multipliceras med
   SPREAD_COST_MULTIPLIER = 0.0 innan den adderas/dras av. Beräkningen
   av spreaden i sig tas INTE bort, bara dess kostnadseffekt
   nollställs, så att validate_friction_usage.py:s AST-kontroll (import
   + faktiskt anrop av båda friktionsfunktionerna) fortfarande går
   igenom - annars skulle ablationen inte bevisa något, eftersom man då
   inte vet om frånvaron av kostnad kom från en faktisk nollberäkning
   eller bara från att kostnadsvägen aldrig kördes.

Kapacitetsspärren (MAX_ADV_PCT) förblir AKTIV och oförändrad - den
mäter handelsbarhet, inte kostnad, och ingår inte i ablationen.

Kör vid flera kapitalnivåer via --capital <belopp>, eller alla tre
(100000, 1000000, 10000000) via --all-levels.

PRESTANDAOPTIMERAD 2026-07-29 (CEO-beslut, ren hastighetsoptimering,
INGEN ändring av ekonomisk logik/metodik): compute_beta() och
run_backtest() skrevs om till vektoriserad numpy-indexering istället för
Python-loopar med pandas ".loc[]"-uppslag per ticker/dag (produktions-
universumet har 5162 tickers - miljontals enskilda uppslag i den
ursprungliga versionen). Se respektive funktions docstring för exakt vad
som ändrades. Verifierat numeriskt IDENTISKT mot originalversionen på
full skala (samtliga 5162 tickers, alla tre kapitalnivåer - 0.0 skillnad
i portfolio_value och trade_log) innan denna version ersatte originalet
- se scripts/validate_beta_optimization.py och
scripts/validate_run_backtest_optimization.py. Total körtid gick från
100+ minuter till ~6-8 minuter för hela HYP-009 (identify_pairs_dynamic/
compute_zscore/compute_spread_matrix är ANNU inte optimerade och
dominerar nu den kvarvarande körtiden).
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

# ════════════════════════════════════════════════════════════
#  PARAMETRAR (identiska med HYP-008/v6-kärnan där de överlappar)
# ════════════════════════════════════════════════════════════
FULL_START = "2010-01-01"
FULL_END = "2024-12-31"

COINT_WINDOW = 252
ZSCORE_WINDOW = 63
MIN_PAIRS = 3
CORR_THRESH = 0.70
MAX_PAIRS = 8
TRADE_Z_THRESH = 1.5
STOP_LOSS = 0.06
MAX_POS = 12
RF_ANNUAL = 0.02
BETA_WINDOW = 126
FIXED_FRAC = 0.05

# ── ABLATION (spec §3 / kriteriet) - ENDA skillnaden mot HYP-008 ──
BORROW_ANNUAL_RATE = 0.0     # HYP-008: 0.03. Ablation: friktion -> 0.
SPREAD_COST_MULTIPLIER = 0.0  # HYP-008: kostnadstermen appliceras med
                               # multiplikator 1 (implicit). Ablation:
                               # spreaden beräknas fortfarande, men dess
                               # kostnadseffekt nollställs.

MAX_ADV_PCT = 0.10  # Kapacitetsspärr - OFÖRÄNDRAD, ej del av ablationen
ADV_WINDOW = 20

HEDGE = "SPY"


# ════════════════════════════════════════════════════════════
#  DATA (från lokal cache, ingen ny hämtning) - identiskt med HYP-008
# ════════════════════════════════════════════════════════════
def load_universe():
    with UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_by_month = json.load(f)
    all_tickers = sorted({t for tickers in universe_by_month.values() for t in tickers})
    return all_tickers, universe_by_month


def trading_calendar(start, end):
    """
    Riktig handelskalender, härledd från SPY:s FAKTISKA handelsdagar -
    identiskt med HYP-008 (se den filens docstring för bakgrunden till
    varför pd.bdate_range inte används).
    """
    path = OHLCV_DIR / f"{HEDGE}.csv"
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


def load_hedge(start, end):
    path = OHLCV_DIR / f"{HEDGE}.csv"
    df = pd.read_csv(path, usecols=["date", "close"], parse_dates=["date"])
    df = df.drop_duplicates(subset="date", keep="last").set_index("date").sort_index()
    date_index = trading_calendar(start, end)
    return df["close"].reindex(date_index)


# ════════════════════════════════════════════════════════════
#  PAR-IDENTIFIERING (identisk med HYP-008)
# ════════════════════════════════════════════════════════════
def identify_pairs_dynamic(close, log_ret, universe_by_month, cointegration_window, min_pairs, corr_thresh, max_pairs):
    rebal_dates = close.resample("ME").last().index
    pairs_by_date = {}

    for rd in rebal_dates:
        month_key = rd.strftime("%Y-%m-%d")
        eligible = [t for t in universe_by_month.get(month_key, []) if t in close.columns]
        if len(eligible) < 2:
            pairs_by_date[rd] = {}
            continue

        mask = log_ret.index <= rd
        if mask.sum() < cointegration_window:
            pairs_by_date[rd] = {}
            continue

        window = log_ret.loc[mask, eligible].iloc[-cointegration_window:]
        clean_cols = window.columns[window.notna().all()]
        if len(clean_cols) < 2:
            pairs_by_date[rd] = {}
            continue

        corr = window[clean_cols].corr()
        pd_ = {}
        for t in clean_cols:
            ct = corr[t].drop(t).sort_values(ascending=False)
            top = ct[ct >= corr_thresh].head(max_pairs).index.tolist()
            if len(top) >= min_pairs:
                pd_[t] = top
        pairs_by_date[rd] = pd_

    return pairs_by_date


# ════════════════════════════════════════════════════════════
#  Z-SCORE (identisk logik med HYP-008, look-ahead-fri)
# ════════════════════════════════════════════════════════════
def compute_zscore(prices, log_p, pairs_by_date, cointegration_window, zscore_window, tidx):
    DAYS, N = prices.shape
    rebal_list = sorted(pairs_by_date.keys())
    z_arr = np.full((DAYS, N), np.nan, dtype="float32")

    log_p_vals = log_p.values

    for day_i, date in enumerate(prices.index):
        if day_i < cointegration_window:
            continue
        past = [r for r in rebal_list if r <= date]
        if not past:
            continue
        pairs = pairs_by_date[past[-1]]
        if not pairs:
            continue

        ws = max(0, day_i - zscore_window)
        for t, ps in pairs.items():
            ti = tidx.get(t)
            if ti is None:
                continue
            pi = [tidx[p] for p in ps if p in tidx]
            if not pi:
                continue
            y = log_p_vals[ws:day_i, ti]
            X = log_p_vals[ws:day_i, pi]
            if len(y) < 20 or np.any(np.isnan(y)) or np.any(np.isnan(X)):
                continue
            try:
                Xm = np.column_stack([np.ones(len(y)), X])
                coef, *_ = np.linalg.lstsq(Xm, y, rcond=None)

                fh_hist = coef[0] + X[:-1] @ coef[1:]
                spread_hist = y[:-1] - fh_hist
                spread_mean = spread_hist.mean()
                spread_std = spread_hist.std()

                y_today = log_p_vals[day_i, ti]
                x_today = log_p_vals[day_i, pi]
                fv_today = coef[0] + np.dot(x_today, coef[1:])
                spread_today = y_today - fv_today

                if spread_std > 1e-6:
                    z_arr[day_i, ti] = (spread_today - spread_mean) / spread_std
            except Exception:
                continue

    return pd.DataFrame(z_arr, index=prices.index, columns=prices.columns)


# ════════════════════════════════════════════════════════════
#  BETA (identisk logik med HYP-008)
# ════════════════════════════════════════════════════════════
def compute_beta(prices, hedge, beta_window):
    """
    OPTIMERAD (2026-07-29): vektoriserad over ALLA tickers samtidigt via
    pandas rolling-summor, istallet for en Python-loop per ticker per dag
    (5162 tickers x ~3500 dagar i produktionsuniversumet - miljontals
    enskilda np.cov()-anrop i originalversionen).

    Matematiskt IDENTISK formel, bara omskriven till kumulativa summor sa
    den kan koras vektoriserat (samma algebra som np.cov med ddof=1):
        cov(x,y) = (sum(xy) - n*mean(x)*mean(y)) / (n-1)
        var(y)   = (sum(y^2) - n*mean(y)^2) / (n-1)
    Fonstret [i-beta_window, i) (exkl. dag i, exakt som originalet) fas
    via rolling(w).sum().shift(1) - pandas rolling(w) vid rad i summerar
    [i-w+1, i] (inkl. rad i), shift(1) flyttar det till att galla rad i+1,
    dvs motsvarar exakt [i-w, i-1] for rad i. Verifierad numeriskt mot den
    ursprungliga loop-baserade implementationen pa riktig data innan
    integrering - se scripts/validate_beta_optimization.py.
    """
    DAYS, N = prices.shape
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

    return pd.DataFrame(beta_arr, index=prices.index, columns=prices.columns)


# ════════════════════════════════════════════════════════════
#  FRIKTION: Corwin-Schultz-spread per ticker, hela perioden
#  (SKATTNINGEN är identisk med HYP-008 - ablationen sker bara i hur
#  kostnadseffekten appliceras i run_backtest, se SPREAD_COST_MULTIPLIER)
# ════════════════════════════════════════════════════════════
def compute_spread_matrix(high, low):
    spread = {}
    for t in high.columns:
        spread[t] = corwin_schultz_spread(high[t].values, low[t].values)
    return pd.DataFrame(spread, index=high.index)


# ════════════════════════════════════════════════════════════
#  BACKTEST-MOTOR: v6-signaler + friktion (nollställd) + kapacitetsspärr
# ════════════════════════════════════════════════════════════
def run_backtest(prices, hedge, zscore_df, beta_df, spread_df, volume,
                 capital_level: float):
    """
    OPTIMERAD (2026-07-29): all daglig dataatkomst gar via raa numpy-
    arrayer (indexerade med heltalsposition + tidx[ticker]) istallet for
    pandas ".loc[date, t]"-uppslag - flera miljoner sadana uppslag i
    produktionsuniversumet (5162 tickers), och .loc ar storleksordningar
    langsammare an numpy-indexering. Ingen logik, trosklar, eller ordning
    har andrats - bara SATTET att lasa exakt samma varden pa. Verifierad
    numeriskt (identisk trade_log/portfolio_value) mot originalversionen
    i strategies/HYP-009/backtest.py - se
    scripts/validate_run_backtest_optimization.py.
    """
    hedge_ret = hedge.pct_change()
    mom_3d = prices.pct_change(3)
    mom_10d = prices.pct_change(10)
    rf_daily = RF_ANNUAL / 252
    tickers = list(prices.columns)
    tidx = {t: i for i, t in enumerate(tickers)}

    dollar_volume = (prices * volume).rolling(ADV_WINDOW).mean()

    trade_state_vals = np.where(zscore_df.values < -TRADE_Z_THRESH, 1,
                                 np.where(zscore_df.values > TRADE_Z_THRESH, -1, 0))

    start_idx = max(COINT_WINDOW, BETA_WINDOW)
    trade_dates = prices.index[start_idx:]

    # Raa numpy-vyer, en gang, aterananda for varje dag i loopen nedan.
    prices_v = prices.values
    zscore_v = zscore_df.values
    mom3_v = mom_3d.values
    mom10_v = mom_10d.values
    beta_v = beta_df.values
    dollar_volume_v = dollar_volume.values
    hedge_ret_v = hedge_ret.values
    # spread_df kan sakna nagra kolumner (samma semantik som originalets
    # "if t in spread_df.columns else nan") - reindex fyller saknade med NaN.
    spread_v = spread_df.reindex(columns=tickers).values

    cash, positions, pv_list, trade_log = float(capital_level), {}, [float(capital_level)], []

    for date_i in range(start_idx, len(prices.index)):
        date = prices.index[date_i]
        hr_raw = hedge_ret_v[date_i]
        hr = float(hr_raw) if not np.isnan(hr_raw) else 0.0
        cash += cash * rf_daily

        # ── Stäng positioner ────────────────────────────────
        to_close = []
        for t, pos in positions.items():
            ti = tidx[t]
            cp = float(prices_v[date_i, ti])
            cz = float(zscore_v[date_i, ti])
            if np.isnan(cp):
                continue
            hit_stop = cp <= pos["stop"]
            hit_target = not np.isnan(cz) and abs(cz) < 0.3
            if hit_stop or hit_target:
                gross_ret = cp / pos["entry"] - 1
                proceeds = pos["size"] * (cp / pos["entry"])

                # Friktion (ablation): halva Corwin-Schultz-spreaden
                # beräknas exakt som i HYP-008, men kostnadseffekten
                # multipliceras med SPREAD_COST_MULTIPLIER (=0.0 här).
                exit_spread = spread_v[date_i, ti]
                if not np.isnan(exit_spread):
                    proceeds -= proceeds * (exit_spread / 2) * SPREAD_COST_MULTIPLIER

                cash += proceeds
                net_ret = proceeds / pos["size"] - 1
                to_close.append(t)
                trade_log.append({
                    "date": date, "ticker": t, "ret": net_ret, "gross_ret": gross_ret,
                    "type": "stop" if hit_stop else "target",
                })
        for t in to_close:
            del positions[t]

        # ── Öppna nya positioner (kapacitetsspärrad storlek) ──
        if len(positions) < MAX_POS:
            cands = []
            row_state = trade_state_vals[date_i]
            row_prices = prices_v[date_i]
            row_z = zscore_v[date_i]
            row_m3 = mom3_v[date_i]
            row_m10 = mom10_v[date_i]
            # Vektoriserad forfiltrering (ersatter en Python-loop over
            # ALLA tickers): bara de med aktiv koptrigger (cst==1) och
            # icke-NaN pris/z-score gar vidare till momentumkontrollen.
            buy_signal = (row_state == 1) & (row_z < -TRADE_Z_THRESH) & \
                         ~np.isnan(row_prices) & ~np.isnan(row_z)
            for ti in np.flatnonzero(buy_signal):
                t = tickers[ti]
                if t in positions:
                    continue
                cm3 = row_m3[ti]
                cm10 = row_m10[ti]
                mom_ok = (not np.isnan(cm3) and cm3 > -0.04) or \
                         (not np.isnan(cm10) and cm10 > -0.06)
                if not mom_ok:
                    continue
                cands.append((abs(row_z[ti]), t, float(row_prices[ti])))
            cands.sort(reverse=True)
            slots = max(0, MAX_POS - len(positions))
            for _, t, cp in cands[:slots]:
                ti = tidx[t]
                desired = FIXED_FRAC * cash

                # Kapacitetsspärr: max MAX_ADV_PCT av 20-dagars snittlig
                # dollarvolym - OFÖRÄNDRAD, inte del av ablationen.
                adv = dollar_volume_v[date_i, ti]
                cap = adv * MAX_ADV_PCT if not np.isnan(adv) else desired
                sz = min(desired, cap)

                if sz < capital_level * 0.0001:
                    continue

                # Friktion (ablation): halva spreaden vid öppning,
                # samma nollställning som vid stängning ovan.
                entry_spread = spread_v[date_i, ti]
                if not np.isnan(entry_spread):
                    effective_entry = cp * (1 + entry_spread / 2 * SPREAD_COST_MULTIPLIER)
                else:
                    effective_entry = cp

                cash -= sz
                positions[t] = {"entry": effective_entry, "size": sz,
                                "stop": effective_entry * (1 - STOP_LOSS)}

        # ── Portföljvärde (beta-neutral hedge mot SPY + borrow-kostnad) ──
        long_beta = 0.0
        for t, pos in positions.items():
            ti = tidx[t]
            cp = float(prices_v[date_i, ti])
            if not np.isnan(cp):
                long_beta += pos["size"] * cp / pos["entry"] * float(beta_v[date_i, ti])
        # Friktion (ablation): borrow_cost() anropas fortfarande, men med
        # BORROW_ANNUAL_RATE=0.0 (HYP-008 använde 0.03).
        daily_borrow = borrow_cost(position_value=abs(long_beta), holding_days=1, annual_rate=BORROW_ANNUAL_RATE)
        hedge_pnl = -long_beta * hr - long_beta * (RF_ANNUAL / 2 / 252) - daily_borrow

        long_val = 0.0
        for t, pos in positions.items():
            cp = float(prices_v[date_i, tidx[t]])
            if not np.isnan(cp):
                long_val += pos["size"] * cp / pos["entry"]
        pv_list.append(cash + long_val + hedge_pnl)

    pv = pd.Series(pv_list[1:], index=trade_dates)
    tl = pd.DataFrame(trade_log)
    return pv, tl


# ════════════════════════════════════════════════════════════
#  METRICS (identiska definitioner mot HYP-008)
# ════════════════════════════════════════════════════════════
def sharpe(s, rf=0.02):
    r = s.pct_change().dropna()
    return float(np.sqrt(252) * (r - rf / 252).mean() / r.std()) if r.std() > 0 else 0.0


def max_drawdown(s):
    return float(((s - s.cummax()) / s.cummax()).min())


def cagr(s):
    return float((s.iloc[-1] / s.iloc[0]) ** (252 / len(s)) - 1)


def calmar(s):
    md = abs(max_drawdown(s))
    return cagr(s) / md if md > 0 else 0.0


def trade_stats(tl):
    if len(tl) == 0:
        return dict(n=0, win_rate=0.0, avg_ret=0.0, pf=np.nan)
    wins = tl[tl["ret"] > 0]["ret"]
    losses = tl[tl["ret"] <= 0]["ret"]
    pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 and losses.sum() != 0 else np.nan
    return dict(n=len(tl), win_rate=len(wins) / len(tl), avg_ret=tl["ret"].mean(), pf=pf)


def best_trade_excluded_metrics(pv, tl, capital_level):
    """
    Återanvänd oförändrad från HYP-008 (spec §4: relevant att rapportera
    men inte del av HYP-009:s egna, rent Sharpe-baserade kriterium).
    """
    if len(tl) == 0:
        return {"sharpe_excl_best": None, "calmar_excl_best": None}

    best_idx = tl["ret"].idxmax()
    best_trade = tl.loc[best_idx]
    best_date = best_trade["date"]
    best_dollar_pnl = best_trade["ret"] * capital_level * FIXED_FRAC

    pv_adj = pv.copy()
    pv_adj.loc[pv_adj.index >= best_date] -= best_dollar_pnl

    return {
        "sharpe_excl_best": sharpe(pv_adj),
        "calmar_excl_best": calmar(pv_adj),
    }


# ════════════════════════════════════════════════════════════
#  KÖRNING
# ════════════════════════════════════════════════════════════
def run_for_capital_level(capital_level, close, hedge, zscore_df, beta_df,
                          spread_df, volume):
    print(f"    Kör backtest (kapitalnivå {capital_level:,.0f})...")
    pv, tl = run_backtest(close, hedge, zscore_df, beta_df, spread_df, volume, capital_level)

    result = {
        "capital_level": capital_level,
        "cagr": cagr(pv),
        "sharpe": sharpe(pv),
        "calmar": calmar(pv),
        "max_drawdown": max_drawdown(pv),
        "trade_stats": trade_stats(tl),
    }
    result.update(best_trade_excluded_metrics(pv, tl, capital_level))

    RESULTS_DIR.mkdir(exist_ok=True)
    pv.to_csv(RESULTS_DIR / f"portfolio_value_{int(capital_level)}.csv", header=["portfolio_value"])
    tl.to_csv(RESULTS_DIR / f"trade_log_{int(capital_level)}.csv", index=False)

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capital", type=float, default=None)
    parser.add_argument("--all-levels", action="store_true")
    args = parser.parse_args()

    levels = [100_000, 1_000_000, 10_000_000] if args.all_levels else [args.capital or 100_000]

    print("Laddar universum...")
    tickers, universe_by_month = load_universe()
    print(f"  {len(tickers)} unika tickers någonsin i universumet.\n")

    print("Laddar prismatriser (close/high/low/volume) från cache...")
    close, high, low, volume = load_price_matrices(tickers, FULL_START, FULL_END)
    hedge = load_hedge(FULL_START, FULL_END)
    print(f"  Prismatris: {close.shape}\n")

    tidx = {t: i for i, t in enumerate(close.columns)}
    log_ret = np.log(close).diff()

    print("Identifierar par (dynamiskt universum, månadsvis)...")
    pairs_by_date = identify_pairs_dynamic(close, log_ret, universe_by_month,
                                           COINT_WINDOW, MIN_PAIRS, CORR_THRESH, MAX_PAIRS)
    n_pairs_months = sum(1 for v in pairs_by_date.values() if v)
    print(f"  {n_pairs_months}/{len(pairs_by_date)} månader med minst ett identifierat par.\n")

    # Beräknas EN gång - beror inte på kapitalnivå, återanvänds för alla tre
    log_p = np.log(close)
    print("Beräknar z-score (görs en gång, delas mellan kapitalnivåer)...")
    zscore_df = compute_zscore(close, log_p, pairs_by_date, COINT_WINDOW, ZSCORE_WINDOW, tidx)

    print("Estimerar beta (görs en gång)...")
    beta_df = compute_beta(close, hedge, BETA_WINDOW)

    print("Beräknar Corwin-Schultz-spread (görs en gång, ablationen nollställer bara kostnadseffekten)...\n")
    spread_df = compute_spread_matrix(high, low)

    all_results = []
    for level in levels:
        print(f"--- Kapitalnivå: ${level:,.0f} ---")
        result = run_for_capital_level(level, close, hedge, zscore_df, beta_df, spread_df, volume)
        all_results.append(result)
        print(f"    CAGR={result['cagr']:+.2%}  Sharpe={result['sharpe']:.2f}  "
              f"Calmar={result['calmar']:.2f}  MaxDD={result['max_drawdown']:.1%}  "
              f"Trades={result['trade_stats']['n']}\n")

    RESULTS_DIR.mkdir(exist_ok=True)
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
