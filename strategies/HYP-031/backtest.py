"""
HYP-023: Sektorspecifik krasch-trigger (bank-/finanskomposit) pa HYP-017
(idiosynkratisk vol + SPY-krasch-overlay, PASSED, K=16, fortfarande
referensimplementationen).

Se research/hypothesis_registry/HYP-023-sektor-krasch-trigger-hyp017.yaml
for det lasta kriteriet, och research/strategy_specs/HYP-023-spec.md for
den fulla specen.

DIAGNOS: HYP-022 (statiskt 15%-tak pa bank-/finansinnehav) loste mars
2023-episoden men gav NETTO-SAMRE MaxDD an HYP-017 vid $1M/$10M, eftersom
en PERMANENT begransning tar bort banksektorns stabiliserande roll under
lugna perioder (bankmarginaler gynnades av ranteh0jningar anda fram till
SVB-kollapsen). Denna hypotes anvander i stallet en DYNAMISK,
handelsetriggad mekanism - samma arkitektur som redan bevisat fungerar
for SPY-overlayen - som bara griper in under akut sektorspecifik stress.

TILLAGG mot HYP-017 (allt annat - signal, universum, friktion, hedge,
kapacitetsspärr, SPY-krasch-overlay, de tre motorfixarna - AR OFORANDRAT):
  En ANDRA, sektorspecifik krasch-trigger pa ett likaviktat bank-/
  finanskompositindex (manadens hela eligible-universum, samma
  sector.py-klassificering som HYP-022). Om kompositens egna 10-dagars-
  avkastning < -10% (SAMMA konstanter som SPY-overlayen, ateranvanda
  for att undvika facit-anpassning), skars ENDAST bank-/finansinnehaven
  (INTE hela portfoljen) till 40% av dagens varde. Kors EFTER
  SPY-overlayen i samma loop-iteration.

HYP-031: BETA-HEDGE-INSTRUMENTET byts fran SPY till IWM (Russell 2000)
- ENDA andringen mot HYP-023. Signalens residualisering (idio-vol),
  SPY-krasch-overlayen, sektor-triggern, kalendern: ALLA fortsatt mot
  SPY, oforandrade. Bara den FAKTISKA korta hedgepositionens P&L
  (long_beta * hedge_avkastning) racknas nu mot IWM:s egen beta/
  avkastning i stallet for SPY:s. Se
  research/hypothesis_registry/HYP-031-iwm-beta-hedge.yaml for det
  lasta kriteriet. Motivering: basis-risk mellan ett micro/small-cap-
  handlat book ($100M-$2B) och en mega-cap-hedge (SPY).
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
from sector import load_bank_financial_flags  # noqa: E402

# ════════════════════════════════════════════════════════════
#  PARAMETRAR
# ════════════════════════════════════════════════════════════
FULL_START = "2010-01-01"
FULL_END = "2024-12-31"

VOL_LOOKBACK_DAYS = 120   # trailing residual-std, samma fonster som HYP-014 anvande for total std
VOL_MIN_HISTORY = 130

DECILE_FRACTION = 0.10    # lagsta idiosynkratiska-vol-decilen
REBAL_FREQ = "QE"         # kvartalsvis - oforandrat mot HYP-014
RF_ANNUAL = 0.02
BETA_WINDOW = 126

BORROW_ANNUAL_RATE = 0.03
MAX_ADV_PCT = 0.10
ADV_WINDOW = 20

MAX_MARKET_CAP = 2_000_000_000  # universumets ovre marknadsvardesgrans - anvands av liquiditetsfiltret

# Krasch-overlay (ny i HYP-017, se pass_fail_criterion - lockade, ej fria parametrar)
CRASH_LOOKBACK_DAYS = 10     # SPY:s egen kumulativa avkastningsfonster
CRASH_TRIGGER_RET = -0.10    # trigger: SPY 10-dagars-avkastning under -10%
CRASH_HAIRCUT_FRACTION = 0.40  # skar ner till 40% av dagens varde vid trigger

# Sektor-krasch-trigger (ny i HYP-023, se pass_fail_criterion - lockade,
# SAMMA konstanter som SPY-overlayen, medvetet ateranvanda ist for nya)
SECTOR_CRASH_LOOKBACK_DAYS = 10
SECTOR_CRASH_TRIGGER_RET = -0.10
SECTOR_CRASH_HAIRCUT_FRACTION = 0.40

HEDGE = "SPY"          # kalender, signalresidualisering, krasch-overlay - OFORANDRAT
BETA_HEDGE = "IWM"     # ny i HYP-031: den FAKTISKA korta hedgepositionens instrument


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


def load_hedge(start, end, ticker=None):
    """adjusted_close genomgaende (utdelningsjusterad), eftersom
    hedgen bara anvands for avkastningsberakningar (hedge_ret), aldrig
    for ett eget positionsvarde i dollar. `ticker` - ny i HYP-031, later
    samma funktion aterananvandas for bade SPY (kalender/overlay) och
    IWM (den faktiska beta-hedgen) - default SPY for bakatkompatibilitet."""
    ticker = ticker or HEDGE
    path = OHLCV_DIR / f"{ticker}.csv"
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
#  BANK-/FINANSKOMPOSIT (ny i HYP-023, samma likaviktade metod som
#  HYP-021:s small-cap-komposit, men begransad till bank-/finansnamn i
#  manadens eligible-universum - INTE bara innehavda namn, for att
#  undvika cirkularitet)
# ════════════════════════════════════════════════════════════
def compute_bank_composite_returns(close_adj, universe_by_month, bank_flags, date_index):
    bank_all = [t for t in close_adj.columns if bank_flags.get(t, False)]
    bank_rets = close_adj[bank_all].pct_change()

    month_keys = sorted(universe_by_month.keys())
    month_dates = pd.to_datetime(month_keys)
    day_month_idx = month_dates.searchsorted(date_index, side="right") - 1
    day_month_idx = np.clip(day_month_idx, 0, len(month_dates) - 1)

    composite = pd.Series(index=date_index, dtype="float64")
    for mi in np.unique(day_month_idx):
        mask = day_month_idx == mi
        mk = month_keys[mi]
        eligible_bank = [t for t in universe_by_month.get(mk, [])
                          if bank_flags.get(t, False) and t in bank_rets.columns]
        if eligible_bank:
            composite.iloc[mask] = bank_rets.loc[date_index[mask], eligible_bank].mean(axis=1).values
    return composite


# ════════════════════════════════════════════════════════════
#  SIGNAL: IDIOSYNKRATISK VOLATILITET (ny - ersatter total-vol-signalen)
# ════════════════════════════════════════════════════════════
def compute_idiosyncratic_vol(close_adj, hedge_adj, beta_df, lookback_days):
    """
    Residual = daglig aktieavkastning - beta * daglig hedgeavkastning
    (bada berakade pa adjusted_close, se motorfix 2). Signal = rullande
    std av residualen - den robusta, litteraturstodda formen av
    lagvolatilitetsanomalin (Ang, Hodrick, Xing & Zhang 2006), till
    skillnad fran HYP-014:s TOTALA std.
    """
    stock_ret = close_adj.pct_change()
    hedge_ret = hedge_adj.pct_change()
    resid = stock_ret.sub(beta_df.multiply(hedge_ret, axis=0))
    return resid.rolling(lookback_days).std().astype("float32")


# ════════════════════════════════════════════════════════════
#  BACKTEST-MOTOR (samma struktur som HYP-014, MED motorfix 1: snappade
#  ombalanseringsdatum i stallet for ra kalender-etikettsmatchning)
# ════════════════════════════════════════════════════════════
def run_backtest(close, close_adj, hedge, crash_ref, vol_df, beta_df, spread_df, volume,
                 universe_by_month, capital_level: float, bank_flags: dict):
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

    HYP-031: `hedge` ar NU IWM (den faktiska beta-hedgens instrument -
    hedge_ret/beta_df racknas mot IWM), `crash_ref` ar SPY (ENDAST for
    krasch-overlayens trigger - OFORANDRAT fran HYP-023). Tva separata
    serier dar HYP-023 bara hade en.
    """
    tickers = list(close.columns)
    tidx = {t: i for i, t in enumerate(tickers)}
    hedge_ret = hedge.pct_change()  # HYP-031: IWM:s avkastning (var SPY i HYP-023)
    dollar_volume = (close * volume).rolling(ADV_WINDOW).mean()

    # KRASCH-OVERLAY (ny i HYP-017, OFORANDRAD i HYP-031): SPY:s egen
    # kumulativa 10-dagars-avkastning (crash_ref, INTE hedge - se
    # funktionsdocstring), kontrollerad VARJE handelsdag.
    spy_10d_ret_v = crash_ref.pct_change(CRASH_LOOKBACK_DAYS).values
    haircut_active = False

    # SEKTOR-KRASCH-TRIGGER (ny i HYP-023): likaviktad bank-/finanskomposit,
    # samma 10-dagars/-10%-mekanism som SPY-overlayen men skar ENDAST
    # bank-/finansinnehav. Eget haircut-tillstand, oberoende av SPY-overlayens.
    bank_tickers_set = {t for t in tickers if bank_flags.get(t, False)}
    bank_composite = compute_bank_composite_returns(close_adj, universe_by_month, bank_flags, close.index)
    bank_composite_price = (1.0 + bank_composite.fillna(0.0)).cumprod()
    sector_10d_ret_v = bank_composite_price.pct_change(SECTOR_CRASH_LOOKBACK_DAYS).values
    sector_haircut_active = False

    calendar_dates = close.resample(REBAL_FREQ).last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[VOL_MIN_HISTORY]) & (calendar_dates <= close.index[-1])]
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
    sector_trigger_log = []

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
            vol_today = vol_df.loc[date]
            scores = []
            for t in eligible:
                v = vol_today[t]
                cp = prices_v[date_i, tidx[t]]
                if not np.isnan(v) and not np.isnan(cp) and cp > 0:
                    scores.append((v, t, cp))
            scores.sort()  # LAGST idiosynkratisk vol forst
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

        # ── Krasch-overlay (ny, HYP-017): DAGLIG kontroll, oberoende av
        # rebal_set. Skar ner till CRASH_HAIRCUT_FRACTION av innehaven EN
        # gang per sammanhangande episod under triggerntroskeln - ateruppbyggnad
        # sker INTE har, bara vid nasta ordinarie decil-ombalansering (se
        # moduldocstring/spec for motivering av denna asymmetri).
        spy10 = spy_10d_ret_v[date_i]
        if not np.isnan(spy10) and spy10 < CRASH_TRIGGER_RET and not haircut_active:
            for t in list(holdings.keys()):
                ti = tidx[t]
                cp = prices_v[date_i, ti]
                if np.isnan(cp):
                    cp = holdings[t]["last_price"]
                shares_to_sell = holdings[t]["shares"] * (1 - CRASH_HAIRCUT_FRACTION)
                proceeds = shares_to_sell * cp
                exit_spread = spread_v[date_i, ti]
                if not np.isnan(exit_spread):
                    proceeds -= proceeds * (exit_spread / 2)
                cash += proceeds
                sold_cost = holdings[t]["cost"] * (1 - CRASH_HAIRCUT_FRACTION)
                ret = proceeds / sold_cost - 1 if sold_cost > 0 else 0.0
                trade_log.append({"date": date, "ticker": t, "ret": ret,
                                   "gross_ret": cp / holdings[t]["entry"] - 1, "type": "crash_overlay_exit",
                                   "cost": sold_cost})
                holdings[t]["shares"] -= shares_to_sell
                holdings[t]["cost"] -= sold_cost
            haircut_active = True
        elif not np.isnan(spy10) and spy10 >= CRASH_TRIGGER_RET:
            haircut_active = False

        # ── Sektor-krasch-trigger (ny, HYP-023): DAGLIG kontroll, EFTER
        # SPY-overlayen (pa vad som aterstar av bankinnehaven efter en
        # eventuell portfoljbred nedskarning samma dag). Skar ENDAST
        # bank-/finansinnehav till SECTOR_CRASH_HAIRCUT_FRACTION av
        # dagens varde - inte hela portfoljen.
        sector10 = sector_10d_ret_v[date_i]
        if not np.isnan(sector10) and sector10 < SECTOR_CRASH_TRIGGER_RET and not sector_haircut_active:
            for t in list(holdings.keys()):
                if t not in bank_tickers_set:
                    continue
                ti = tidx[t]
                cp = prices_v[date_i, ti]
                if np.isnan(cp):
                    cp = holdings[t]["last_price"]
                shares_to_sell = holdings[t]["shares"] * (1 - SECTOR_CRASH_HAIRCUT_FRACTION)
                proceeds = shares_to_sell * cp
                exit_spread = spread_v[date_i, ti]
                if not np.isnan(exit_spread):
                    proceeds -= proceeds * (exit_spread / 2)
                cash += proceeds
                sold_cost = holdings[t]["cost"] * (1 - SECTOR_CRASH_HAIRCUT_FRACTION)
                ret = proceeds / sold_cost - 1 if sold_cost > 0 else 0.0
                trade_log.append({"date": date, "ticker": t, "ret": ret,
                                   "gross_ret": cp / holdings[t]["entry"] - 1, "type": "sector_crash_overlay_exit",
                                   "cost": sold_cost})
                holdings[t]["shares"] -= shares_to_sell
                holdings[t]["cost"] -= sold_cost
            sector_trigger_log.append({"date": date, "sector_10d_ret": float(sector10)})
            sector_haircut_active = True
        elif not np.isnan(sector10) and sector10 >= SECTOR_CRASH_TRIGGER_RET:
            sector_haircut_active = False

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
    stl = pd.DataFrame(sector_trigger_log)
    return pv, tl, stl


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
def march_2023_episode_return(pv):
    """Villkor 3 i HYP-023:s pass_fail_criterion: avkastning 2023-02-01
    till 2023-05-01, jamfor direkt mot HYP-017:s -14.8% pa samma fonster."""
    window = pv.loc["2023-02-01":"2023-05-01"]
    if len(window) < 2:
        return None
    return float(window.iloc[-1] / window.iloc[0] - 1)


def run_for_capital_level(capital_level, close, close_adj, iwm, spy, vol_df, beta_hedge_df, spread_df, volume,
                           universe_by_month, bank_flags):
    print(f"    Kör backtest (kapitalnivå {capital_level:,.0f})...")
    pv, tl, stl = run_backtest(close, close_adj, iwm, spy, vol_df, beta_hedge_df, spread_df, volume, universe_by_month,
                                capital_level, bank_flags)

    result = {
        "capital_level": capital_level,
        "cagr": cagr(pv),
        "sharpe": sharpe(pv),
        "calmar": calmar(pv),
        "max_drawdown": max_drawdown(pv),
        "trade_stats": trade_stats(tl),
        "n_sector_trigger_episodes": len(stl),
        "march_2023_episode_return": march_2023_episode_return(pv),
    }
    result.update(best_trade_excluded_metrics(pv, tl, capital_level))

    RESULTS_DIR.mkdir(exist_ok=True)
    pv.to_csv(RESULTS_DIR / f"portfolio_value_{int(capital_level)}.csv", header=["portfolio_value"])
    tl.to_csv(RESULTS_DIR / f"trade_log_{int(capital_level)}.csv", index=False)
    stl.to_csv(RESULTS_DIR / f"sector_trigger_log_{int(capital_level)}.csv", index=False)

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
    spy = load_hedge(FULL_START, FULL_END, ticker=HEDGE)
    iwm = load_hedge(FULL_START, FULL_END, ticker=BETA_HEDGE)
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

    print("Estimerar beta mot SPY (signalens residualisering, OFORANDRAD fran HYP-023)...")
    beta_df_signal = compute_beta(close_adj, spy, BETA_WINDOW)

    print("Beräknar idiosynkratisk-volatilitets-signal (trailing 120 dagar, pa adjusted_close, mot SPY)...")
    vol_df = compute_idiosyncratic_vol(close_adj, spy, beta_df_signal, VOL_LOOKBACK_DAYS)

    print("Estimerar beta mot IWM (HYP-031: den FAKTISKA hedgepositionens instrument)...")
    beta_hedge_df = compute_beta(close_adj, iwm, BETA_WINDOW)

    print("Beräknar Corwin-Schultz-spread (pa ra high/low, görs en gång)...\n")
    spread_df = compute_spread_matrix(high, low)

    print("Klassificerar bank-/finansnamn (data/cache/smallcap_classification.jsonl)...")
    bank_flags = load_bank_financial_flags(tickers)
    print(f"  {sum(bank_flags.values())} av {len(tickers)} tickers klassade som bank/finans.\n")

    all_results = []
    for level in levels:
        print(f"--- Kapitalnivå: ${level:,.0f} ---")
        result = run_for_capital_level(level, close, close_adj, iwm, spy, vol_df, beta_hedge_df, spread_df, volume,
                                        universe_by_month, bank_flags)
        all_results.append(result)
        print(f"    CAGR={result['cagr']:+.2%}  Sharpe={result['sharpe']:.2f}  "
              f"Calmar={result['calmar']:.2f}  MaxDD={result['max_drawdown']:.1%}  "
              f"SektorTriggers={result['n_sector_trigger_episodes']}  "
              f"Mars2023={result['march_2023_episode_return']:+.1%}  "
              f"Trades={result['trade_stats']['n']}\n")

    RESULTS_DIR.mkdir(exist_ok=True)
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
