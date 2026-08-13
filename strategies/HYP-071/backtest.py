"""
HYP-071: Nettoemissionsflode (nyemission minus aterkop / marknadsvarde)
som exponeringsoverlagg pa HYP-056.

Se research/hypothesis_registry/HYP-071-nettoemission-overlay-hyp056.yaml
for det lasta kriteriet.

MEKANISM (lockad): kvartalsvis aggregat over hela small-cap-universumet:
(senaste FY-nyemission - senaste FY-aterkop) / aggregerat marknadsvarde.
Jamfor mot egen rullande 12-kvartals (3-ars) historik - overre tercilen
(>66.7:e percentilen) -> 40% exponering pa HYP-056:s portfolj, annars
100%. Ingen aterinträdeslogik - tercilstatus omprovas varje kvartal.

INGEN NY BACKTEST-MOTOR for sjalva overlayn (ren exponeringsskalning pa
HYP-056:s redan berknade serier) - signalen sjalv byggs dock over hela
universumet (aggregat, inte per-aktie-urval).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

STRATEGY_DIR = Path(__file__).resolve().parent
STRATEGIES_ROOT = STRATEGY_DIR.parent
REPO_ROOT = STRATEGIES_ROOT.parent
DATA_DIR = REPO_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
OHLCV_DIR = CACHE_DIR / "ohlcv"
UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_by_month.json"
UNIVERSE_2025_FILE = CACHE_DIR / "smallcap_universe_2025_extension.json"
BUYBACK_FILE = CACHE_DIR / "buyback_by_ticker.jsonl"
ISSUANCE_FILE = CACHE_DIR / "issuance_by_ticker.jsonl"
RESULTS_DIR = STRATEGY_DIR / "results"

HYP056_RESULTS = STRATEGIES_ROOT / "HYP-056" / "results"

RF_ANNUAL = 0.02
HAIRCUT = 0.40  # samma niva som HYP-037/045
TERCILE_THRESHOLD = 2.0 / 3.0
ROLLING_QUARTERS = 12
OOS_START = "2025-01-01"


def load_universe():
    with UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_orig = json.load(f)
    with UNIVERSE_2025_FILE.open(encoding="utf-8") as f:
        universe_2025 = json.load(f)
    return {**universe_orig, **universe_2025}


def load_annual_series(path: Path, value_key: str) -> dict:
    """Per ticker: sorterad [(filed, val)] - generisk laddare for
    aterkop/emission (bagge bygger pa samma FY/10-K-struktur)."""
    out = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            entries = row.get(value_key, [])
            pairs = sorted([(e["filed"], e["val"]) for e in entries if e.get("val") is not None])
            if pairs:
                out[row["ticker"]] = pairs
    return out


def load_shares_series() -> dict:
    """Aktieantal ligger i buyback_by_ticker.jsonl (redan hamtat dar)."""
    out = {}
    if not BUYBACK_FILE.exists():
        return out
    with BUYBACK_FILE.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            sh = sorted([(e["filed"], e["val"]) for e in row.get("shares_outstanding", [])
                         if e.get("val") not in (None, 0)])
            if sh:
                out[row["ticker"]] = sh
    return out


def _asof(sorted_pairs, as_of_date_str):
    if not sorted_pairs:
        return None
    import bisect
    dates = [p[0] for p in sorted_pairs]
    idx = bisect.bisect_left(dates, as_of_date_str) - 1
    if idx < 0:
        return None
    return sorted_pairs[idx][1]


def load_close_prices(tickers, start, end) -> pd.DataFrame:
    hedge_path = OHLCV_DIR / "SPY.csv"
    dates_all = pd.read_csv(hedge_path, usecols=["date"], parse_dates=["date"])["date"].drop_duplicates().sort_values()
    date_index = pd.DatetimeIndex(dates_all[(dates_all >= start) & (dates_all <= end)])

    close_s = {}
    for t in tickers:
        path = OHLCV_DIR / f"{t}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path, usecols=["date", "close"], parse_dates=["date"])
        df = df.drop_duplicates(subset="date", keep="last").set_index("date").sort_index()
        close_s[t] = df["close"].astype("float32")
    return pd.DataFrame(close_s).reindex(date_index)


def compute_net_flow_signal(universe_by_month, close, buyback, issuance, shares):
    """Returnerar en pd.Series indexerad pa kvartalsslutsdatum:
    (aggregerad emission - aggregerad aterkop) / aggregerat marknadsvarde."""
    quarter_ends = sorted(universe_by_month.keys())
    rows = []
    for q in quarter_ends:
        as_of = q
        tickers = universe_by_month[q]
        # anvand narmast foregaende handelsdag <= kvartalsslutet for pris
        idx = close.index[close.index <= pd.Timestamp(q)]
        if len(idx) == 0:
            continue
        price_date = idx[-1]

        total_issuance, total_buyback, total_mcap = 0.0, 0.0, 0.0
        for t in tickers:
            if t not in close.columns:
                continue
            price = close.loc[price_date, t]
            if pd.isna(price) or price <= 0:
                continue
            sh_val = _asof(shares.get(t, []), as_of)
            if sh_val is None or sh_val <= 0:
                continue
            mcap = price * sh_val
            total_mcap += mcap
            iss_val = _asof(issuance.get(t, []), as_of)
            bb_val = _asof(buyback.get(t, []), as_of)
            if iss_val is not None and iss_val > 0:
                total_issuance += iss_val
            if bb_val is not None and bb_val > 0:
                total_buyback += bb_val

        if total_mcap > 0:
            rows.append({"date": pd.Timestamp(q), "net_flow_ratio": (total_issuance - total_buyback) / total_mcap})

    return pd.DataFrame(rows).set_index("date")["net_flow_ratio"]


def compute_exposure_schedule(net_flow: pd.Series) -> pd.Series:
    """Overre tercilen av EGEN rullande 12-kvartals historik -> haircut."""
    exposure = pd.Series(index=net_flow.index, dtype=float)
    for i, date in enumerate(net_flow.index):
        window = net_flow.iloc[max(0, i - ROLLING_QUARTERS + 1):i + 1]
        if len(window) < 4:  # otillrackligt historik -> full exponering
            exposure.loc[date] = 1.0
            continue
        rank = (window < window.iloc[-1]).sum() / len(window)
        exposure.loc[date] = HAIRCUT if rank >= TERCILE_THRESHOLD else 1.0
    return exposure


def apply_overlay(pv: pd.Series, exposure_quarterly: pd.Series, rf_annual=RF_ANNUAL) -> pd.Series:
    """Applicerar kvartalsvis exponering pa en daglig portfoljvardesserie
    - exponeringen hallen konstant mellan beslutsdatum (ffill), och galler
    FRAMAT fran varje beslut (ingen look-ahead: beslutet pa datum t
    anvander bara data KAND vid t, se compute_net_flow_signal)."""
    daily_exposure = exposure_quarterly.reindex(pv.index, method="ffill").fillna(1.0)
    raw_ret = pv.pct_change().fillna(0.0)
    values, dates = [1.0], [pv.index[0]]
    for i in range(1, len(pv)):
        date = pv.index[i]
        r = raw_ret.iloc[i]
        f = daily_exposure.loc[date]
        blended = f * r + (1 - f) * (rf_annual / 252)
        values.append(values[-1] * (1 + blended))
        dates.append(date)
    return pd.Series(values[1:], index=dates[1:])


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


HYP056_MAIN_REF = {
    100_000: {"sharpe": 1.2228, "max_drawdown": -0.0592},
    1_000_000: {"sharpe": 1.2177, "max_drawdown": -0.0602},
    10_000_000: {"sharpe": 1.1923, "max_drawdown": -0.0564},
}
HYP056_OOS_REF = {100_000: 1.7585, 1_000_000: 1.7379, 10_000_000: 1.7579}


def main():
    print("Laddar universum (grundsanning 2010-2024 + 2025-utokning)...")
    universe_by_month = load_universe()
    all_tickers = sorted({t for tickers in universe_by_month.values() for t in tickers})
    print(f"  {len(universe_by_month)} manader, {len(all_tickers)} unika tickers.\n")

    print("Laddar stangningskurser...")
    close = load_close_prices(all_tickers, "2010-01-01", "2025-12-31")
    print(f"  Prismatris: {close.shape}\n")

    print("Laddar aterkop/emission/aktieantal...")
    buyback = load_annual_series(BUYBACK_FILE, "buybacks")
    issuance = load_annual_series(ISSUANCE_FILE, "issuance")
    shares = load_shares_series()
    print(f"  {len(buyback)} med aterkopsdata, {len(issuance)} med emissionsdata, {len(shares)} med aktieantal.\n")

    print("Berknar aggregerad netto-flode-signal (kvartalsvis, over hela universumet)...")
    net_flow = compute_net_flow_signal(universe_by_month, close, buyback, issuance, shares)
    print(f"  {len(net_flow)} kvartal berknade.\n")
    net_flow.to_csv(RESULTS_DIR / "net_flow_signal.csv", header=["net_flow_ratio"])

    exposure = compute_exposure_schedule(net_flow)
    exposure.to_csv(RESULTS_DIR / "quarterly_exposure_schedule.csv", header=["exposure"])
    pct_haircut = float((exposure < 1.0).mean())
    print(f"  Andel kvartal i haircut-lage: {pct_haircut:.1%}\n")

    main_results, oos_results = [], []
    for level in [100_000, 1_000_000, 10_000_000]:
        pv_main = pd.read_csv(HYP056_RESULTS / f"portfolio_value_combined_scaled_{level}.csv",
                               index_col=0, parse_dates=True)["portfolio_value"]
        pv_oos = pd.read_csv(HYP056_RESULTS / f"portfolio_value_oos2025_combined_scaled_{level}.csv",
                              index_col=0, parse_dates=True)["portfolio_value"]

        scaled_main = apply_overlay(pv_main, exposure)
        scaled_oos = apply_overlay(pv_oos, exposure)

        scaled_main.to_csv(RESULTS_DIR / f"portfolio_value_overlay_main_{level}.csv", header=["portfolio_value"])
        scaled_oos.to_csv(RESULTS_DIR / f"portfolio_value_overlay_oos2025_{level}.csv", header=["portfolio_value"])

        m = {"capital_level": level, "sharpe": sharpe(scaled_main), "cagr": cagr(scaled_main),
             "max_drawdown": max_drawdown(scaled_main), "calmar": calmar(scaled_main)}
        main_results.append(m)
        o = {"capital_level": level, "oos_2025_sharpe": sharpe(scaled_oos),
             "oos_2025_total_return": float(scaled_oos.iloc[-1] / scaled_oos.iloc[0] - 1)}
        oos_results.append(o)

        ref = HYP056_MAIN_REF[level]
        ref_oos = HYP056_OOS_REF[level]
        g1 = m["sharpe"] >= ref["sharpe"]
        g2 = m["max_drawdown"] > ref["max_drawdown"]
        g3 = o["oos_2025_sharpe"] > ref_oos
        print(f"  ${level:>10,.0f}  Sharpe={m['sharpe']:.4f} ({'PASS' if g1 else 'FAIL'} vs {ref['sharpe']:.4f})  "
              f"MaxDD={m['max_drawdown']:.2%} ({'PASS' if g2 else 'FAIL'} vs {ref['max_drawdown']:.2%})  "
              f"OOS-Sharpe={o['oos_2025_sharpe']:.4f} ({'PASS' if g3 else 'FAIL'} vs {ref_oos:.4f})  "
              f"CAGR={m['cagr']:+.2%}")

    lvl = 100_000
    m100k = main_results[0]
    o100k = oos_results[0]
    ref = HYP056_MAIN_REF[lvl]
    ref_oos = HYP056_OOS_REF[lvl]
    all_pass = all(
        main_results[i]["sharpe"] >= HYP056_MAIN_REF[main_results[i]["capital_level"]]["sharpe"]
        and main_results[i]["max_drawdown"] > HYP056_MAIN_REF[main_results[i]["capital_level"]]["max_drawdown"]
        and oos_results[i]["oos_2025_sharpe"] > HYP056_OOS_REF[main_results[i]["capital_level"]]
        for i in range(3)
    )
    overall = "PASSED" if all_pass else "FAILED"
    print(f"\n=== SLUTBEDOMNING (alla tre villkor maste halla PA ALLA TRE NIVAER) === -> {overall}\n")

    summary = {
        "main": main_results, "oos_2025": oos_results, "hyp056_main_ref": HYP056_MAIN_REF,
        "hyp056_oos_ref": HYP056_OOS_REF, "pct_quarters_haircut": pct_haircut,
        "pass_fail": {"overall": overall},
    }
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
