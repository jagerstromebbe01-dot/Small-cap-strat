"""
HYP-020: PEAD (Post-Earnings-Announcement Drift) via SUE pa small-cap-
universumet.

Se research/hypothesis_registry/HYP-020-pead-via-sue.yaml for det lasta
kriteriet, och research/strategy_specs/HYP-020-spec.md for den fulla
specen.

Aterananvander HYP-015:s motor (universum, friktion, SPY-hedge,
kapacitetsspärr, de tre motorfixarna) - manatlig ombalansering (INTE
kvartalsvis - PEAD ar en snabbare-roterande signal an lagvol/storlek,
samma konvention som HYP-012:s momentum) - enda metodikskillnaden ar
signalen: SUE (Standardized Unexpected Earnings) i stallet for
idiosynkratisk volatilitet.

SUE = (EPS denna kvartal - EPS samma kvartal foregaende ar), dividerat
med std av de senaste 8 kvartalens motsvarande overraskning
(Foster, Olsen & Shevlin 1984 - "saisongrandom walk"-varianten av SUE,
som INTE kraver analytikerkonsensus, till skillnad fran den andra
klassiska varianten). Anvander URSPRUNGLIGA rapportens filingsdatum
(inte periodens slutdatum) for att undvika framatblick - signalen blir
"kand" av marknaden forst pa filingsdatumet.

Datakalla: data/fetch_eps_history.py (SEC EDGAR companyfacts-API,
per-CIK, ateranvander redan byggd ticker->CIK-mappning fran
data/cache/smallcap_classification.jsonl) - cachad i
data/cache/eps_by_ticker.jsonl.

Motorfixar (delade med HYP-015/016/017/018/019): snappade
ombalanseringsdatum, adjusted_close genomgaende, flag_implausible_liquidity().
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
EPS_FILE = CACHE_DIR / "eps_by_ticker.jsonl"
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

MIN_HISTORY = 130   # samma buffert som HYP-015/019 - styrs av BETA_WINDOW (126)

SUE_MIN_TRAILING_QUARTERS = 4   # minst 4 tidigare overraskningar innan std-avvikelsen litas pa
SUE_STD_WINDOW = 8              # rullande antal kvartal for standardiseringens std-avvikelse
SUE_FRESHNESS_DAYS = 63         # ~90 kalenderdagar / ~3 manader i handelsdagar - hur "farskt" ett SUE-varde far vara

DECILE_FRACTION = 0.10    # HOGSTA SUE-decilen (positiv overraskning) - motsatt sortering mot HYP-014/015/019
REBAL_FREQ = "ME"         # manatlig - PEAD ar en snabbare-roterande signal, samma konvention som HYP-012:s momentum
RF_ANNUAL = 0.02
BETA_WINDOW = 126

BORROW_ANNUAL_RATE = 0.03
MAX_ADV_PCT = 0.10
ADV_WINDOW = 20

MAX_MARKET_CAP = 2_000_000_000  # universumets ovre marknadsvardesgrans - anvands av liquiditetsfiltret

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
    """Laddar bade ra close (for exekvering/positionsvarde) och
    adjusted_close (for alla avkastnings-/signalberakningar) - se
    modulens docstring, motorfix 2."""
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
    """SPY - adjusted_close genomgaende (utdelningsjusterad), eftersom
    hedgen bara anvands for avkastningsberakningar (hedge_ret), aldrig
    for ett eget positionsvarde i dollar."""
    path = OHLCV_DIR / f"{HEDGE}.csv"
    df = pd.read_csv(path, usecols=["date", "adjusted_close"], parse_dates=["date"])
    df = df.drop_duplicates(subset="date", keep="last").set_index("date").sort_index()
    date_index = trading_calendar(start, end)
    return df["adjusted_close"].reindex(date_index)


# ════════════════════════════════════════════════════════════
#  BETA (identisk med HYP-014, MED sakerhetsspärren mot degenererad beta)
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
    beta_arr = np.clip(beta_arr, -5.0, 5.0)

    return pd.DataFrame(beta_arr, index=prices.index, columns=prices.columns)


def compute_spread_matrix(high, low):
    spread = {}
    for t in high.columns:
        spread[t] = corwin_schultz_spread(high[t].values, low[t].values)
    return pd.DataFrame(spread, index=high.index)


# ════════════════════════════════════════════════════════════
#  SIGNAL: SUE (ny - ersatter idiosynkratisk-vol-signalen)
# ════════════════════════════════════════════════════════════
def load_sue_signal(trading_calendar_index):
    """
    Laddar EPS-historik (data/cache/eps_by_ticker.jsonl, se
    data/fetch_eps_history.py), beraknar SUE per ticker per kvartal, och
    bygger en daglig, framatfylld DataFrame (index=handelsdag,
    columns=ticker, values=standardiserat SUE).

    Per ticker:
      1. Gruppera rapporterade observationer per (fy, fp) - ta den
         TIDIGASTE filed-datumet per grupp (ursprunglig rapport, inte
         senare omrakningar/andringar - anvander en senare/annan
         rapports varde vore framatblick).
      2. Matcha "samma kvartal foregaende ar" via (fy-1, fp) - INTE ett
         kalenderdatum-offset, sa det fungerar aven for bolag med
         icke-kalenderar rakenskapsar.
      3. SUE_raw = EPS_t - EPS_(t-4). Standardisera med std av de
         SUE_STD_WINDOW senaste raa overraskningarna (kraver minst
         SUE_MIN_TRAILING_QUARTERS observationer forst).
      4. Signalen "blir kand" forst pa filingsdatumet - snappas till
         FORSTA FAKTISKA HANDELSDAG PA ELLER EFTER filingsdatumet
         (INTE narmaste FOREGAENDE, till skillnad fran
         snap_rebalance_dates - en handelse kan bara paverka framtiden,
         aldrig ett tidigare datum).
    """
    sue_by_ticker = {}
    cal = trading_calendar_index.values

    with EPS_FILE.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            ticker = row["ticker"]
            entries = row.get("entries", [])
            if not entries:
                continue

            # Nagra fa XBRL-poster saknar fy/fp helt (ovanliga tidiga
            # inlamningar) - kan inte matchas mot "samma kvartal
            # foregaende ar" utan bada faltet, hoppas over har.
            entries = [e for e in entries if e.get("fy") is not None and e.get("fp")]
            if not entries:
                continue

            by_period = {}
            for e in entries:
                key = (e["fy"], e["fp"])
                if key not in by_period or e["filed"] < by_period[key]["filed"]:
                    by_period[key] = e

            quarters = sorted(by_period.values(), key=lambda e: e["end"])
            if len(quarters) < SUE_MIN_TRAILING_QUARTERS + 5:
                continue

            by_fy_fp = {(e["fy"], e["fp"]): e for e in quarters}
            raw_surprises = []
            for e in quarters:
                prior = by_fy_fp.get((e["fy"] - 1, e["fp"]))
                if prior is None:
                    continue
                raw_surprises.append({"end": e["end"], "filed": e["filed"], "surprise": e["val"] - prior["val"]})

            if len(raw_surprises) < SUE_MIN_TRAILING_QUARTERS + 1:
                continue

            raw_surprises.sort(key=lambda x: x["end"])
            surprise_vals = [s["surprise"] for s in raw_surprises]

            sue_points = {}
            for i in range(SUE_MIN_TRAILING_QUARTERS, len(raw_surprises)):
                trailing = surprise_vals[max(0, i - SUE_STD_WINDOW):i]
                std = np.std(trailing, ddof=1) if len(trailing) >= 2 else np.nan
                if not std or np.isnan(std) or std == 0:
                    continue
                sue_points[raw_surprises[i]["filed"]] = surprise_vals[i] / std

            if not sue_points:
                continue

            filed_dates = pd.to_datetime(list(sue_points.keys())).values
            snapped_idx = np.searchsorted(cal, filed_dates, side="left")
            valid = snapped_idx < len(cal)
            if not valid.any():
                continue
            snapped_dates = cal[snapped_idx[valid]]
            values = np.array(list(sue_points.values()))[valid]

            s = pd.Series(values, index=pd.DatetimeIndex(snapped_dates))
            s = s.sort_index()
            s = s[~s.index.duplicated(keep="last")]
            sue_by_ticker[ticker] = s

    print(f"    {len(sue_by_ticker)} tickers med minst ett anvandbart SUE-varde.")

    sue_df = pd.DataFrame(sue_by_ticker)
    sue_df = sue_df.reindex(trading_calendar_index)
    sue_df = sue_df.ffill(limit=SUE_FRESHNESS_DAYS)
    return sue_df.astype("float32")


# ════════════════════════════════════════════════════════════
#  BACKTEST-MOTOR (samma struktur som HYP-014, MED motorfix 1: snappade
#  ombalanseringsdatum i stallet for ra kalender-etikettsmatchning)
# ════════════════════════════════════════════════════════════
def run_backtest(close, close_adj, hedge, sue_df, beta_df, spread_df, volume,
                 universe_by_month, capital_level: float):
    """
    VIKTIGT (motorfix 2, korrigerad 2026-07-29 efter att HYP-015:s forsta
    korning fortfarande visade en split-artefakt - ticker "COL", +1362% i
    en enda trade): adjusted_close racker INTE bara for signalen/rankningen
    - POSITIONSVARDERING (aktieantal, entry-/exitpris, P&L) maste OCKSA
    anvanda adjusted_close, annars racknas aktieantalet fran ett rått
    ingangspris och varderas senare mot ett rått utgangspris over en
    riktig aktiesplit (COL 10x den 2016-06-01, bekraftat i radata) - exakt
    samma typ av falsk vinst som ESSA/ARDMQ, fast via en annan kodvag an
    den som redan fixades. `close` (ra) anvands harefter ENDAST for
    dollar_volume/kapacitetsspärren (ADV ska spegla verklig, handlad
    likviditet till verkligt kvoterat pris - inte en teoretisk justerad
    likviditet).
    """
    tickers = list(close.columns)
    tidx = {t: i for i, t in enumerate(tickers)}
    hedge_ret = hedge.pct_change()
    dollar_volume = (close * volume).rolling(ADV_WINDOW).mean()

    calendar_dates = close.resample(REBAL_FREQ).last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[MIN_HISTORY]) & (calendar_dates <= close.index[-1])]
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
            # VIKTIGT (motorfix 1): universum-uppslagningen anvander den
            # URSPRUNGLIGA kalenderetiketten (t.ex. "2023-12-31"), INTE
            # exekveringsdatumet (t.ex. "2023-12-29") - universumfilen ar
            # byggd med kalender-manadsslut som nycklar.
            month_key = rebal_map[date].strftime("%Y-%m-%d")
            eligible = [t for t in universe_by_month.get(month_key, []) if t in tidx]
            sue_today = sue_df.loc[date]
            scores = []
            for t in eligible:
                v = sue_today.get(t, np.nan)  # sue_df har bara kolumner for tickers med anvandbar SUE-data, inte hela universumet
                cp = prices_v[date_i, tidx[t]]
                if not np.isnan(v) and not np.isnan(cp) and cp > 0:
                    scores.append((v, t, cp))
            scores.sort(reverse=True)  # HOGST SUE (mest positiva overraskning) forst
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
#  METRICS (identiska definitioner mot HYP-014)
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
#  KÖRNING
# ════════════════════════════════════════════════════════════
def run_for_capital_level(capital_level, close, close_adj, hedge, sue_df, beta_df, spread_df, volume, universe_by_month):
    print(f"    Kör backtest (kapitalnivå {capital_level:,.0f})...")
    pv, tl = run_backtest(close, close_adj, hedge, sue_df, beta_df, spread_df, volume, universe_by_month, capital_level)

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

    print("Laddar prismatriser (close/adjusted_close/high/low/volume) från cache...")
    close, close_adj, high, low, volume = load_price_matrices(tickers, FULL_START, FULL_END)
    hedge = load_hedge(FULL_START, FULL_END)
    print(f"  Prismatris: {close.shape}\n")

    print("Sanerar prisdata (nollpriser/orimliga engångsrörelser/volym=0)...")
    close, high, low = clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())  # samma NaN-monster som ra close efter clean_price_matrix

    print("Flaggar leverantors-datafel (implausibel likviditet relativt marknadsvardesbandet)...")
    implausible = flag_implausible_liquidity(close, volume, max_market_cap=MAX_MARKET_CAP,
                                              window=ADV_WINDOW, multiplier=1.0)
    close = close.mask(implausible)
    close_adj = close_adj.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)
    print(f"  {int(implausible.values.sum())} ticker-dagar maskade.\n")

    print("Estimerar beta (pa adjusted_close, görs en gång)...")
    beta_df = compute_beta(close_adj, hedge, BETA_WINDOW)

    print("Laddar EPS-historik och beräknar SUE-signal (se data/fetch_eps_history.py)...")
    sue_df = load_sue_signal(close.index)

    print("Beräknar Corwin-Schultz-spread (pa ra high/low, görs en gång)...\n")
    spread_df = compute_spread_matrix(high, low)

    all_results = []
    for level in levels:
        print(f"--- Kapitalnivå: ${level:,.0f} ---")
        result = run_for_capital_level(level, close, close_adj, hedge, sue_df, beta_df, spread_df, volume, universe_by_month)
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
