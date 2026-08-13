#!/usr/bin/env python3
"""
FAS A-diagnostik for CEO:s idé 2026-08-10 ("identifiera marknader med
liknande egenskaper som small-cap, lana strategier darifran"). INGEN
K-kostnad - detta ar en ren karakteristikjamforelse, ingen strategi
testas har.

Fyra matt, valda for att vara berakningsbara pa ALLA tre marknader utan
att behova marknadsvarde (som saknas rent for crypto via EODHD utan en
separat fundamentals-anrop per coin):
  1. Annualiserad realiserad volatilitet
  2. Genomsnittlig Corwin-Schultz bid-ask-spread-proxy
  3. Forsta ordningens autokorrelation i dagsavkastning (Lo-MacKinlay-
     illikviditetsproxy - negativ/nara-noll autokorrelation antyder
     kontinuerlig prisbildning, positiv antyder trog/illikvid prisbildning)
  4. Volymens variationskoefficient (std/medel av daglig volym) - grov
     "oregelbunden likviditet"-proxy

Gemensamt fonster 2021-01-01 till 2024-12-31 (4 ar) for rattvis
jamforelse - de flesta crypto-altcoins saknar tillforlitlig historik
fore 2020-2021.
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "data"))
sys.path.insert(0, str(REPO_ROOT / "strategies" / "HYP-037"))
sys.path.insert(0, str(REPO_ROOT / "strategies" / "common"))

from eodhd_adapter import _get, get_smallcap_universe, get_daily_ohlcv  # noqa: E402
from friction import corwin_schultz_spread  # noqa: E402
import backtest as hyp037  # noqa: E402

START, END = "2021-01-01", "2024-12-31"
CACHE = REPO_ROOT / "data" / "cache" / "ohlcv"

CRYPTO_TICKERS = ["SOL-USD", "ADA-USD", "DOT-USD", "AVAX-USD", "LINK-USD",
                   "ATOM-USD", "ALGO-USD", "XLM-USD", "LTC-USD", "XRP-USD"]
HIGHYIELD_TICKERS = ["HYG", "JNK", "ANGL"]  # high-yield/distressed foretagsobligations-ETF:er


def fetch_crypto(ticker: str) -> pd.DataFrame:
    path = CACHE / f"{ticker.replace('-USD', '_crypto')}.csv"
    if path.exists():
        return pd.read_csv(path, parse_dates=["date"]).set_index("date")
    data = _get(f"eod/{ticker}.CC", {"from": START, "to": END, "period": "d"})
    if not isinstance(data, list) or not data:
        return pd.DataFrame()
    df = pd.DataFrame(data).set_index("date")
    df.index = pd.to_datetime(df.index)
    df.to_csv(path)
    time.sleep(0.3)
    return df


def characteristics(close: pd.Series, high: pd.Series, low: pd.Series, volume: pd.Series) -> dict:
    ret = close.pct_change().dropna()
    if len(ret) < 30:
        return {}
    ann_vol = float(ret.std() * np.sqrt(252))
    spread = corwin_schultz_spread(high.values, low.values)
    avg_spread = float(np.nanmean(spread))
    autocorr = float(ret.autocorr(lag=1))
    vol_cv = float(volume.std() / volume.mean()) if volume.mean() > 0 else np.nan
    return {"ann_vol": ann_vol, "avg_spread": avg_spread, "autocorr_lag1": autocorr, "volume_cv": vol_cv}


def main():
    print("=== FAS A: marknadskaraktäristik-jämförelse (2021-2024) ===\n")

    # --- Guld (GLD, redan cachead) ---
    gld = pd.read_csv(CACHE / "GLD.csv", parse_dates=["date"]).set_index("date")
    gld = gld.loc[START:END]
    gold_chars = characteristics(gld["adjusted_close"], gld["high"], gld["low"], gld["volume"])
    print(f"GULD (GLD-proxy): {gold_chars}\n")

    # --- Crypto (basket, medel över tickers) ---
    crypto_chars_list = []
    for t in CRYPTO_TICKERS:
        try:
            df = fetch_crypto(t)
            if df.empty:
                print(f"  {t}: ingen data, hoppar över")
                continue
            df = df.loc[START:END]
            c = characteristics(df["adjusted_close"], df["high"], df["low"], df["volume"])
            if c:
                crypto_chars_list.append(c)
                print(f"  {t}: {c}")
        except Exception as e:
            print(f"  {t}: FEL - {e}")
    crypto_avg = {k: float(np.mean([c[k] for c in crypto_chars_list])) for k in crypto_chars_list[0]} if crypto_chars_list else {}
    print(f"\nCRYPTO (medel över {len(crypto_chars_list)} altcoins): {crypto_avg}\n")

    # --- High-yield/distressed företagsobligationer (ETF-proxy) ---
    hy_chars_list = []
    for t in HIGHYIELD_TICKERS:
        path = CACHE / f"{t}.csv"
        if path.exists():
            df = pd.read_csv(path, parse_dates=["date"]).set_index("date")
        else:
            data = get_daily_ohlcv(t, START, END)
            if not data:
                print(f"  {t}: ingen data, hoppar över")
                continue
            df = pd.DataFrame(data).set_index("date")
            df.index = pd.to_datetime(df.index)
            df.to_csv(path)
        df = df.loc[START:END]
        c = characteristics(df["adjusted_close"], df["high"], df["low"], df["volume"])
        if c:
            hy_chars_list.append(c)
            print(f"  {t}: {c}")
    hy_avg = {k: float(np.mean([c[k] for c in hy_chars_list])) for k in hy_chars_list[0]} if hy_chars_list else {}
    print(f"\nHIGH-YIELD-OBLIGATIONER (medel över {len(hy_chars_list)} ETF:er): {hy_avg}\n")

    # --- Micro-cap ($10M-$100M, fräsch sampling, begränsad för tid/kostnad) ---
    print("Hämtar micro-cap-sample ($10M-$100M, kan ta någon minut pga fundamentals-anrop)...")
    microcap_universe = get_smallcap_universe(min_cap=10_000_000, max_cap=100_000_000, limit=250, request_delay=0.5)
    microcap_tickers = [row["Code"] for row in microcap_universe][:80]
    print(f"  {len(microcap_tickers)} micro-cap-namn hittade (av 250 skannade).")

    micro_chars_list = []
    if microcap_tickers:
        mclose, mclose_adj, mhigh, mlow, mvolume = hyp037.load_price_matrices(microcap_tickers, START, END)
        mclose, mhigh, mlow = hyp037.clean_price_matrix(mclose, mhigh, mlow, volume=mvolume)
        mclose_adj = mclose_adj.where(mclose.notna())
        for t in microcap_tickers:
            if t not in mclose_adj.columns:
                continue
            c = characteristics(mclose_adj[t].dropna(), mhigh[t], mlow[t], mvolume[t])
            if c and not any(np.isnan(v) for v in c.values()):
                micro_chars_list.append(c)
    micro_avg = {k: float(np.median([c[k] for c in micro_chars_list])) for k in micro_chars_list[0]} if micro_chars_list else {}
    print(f"MICRO-CAP (median över {len(micro_chars_list)} namn): {micro_avg}\n")

    # --- Small-cap (sample av universum, samma period) ---
    import json
    with hyp037.CACHE_DIR.joinpath("smallcap_universe_by_month_filed_date.json").open(encoding="utf-8") as f:
        universe = json.load(f)
    with hyp037.CACHE_DIR.joinpath("smallcap_universe_2025_extension_filed_date.json").open(encoding="utf-8") as f:
        universe.update(json.load(f))
    recent_key = max(k for k in universe if k <= "2024-12-31")
    sample_tickers = sorted(universe[recent_key])[:300]  # sampla 300 för hastighet, inte hela ~5000

    close, close_adj, high, low, volume = hyp037.load_price_matrices(sample_tickers, START, END)
    close, high, low = hyp037.clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())

    per_ticker = []
    for t in sample_tickers:
        if t not in close_adj.columns:
            continue
        c = characteristics(close_adj[t].dropna(), high[t], low[t], volume[t])
        if c and not any(np.isnan(v) for v in c.values()):
            per_ticker.append(c)

    smallcap_chars = {k: float(np.median([c[k] for c in per_ticker])) for k in per_ticker[0]} if per_ticker else {}
    print(f"SMALL-CAP (median över {len(per_ticker)} namn, sample av {recent_key}): {smallcap_chars}\n")

    # --- Likhetsjämförelse ---
    print("=== LIKHETSJÄMFÖRELSE (relativ avvikelse mot small-cap, lägre = mer likt) ===\n")
    for name, chars in [("GULD", gold_chars), ("CRYPTO", crypto_avg), ("HIGH-YIELD", hy_avg), ("MICRO-CAP", micro_avg)]:
        if not chars or not smallcap_chars:
            continue
        print(f"{name}:")
        total_abs_pct_diff = 0.0
        for k in smallcap_chars:
            sc_val, other_val = smallcap_chars[k], chars.get(k)
            if other_val is None:
                continue
            pct_diff = abs(other_val - sc_val) / (abs(sc_val) + 1e-9) * 100
            total_abs_pct_diff += pct_diff
            print(f"  {k}: small-cap={sc_val:.4f}  {name.lower()}={other_val:.4f}  avvikelse={pct_diff:.0f}%")
        print(f"  SUMMA avvikelse: {total_abs_pct_diff:.0f}%\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
