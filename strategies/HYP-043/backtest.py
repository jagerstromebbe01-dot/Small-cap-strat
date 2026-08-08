"""
HYP-043: Naiv tredelad kombination (kvartalsvis ombalanserad) - SPY +
HYP-037 + momentum long/short-svit (egenbyggd, ej ETF-proxy).

Se research/hypothesis_registry/HYP-043-naiv-kombination-spy-hyp037-momentum-ls.yaml
for det lasta kriteriet. Tredje kombinationshypotesen i projektet (efter
HYP-039, HYP-041), per spec §5b - korrelation berknad FORE lasning,
naiv (ej in-sample-optimerad) vikt, egen K-kostnad.

Momentum L/S-sviten byggs fran grunden (INTE en redan kand serie som
SPY/TLT var) - 12-1-manaders momentum, long topp-decil/kort botten-
decil, dollar-neutralt, kvartalsvis, over small-cap-universumet. Bygger
vidare pa scripts/diagnostic_momentum_long_short_daily.py (samma
mekanism, verifierad look-ahead-fri och sanerad mot den nya "konstant
orimlig adjusted_close/close-kvot"-buggklassen som hittades under
HYP-042:s bygge samma dag).

EN enda genomgang av hela 2010-2025-perioden med det SAMMANSLAGNA
universumet (huvudserie + 2025-utokning) racker for bade huvudtest och
OOS - eftersom 2025-utokningens nycklar bara LAGGER TILL 2025-manader,
paverkar den aldrig 2010-2024-eligibiliteten (samma logik som HYP-037:s
egen OOS-metod).
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
RESULTS_DIR = STRATEGY_DIR / "results_corrected_2026-08-08"

HYP037_DIR = STRATEGIES_ROOT / "HYP-037"
HYP037_RESULTS = HYP037_DIR / "results_corrected_2026-08-08"
HYP037_OOS_RESULTS = REPO_ROOT / "paper_trading" / "HYP-037" / "oos_2025_results"

# GRANSKNINGSFYND 2026-08-08: filed-datum-korrigerade universumfiler
# (samma fix som HYP-037:s egen UNIVERSE_FILE, se dess backtest.py) -
# denna fils EGNA momentum L/S-svit byggs fran grunden och laddade
# tidigare den periodslut-daterade (look-ahead-biasade) originalfilen.
ORIGINAL_UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_by_month_filed_date.json"
EXTENSION_UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_2025_extension_filed_date.json"

sys.path.insert(0, str(HYP037_DIR))
import backtest as hyp037  # noqa: E402
from friction import borrow_cost  # noqa: E402

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
from rebalancing import snap_rebalance_dates  # noqa: E402
from data_hygiene import mask_implausible_adjusted_close_ratio  # noqa: E402

REBAL_FREQ = "QE"
WEIGHT_EACH = 1.0 / 3.0

# GRANSKNINGSFYND 2026-08-08: portfoljniva-ombalansering (combine_thirds
# nedan) hade NOLL transaktionskostnad - se HYP-039:s identiska kommentar
# for full motivering. Samma 10bps-schablon ateranvand konsekvent i alla
# sju kombinationshypoteser.
REBALANCE_COST_BPS = 0.0010

MOM_LOOKBACK_DAYS = 252
MOM_SKIP_DAYS = 21
DECILE_FRACTION = 0.10
BORROW_ANNUAL_RATE = 0.03
RF_ANNUAL = 0.02

OOS_START = "2025-01-01"
FULL_END_WITH_OOS = "2025-12-31"

# HYP-039:s EGNA redan registrerade varden - jamforelsepunkten
HYP039_REF = {
    100_000: {"sharpe": 1.0191, "max_drawdown": -0.2203, "oos_2025_sharpe": 0.9185},
    1_000_000: {"sharpe": 1.0300, "max_drawdown": -0.2216, "oos_2025_sharpe": 0.8116},
    10_000_000: {"sharpe": 0.9879, "max_drawdown": -0.2003, "oos_2025_sharpe": 0.7932},
}


def compute_momentum_ls_sleeve(universe_by_month: dict) -> pd.Series:
    """Bygger momentum L/S-sviten over HELA 2010-2025-perioden med det
    givna (eventuellt sammanslagna) universumet. Samma mekanism som
    scripts/diagnostic_momentum_long_short_daily.py.

    BUGGVAKT: tickerlistan harleds fran DET GIVNA universum-by-month-
    dictet (inte fran hyp037.load_universe()'s egen, ENDAST 2010-2024-
    baserade lista) - annars skulle tickers som bara finns i 2025-
    utokningen (inte i huvudserien) tyst saknas fran prismatrisen,
    exakt samma princip som HYP-037:s egen oos_backtest_2025.py redan
    tillampar."""
    tickers = sorted({t for tks in universe_by_month.values() for t in tks})
    close, close_adj, high, low, volume = hyp037.load_price_matrices(tickers, hyp037.FULL_START, FULL_END_WITH_OOS)

    close, high, low = hyp037.clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    implausible = hyp037.flag_implausible_liquidity(close, volume, max_market_cap=hyp037.MAX_MARKET_CAP,
                                                      window=hyp037.ADV_WINDOW, multiplier=1.0)
    close_adj = close_adj.mask(implausible)
    close_adj = mask_implausible_adjusted_close_ratio(close, close_adj)

    momentum = close_adj.shift(MOM_SKIP_DAYS) / close_adj.shift(MOM_LOOKBACK_DAYS) - 1
    daily_ret = close_adj.pct_change()

    tidx = {t: i for i, t in enumerate(close.columns)}
    calendar_dates = close.resample(REBAL_FREQ).last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[MOM_LOOKBACK_DAYS])
                                     & (calendar_dates <= close.index[-1])]
    snapped = snap_rebalance_dates(calendar_dates, close.index)
    rebal_map = dict(zip(snapped["execution_date"], snapped["calendar_label"]))
    rebal_set = set(snapped["execution_date"])

    start_idx = close.index.get_indexer([snapped["execution_date"].iloc[0]])[0]
    trade_dates = close.index[start_idx:]

    long_names, short_names = [], []
    pv_list = [1.0]

    for date_i in range(start_idx, len(close.index)):
        date = close.index[date_i]

        if date in rebal_set:
            month_key = rebal_map[date].strftime("%Y-%m-%d")
            eligible = [t for t in universe_by_month.get(month_key, []) if t in tidx]
            mom_today = momentum.loc[date, eligible].dropna()
            if len(mom_today) >= 20:
                ranked = mom_today.sort_values()
                n_decile = max(1, int(len(ranked) * DECILE_FRACTION))
                short_names = list(ranked.index[:n_decile])
                long_names = list(ranked.index[-n_decile:])

        if date_i > start_idx and (long_names or short_names):
            long_r = daily_ret.loc[date, long_names].mean() if long_names else 0.0
            short_r = daily_ret.loc[date, short_names].mean() if short_names else 0.0
            long_r = 0.0 if np.isnan(long_r) else long_r
            short_r = 0.0 if np.isnan(short_r) else short_r
            daily_borrow = borrow_cost(position_value=0.5, holding_days=1, annual_rate=BORROW_ANNUAL_RATE)
            period_ret = 0.5 * long_r - 0.5 * short_r - daily_borrow + (RF_ANNUAL / 252)
            pv_list.append(pv_list[-1] * (1 + period_ret))
        else:
            pv_list.append(pv_list[-1])

    return pd.Series(pv_list[1:], index=trade_dates)


def load_spy(start=None, end=None):
    s = hyp037.load_hedge(hyp037.FULL_START, FULL_END_WITH_OOS)
    if start is not None or end is not None:
        s = s.loc[start:end]
    return s


def combine_thirds(spy_price, hyp037_pv, mom_ls_pv, start_capital=1.0):
    df = pd.concat([spy_price.rename("spy"), hyp037_pv.rename("hyp037"), mom_ls_pv.rename("mom_ls")],
                    axis=1, join="inner").dropna()
    spy_ret = df["spy"].pct_change()
    hyp_ret = df["hyp037"].pct_change()
    mom_ret = df["mom_ls"].pct_change()

    calendar_dates = df.resample(REBAL_FREQ).last().index
    snapped = snap_rebalance_dates(calendar_dates, df.index)
    rebal_set = set(snapped["execution_date"])

    spy_leg = start_capital * WEIGHT_EACH
    hyp_leg = start_capital * WEIGHT_EACH
    mom_leg = start_capital * WEIGHT_EACH
    values, dates = [], []

    for i in range(1, len(df)):
        date = df.index[i]
        r_spy, r_hyp, r_mom = spy_ret.iloc[i], hyp_ret.iloc[i], mom_ret.iloc[i]
        if not np.isnan(r_spy):
            spy_leg *= (1 + r_spy)
        if not np.isnan(r_hyp):
            hyp_leg *= (1 + r_hyp)
        if not np.isnan(r_mom):
            mom_leg *= (1 + r_mom)
        total = spy_leg + hyp_leg + mom_leg
        if date in rebal_set:
            target_spy = total * WEIGHT_EACH
            target_hyp = total * WEIGHT_EACH
            target_mom = total * WEIGHT_EACH
            turnover = abs(target_spy - spy_leg) + abs(target_hyp - hyp_leg) + abs(target_mom - mom_leg)
            total -= turnover * REBALANCE_COST_BPS
            spy_leg = total * WEIGHT_EACH
            hyp_leg = total * WEIGHT_EACH
            mom_leg = total * WEIGHT_EACH
        values.append(total)
        dates.append(date)

    return pd.Series(values, index=dates)


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


def main():
    print("Laddar universum (huvudserie + 2025-utokning, sammanslaget)...")
    with ORIGINAL_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_orig = json.load(f)
    with EXTENSION_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_2025 = json.load(f)
    universe_merged = {**universe_orig, **universe_2025}

    print("Bygger momentum L/S-sviten over HELA 2010-2025 (en genomgang racker, se moduldocstring)...")
    mom_ls_full = compute_momentum_ls_sleeve(universe_merged)
    RESULTS_DIR.mkdir(exist_ok=True)
    mom_ls_full.to_csv(RESULTS_DIR / "momentum_ls_sleeve_pv.csv", header=["portfolio_value"])
    print(f"  {len(mom_ls_full)} dagar, {mom_ls_full.index[0].date()} till {mom_ls_full.index[-1].date()}\n")

    spy_full = load_spy()
    levels = [100_000, 1_000_000, 10_000_000]

    print("=== HYP-043: huvudbacktest (2010-2024) ===")
    main_results = []
    for level in levels:
        hyp037_pv = pd.read_csv(HYP037_RESULTS / f"portfolio_value_{level}.csv",
                                 index_col=0, parse_dates=True)["portfolio_value"]
        combined = combine_thirds(spy_full, hyp037_pv, mom_ls_full)
        combined.to_csv(RESULTS_DIR / f"portfolio_value_combined_{level}.csv", header=["portfolio_value"])

        r = {"capital_level": level, "sharpe": sharpe(combined), "cagr": cagr(combined),
             "max_drawdown": max_drawdown(combined), "calmar": calmar(combined), "n_days": len(combined)}
        main_results.append(r)
        ref = HYP039_REF[level]
        g1 = "PASS" if r["sharpe"] >= 1.0 else "FAIL"
        g2 = "PASS" if r["sharpe"] > ref["sharpe"] else "FAIL"
        g3 = "PASS" if r["max_drawdown"] > ref["max_drawdown"] else "FAIL"
        print(f"  ${level:>10,.0f}  Sharpe={r['sharpe']:.4f} ({g1} >=1.0; {g2} mot HYP-039:s {ref['sharpe']:.4f})  "
              f"MaxDD={r['max_drawdown']:.2%} ({g3} mot HYP-039:s {ref['max_drawdown']:.2%})  "
              f"CAGR={r['cagr']:+.2%}  Calmar={r['calmar']:.3f}")

    print("\n=== HYP-043: OOS-2025 ===")
    oos_results = []
    spy_oos = load_spy(start=OOS_START, end=FULL_END_WITH_OOS)
    mom_ls_oos = mom_ls_full.loc[OOS_START:FULL_END_WITH_OOS]
    for level in levels:
        hyp037_oos_pv = pd.read_csv(HYP037_OOS_RESULTS / f"portfolio_value_oos_2025_{level}.csv",
                                     index_col=0, parse_dates=True)["portfolio_value"]
        combined_oos = combine_thirds(spy_oos, hyp037_oos_pv, mom_ls_oos)
        combined_oos.to_csv(RESULTS_DIR / f"portfolio_value_oos2025_combined_{level}.csv", header=["portfolio_value"])

        r = {"capital_level": level, "oos_2025_sharpe": sharpe(combined_oos),
             "oos_2025_max_drawdown": max_drawdown(combined_oos),
             "oos_2025_total_return": float(combined_oos.iloc[-1] / combined_oos.iloc[0] - 1) if len(combined_oos) > 1 else None,
             "n_days": len(combined_oos)}
        oos_results.append(r)
        ref = HYP039_REF[level]
        g4 = "PASS" if r["oos_2025_sharpe"] > ref["oos_2025_sharpe"] else "FAIL"
        print(f"  ${level:>10,.0f}  OOS-Sharpe={r['oos_2025_sharpe']:.4f} ({g4} mot HYP-039:s {ref['oos_2025_sharpe']:.4f})  "
              f"OOS-avkastning={r['oos_2025_total_return']:+.2%}  OOS-MaxDD={r['oos_2025_max_drawdown']:.2%}  "
              f"({r['n_days']} dagar)")

    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump({"main": main_results, "oos_2025": oos_results}, f, indent=2, default=str)

    print("\nKLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
