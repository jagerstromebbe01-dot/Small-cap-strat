"""
HYP-013: Enskild-aktie kortsiktig reversal pa small-cap - INGEN
partner-aktie kravs (till skillnad fran v6-karnan/HYP-008/009/011).

Andra av tre "pivot"-hypoteser (HYP-012/013/014). Testar direkt om
HYP-008/009/011:s problem (lag korrelation mellan small-cap-aktier gor
par-baserad reversal svag) loses genom att ta bort partnerkravet helt -
signalen ar en z-score av aktiens EGEN avkastning mot sin EGEN trailing-
fordelning, ingen regression, ingen par-identifiering.

Se research/hypothesis_registry/HYP-013-enskild-aktie-kortsiktig-reversal-pa.yaml
for det lasta kriteriet.

Aterananvander samma redan validerade infrastruktur som HYP-008/009/011:
universum, prisdata, friktionsmodell, SPY-beta-hedge (med
sakerhetsspärren mot degenererad beta, se compute_beta() nedan -
upptackt 2026-07-29 vid HYP-012), kapacitetsspärr.

METODIK:
- Signal: z(t) = (r_5d(t) - mean(r_5d, 63d)) / std(r_5d, 63d), dar r_5d
  ar aktiens EGEN kumulativa avkastning senaste 5 handelsdagarna. Kop
  nar z < -1.5 (oversald mot sin egen historik).
- Exit: konvergens (|z| < 0.3) ELLER max hålltid 20 handelsdagar (kortare
  an v6:s hålltid - reversal ar en snabbare effekt per litteraturen,
  Lehmann 1990/Jegadeesh 1990).
- Position: samma FIXED_FRAC/MAX_POS-modell som HYP-008 (individuella
  handelstillfallen, inte manatlig portfolj-ombalansering som HYP-012).
- Friktion/hedge/kapacitetsspärr: identiskt med HYP-008.

Kör vid flera kapitalnivåer via --capital <belopp>, eller alla tre
(100000, 1000000, 10000000) via --all-levels.
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
from data_hygiene import clean_price_matrix  # noqa: E402

# ════════════════════════════════════════════════════════════
#  PARAMETRAR
# ════════════════════════════════════════════════════════════
FULL_START = "2010-01-01"
FULL_END = "2024-12-31"

RET_WINDOW = 5           # dagars avkastning som mats
ZSCORE_WINDOW = 63       # trailing-fonster for z-score (samma som v6)
MIN_HISTORY = 68         # RET_WINDOW + ZSCORE_WINDOW
TRADE_Z_THRESH = 1.5     # samma troskel som v6 - INTE reverse-engineered
TARGET_Z = 0.3           # samma konvergensmal som v6
MAX_HOLDING_DAYS = 20    # kortare an v6 (60/oandligt) - reversal ar snabbare

STOP_LOSS = 0.06         # samma som v6/HYP-008 - oforandrad
MAX_POS = 12             # samma som HYP-008
FIXED_FRAC = 0.05        # samma som HYP-008
RF_ANNUAL = 0.02
BETA_WINDOW = 126

BORROW_ANNUAL_RATE = 0.03  # samma som HYP-008 - riktig friktion
MAX_ADV_PCT = 0.10
ADV_WINDOW = 20

HEDGE = "SPY"


# ════════════════════════════════════════════════════════════
#  DATA (identiskt med HYP-008)
# ════════════════════════════════════════════════════════════
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
#  BETA (identisk, vektoriserad, MED sakerhetsspärren mot degenererad beta)
# ════════════════════════════════════════════════════════════
def compute_beta(prices, hedge, beta_window):
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

    # SÄKERHETSSPÄRR (upptäckt 2026-07-29, HYP-012): se den filens
    # backtest.py for full forklaring - extremt tunt handlade tickers kan
    # fa en nastan-noll varians och darmed en astronomisk beta-skattning.
    beta_arr = np.clip(beta_arr, -5.0, 5.0)

    return pd.DataFrame(beta_arr, index=prices.index, columns=prices.columns)


def compute_spread_matrix(high, low):
    spread = {}
    for t in high.columns:
        spread[t] = corwin_schultz_spread(high[t].values, low[t].values)
    return pd.DataFrame(spread, index=high.index)


# ════════════════════════════════════════════════════════════
#  REVERSAL-SIGNAL (ny, ersatter par-identifiering + par-regression-zscore)
# ════════════════════════════════════════════════════════════
def compute_own_zscore(close, ret_window, zscore_window):
    """
    z(t) = (r_5d(t) - rullande_medel(r_5d, 63d)) / rullande_std(r_5d, 63d).
    Helt vektoriserad over alla tickers samtidigt - ingen per-ticker-loop,
    ingen regression, inget par-krav.
    """
    r5 = close.pct_change(ret_window)
    roll_mean = r5.rolling(zscore_window).mean()
    roll_std = r5.rolling(zscore_window).std()
    z = (r5 - roll_mean) / roll_std
    return z.astype("float32")


# ════════════════════════════════════════════════════════════
#  BACKTEST-MOTOR (samma struktur som HYP-008/009/011, ny signal + kortare hålltid)
# ════════════════════════════════════════════════════════════
def run_backtest(prices, hedge, zscore_df, beta_df, spread_df, volume,
                 capital_level: float):
    hedge_ret = hedge.pct_change()
    rf_daily = RF_ANNUAL / 252
    tickers = list(prices.columns)
    tidx = {t: i for i, t in enumerate(tickers)}

    dollar_volume = (prices * volume).rolling(ADV_WINDOW).mean()

    trade_state_vals = np.where(zscore_df.values < -TRADE_Z_THRESH, 1, 0)

    start_idx = MIN_HISTORY + BETA_WINDOW
    trade_dates = prices.index[start_idx:]

    prices_v = prices.values
    zscore_v = zscore_df.values
    beta_v = beta_df.values
    dollar_volume_v = dollar_volume.values
    hedge_ret_v = hedge_ret.values
    spread_v = spread_df.reindex(columns=tickers).values
    volume_v = volume.reindex(columns=tickers).values

    cash, positions, pv_list, trade_log = float(capital_level), {}, [float(capital_level)], []

    for date_i in range(start_idx, len(prices.index)):
        date = prices.index[date_i]
        hr_raw = hedge_ret_v[date_i]
        hr = float(hr_raw) if not np.isnan(hr_raw) else 0.0
        cash += cash * rf_daily

        # ── Stäng positioner (stop, mal, ELLER max hålltid) ──
        row_volume_today = volume_v[date_i]
        to_close = []
        for t, pos in positions.items():
            ti = tidx[t]
            cp = float(prices_v[date_i, ti])
            cz = float(zscore_v[date_i, ti])
            if np.isnan(cp):
                continue
            # Volym=0 (upptackt 2026-07-29): flera tickers har enstaka
            # dagar med korrupt pris OCH noll handel samma dag (t.ex.
            # IARED gav 8749x "vinst" via en falsk target-utgang driven av
            # en sadan dag). Utan riktig handel gar dagens pris inte att
            # lita pa for varken stop/target/tid - hoppa over hela dagen
            # for just den har positionen, kolla igen nasta dag.
            vt = row_volume_today[ti]
            if np.isnan(vt) or vt <= 0:
                continue
            hit_stop = cp <= pos["stop"]
            hit_target = not np.isnan(cz) and abs(cz) < TARGET_Z
            hit_time = (date_i - pos["entry_day_i"]) >= MAX_HOLDING_DAYS
            if hit_stop or hit_target or hit_time:
                # Sakerhetsklipp (upptackt 2026-07-29): tickers som JET
                # (936x) och PCD (99x) gav fysiskt omojliga vinster pa en
                # 20-dagars hålltid - sannolikt oadjusterade omvanda
                # aktiesplittar i datacachen, inte verkliga utfall. Ett
                # enskilt smabolag kan i extremfall verkligen dubblas eller
                # mer pa kort tid, men flera hundra ganger ar alltid ett
                # datafel. Klipp prisforhallandet, inte bara den loggade
                # returen, sa proceeds/cash forblir konsistenta.
                price_ratio = np.clip(cp / pos["entry"], 0.05, 4.0)
                gross_ret = price_ratio - 1
                proceeds = pos["size"] * price_ratio
                exit_spread = spread_v[date_i, ti]
                if not np.isnan(exit_spread):
                    proceeds -= proceeds * (exit_spread / 2)
                cash += proceeds
                net_ret = proceeds / pos["size"] - 1
                to_close.append(t)
                exit_type = "stop" if hit_stop else ("target" if hit_target else "time")
                trade_log.append({"date": date, "ticker": t, "ret": net_ret, "gross_ret": gross_ret,
                                   "type": exit_type, "cost": pos["size"]})
        for t in to_close:
            del positions[t]

        # ── Öppna nya positioner (kapacitetsspärrad storlek) ──
        if len(positions) < MAX_POS:
            cands = []
            row_state = trade_state_vals[date_i]
            row_prices = prices_v[date_i]
            row_z = zscore_v[date_i]
            row_volume = volume_v[date_i]
            # row_prices > 0 kravs har (upptackt 2026-07-29): nagra tickers
            # har enstaka rader med pris exakt 0.0 i cachen (dataartefakt,
            # inte NaN) - utan detta filter kan effective_entry bli 0 och
            # senare ge ZeroDivisionError vid utgang.
            # row_volume > 0 kravs har (upptackt 2026-07-29, konkret fall:
            # ticker MDVL fick close=12.39 den 2014-04-16 med VOLYM=0,
            # mellan tva dagar runt ~7000-7500 - ett rent datafel, inte en
            # verklig prisrorelse. En dag utan handel gar inte att handla i
            # verkligheten heller - rimligt filter oavsett detta specifika
            # fall, gav en falsk 594x-"vinst" i traden innan detta lades till.
            buy_signal = (row_state == 1) & (row_z < -TRADE_Z_THRESH) & \
                         ~np.isnan(row_prices) & (row_prices > 0) & \
                         ~np.isnan(row_z) & (row_volume > 0)
            for ti in np.flatnonzero(buy_signal):
                t = tickers[ti]
                if t in positions:
                    continue
                cands.append((abs(row_z[ti]), t, float(row_prices[ti])))
            cands.sort(reverse=True)
            slots = max(0, MAX_POS - len(positions))
            for _, t, cp in cands[:slots]:
                ti = tidx[t]
                desired = FIXED_FRAC * cash
                adv = dollar_volume_v[date_i, ti]
                cap = adv * MAX_ADV_PCT if not np.isnan(adv) else desired
                sz = min(desired, cap)
                if sz < capital_level * 0.0001:
                    continue
                entry_spread = spread_v[date_i, ti]
                if not np.isnan(entry_spread):
                    effective_entry = cp * (1 + entry_spread / 2)
                else:
                    effective_entry = cp
                cash -= sz
                positions[t] = {"entry": effective_entry, "size": sz,
                                "stop": effective_entry * (1 - STOP_LOSS),
                                "entry_day_i": date_i}

        # ── Portföljvärde (beta-neutral hedge mot SPY + borrow-kostnad) ──
        # Samma sakerhetsklipp som vid stangning (upptackt 2026-07-29,
        # se kommentaren dar) appliceras har pa MARKNADSVARDERINGEN av
        # fortfarande OPPNA positioner - en korrupt/oadjusterad-split-pris
        # en enda dag kan annars fa hela portfoljvardet att spika (konkret
        # exempel: 2012-12-26 gav en dagsrorelse pa 2449% innan detta
        # lades till, fran en oppen positions dagsvarde, inte en trade).
        long_beta = 0.0
        long_val = 0.0
        for t, pos in positions.items():
            ti = tidx[t]
            cp = float(prices_v[date_i, ti])
            vt = volume_v[date_i, ti]
            if np.isnan(cp) or np.isnan(vt) or vt <= 0:
                cp = pos["entry"]  # ingen handel/korrupt pris denna dag - behall senast kanda kostnadsvarde
            price_ratio = np.clip(cp / pos["entry"], 0.05, 4.0)
            long_beta += pos["size"] * price_ratio * float(beta_v[date_i, ti])
            long_val += pos["size"] * price_ratio
        daily_borrow = borrow_cost(position_value=abs(long_beta), holding_days=1, annual_rate=BORROW_ANNUAL_RATE)
        hedge_pnl = -long_beta * hr - long_beta * (RF_ANNUAL / 2 / 252) - daily_borrow

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
    Kriteriets punkt 3. Anvander den FAKTISKA positionskostnaden ("cost")
    for den basta traden, inte en uppskattning fran capital_level*FIXED_FRAC
    (samma bugg som hittades 2026-07-29 i HYP-008/009/011 - se
    strategies/HYP-012/backtest.py for full forklaring. Fixad har direkt
    istallet for att atenskapas.)
    """
    if len(tl) == 0:
        return {"sharpe_excl_best": None, "calmar_excl_best": None}
    best_idx = tl["ret"].idxmax()
    best_trade = tl.loc[best_idx]
    best_date = best_trade["date"]
    best_dollar_pnl = best_trade["ret"] * best_trade["cost"]
    pv_adj = pv.copy()
    pv_adj.loc[pv_adj.index >= best_date] -= best_dollar_pnl
    return {"sharpe_excl_best": sharpe(pv_adj), "calmar_excl_best": calmar(pv_adj)}


# ════════════════════════════════════════════════════════════
#  KÖRNING
# ════════════════════════════════════════════════════════════
def run_for_capital_level(capital_level, close, hedge, zscore_df, beta_df, spread_df, volume):
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

    print("Sanerar prisdata (nollpriser/orimliga engångsrörelser, se strategies/common/data_hygiene.py)...")
    close, high, low = clean_price_matrix(close, high, low, volume=volume)

    print("Beräknar reversal-z-score (enskild aktie, vektoriserad)...")
    zscore_df = compute_own_zscore(close, RET_WINDOW, ZSCORE_WINDOW)

    print("Estimerar beta (görs en gång)...")
    beta_df = compute_beta(close, hedge, BETA_WINDOW)

    print("Beräknar Corwin-Schultz-spread (görs en gång)...\n")
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
