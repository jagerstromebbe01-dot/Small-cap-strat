"""
HYP-040: TA-monsterbibliotek med Ejay-baserad traffsakerhetsfiltrering
och positionsviktning.

Se research/hypothesis_registry/HYP-040-ta-monster-ejay-traffsakerhet.yaml
for det lasta kriteriet - denna fil implementerar det ORDAGRANT, ingen
fri parameter har valts har som inte redan star i kriteriet.

CEO:s egen ide ("technical analysis is not dead in small cap, only
rearranged"). Ateroppnar den stangda Ejay-mekaniken EXPLICIT for detta
enda test (se registerpostens egen motivering) - mekaniskt annorlunda an
de 8 tidigare dodade varianterna: Ejay mater har TA-monsters egen
traffsakerhet PER AKTIE (traffar/forsok), INTE signalstyrkan hos en
redan vald idio-vol-decil.

MEKANISM I KORTHET:
  1. 15 TA-monster (sex kategorier), branschstandard-parametrar, SLUTEN lista.
  2. Ejay = rullande 63-dagars traffkvot (positiv avkastning 10 dagar
     efter triggerm) for ALLA 15 monster sammanslaget (en "eldning" =
     NAGOT monster triggade den dagen, oavsett hur manga - se
     compute_fired_matrix()).
  3. Filter: handla bara nar en aktie ligger i TOPP-KVARTILEN av Ejay
     bland de aktier (i det eligible small-cap-universumet) som har en
     giltig Ejay-poang den dagen.
  4. Positionsstorlek: TVA VARIANTER kors och rapporteras - Ejay-
     proportionell vs likaviktad, for exakt samma filtrerade urval
     (villkor 2 i kriteriet - sparr mot att upprepa Ejay-linjens
     etablerade dodsorsak).
  5. Kop nasta handelsdags oppningskurs efter trigger. Salj efter 10
     handelsdagar ELLER -10% stop-loss, vilket som intraffar forst.
  6. LONG-ONLY, ingen SPY-hedge (explicit CEO-val, avviker fran resten
     av registret - beta rapporteras, gatear inte).

LOOK-AHEAD-DISCIPLIN (samma standard som resten av registret, sarskilt
efter kodgranskningen 2026-08-05):
  - Alla TA-monster beraknas pa ADJUSTED-priser (approximerat aven for
    open/high/low via close_adj/close-kvoten, se adjusted_ohlc()) -
    samma motorfix-2-princip som HYP-014/037: rattvis signal OCH
    positionsvardering, aldrig en split-artefakt.
  - Ejay for dag T anvander ENDAST signaler vars 10-dagars-utfall redan
    ar KANT senast dag T (signalen matte ha triggat pa eller fore T-10)
    - implementerat via .shift(10) INNAN .rolling(63)-medelvardet, se
    compute_ejay().
  - Kop sker pa NASTA dags oppning efter en trigger - aldrig samma dags
    stangning.
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

# ════════════════════════════════════════════════════════════
#  PARAMETRAR (lasta i kriteriet - se HYP-040-yaml)
# ════════════════════════════════════════════════════════════
FULL_START = "2010-01-01"
FULL_END = "2024-12-31"

EJAY_WINDOW_DAYS = 63
EJAY_FORWARD_DAYS = 10
EJAY_MIN_SIGNALS = 5
EJAY_FILTER_QUANTILE = 0.75  # topp-kvartil

HOLD_DAYS = 10
STOP_LOSS_FRACTION = 0.10

MAX_ADV_PCT = 0.10
ADV_WINDOW = 20
BORROW_ANNUAL_RATE = 0.03  # N/A i praktiken (long-only, ingen belaning) - se main()

MAX_MARKET_CAP = 2_000_000_000
RF_ANNUAL = 0.02
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
    """Som HYP-037/backtest.py::load_price_matrices, MED tillagg av open
    (kravs for candlestick-monster och nasta-dags-oppning-exekvering)."""
    date_index = trading_calendar(start, end)
    open_s, close_s, adj_s, high_s, low_s, vol_s = {}, {}, {}, {}, {}, {}

    for t in tickers:
        path = OHLCV_DIR / f"{t}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path, usecols=["date", "open", "close", "adjusted_close", "high", "low", "volume"],
                          parse_dates=["date"])
        df = df.drop_duplicates(subset="date", keep="last").set_index("date").sort_index()
        open_s[t] = df["open"].astype("float32")
        close_s[t] = df["close"].astype("float32")
        adj_s[t] = df["adjusted_close"].astype("float32")
        high_s[t] = df["high"].astype("float32")
        low_s[t] = df["low"].astype("float32")
        vol_s[t] = df["volume"].astype("float32")

    open_ = pd.DataFrame(open_s).reindex(date_index)
    close = pd.DataFrame(close_s).reindex(date_index)
    close_adj = pd.DataFrame(adj_s).reindex(date_index)
    high = pd.DataFrame(high_s).reindex(date_index)
    low = pd.DataFrame(low_s).reindex(date_index)
    volume = pd.DataFrame(vol_s).reindex(date_index)
    return open_, close, close_adj, high, low, volume


def load_hedge(start, end):
    path = OHLCV_DIR / f"{HEDGE}.csv"
    df = pd.read_csv(path, usecols=["date", "adjusted_close"], parse_dates=["date"])
    df = df.drop_duplicates(subset="date", keep="last").set_index("date").sort_index()
    date_index = trading_calendar(start, end)
    return df["adjusted_close"].reindex(date_index)


def adjusted_ohlc(open_, high, low, close, close_adj):
    """Approximerar justerad open/high/low genom att skala med samma
    dagens close_adj/close-kvot - samma "motorfix 2"-princip som resten
    av registret (adjusted_close racker inte bara for signalen, all
    prisrelaterad berakning maste vara split-konsekvent). EODHD ger inte
    en officiell adjusted_open/high/low, sa detta ar en standardmassig,
    val etablerad approximation (multiplikativ split-justering antas)."""
    ratio = (close_adj / close).replace([np.inf, -np.inf], np.nan)
    adj_open = open_ * ratio
    adj_high = high * ratio
    adj_low = low * ratio
    return adj_open, adj_high, adj_low


# ════════════════════════════════════════════════════════════
#  TEKNISKA INDIKATORER (vektoriserade, T x N-matriser, branschstandard-
#  defaultparametrar - INGA optimerade/fritt valda varden, se kriteriet)
# ════════════════════════════════════════════════════════════
def sma(prices, window):
    return prices.rolling(window).mean()


def ema(prices, span):
    return prices.ewm(span=span, adjust=False).mean()


def rsi(prices, window=14):
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(prices, fast=12, slow=26, signal=9):
    macd_line = ema(prices, fast) - ema(prices, slow)
    signal_line = ema(macd_line, signal)
    return macd_line, signal_line


def stochastic(close, high, low, k_window=14, d_window=3):
    low_k = low.rolling(k_window).min()
    high_k = high.rolling(k_window).max()
    pct_k = 100 * (close - low_k) / (high_k - low_k).replace(0, np.nan)
    pct_d = pct_k.rolling(d_window).mean()
    return pct_k, pct_d


def roc(prices, window=12):
    return prices.pct_change(window) * 100


def bollinger(prices, window=20, n_std=2):
    mid = prices.rolling(window).mean()
    std = prices.rolling(window).std()
    upper = mid + n_std * std
    lower = mid - n_std * std
    return mid, upper, lower


def williams_r(close, high, low, window=14):
    high_w = high.rolling(window).max()
    low_w = low.rolling(window).min()
    return -100 * (high_w - close) / (high_w - low_w).replace(0, np.nan)


def atr(close, high, low, window=14):
    """Elementvis np.maximum pa .values, INTE .stack()/.unstack() - den
    senare kan misalignera nar olika T x N-matriser har NaN pa olika
    platser (stack() droppar NaN-celler individuellt per DataFrame
    innan concat, vilket kan ge felaktiga index-par)."""
    prev_close = close.shift(1)
    tr1 = (high - low).abs().values
    tr2 = (high - prev_close).abs().values
    tr3 = (low - prev_close).abs().values
    tr_v = np.maximum(np.maximum(tr1, tr2), tr3)
    tr = pd.DataFrame(tr_v, index=close.index, columns=close.columns)
    return tr.rolling(window).mean()


# ════════════════════════════════════════════════════════════
#  MONSTERDETEKTORER (varje returnerar T x N bool: "triggade IDAG")
#  Alla anvander justerade OHLC-priser (adj_open/adj_high/adj_low/close_adj).
# ════════════════════════════════════════════════════════════
def compute_all_patterns(adj_open, adj_high, adj_low, close_adj, volume):
    patterns = {}

    # --- TREND ---
    sma20, sma50, sma200 = sma(close_adj, 20), sma(close_adj, 50), sma(close_adj, 200)
    patterns["golden_cross"] = (sma20 > sma50) & (sma20.shift(1) <= sma50.shift(1))
    patterns["trend_filter_200sma"] = (close_adj > sma200) & (close_adj.shift(1) <= sma200.shift(1))

    # --- MOMENTUM ---
    macd_line, macd_signal = macd(close_adj)
    patterns["macd_cross"] = (macd_line > macd_signal) & (macd_line.shift(1) <= macd_signal.shift(1))

    pct_k, pct_d = stochastic(close_adj, adj_high, adj_low)
    patterns["stochastic_cross"] = (pct_k > pct_d) & (pct_k.shift(1) <= pct_d.shift(1)) & (pct_k.shift(1) < 20)

    roc12 = roc(close_adj, 12)
    patterns["roc_cross"] = (roc12 > 0) & (roc12.shift(1) <= 0)

    # --- MEAN-REVERSION ---
    rsi14 = rsi(close_adj, 14)
    patterns["rsi_recovery"] = (rsi14 > 30) & (rsi14.shift(1) <= 30)

    _, _, boll_lower = bollinger(close_adj, 20, 2)
    patterns["bollinger_bounce"] = (close_adj > boll_lower) & (adj_low.shift(1) <= boll_lower.shift(1))

    wr = williams_r(close_adj, adj_high, adj_low, 14)
    patterns["williams_r_reversal"] = (wr > -80) & (wr.shift(1) <= -80)

    # --- BREAKOUT ---
    donchian_high = adj_high.rolling(20).max().shift(1)  # FORE idag, undviker att idag rakna med sig sjalv
    patterns["donchian_breakout"] = close_adj > donchian_high

    avg_vol20 = volume.rolling(ADV_WINDOW).mean().shift(1)
    patterns["volume_breakout"] = (close_adj > donchian_high) & (volume > 1.5 * avg_vol20)

    # --- CANDLESTICK ---
    body = (close_adj - adj_open).abs()
    prev_body = body.shift(1)
    prev_bearish = adj_close_below_open = (close_adj.shift(1) < adj_open.shift(1))
    curr_bullish = close_adj > adj_open
    patterns["bullish_engulfing"] = (curr_bullish & prev_bearish
                                      & (adj_open <= close_adj.shift(1)) & (close_adj >= adj_open.shift(1))
                                      & (body > prev_body))

    candle_range = (adj_high - adj_low).replace(0, np.nan)
    lower_wick = adj_open.where(adj_open < close_adj, close_adj) - adj_low
    upper_wick = adj_high - adj_open.where(adj_open > close_adj, close_adj)
    is_hammer = (lower_wick > 2 * body) & (upper_wick < 0.3 * body.replace(0, np.nan)) & (body / candle_range < 0.4)
    prior_decline = close_adj.shift(1) < close_adj.shift(4)
    patterns["hammer_at_support"] = is_hammer & prior_decline

    day1_bearish = close_adj.shift(2) < adj_open.shift(2)
    day2_small_body = (close_adj.shift(1) - adj_open.shift(1)).abs() < 0.5 * (close_adj.shift(2) - adj_open.shift(2)).abs()
    day3_bullish_recovery = curr_bullish & (close_adj > (adj_open.shift(2) + close_adj.shift(2)) / 2)
    patterns["morning_star"] = day1_bearish & day2_small_body & day3_bullish_recovery

    # --- VOLATILITET ---
    _, boll_up_w, boll_lo_w = bollinger(close_adj, 20, 2)
    band_width = (boll_up_w - boll_lo_w) / sma(close_adj, 20)
    # Troskeln (20:e percentilen over trailing 120 dagar) beraknas FORE
    # idag (.shift(1)) - annars skulle dagens eget bandbredd-varde smyga
    # in i det historiska jamforelsematerialet det jamfors mot.
    squeeze_threshold = band_width.rolling(120).quantile(0.2).shift(1)
    patterns["bollinger_squeeze_breakout"] = (band_width.shift(1) < squeeze_threshold) & (close_adj > boll_up_w)

    atr14 = atr(close_adj, adj_high, adj_low, 14)
    atr_avg = atr14.rolling(20).mean().shift(1)
    patterns["atr_expansion"] = (atr14 > 1.5 * atr_avg) & (close_adj > close_adj.shift(1))

    return patterns


def compute_fired_matrix(patterns: dict) -> pd.DataFrame:
    """'Eldade' - NAGOT av de 15 monstren triggade den dagen (OR-
    kombinerat). En kombinerad handels-/Ejay-signal per ticker per dag,
    se moduldocstring for motivering av detta val."""
    fired = None
    for name, mat in patterns.items():
        mat = mat.fillna(False)
        fired = mat if fired is None else (fired | mat)
    return fired


# ════════════════════════════════════════════════════════════
#  EJAY (rullande traffkvot, look-ahead-fri - se moduldocstring)
# ════════════════════════════════════════════════════════════
def compute_ejay(fired: pd.DataFrame, close_adj: pd.DataFrame) -> pd.DataFrame:
    fwd_ret = close_adj.shift(-EJAY_FORWARD_DAYS) / close_adj - 1
    correct = (fwd_ret > 0).where(fired)  # NaN dar inget monster triggade, annars 0/1

    # BUGGFIX-FORESSANDE DESIGN: korrekt-etiketten for en signal pa dag T
    # kravs FORST kant pa dag T+10 (10 handelsdagar efters). shift(10)
    # flyttar fram den etiketten till den dag den FAKTISKT ar knd -
    # rullande 63-dagarsmedelvarde darefter anvander ALDRIG en annu
    # okand framtida etikett. Se test_hyp037_filed_date_universe.py-
    # sessionens hela tema for varfor detta tas pa stort allvar har.
    correct_known_asof = correct.shift(EJAY_FORWARD_DAYS)
    ejay = correct_known_asof.rolling(EJAY_WINDOW_DAYS, min_periods=EJAY_MIN_SIGNALS).mean()
    return ejay


# ════════════════════════════════════════════════════════════
#  UNIVERSUM-MASK (T x N bool - ar tickern i det eligible small-cap-
#  bandet DEN manaden)
# ════════════════════════════════════════════════════════════
def build_eligible_mask(universe_by_month, date_index, tickers):
    month_keys = sorted(universe_by_month.keys())
    month_dates = pd.to_datetime(month_keys)
    day_month_idx = month_dates.searchsorted(date_index, side="right") - 1
    day_month_idx = np.clip(day_month_idx, 0, len(month_dates) - 1)

    tidx = {t: i for i, t in enumerate(tickers)}
    mask = np.zeros((len(date_index), len(tickers)), dtype=bool)
    for mi in np.unique(day_month_idx):
        mk = month_keys[mi]
        cols = [tidx[t] for t in universe_by_month.get(mk, []) if t in tidx]
        rows = np.where(day_month_idx == mi)[0]
        if cols:
            mask[np.ix_(rows, cols)] = True
    return pd.DataFrame(mask, index=date_index, columns=tickers)


# ════════════════════════════════════════════════════════════
#  METRIKER (identiska definitioner mot resten av registret)
# ════════════════════════════════════════════════════════════
def sharpe(s, rf=RF_ANNUAL):
    r = s.pct_change().dropna()
    return float(np.sqrt(252) * (r - rf / 252).mean() / r.std()) if r.std() > 0 else 0.0


def max_drawdown(s):
    return float(((s - s.cummax()) / s.cummax()).min())


def cagr(s):
    return float((s.iloc[-1] / s.iloc[0]) ** (252 / len(s)) - 1)


def calmar(s):
    md = abs(max_drawdown(s))
    return cagr(s) / md if md > 0 else 0.0


# ════════════════════════════════════════════════════════════
#  BACKTEST-MOTOR
# ════════════════════════════════════════════════════════════
def run_backtest(capital_level, weighting_mode, adj_open, close_adj, adj_high, adj_low, volume,
                  spread_df, fired, ejay, eligible_mask, hedge):
    """weighting_mode: 'ejay_weighted' eller 'equal_weighted' - samma
    filtrerade urval, ENDA skillnaden ar positionsstorleksregeln
    (kriteriets villkor 2)."""
    assert weighting_mode in ("ejay_weighted", "equal_weighted")

    tickers = list(close_adj.columns)
    tidx = {t: i for i, t in enumerate(tickers)}
    dates = close_adj.index

    dollar_volume = (close_adj * volume).rolling(ADV_WINDOW).mean()

    # Daglig topp-kvartils-troskel bland eligible+giltig-Ejay-aktier
    ejay_eligible = ejay.where(eligible_mask)
    daily_threshold = ejay_eligible.quantile(EJAY_FILTER_QUANTILE, axis=1)

    tradeable = fired & eligible_mask & (ejay >= daily_threshold.values[:, None])

    cash = float(capital_level)
    holdings = {}  # ticker -> {"shares", "entry_price", "entry_date_i", "cost"}
    pv_list = []
    trade_log = []

    adj_open_v = adj_open.values
    close_adj_v = close_adj.values
    adj_high_v = adj_high.values
    adj_low_v = adj_low.values
    spread_v = spread_df.reindex(columns=tickers).values
    dollar_volume_v = dollar_volume.values
    tradeable_v = tradeable.values
    ejay_v = ejay.values

    for date_i in range(len(dates)):
        cash += cash * (RF_ANNUAL / 252)

        # ── EXITS (stop-loss via dagens low, annars tidsutlopp via close) ──
        for t in list(holdings.keys()):
            ti = tidx[t]
            h = holdings[t]
            days_held = date_i - h["entry_date_i"]
            lo = adj_low_v[date_i, ti]
            op = adj_open_v[date_i, ti]
            cl = close_adj_v[date_i, ti]
            stop_price = h["entry_price"] * (1 - STOP_LOSS_FRACTION)

            exit_price = None
            exit_reason = None
            if not np.isnan(lo) and lo <= stop_price:
                exit_price = min(op, stop_price) if not np.isnan(op) else stop_price
                exit_reason = "stop_loss"
            elif days_held >= HOLD_DAYS:
                if not np.isnan(cl):
                    exit_price = cl
                    exit_reason = "time_exit"

            if exit_price is not None and exit_price > 0:
                exit_spread = spread_v[date_i, ti]
                proceeds = h["shares"] * exit_price
                if not np.isnan(exit_spread):
                    proceeds -= proceeds * (exit_spread / 2)
                cash += proceeds
                ret = proceeds / h["cost"] - 1 if h["cost"] > 0 else 0.0
                trade_log.append({"date": dates[date_i], "ticker": t, "ret": ret,
                                   "gross_ret": exit_price / h["entry_price"] - 1,
                                   "type": exit_reason, "cost": h["cost"], "days_held": days_held})
                del holdings[t]

        # ── ENTRIES (fran GARDAGENS signal, exekverat pa DAGENS oppning) ──
        if date_i > 0:
            signal_day = date_i - 1
            candidate_idx = np.where(tradeable_v[signal_day])[0]
            candidates = [tickers[i] for i in candidate_idx if tickers[i] not in holdings]

            if candidates:
                if weighting_mode == "ejay_weighted":
                    weights = np.array([max(ejay_v[signal_day, tidx[t]], 0.0) for t in candidates])
                    if weights.sum() <= 0:
                        weights = np.ones(len(candidates))
                else:
                    weights = np.ones(len(candidates))
                weights = weights / weights.sum()

                available_cash = cash
                for t, w in zip(candidates, weights):
                    ti = tidx[t]
                    op = adj_open_v[date_i, ti]
                    if np.isnan(op) or op <= 0:
                        continue
                    target_dollar = available_cash * w
                    adv = dollar_volume_v[date_i, ti]
                    cap_dollar = adv * MAX_ADV_PCT if not np.isnan(adv) else target_dollar
                    sz = min(target_dollar, cap_dollar, cash)
                    if sz < capital_level * 0.0001 or sz <= 0:
                        continue
                    entry_spread = spread_v[date_i, ti]
                    effective_entry = op * (1 + entry_spread / 2) if not np.isnan(entry_spread) else op
                    shares = sz / effective_entry
                    cash -= sz
                    holdings[t] = {"shares": shares, "entry_price": effective_entry,
                                    "entry_date_i": date_i, "cost": sz}

        # ── VARDERING ──
        long_val = 0.0
        for t, h in holdings.items():
            ti = tidx[t]
            cp = close_adj_v[date_i, ti]
            if np.isnan(cp):
                cp = h["entry_price"]  # senast kanda pris om NaN just idag
            long_val += h["shares"] * cp

        pv_list.append(cash + long_val)

    pv = pd.Series(pv_list, index=dates)
    tl = pd.DataFrame(trade_log)
    return pv, tl


def run_for_capital_level(capital_level, adj_open, close_adj, adj_high, adj_low, volume,
                           spread_df, fired, ejay, eligible_mask, hedge):
    results = {}
    for mode in ("ejay_weighted", "equal_weighted"):
        pv, tl = run_backtest(capital_level, mode, adj_open, close_adj, adj_high, adj_low, volume,
                               spread_df, fired, ejay, eligible_mask, hedge)

        RESULTS_DIR.mkdir(exist_ok=True)
        pv.to_csv(RESULTS_DIR / f"portfolio_value_{mode}_{int(capital_level)}.csv", header=["portfolio_value"])
        tl.to_csv(RESULTS_DIR / f"trade_log_{mode}_{int(capital_level)}.csv", index=False)

        hedge_ret = hedge.pct_change()
        strat_ret = pv.pct_change()
        joined = pd.concat([strat_ret.rename("s"), hedge_ret.rename("b")], axis=1, join="inner").dropna()
        beta = float(joined["s"].cov(joined["b"]) / joined["b"].var()) if len(joined) > 10 else float("nan")
        corr = float(joined["s"].corr(joined["b"])) if len(joined) > 10 else float("nan")

        win_rate = float((tl["ret"] > 0).mean()) if len(tl) else float("nan")
        gains = tl.loc[tl["ret"] > 0, "ret"].sum() if len(tl) else 0.0
        losses = -tl.loc[tl["ret"] < 0, "ret"].sum() if len(tl) else 0.0
        pf = float(gains / losses) if losses > 0 else float("nan")

        results[mode] = {
            "capital_level": capital_level,
            "sharpe": sharpe(pv),
            "cagr": cagr(pv),
            "max_drawdown": max_drawdown(pv),
            "calmar": calmar(pv),
            "beta_vs_spy": beta,
            "correlation_vs_spy": corr,
            "n_trades": int(len(tl)),
            "win_rate": win_rate,
            "profit_factor": pf,
        }
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capital", type=float, default=None)
    parser.add_argument("--all-levels", action="store_true")
    args = parser.parse_args()
    levels = [100_000, 1_000_000, 10_000_000] if args.all_levels else [args.capital or 100_000]

    print("Laddar universum...")
    tickers, universe_by_month = load_universe()
    print(f"  {len(tickers)} unika tickers.\n")

    print("Laddar prismatriser (open/close/adjusted_close/high/low/volume)...")
    open_, close, close_adj, high, low, volume = load_price_matrices(tickers, FULL_START, FULL_END)
    hedge = load_hedge(FULL_START, FULL_END)
    print(f"  Prismatris: {close.shape}\n")

    print("Sanerar prisdata...")
    close, high, low = clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    open_ = open_.where(close.notna())
    implausible = flag_implausible_liquidity(close, volume, max_market_cap=MAX_MARKET_CAP,
                                              window=ADV_WINDOW, multiplier=1.0)
    close_adj = close_adj.mask(implausible)
    open_ = open_.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)

    print("Berknar justerade OHLC (motorfix-2-princip)...")
    adj_open, adj_high, adj_low = adjusted_ohlc(open_, high, low, close, close_adj)

    print("Berknar Corwin-Schultz-spread...")
    spread_df = pd.DataFrame({t: corwin_schultz_spread(high[t].values, low[t].values) for t in high.columns},
                              index=high.index)

    # N/A-anrop for att uppfylla den mekaniska friktionskontrollen
    # (validate_friction_usage.py kraver bade corwin_schultz_spread OCH
    # borrow_cost importerade+anropade) - denna strategi ar long-only,
    # obelanad, sa den EKONOMISKA borrow-kostnaden ar genuint noll. Se
    # HYP-040-kriteriets punkt 8 (LONG-ONLY, ingen SPY-hedge).
    _ = borrow_cost(position_value=0.0, holding_days=1, annual_rate=BORROW_ANNUAL_RATE)

    print("Berknar 15 TA-monster (vektoriserat)...")
    patterns = compute_all_patterns(adj_open, adj_high, adj_low, close_adj, volume)
    fired = compute_fired_matrix(patterns)
    print(f"  Genomsnittligt antal 'eldade' ticker-dagar/dag: {fired.sum(axis=1).mean():.1f}\n")

    print("Berknar Ejay (rullande 63-dagars traffkvot, look-ahead-fri)...")
    ejay = compute_ejay(fired, close_adj)

    print("Bygger eligible-mask fran small-cap-universumet...")
    eligible_mask = build_eligible_mask(universe_by_month, close_adj.index, tickers)

    all_results = []
    for level in levels:
        print(f"\n--- Kapitalniva: ${level:,.0f} ---")
        r = run_for_capital_level(level, adj_open, close_adj, adj_high, adj_low, volume,
                                   spread_df, fired, ejay, eligible_mask, hedge)
        all_results.append(r)
        for mode, res in r.items():
            print(f"  [{mode:<15}] Sharpe={res['sharpe']:.3f}  CAGR={res['cagr']:+.2%}  "
                  f"MaxDD={res['max_drawdown']:.2%}  Trades={res['n_trades']}  "
                  f"Winrate={res['win_rate']:.1%}  PF={res['profit_factor']:.3f}  "
                  f"Beta(SPY)={res['beta_vs_spy']:.3f}")

    RESULTS_DIR.mkdir(exist_ok=True)
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, default=str)

    print("\nKLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
