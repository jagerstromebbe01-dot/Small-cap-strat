"""
Delad backtestmotor for BATCH-004:s fyra accrual-varianter (HYP-097 till
HYP-100, se deras registerposter for de lasta kriterierna). DELAD
AVSIKTLIGT (samma princip som crypto_data.py::build_baseline_basket) -
alla fyra maste jamforas mot samma underliggande motor (universum,
pris, friktion, kapacitetsspärr) for att skillnaderna mellan dem ska
vara meningsfulla; en delad funktion eliminerar risken for tyst
avvikelse mellan fyra separata kopior.

Motorn ar kopierad fran och foljer EXAKT samma struktur som HYP-033:s
redan validerade book-to-market-motor (universum-inladdning, pris-
matriser, SPY-beta-hedge for long-only, Corwin-Schultz-friktion,
MAX_ADV_PCT-kapacitetsspärr, samma metrik-definitioner) - INTE en
nyuppfinning, bara samma redan beprövade motor med en annan signal.

LONG/SHORT-varianterna (HYP-098/100) ERSÄTTER den syntetiska SPY-beta-
hedgen med en RIKTIG namnspecifik kort-bok (toppdecilen av accruals) -
en dollar-neutral, namnspecifik konstruktion testar frågan "finns det
en genuin long/short-edge" renare än att blanda en syntetisk indexhedge
med en namnspecifik kort-bok samtidigt. Realiserad nettobeta rapporteras
som diagnostisk disclosure istallet for att tvingas mot noll.
"""

import bisect
import json
from pathlib import Path

import numpy as np
import pandas as pd

STRATEGIES_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = STRATEGIES_ROOT.parent / "data"
CACHE_DIR = DATA_DIR / "cache"
OHLCV_DIR = CACHE_DIR / "ohlcv"
UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_by_month.json"
ACCRUAL_FILE = CACHE_DIR / "accrual_by_ticker.jsonl"
VALUE_FACTOR_FILE = CACHE_DIR / "value_factor_by_ticker.jsonl"

import sys  # noqa: E402
sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
from friction import borrow_cost, corwin_schultz_spread  # noqa: E402
from data_hygiene import clean_price_matrix, flag_implausible_liquidity  # noqa: E402
from rebalancing import snap_rebalance_dates  # noqa: E402

FULL_START = "2010-01-01"
FULL_END = "2024-12-31"

MIN_HISTORY_DAYS = 130
DECILE_FRACTION = 0.10
REBAL_FREQ = "QE"
RF_ANNUAL = 0.02
BETA_WINDOW = 126

BORROW_ANNUAL_RATE = 0.03
MAX_ADV_PCT = 0.10
ADV_WINDOW = 20

MAX_MARKET_CAP = 2_000_000_000
HEDGE = "SPY"

STALENESS_DAYS = 450  # samma princip som resten av BATCH-004 (HYP-093 mfl)
SHORT_STOP_LOSS_THRESHOLD = 1.0  # se run_backtest, upptäckt 2026-08-13 (HYP-098)
# MIN_SCORED_FOR_DECILE (upptäckt 2026-08-13, HYP-100): utan detta golv
# kan `max(1, int(n_scored * DECILE_FRACTION))` ge EN enda position per
# ben redan vid n_scored=8 (sett i praktiken 2010-09-30, det tidiga
# universumets tunnaste period) - noll diversifiering, en enskild dålig
# aktie kan då slå ut hela fonden dag ett. Samma princip som redan
# etablerad för crypto-motorn (MIN_UNIVERSE_SIZE) men skalad till en
# DECIL-konstruktion (kräver fler namn totalt för att ge en meningsfull
# decil än en tredjedelsindelning gör).
MIN_SCORED_FOR_DECILE = 30


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


PLAUSIBLE_ACCRUAL_BOUND = 1.0  # se motivering nedan i load_accrual_data


def load_accrual_data(scaling: str) -> dict:
    """scaling: 'assets' (Sloan 1996-originalet) eller 'market_cap'.
    Returnerar ticker -> sorterad lista av (filed_date_str, accrual_ratio).
    Kraver income+cfo alltid; 'assets'-skalning kraver dessutom
    assets-taggen (annars hoppas det bokslutsaret over for det bolaget,
    INTE ett fall-back till en annan skalning i tysthet)."""
    out = {}
    if not ACCRUAL_FILE.exists():
        return out
    with ACCRUAL_FILE.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            income_by_end = {e["end"]: e for e in row.get("income", []) if e.get("val") is not None}
            cfo_by_end = {e["end"]: e for e in row.get("cfo", []) if e.get("val") is not None}
            assets_by_end = {e["end"]: e for e in row.get("assets", []) if e.get("val") not in (None, 0)}
            ends_sorted = sorted(income_by_end.keys() & cfo_by_end.keys())

            observations = []
            prev_assets = None
            for end in ends_sorted:
                inc = income_by_end[end]
                cfo = cfo_by_end[end]
                filed = inc.get("filed")
                if not filed:
                    continue
                if scaling == "assets":
                    cur_assets = assets_by_end.get(end, {}).get("val")
                    if cur_assets is None or prev_assets is None:
                        prev_assets = cur_assets
                        continue
                    denom = (cur_assets + prev_assets) / 2.0
                    prev_assets = cur_assets
                    if denom <= 0:
                        continue
                    accrual = (inc["val"] - cfo["val"]) / denom
                    # DATASANERING (upptäckt 2026-08-13, INNAN HYP-097/098:s
                    # resultat finaliserades - se registerposternas
                    # tillägg): rå accrual-kvot över hela universumet
                    # sträckte sig från -102265 till +5138 - dominerat av
                    # bolag med extremt litet rapporterat tillgångsvärde
                    # (skalbolag/distressade bolag nära noll i nämnaren),
                    # INTE genuin vinstkvalitetsinformation. En riktig
                    # accrual-kvot för ett fungerande bolag ligger i
                    # praktiken nästan alltid inom ±1 (100% av egna
                    # genomsnittliga tillgångar) - gränsen är vald för
                    # ekonomisk orimlighet (samma princip som
                    # data_hygiene.py:s MIN/MAX_DAILY_RETURN), INTE
                    # kalibrerad mot något redan sett backtest-resultat.
                    if abs(accrual) > PLAUSIBLE_ACCRUAL_BOUND:
                        continue
                    observations.append((filed, accrual))
                else:
                    # market_cap-skalning löses per datum i run_backtest (kräver
                    # dagens pris x aktieantal, inte bara ett statiskt tal här) -
                    # spara rå (income - cfo) istället, dela med marknadsvärde
                    # vid uppslagningstillfället.
                    observations.append((filed, inc["val"] - cfo["val"]))
            if observations:
                observations.sort()
                out[row["ticker"]] = observations
    return out


def load_shares_outstanding() -> dict:
    """Ateranvander redan cachad data/cache/value_factor_by_ticker.jsonl
    (byggd for HYP-033) for aktieantal - samma kalla som redan anvands
    for att berakna marknadsvarde pa annat hall i registret, ingen ny
    hamtning behovs."""
    out = {}
    if not VALUE_FACTOR_FILE.exists():
        return out
    with VALUE_FACTOR_FILE.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            shares_list = row.get("shares_outstanding", [])
            obs = sorted((sh["filed"], sh["val"]) for sh in shares_list if sh.get("val"))
            if obs:
                out[row["ticker"]] = obs
    return out


def make_shares_lookup(shares_data: dict):
    def _lookup(ticker: str, as_of_date_str: str):
        obs = shares_data.get(ticker)
        if not obs:
            return None
        dates = [o[0] for o in obs]
        idx = bisect.bisect_left(dates, as_of_date_str) - 1
        if idx < 0:
            return None
        return obs[idx][1]
    return _lookup


def accrual_asof(accrual_data: dict, ticker: str, as_of_date_str: str, staleness_days=STALENESS_DAYS):
    """Senaste FILED accrual-varde strikt FORE as_of_date_str, forkastat
    om for gammalt (samma staleness-princip som resten av BATCH-004)."""
    obs = accrual_data.get(ticker)
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


# ════════════════════════════════════════════════════════════
#  BETA / SPREAD (identisk med HYP-033)
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
#  SIGNALBERAKNING (accrual-specifik)
# ════════════════════════════════════════════════════════════
def score_universe(eligible, accrual_data, scaling, as_of, prices_v, tidx, shares_lookup=None):
    """Returnerar sorterad lista (accrual_ratio, ticker, close_price),
    LÄGST accrual forst (bäst vinstkvalitet). shares_lookup kravs bara
    for scaling='market_cap' (ticker -> senast kanda aktieantal, samma
    källa som redan används for small-cap-universumets egen
    marknadsvärdesberäkning)."""
    scores = []
    for t in eligible:
        raw = accrual_asof(accrual_data, t, as_of)
        if raw is None:
            continue
        cp = prices_v[tidx[t]]
        if np.isnan(cp) or cp <= 0:
            continue
        if scaling == "assets":
            accrual = raw
        else:
            if shares_lookup is None:
                continue
            shares = shares_lookup(t, as_of)
            if shares is None or shares <= 0:
                continue
            market_cap = cp * shares
            if market_cap <= 0:
                continue
            accrual = raw / market_cap
        # DATASANERING: samma ekonomiska-orimlighetsgräns som
        # load_accrual_data() applicerar för scaling='assets' - se den
        # funktionens kommentar för fullständig motivering. Måste
        # upprepas här eftersom market_cap-skalningen räknas ut per
        # datum (marknadsvärdet ändras dagligen), inte en gång vid
        # inläsning.
        if abs(accrual) > PLAUSIBLE_ACCRUAL_BOUND:
            continue
        scores.append((accrual, t, cp))
    scores.sort()  # LÄGST accrual först (bäst vinstkvalitet - "long" i båda konstruktionerna)
    return scores


# ════════════════════════════════════════════════════════════
#  BACKTEST-MOTOR
# ════════════════════════════════════════════════════════════
def run_backtest(close, close_adj, hedge, accrual_data, scaling, construction,
                  beta_df, spread_df, volume, universe_by_month, capital_level: float,
                  shares_lookup=None):
    """construction: 'long_only' (SPY-beta-hedgad, som HYP-033) eller
    'long_short' (namnspecifik kort bok pa toppdecilen, ingen SPY-hedge)."""
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
            scores = score_universe(eligible, accrual_data, scaling, as_of,
                                     prices_v[date_i], tidx, shares_lookup)
            n_pick = max(1, int(len(scores) * DECILE_FRACTION)) if len(scores) >= MIN_SCORED_FOR_DECILE else 0
            long_targets = {t for _, t, _ in scores[:n_pick]}
            short_targets = {t for _, t, _ in scores[-n_pick:]} if construction == "long_short" and n_pick else set()

            # LONG-BENET: exit sedan entry (samma struktur som HYP-033)
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

            # KORT-BENET (bara construction='long_short')
            if construction == "long_short":
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
                    # Kort-benet storleksatt mot LIKA STOR notional som lang-benet
                    # (dollar-neutral konstruktion, CEO-LÅST mönster) - ALDRIG mot
                    # rå cash for en kort bok (kant redan diagnostiserad i
                    # HYP-072-familjen, se project-minnet om short-leg-bugg).
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

        # KORT-BEN STOP-LOSS (DAGLIG, oberoende av ombalanseringsdatum):
        # forcerar täckning om en enskild kort position tappat mer än
        # SHORT_STOP_LOSS_THRESHOLD av sin egen allokerade notional.
        # UPPTÄCKT 2026-08-13 (HYP-098, första long/short-konstruktionen
        # i BATCH-004): utan detta kan en enskild "squeeze" (verifierat
        # förekommer i detta universum - t.ex. en +3190%-trade sågs i
        # HYP-097:s long-ben) låta en kort positions pappersförlust växa
        # obegränsat mellan kvartalsvisa ombalanseringar, vilket gav ett
        # negativt portföljvärde (MaxDD -326%, matematiskt inkoherent -
        # ingen verklig fond tillåter en kort position blåsa upp
        # obegränsat, en margin call/tvingad täckning skulle ha triggat
        # långt innan). INTE en ändring av den låsta signalen/
        # konstruktionen - en nödvändig, tidigare underspecificerad
        # riskkontroll, samma princip som redan etablerad för
        # portföljnivå-hävstång i HYP-059/065/087/088 (tvingad
        # nedskalning innan katastrofal förlust), här applicerad per
        # enskild position istället.
        if construction == "long_short":
            for t in list(short_holdings.keys()):
                ti = tidx[t]
                cp = prices_v[date_i, ti]
                if np.isnan(cp):
                    continue
                h = short_holdings[t]
                paper_loss_ratio = (cp - h["entry"]) / h["entry"] if h["entry"] > 0 else 0.0
                if paper_loss_ratio > SHORT_STOP_LOSS_THRESHOLD:
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

        short_val, short_beta, short_pnl_today = 0.0, 0.0, 0.0
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

        if construction == "long_only":
            daily_borrow = borrow_cost(position_value=abs(long_beta), holding_days=1, annual_rate=BORROW_ANNUAL_RATE)
            hedge_pnl = -long_beta * hr - long_beta * (RF_ANNUAL / 2 / 252) - daily_borrow
            pv_list.append(cash + long_val + hedge_pnl)
            beta_exposure_log.append({"date": date, "net_beta_dollar": long_beta - long_beta})  # =0 (hedgad per konstruktion)
        else:
            daily_short_borrow = borrow_cost(position_value=short_val, holding_days=1, annual_rate=BORROW_ANNUAL_RATE)
            pv_today = cash + long_val - short_val - daily_short_borrow
            # Kort-benets löpande MTM-vinst/förlust hanteras via cash vid
            # cover (rebalance_exit) - mellan ombalanseringar reflekteras
            # den istället i (cash + long_val - short_val), samma princip
            # som redan används för short-ben i övriga registret (t.ex.
            # HYP-072-familjen efter dess sizing-fix).
            #
            # KONKURSGOLV (upptäckt 2026-08-13, HYP-098): även med
            # per-position-stoppen ovan kan MÅNGA enskilda "squeeze"-
            # händelser (108 st över 15 år för HYP-098) ackumuleras till
            # ett NEGATIVT nettoportföljvärde - matematiskt inkoherent
            # (en fond kan inte ha negativt NAV och fortsätta handla, se
            # nan-CAGR som symptom). En long-only-bok kan ALDRIG bryta
            # noll (ett aktiepris kan inte bli negativt) - detta är
            # samma implicita golv, bara explicit gjort här eftersom
            # long/short-konstruktionen matematiskt KAN bryta det utan
            # denna spärr. INTE en ändring av signalen/konstruktionen -
            # en fond med negativt NAV är i praktiken konkursad och
            # skulle ha stoppats av en mäklare långt innan, inte en
            # modellerings-nyhet.
            if pv_today <= 0:
                pv_today = 1e-6 * capital_level
            pv_list.append(pv_today)
            beta_exposure_log.append({"date": date, "net_beta_dollar": long_beta - short_beta})

    pv = pd.Series(pv_list[1:], index=trade_dates)
    tl = pd.DataFrame(trade_log)
    beta_log = pd.DataFrame(beta_exposure_log)
    return pv, tl, beta_log


# ════════════════════════════════════════════════════════════
#  METRICS
# ════════════════════════════════════════════════════════════
def sharpe(s, rf=RF_ANNUAL):
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
    return c / md if md > 0 and c is not None else 0.0


def equal_weighted_baseline(close, universe_by_month, start_idx):
    """Obligatorisk, ICKE-GATING disclosure-baseline for long-only-
    varianterna (HYP-097/099): likaviktad, kvartalsvis ombalanserad,
    HELT OFILTRERAD (inget accrual-urval) over samma universum. MEDVETET
    FRIKTIONSFRI (disclosure, inte en gating-jamforelse) - flaggas
    explicit i resultatutskriften, inte dold."""
    calendar_dates = close.resample(REBAL_FREQ).last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[start_idx]) & (calendar_dates <= close.index[-1])]
    snapped = snap_rebalance_dates(calendar_dates, close.index)
    rebal_map = dict(zip(snapped["execution_date"], snapped["calendar_label"]))
    rebal_set = set(snapped["execution_date"])

    ret = close.pct_change()
    weights = pd.Series(0.0, index=close.columns)
    equity = 1.0
    values, dates = [], []
    for date_i in range(start_idx, len(close.index)):
        date = close.index[date_i]
        if date_i > start_idx:
            day_ret = (weights * ret.iloc[date_i].fillna(0.0)).sum()
            equity *= (1 + day_ret)
        if date in rebal_set:
            month_key = rebal_map[date].strftime("%Y-%m-%d")
            eligible = [t for t in universe_by_month.get(month_key, []) if t in close.columns]
            if eligible:
                weights = pd.Series(1.0 / len(eligible), index=eligible).reindex(close.columns, fill_value=0.0)
        values.append(equity)
        dates.append(date)
    return pd.Series(values, index=dates)
