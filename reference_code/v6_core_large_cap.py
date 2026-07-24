# ============================================================
#  V6 CORE - REFERENS-KOD, REDAN EMPIRISKT VALIDERAD
#
#  Detta är den RENA v6-kärnan: beta-neutral OLS-parhandel,
#  INGET ejay-filter, INGEN Kelly-sizing, fast positionsstorlek.
#  Motsvarar "Bok A" / "STANDARD"-versionen som testats upprepade
#  gånger i tidigare arbete (Test 5, dollarvolym-viktnings-testet)
#  med konsekvent resultat på large-cap, 2010-2024:
#
#    CAGR:           ~4.8%
#    Sharpe:         ~0.55
#    Calmar:         ~0.56
#    Max Drawdown:   ~-8.6%
#    Win rate:       ~59.5%
#    Profit factor:  ~1.59
#    Antal trades:   ~964 över 14 år (~69/år)
#
#  DETTA RÄKNAS INTE SOM EN NY HYPOTES och kräver INGEN ny
#  K-räkning eller registerpost i hypothesis_registry - resultatet
#  ovan är redan etablerat FÖRE detta agent-system byggdes.
#
#  ANVÄNDNING: Strategy Builder / Kodare använder denna fil som
#  ÅTERANVÄNDBAR MALL/LOGIK när nya hypoteser (t.ex. HYP-008,
#  v6 på small-cap) ska implementeras på ett nytt universum.
#  ÄNDRA INTE denna fil direkt - kopiera och anpassa i en ny fil
#  under /strategies/HYP-XXX/ istället, så referens-kärnan
#  förblir orörd och verifierbar.
#
#  Ingen ejay, ingen Kelly-filtrering eller -sizing finns i denna
#  fil. Om en framtida hypotes vill testa filtrering/sizing ovanpå
#  detta, ska det ske som en EGEN, separat pre-registrerad
#  hypotes - inte genom att ändra i denna referensfil.
# ============================================================

import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

# ════════════════════════════════════════════════════════════
#  PARAMETRAR (identiska med de som redan validerats)
# ════════════════════════════════════════════════════════════
FULL_START     = "2010-01-01"
FULL_END       = "2024-01-01"

COINT_WINDOW   = 252   # dagar av historik som krävs för att
                       # identifiera samintegrerade par
ZSCORE_WINDOW  = 63    # rullande fönster för z-score-beräkning
MIN_PAIRS      = 3     # minsta antal korrelerade motparter för
                       # att en aktie ska få ett par-universum
CORR_THRESH    = 0.70  # min korrelation för att räknas som par
MAX_PAIRS      = 8     # max antal motparter per aktie i regressionen
TRADE_Z_THRESH = 1.5   # z-score-tröskel för att öppna en trade
STOP_LOSS      = 0.06  # hård stop-loss, 6% mot entry
MAX_POS        = 12    # max samtidiga öppna positioner
RF_ANNUAL      = 0.02  # riskfri ränta (för hedge-kostnad och cash)
BETA_WINDOW    = 126   # rullande fönster för beta-skattning mot SPY
FIXED_FRAC     = 0.05  # FAST positionsstorlek: 5% av tillgängligt
                       # kapital per trade. INGEN Kelly-sizing.

# TICKERS: byt ut mot nytt universum vid anpassning (t.ex.
# small-cap-tickers från EODHD för HYP-008). Denna referensfil
# använder large-cap-listan den ursprungligen validerades på.
TICKERS = [
    "AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMD", "INTC",
    "JPM",  "BAC",  "WFC",   "GS",   "MS",   "C",
    "JNJ",  "UNH",  "PFE",   "ABBV", "MRK",  "CVS",
    "CAT",  "HON",  "UPS",   "GE",   "MMM",
    "PG",   "KO",   "WMT",   "MCD",  "HD",
    "XOM",  "CVX",
]
HEDGE = "SPY"   # beta-hedge-instrument

# ════════════════════════════════════════════════════════════
#  DATA
# ════════════════════════════════════════════════════════════
def load_data(tickers, hedge, start, end):
    raw = yf.download(tickers + [hedge], start=start, end=end,
                      auto_adjust=True, progress=False)
    prices_all = raw["Close"].dropna(how="all", axis=1)
    spy    = prices_all[hedge]
    prices = prices_all[[t for t in tickers if t in prices_all.columns]]
    return prices, spy

# ════════════════════════════════════════════════════════════
#  PAR-IDENTIFIERING (månadsvis ombalanserad korrelationsfiltrering)
# ════════════════════════════════════════════════════════════
def identify_pairs(prices, log_ret, cointegration_window, min_pairs,
                   corr_thresh, max_pairs):
    rebal_dates   = prices.resample('M').last().index
    pairs_by_date = {}
    for rd in rebal_dates:
        mask = log_ret.index <= rd
        if mask.sum() < cointegration_window:
            continue
        corr = log_ret[mask].iloc[-cointegration_window:].corr()
        pd_ = {}
        for t in prices.columns:
            if t not in corr.columns:
                continue
            ct  = corr[t].drop(t).sort_values(ascending=False)
            top = ct[ct >= corr_thresh].head(max_pairs).index.tolist()
            if len(top) >= min_pairs:
                pd_[t] = top
        pairs_by_date[rd] = pd_
    return pairs_by_date

# ════════════════════════════════════════════════════════════
#  Z-SCORE (rullande OLS-regression, look-ahead-fri)
# ════════════════════════════════════════════════════════════
def compute_zscore(prices, log_p, pairs_by_date, cointegration_window,
                   zscore_window, tidx):
    DAYS, N = prices.shape
    rebal_list = sorted(pairs_by_date.keys())
    z_arr = np.full((DAYS, N), np.nan)

    for day_i, date in enumerate(prices.index):
        if day_i < cointegration_window:
            continue
        past = [r for r in rebal_list if r <= date]
        if not past:
            continue
        for t, pairs in pairs_by_date[past[-1]].items():
            ti = tidx[t]
            pi = [tidx[p] for p in pairs if p in tidx]
            if not pi:
                continue
            ws = max(0, day_i - zscore_window)
            y  = log_p.iloc[ws:day_i, ti].values
            X  = log_p.iloc[ws:day_i, pi].values
            if len(y) < 20 or np.any(np.isnan(y)) or np.any(np.isnan(X)):
                continue
            try:
                Xm = np.column_stack([np.ones(len(y)), X])
                coef, *_ = np.linalg.lstsq(Xm, y, rcond=None)

                # Historisk spread EXKLUSIVE dagens observation
                # (look-ahead-fix: parametrarna sätts på t-1-historik,
                # dagens värde används bara för att räkna ut dagens
                # z-score, aldrig för att skatta modellen)
                fh_hist     = coef[0] + X[:-1] @ coef[1:]
                spread_hist = y[:-1] - fh_hist
                spread_mean = spread_hist.mean()
                spread_std  = spread_hist.std()

                y_today      = log_p.iloc[day_i, ti]
                x_today      = log_p.iloc[day_i, pi].values
                fv_today     = coef[0] + np.dot(x_today, coef[1:])
                spread_today = y_today - fv_today

                if spread_std > 1e-6:
                    z_arr[day_i, ti] = (spread_today - spread_mean) / spread_std
            except Exception:
                continue
    return pd.DataFrame(z_arr, index=prices.index, columns=prices.columns)

# ════════════════════════════════════════════════════════════
#  BETA (rullande, mot hedge-instrumentet)
# ════════════════════════════════════════════════════════════
def compute_beta(prices, spy, beta_window):
    DAYS, N   = prices.shape
    spy_ret   = spy.pct_change()
    stock_ret = prices.pct_change()
    beta_arr  = np.full((DAYS, N), 1.0)
    for si in range(N):
        for i in range(beta_window, DAYS):
            rs  = stock_ret.iloc[i-beta_window:i, si].values
            rm  = spy_ret.iloc[i-beta_window:i].values
            msk = ~np.isnan(rs) & ~np.isnan(rm)
            if msk.sum() < 20:
                continue
            cov = np.cov(rs[msk], rm[msk])
            if cov[1, 1] > 1e-8:
                beta_arr[i, si] = cov[0, 1] / cov[1, 1]
    return pd.DataFrame(beta_arr, index=prices.index, columns=prices.columns)

# ════════════════════════════════════════════════════════════
#  BACKTEST-MOTOR (ingen ejay, ingen Kelly - fast storlek, FIXED_FRAC)
# ════════════════════════════════════════════════════════════
def run_v6_core(prices, spy, zscore_df, beta_df,
                trade_z_thresh, stop_loss, max_pos, fixed_frac,
                rf_annual, cointegration_window, beta_window):
    spy_ret  = spy.pct_change()
    mom_3d   = prices.pct_change(3)
    mom_10d  = prices.pct_change(10)
    rf_daily = rf_annual / 252
    tickers  = list(prices.columns)

    trade_state = pd.DataFrame(
        np.where(zscore_df.values < -trade_z_thresh,  1,
        np.where(zscore_df.values >  trade_z_thresh, -1, 0)),
        index=prices.index, columns=tickers)

    start_idx   = max(cointegration_window, beta_window)
    trade_dates = prices.index[start_idx:]

    cash, positions, pv_list, trade_log = 1.0, {}, [1.0], []

    for date in trade_dates:
        spy_r = float(spy_ret.loc[date]) if not np.isnan(spy_ret.loc[date]) else 0.0
        cash += cash * rf_daily

        # ── Stäng positioner ────────────────────────────────
        to_close = []
        for t, pos in positions.items():
            try:
                cp = float(prices.loc[date, t])
                cz = float(zscore_df.loc[date, t])
            except Exception:
                continue
            if np.isnan(cp):
                continue
            hit_stop   = cp <= pos['stop']
            hit_target = not np.isnan(cz) and abs(cz) < 0.3
            if hit_stop or hit_target:
                ret = cp / pos['entry'] - 1
                cash += pos['size'] * (cp / pos['entry'])
                to_close.append(t)
                trade_log.append({'date': date, 'ticker': t, 'ret': ret,
                                  'type': 'stop' if hit_stop else 'target'})
        for t in to_close:
            del positions[t]

        # ── Öppna nya positioner (fast storlek, inget filter) ──
        if len(positions) < max_pos:
            cands = []
            for t in tickers:
                if t in positions:
                    continue
                try:
                    cp   = float(prices.loc[date, t])
                    cz   = float(zscore_df.loc[date, t])
                    cst  = int(trade_state.loc[date, t])
                    cm3  = float(mom_3d.loc[date, t])
                    cm10 = float(mom_10d.loc[date, t])
                except Exception:
                    continue
                if any(np.isnan(x) for x in [cp, cz]):
                    continue
                if cst == 1 and cz < -trade_z_thresh:
                    mom_ok = (not np.isnan(cm3)  and cm3  > -0.04) or \
                             (not np.isnan(cm10) and cm10 > -0.06)
                    if not mom_ok:
                        continue
                    cands.append((abs(cz), t, cp))
            cands.sort(reverse=True)
            slots = max(0, max_pos - len(positions))
            for _, t, cp in cands[:slots]:
                sz = fixed_frac * cash    # FAST storlek - ingen Kelly
                if sz < 0.005:
                    continue
                cash -= sz
                positions[t] = {'entry': cp, 'size': sz,
                                'stop': cp * (1 - stop_loss)}

        # ── Portföljvärde (beta-neutral hedge mot SPY) ──────
        long_beta = sum(
            pos['size'] * float(prices.loc[date, t]) / pos['entry']
            * float(beta_df.loc[date, t])
            for t, pos in positions.items()
            if not np.isnan(float(prices.loc[date, t]))
        )
        hedge_pnl = -long_beta * spy_r - long_beta * (rf_annual / 2 / 252)
        long_val  = sum(
            pos['size'] * float(prices.loc[date, t]) / pos['entry']
            for t, pos in positions.items()
            if not np.isnan(float(prices.loc[date, t]))
        )
        pv_list.append(cash + long_val + hedge_pnl)

    pv = pd.Series(pv_list[1:], index=trade_dates)
    tl = pd.DataFrame(trade_log)
    return pv, tl

# ════════════════════════════════════════════════════════════
#  METRICS
# ════════════════════════════════════════════════════════════
def sharpe(s, rf=0.02):
    r = s.pct_change().dropna()
    return float(np.sqrt(252) * (r - rf/252).mean() / r.std()) if r.std() > 0 else 0.0

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
    wins   = tl[tl['ret'] > 0]['ret']
    losses = tl[tl['ret'] <= 0]['ret']
    pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 and losses.sum() != 0 else np.nan
    return dict(n=len(tl), win_rate=len(wins) / len(tl), avg_ret=tl['ret'].mean(), pf=pf)

# ════════════════════════════════════════════════════════════
#  KÖRNING (om filen körs direkt - reproducerar referensresultatet)
# ════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Kör v6-kärnan (referens, large-cap, ingen ejay, ingen Kelly)...")

    prices, spy = load_data(TICKERS, HEDGE, FULL_START, FULL_END)
    tickers     = list(prices.columns)
    tidx        = {t: i for i, t in enumerate(tickers)}
    log_p       = np.log(prices)
    log_ret     = log_p.diff()

    print(f"  {len(tickers)} aktier · {len(prices)} dagar")

    print("Identifierar par...")
    pairs_by_date = identify_pairs(prices, log_ret, COINT_WINDOW,
                                   MIN_PAIRS, CORR_THRESH, MAX_PAIRS)

    print("Beräknar z-score...")
    zscore_df = compute_zscore(prices, log_p, pairs_by_date,
                               COINT_WINDOW, ZSCORE_WINDOW, tidx)

    print("Estimerar beta...")
    beta_df = compute_beta(prices, spy, BETA_WINDOW)

    print("Kör backtest...")
    pv, tl = run_v6_core(prices, spy, zscore_df, beta_df,
                         TRADE_Z_THRESH, STOP_LOSS, MAX_POS, FIXED_FRAC,
                         RF_ANNUAL, COINT_WINDOW, BETA_WINDOW)

    ts = trade_stats(tl)
    print(f"\n{'═'*50}")
    print(f"  V6 CORE - REFERENSRESULTAT (large-cap, 2010-2024)")
    print(f"{'═'*50}")
    print(f"  CAGR:            {cagr(pv):+.1%}")
    print(f"  Sharpe:          {sharpe(pv):.2f}")
    print(f"  Calmar:          {calmar(pv):.2f}")
    print(f"  Max Drawdown:    {max_drawdown(pv):.1%}")
    print(f"  Antal trades:    {ts['n']}")
    print(f"  Win rate:        {ts['win_rate']:.1%}")
    print(f"  Snitt/trade:     {ts['avg_ret']:+.2%}")
    print(f"  Profit factor:   {ts['pf']:.2f}")
    print(f"{'═'*50}")
    print("\n  Om dessa siffror avviker markant från de tidigare")
    print("  dokumenterade referensvärdena (Sharpe ~0.55, CAGR ~4.8%),")
    print("  undersök INNAN du bygger vidare - något i miljön/datan")
    print("  kan ha förändrats sedan referensresultatet skapades.")
