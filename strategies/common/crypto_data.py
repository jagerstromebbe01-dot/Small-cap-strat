"""
Delad datamodul for spot-crypto-batchen (HYP-060..063, LAST 2026-08-11).

Anvander SAMMA redan betalda EODHD-nyckel/adapter (data/eodhd_adapter.py)
som resten av projektet - EODHDs .CC-endpoint for kryptospot, verifierad
fungera utan ny integration under feasibility-diskussionen 2026-08-11
INNAN batchen laste (BTC fran 2010-07-13, ETH fran 2015-08-07, LTC fran
2011-10-13, XRP fran 2013-08-05, DOGE fran 2013-12-15 - samtliga
verifierade direkt mot API:et, inte fran dokumentation).

KAND BEGRANSNING: marknadsvarde/fundamentals for crypto gav 403 Forbidden
pa denna EODHD-plan (verifierat 2026-08-11) - universumet i denna batch
ar darfor en STATISK, i forvag vald lista (langst tillforlitliga
spothistorik), INTE market-cap-bandad som small-cap-universumet.

build_baseline_basket() DELAS AVSIKTLIGT mellan HYP-061/062/063 (till
skillnad fran projektets vanliga monster att kopiera hypotesspecifik
kod per strategimapp) - de tre hypoteserna maste jamforas mot EXAKT
samma referenspunkt (5-coin likaviktad, kvartalsvis ombalanserad,
friktionsjusterad korg) for att jamforelserna ska vara meningsfulla,
och en delad funktion eliminerar risken for tyst avvikelse mellan tre
separata kopior av "samma" berkning.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "data"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eodhd_adapter import _get  # noqa: E402
from friction import corwin_schultz_spread  # noqa: E402
from rebalancing import snap_rebalance_dates  # noqa: E402

CACHE_DIR = REPO_ROOT / "data" / "cache" / "ohlcv_crypto"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

TICKERS = ["BTC-USD.CC", "ETH-USD.CC", "LTC-USD.CC", "XRP-USD.CC", "DOGE-USD.CC"]

MAIN_END = "2024-12-31"
OOS_START = "2025-01-01"
OOS_END = "2025-12-31"

RF_ANNUAL = 0.02
EXCHANGE_FEE = 0.0015  # 0.15% taker-avgift per affar, konservativ crypto-spotniva

# ANNUALISERING: 365 dagar/ar, INTE 252 som resten av registret - crypto
# handlas alla kalenderdagar (BTC-USD.CC har ~364.6 rader/ar over hela
# historiken, verifierat 2026-08-11), till skillnad fran aktiemarknadens
# handelsdagar. Sharpe/CAGR i denna batch ar darfor INTE direkt
# jamforbara med registrets ovriga (252-dagars) tal utan justering -
# medvetet, redovisat val, inte en bugg.
ANNUALIZATION_DAYS = 365


def load_crypto(ticker: str, start: str = "2009-01-01", end: str = OOS_END) -> pd.DataFrame:
    cache_path = CACHE_DIR / f"{ticker.replace('-USD.CC', '')}.csv"
    if cache_path.exists():
        df = pd.read_csv(cache_path, parse_dates=["date"]).set_index("date")
    else:
        data = _get(f"eod/{ticker}", {"from": start, "to": end, "period": "d"})
        if not isinstance(data, list) or not data:
            raise ValueError(f"Ingen data for {ticker}")
        df = pd.DataFrame(data).set_index("date")
        df.index = pd.to_datetime(df.index)
        df.to_csv(cache_path)
    return df.sort_index()


def transition_cost(high: float, low: float, notional_fraction: float) -> float:
    """Kostnad (som andel av totalt portfoljvarde) for att flytta
    notional_fraction av portfoljen in i/ut ur en position: halva
    Corwin-Schultz-spreaden (samma konvention som bear catcher) +
    EXCHANGE_FEE."""
    spread = corwin_schultz_spread(np.array([high, high]), np.array([low, low]))
    half_spread = float(np.nan_to_num(spread[-1], nan=0.0)) / 2.0
    return notional_fraction * (half_spread + EXCHANGE_FEE)


def build_baseline_basket(price_data: dict) -> pd.Series:
    """5-coin likaviktad, KVARTALSVIS ombalanserad korg, friktionsjusterad.
    price_data: {ticker: DataFrame med close/high/low, indexerad pa datum}.
    Gemensamt fonster = fran forsta datum dar ALLA fem tickers har data.

    Detta ar den DELADE referenspunkten for HYP-061 (utan overlay),
    HYP-062 och HYP-063 - se moduldocstring."""
    closes = pd.DataFrame({t: price_data[t]["close"] for t in TICKERS}).dropna()
    common_start = closes.index[0]

    calendar_dates = closes.resample("QE").last().index
    snapped = snap_rebalance_dates(calendar_dates, closes.index)
    rebal_dates = sorted(set(snapped["execution_date"]) & set(closes.loc[common_start:].index))

    weights = pd.Series(0.0, index=TICKERS)
    equity = 1.0
    values = []
    dates = []
    prev_close = None

    for date in closes.loc[common_start:].index:
        row = closes.loc[date]
        if prev_close is not None:
            asset_ret = (row / prev_close - 1.0).fillna(0.0)
            equity *= (1.0 + float((weights * asset_ret).sum()))

        if date in rebal_dates:
            target = pd.Series(1.0 / len(TICKERS), index=TICKERS)
            turnover = (target - weights).abs().sum() / 2.0
            if turnover > 0:
                for t in TICKERS:
                    delta = abs(target[t] - weights[t])
                    if delta > 1e-12:
                        h, l = price_data[t].loc[date, "high"], price_data[t].loc[date, "low"]
                        equity *= (1.0 - transition_cost(h, l, delta))
            weights = target

        values.append(equity)
        dates.append(date)
        prev_close = row

    return pd.Series(values, index=dates)


def sharpe(s, rf=RF_ANNUAL):
    r = s.pct_change().dropna()
    return float(np.sqrt(ANNUALIZATION_DAYS) * (r - rf / ANNUALIZATION_DAYS).mean() / r.std()) if r.std() > 0 else 0.0


def max_drawdown(s):
    return float(((s - s.cummax()) / s.cummax()).min())


def cagr(s):
    return float((s.iloc[-1] / s.iloc[0]) ** (ANNUALIZATION_DAYS / len(s)) - 1)


def calmar(s):
    md = abs(max_drawdown(s))
    return cagr(s) / md if md > 0 else 0.0
