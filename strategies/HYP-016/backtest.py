"""
HYP-016: Volatilitets-hanterad cross-sectional momentum (12-1 manader) pa
small-cap-universumet (uppfoljare till HYP-012, som var FAILED pga
katastrofal maxdrawdown -72% till -78% - inte avsaknad av genomsnittlig
edge, ra Sharpe var faktiskt svagt positiv vid 100k/1M).

Se research/hypothesis_registry/HYP-016-vol-hanterad-momentum.yaml for
det lasta kriteriet, och research/strategy_specs/HYP-016-spec.md for den
fulla specen.

Aterananvander HYP-012:s motor rakt av (universum, momentum-signal
12-1-manader, friktion, SPY-hedge, kapacitetsspärr, manatlig
ombalansering) - enda metodikskillnaden ar VOLATILITETS-SKALNING av
bruttoexponeringen (Barroso & Santa-Clara 2015), riktad direkt mot den
dokumenterade kraschrisken (Daniel & Moskowitz 2016).

TVA-PASS-DESIGN (for att undvika en feedback-loop dar skalningen paverkar
sitt eget vol-estimat): Pass 1 kor exakt HYP-012:s ursprungliga,
oskalade motor (exposure_scale=1.0 hela tiden) for att fa en "raw"
portfoljavkastningsserie. Pass 2 beraknar en skalningsfaktor fran Pass
1:s EGNA rullande 126-dagars realiserade volatilitet (annualiserad,
shiftad en dag sa bara information kand FORE ombalanseringsdatumet
anvands - ingen framatblick), och kor SEDAN motorn en gang till med den
skalningen applicerad pa nya kop. Bada passen anvander samma
verkliga friktion/hedge/kapacitetsspärr - bara bruttoexponeringen skiljer.

DESSUTOM (lockat som en del av kriteriet, delat med HYP-015, se
granskningen 2026-07-29 som hittade dessa i HYP-012/014):
  1. Ombalanseringsdatum snappas till narmaste faktiska handelsdag
     (strategies/common/rebalancing.py) - HYP-012:s kod tystade ~29% av
     manatliga ombalanseringar genom att matcha kalender-manadsslut
     direkt mot handelskalendern.
  2. adjusted_close anvands for momentumberakningen - INTE ra close, som
     tidigare gav en falsk +3923%-manadstrade (ticker ARDMQ, en icke
     split-justerad 1-for-40 omvand split som dominerade hela HYP-012:s
     rapporterade Sharpe). Ra close anvands fortfarande for
     positionsvarde/exekvering.
  3. flag_implausible_liquidity() maskar ticker-dagar dar leverantors-
     datafel (tickerkollisioner av ESSA-typ) ger dollarvolym som ar
     ekonomiskt omojlig for universumets marknadsvardesband.
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

# ════════════════════════════════════════════════════════════
#  PARAMETRAR
# ════════════════════════════════════════════════════════════
FULL_START = "2010-01-01"
FULL_END = "2024-12-31"

MOM_LOOKBACK_DAYS = 252
MOM_SKIP_DAYS = 21
MOM_MIN_HISTORY = 273

DECILE_FRACTION = 0.10
RF_ANNUAL = 0.02
BETA_WINDOW = 126

BORROW_ANNUAL_RATE = 0.03
MAX_ADV_PCT = 0.10
ADV_WINDOW = 20

MAX_MARKET_CAP = 2_000_000_000

# Volatilitets-skalning (Barroso & Santa-Clara 2015) - exakt sa som lockat
# i pass_fail_criterion, inga fria parametrar.
VOL_SCALE_WINDOW = 126        # ~6 manader, dagliga avkastningar
TARGET_VOL_ANNUAL = 0.20      # FAST, INTE skattad fran denna backtests eget fullsampel
SCALE_MIN = 0.2
SCALE_MAX = 2.0

HEDGE = "SPY"


# ════════════════════════════════════════════════════════════
#  DATA
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
#  BETA (identisk med HYP-012/014)
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
#  MOMENTUM-SIGNAL (oforandrad mot HYP-012, MEN pa adjusted_close)
# ════════════════════════════════════════════════════════════
def compute_momentum(close_adj):
    shifted_skip = close_adj.shift(MOM_SKIP_DAYS)
    shifted_lookback = close_adj.shift(MOM_LOOKBACK_DAYS)
    return shifted_skip / shifted_lookback - 1.0


# ════════════════════════════════════════════════════════════
#  VOLATILITETS-SKALNING (Barroso & Santa-Clara 2015) - Pass 2 anvander
#  Pass 1:s EGNA dagliga avkastningar, ingen framatblick (shift(1))
# ════════════════════════════════════════════════════════════
def compute_exposure_scale(pv_base):
    daily_ret = pv_base.pct_change()
    realized_vol_annual = daily_ret.rolling(VOL_SCALE_WINDOW).std() * np.sqrt(252)
    scale = (TARGET_VOL_ANNUAL / realized_vol_annual).clip(lower=SCALE_MIN, upper=SCALE_MAX)
    return scale.shift(1)  # anvand bara vol kand FORE ombalanseringsdatumet


# ════════════════════════════════════════════════════════════
#  BACKTEST-MOTOR: manatlig ombalansering, lika viktad toppdecil,
#  MED snappade ombalanseringsdatum (motorfix 1) och valfri
#  exponerings-skalning pa nya kop (exposure_scale=None => alltid 1.0,
#  dvs identisk med HYP-012:s ursprungliga, oskalade motor - detta ar
#  Pass 1)
# ════════════════════════════════════════════════════════════
def run_backtest(close, close_adj, hedge, mom_df, beta_df, spread_df, volume,
                 universe_by_month, capital_level: float, exposure_scale: pd.Series = None):
    """
    VIKTIGT (motorfix 2, korrigerad 2026-07-29 efter att forsta korningen
    fortfarande visade en split-artefakt i HYP-015 - ticker "COL", +1362%
    i en enda trade): adjusted_close racker INTE bara for signalen -
    POSITIONSVARDERING (aktieantal, entry-/exitpris, P&L) maste OCKSA
    anvanda adjusted_close, annars racknas aktieantalet fran ett rått
    ingangspris och varderas senare mot ett rått utgangspris over en
    riktig aktiesplit (samma monster som ARDMQ, fast dar redan fixat via
    signalen - detta ar den kvarvarande halvan av samma bugg). `close`
    (ra) anvands harefter ENDAST for dollar_volume/kapacitetsspärren (ADV
    ska spegla verklig, handlad likviditet till verkligt kvoterat pris).
    """
    tickers = list(close.columns)
    tidx = {t: i for i, t in enumerate(tickers)}
    hedge_ret = hedge.pct_change()
    dollar_volume = (close * volume).rolling(ADV_WINDOW).mean()

    calendar_dates = close.resample("ME").last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[MOM_MIN_HISTORY]) & (calendar_dates <= close.index[-1])]
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
            eligible = [t for t in universe_by_month.get(month_key, []) if t in tidx]
            mom_today = mom_df.loc[date]
            scores = []
            for t in eligible:
                m = mom_today[t]
                cp = prices_v[date_i, tidx[t]]
                if not np.isnan(m) and not np.isnan(cp) and cp > 0:
                    scores.append((m, t, cp))
            scores.sort(reverse=True)
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

            # ── Kop nya namn i toppdecilen - bruttoexponeringen skalas
            # har (exposure_scale), resten av logiken oforandrad mot
            # HYP-012. Namn som redan hölls fortsatter oskalade (samma
            # forenkling som HYP-012 redan gor - ingen manatlig
            # omviktning till nytt malbelopp for befintliga positioner).
            new_names = [t for t in target_tickers if t not in holdings]
            if new_names:
                scale = 1.0
                if exposure_scale is not None:
                    raw_scale = exposure_scale.get(date, np.nan)
                    if not (isinstance(raw_scale, float) and np.isnan(raw_scale)):
                        scale = float(raw_scale)
                target_dollar_per_name = (cash * scale) / len(new_names) if len(new_names) > 0 else 0.0
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
#  METRICS (identiska definitioner mot HYP-012)
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
#  KÖRNING (tva pass per kapitalniva - se moduldocstring)
# ════════════════════════════════════════════════════════════
def run_for_capital_level(capital_level, close, close_adj, hedge, mom_df, beta_df, spread_df, volume, universe_by_month):
    print(f"    Pass 1/2 (oskalad baslinje, kapitalnivå {capital_level:,.0f})...")
    pv_base, _ = run_backtest(close, close_adj, hedge, mom_df, beta_df, spread_df, volume, universe_by_month,
                               capital_level, exposure_scale=None)

    exposure_scale = compute_exposure_scale(pv_base)

    print(f"    Pass 2/2 (vol-skalad, kapitalnivå {capital_level:,.0f})...")
    pv, tl = run_backtest(close, close_adj, hedge, mom_df, beta_df, spread_df, volume, universe_by_month,
                          capital_level, exposure_scale=exposure_scale)

    result = {
        "capital_level": capital_level,
        "cagr": cagr(pv),
        "sharpe": sharpe(pv),
        "calmar": calmar(pv),
        "max_drawdown": max_drawdown(pv),
        "trade_stats": trade_stats(tl),
        "baseline_cagr": cagr(pv_base),
        "baseline_sharpe": sharpe(pv_base),
        "baseline_max_drawdown": max_drawdown(pv_base),
        "mean_exposure_scale": float(exposure_scale.dropna().mean()) if exposure_scale.notna().any() else None,
    }
    result.update(best_trade_excluded_metrics(pv, tl, capital_level))

    RESULTS_DIR.mkdir(exist_ok=True)
    pv.to_csv(RESULTS_DIR / f"portfolio_value_{int(capital_level)}.csv", header=["portfolio_value"])
    pv_base.to_csv(RESULTS_DIR / f"portfolio_value_baseline_{int(capital_level)}.csv", header=["portfolio_value"])
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

    print("Laddar prismatriser (close/adjusted_close/high/low/volume) från cache...")
    close, close_adj, high, low, volume = load_price_matrices(tickers, FULL_START, FULL_END)
    hedge = load_hedge(FULL_START, FULL_END)
    print(f"  Prismatris: {close.shape}\n")

    print("Sanerar prisdata (nollpriser/orimliga engångsrörelser/volym=0)...")
    close, high, low = clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())

    print("Flaggar leverantors-datafel (implausibel likviditet relativt marknadsvardesbandet)...")
    implausible = flag_implausible_liquidity(close, volume, max_market_cap=MAX_MARKET_CAP,
                                              window=ADV_WINDOW, multiplier=1.0)
    close = close.mask(implausible)
    close_adj = close_adj.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)
    print(f"  {int(implausible.values.sum())} ticker-dagar maskade.\n")

    print("Beräknar momentum-signal (12-1 manader, pa adjusted_close, vektoriserad)...")
    mom_df = compute_momentum(close_adj)

    print("Estimerar beta (pa adjusted_close, görs en gång)...")
    beta_df = compute_beta(close_adj, hedge, BETA_WINDOW)

    print("Beräknar Corwin-Schultz-spread (pa ra high/low, görs en gång)...\n")
    spread_df = compute_spread_matrix(high, low)

    all_results = []
    for level in levels:
        print(f"--- Kapitalnivå: ${level:,.0f} ---")
        result = run_for_capital_level(level, close, close_adj, hedge, mom_df, beta_df, spread_df, volume, universe_by_month)
        all_results.append(result)
        print(f"    CAGR={result['cagr']:+.2%}  Sharpe={result['sharpe']:.2f}  "
              f"Calmar={result['calmar']:.2f}  MaxDD={result['max_drawdown']:.1%}  "
              f"(baslinje utan skalning: Sharpe={result['baseline_sharpe']:.2f}, MaxDD={result['baseline_max_drawdown']:.1%})  "
              f"Trades={result['trade_stats']['n']}\n")

    RESULTS_DIR.mkdir(exist_ok=True)
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
