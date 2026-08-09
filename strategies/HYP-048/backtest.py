"""
HYP-048: Regimstyrd allokering mellan HYP-047:s fyra ben (volatilitetsbetingad).

Se research/hypothesis_registry/HYP-048-regimstyrd-allokering-hyp047-ben.yaml
for det lasta kriteriet. Attonde kombinationshypotesen i registret, forsta
i BATCH-002.

MEKANISM (lockad, se kriteriet): SPY:s rullande 20-dagars realiserade
volatilitet (annualiserad) jamfort mot sitt eget rullande 2-ars (504
handelsdagars) MEDIANVARDE, utvarderat VARJE kvartalsvis ombalansering
(samma snappade datum som HYP-047 redan anvander). LUGNT (vol<=median):
25/25/35/15 (spy/hyp037/mom_ls/bear). STRESS (vol>median): 25/25/15/35.
Bara mom_ls/bear-fordelningen vaxlar, spy/hyp037 fasta pa 25% vardera.

INGEN NY BACKTEST-MOTOR: portfoljniva-ombalansering av HYP-047:s redan
berknade, oforandrade avkastningsserier (SPY, HYP-037, momentum L/S med
friktion, bear catcher) - ingen ny small-cap-signal, inget nytt
handelsuniversum, ingen ny friktionsberakning. small_cap_definition
deklarerar N/A per registerpostens egen text -> requires_friction_check
i scripts/hypothesis_gate.py returnerar False for denna fil (samma
undantag som HYP-039/041/043/044/045/046/047 redan fatt), sa
validate_friction_usage.py kors INTE mot denna fil.

Momentum L/S-benet aterananvands FARDIGBERAKNAT fran
strategies/HYP-043/results_corrected_2026-08-08/momentum_ls_sleeve_pv.csv
(identisk funktion/logik som HYP-047:s egen lokala
compute_momentum_ls_sleeve_with_spread - samma universum, samma
friktionsmetodik, samma USE_SPREAD_COST=True - se HYP-047:s docstring)
istallet for att koras om (samma serie, sparar flera minuters
onodig ombergakning, i linje med uppdragets instruktion att undersoka
vad som redan finns sparat).
"""

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
RESULTS_DIR = STRATEGY_DIR / "results"

HYP037_DIR = STRATEGIES_ROOT / "HYP-037"
HYP037_RESULTS = HYP037_DIR / "results_corrected_2026-08-08"
HYP037_OOS_RESULTS = REPO_ROOT / "paper_trading" / "HYP-037" / "oos_2025_results"
HYP043_RESULTS = STRATEGIES_ROOT / "HYP-043" / "results_corrected_2026-08-08"
HYP047_RESULTS = STRATEGIES_ROOT / "HYP-047" / "results_corrected_2026-08-08"

sys.path.insert(0, str(HYP037_DIR))
import backtest as hyp037  # noqa: E402

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
from rebalancing import snap_rebalance_dates  # noqa: E402

REBAL_FREQ = "QE"
REBALANCE_COST_BPS = 0.0010  # samma schablon som HYP-039/041/043/044/045/046/047

VOL_WINDOW = 20
VOL_MEDIAN_WINDOW = 504
RF_ANNUAL = 0.02

OOS_START = "2025-01-01"
FULL_END_WITH_OOS = "2025-12-31"

# Regimberoende vikter: (spy, hyp037, mom_ls, bear)
WEIGHTS_CALM = {"spy": 0.25, "hyp037": 0.25, "mom_ls": 0.35, "bear": 0.15}
WEIGHTS_STRESS = {"spy": 0.25, "hyp037": 0.25, "mom_ls": 0.15, "bear": 0.35}

# HYP-047:s EGNA lasta korrigerade referensvarden (jamforelsepunkten for
# villkor 1-3, se kriteriet - siffrorna star har EXAKT som de star i det
# lasta kriteriet, inte hamtade om fran summary.json, aven dar de tva
# kallorna skulle rakna avvika i ordning/avrundning).
HYP047_MAIN_REF = {
    100_000: {"sharpe": 1.126, "max_drawdown": -0.0867},
    1_000_000: {"sharpe": 1.127, "max_drawdown": -0.0845},
    10_000_000: {"sharpe": 1.102, "max_drawdown": -0.0820},
}
HYP047_OOS_REF = {100_000: 1.710, 1_000_000: 1.720, 10_000_000: 1.780}

# HYP-047:s egna FAKTISKA (summary.json) varden - anvands bara for
# diagnostisk kontext i utskriften/result_summary, INTE for sjalva
# PASS/FAIL-bedomningen (den anvander uteslutande de lasta talen ovan).
HYP047_MAIN_ACTUAL = {
    100_000: {"sharpe": 1.1259446684184102, "max_drawdown": -0.08666983724474896},
    1_000_000: {"sharpe": 1.1268489733092988, "max_drawdown": -0.08451883083951889},
    10_000_000: {"sharpe": 1.1023551425152134, "max_drawdown": -0.08196198800420938},
}
HYP047_OOS_ACTUAL = {100_000: 1.7780818267817344, 1_000_000: 1.7244618937814808, 10_000_000: 1.7082216630932494}


def load_spy_ohlc(end=None):
    df = pd.read_csv(OHLCV_DIR / "SPY.csv", usecols=["date", "adjusted_close"], parse_dates=["date"])
    df = df.drop_duplicates(subset="date", keep="last").set_index("date").sort_index()
    if end is not None:
        df = df.loc[:end]
    return df["adjusted_close"]


def compute_regime(spy_close: pd.Series) -> pd.Series:
    """SPY dagliga avkastning -> rullande 20-dagars annualiserad std,
    jamfort mot sitt eget rullande 504-dagars (TRAILING, ingen framatblick)
    medianvarde. Returnerar en boolesk serie, True = STRESS (dagens vol >
    trailing 2-ars-median)."""
    daily_ret = spy_close.pct_change()
    vol20 = daily_ret.rolling(VOL_WINDOW).std() * np.sqrt(252)
    median504 = vol20.rolling(VOL_MEDIAN_WINDOW).median()
    stress = vol20 > median504
    return stress, vol20, median504


def combine_regime_weighted(series_dict: dict, stress_series: pd.Series, start_capital=1.0):
    """Som HYP-047:s combine_quarters, men vikterna for mom_ls/bear vaxlar
    med regimen VID VARJE kvartalsvis ombalansering (spy/hyp037 alltid
    25% vardera). Portfoljen driver mellan ombalanseringarna precis som
    resten av registrets kombinationshypoteser."""
    df = pd.concat({k: v.rename(k) for k, v in series_dict.items()}, axis=1, join="inner").dropna()
    rets = df.pct_change()
    calendar_dates = df.resample(REBAL_FREQ).last().index
    snapped = snap_rebalance_dates(calendar_dates, df.index)
    rebal_set = set(snapped["execution_date"])

    legs = {k: start_capital * WEIGHTS_CALM[k] for k in series_dict}
    values, dates, regime_log = [], [], []

    for i in range(1, len(df)):
        date = df.index[i]
        for k in legs:
            r = rets[k].iloc[i]
            if not np.isnan(r):
                legs[k] *= (1 + r)
        total = sum(legs.values())
        if date in rebal_set:
            is_stress = bool(stress_series.get(date, False))
            weights = WEIGHTS_STRESS if is_stress else WEIGHTS_CALM
            targets = {k: total * weights[k] for k in legs}
            turnover = sum(abs(targets[k] - legs[k]) for k in legs)
            total -= turnover * REBALANCE_COST_BPS
            for k in legs:
                legs[k] = total * weights[k]
            regime_log.append({"date": date, "stress": is_stress})
        values.append(total)
        dates.append(date)
    return pd.Series(values, index=dates), pd.DataFrame(regime_log)


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
    print("Laddar redan berknade benserier (SPY, HYP-037, momentum L/S, bear catcher)...")
    spy_close = load_spy_ohlc(end=FULL_END_WITH_OOS)
    spy_raw = hyp037.load_hedge(hyp037.FULL_START, FULL_END_WITH_OOS)
    mom_ls_raw = pd.read_csv(HYP043_RESULTS / "momentum_ls_sleeve_pv.csv", index_col=0, parse_dates=True)["portfolio_value"]
    bear_catcher = pd.read_csv(HYP047_RESULTS / "bear_catcher_pv.csv", index_col=0, parse_dates=True)["portfolio_value"]

    stress_series, vol20, median504 = compute_regime(spy_close)
    n_valid = median504.notna().sum()
    n_stress = int(stress_series[median504.notna()].sum())
    print(f"  Regimindikator giltig fran {median504.dropna().index[0].date()} "
          f"({n_valid} dagar totalt, {n_stress} STRESS-dagar = {n_stress / n_valid:.1%})\n")

    # Korrelationsmatris (dagliga avkastningar, samtliga fyra ben) - redan
    # redovisad fore lasning per kriteriets egen text, aterberknas har
    # bara for spårbarhet i denna korning.
    corr_df = pd.concat({
        "spy": spy_raw.pct_change(), "mom_ls": mom_ls_raw.pct_change(), "bear": bear_catcher.pct_change(),
    }, axis=1, join="inner").dropna()
    print("Parvis dagskorrelation (spy/mom_ls/bear, HYP-037 exkluderad har - kapitalnivaberoende serie):")
    print(corr_df.corr().round(4).to_string())
    print()

    levels = [100_000, 1_000_000, 10_000_000]

    print("=== HYP-048: huvudbacktest (2010-2024) ===")
    main_results = []
    for level in levels:
        hyp037_pv = pd.read_csv(HYP037_RESULTS / f"portfolio_value_{level}.csv",
                                 index_col=0, parse_dates=True)["portfolio_value"]
        combined, regime_log = combine_regime_weighted(
            {"spy": spy_raw, "hyp037": hyp037_pv, "mom_ls": mom_ls_raw, "bear": bear_catcher}, stress_series)
        combined.to_csv(RESULTS_DIR / f"portfolio_value_combined_{level}.csv", header=["portfolio_value"])
        if level == levels[0]:
            regime_log.to_csv(RESULTS_DIR / "regime_log.csv", index=False)

        r = {"capital_level": level, "sharpe": sharpe(combined), "cagr": cagr(combined),
             "max_drawdown": max_drawdown(combined), "calmar": calmar(combined), "n_days": len(combined),
             "n_rebalances": len(regime_log), "n_stress_rebalances": int(regime_log["stress"].sum()) if len(regime_log) else 0}
        main_results.append(r)
        ref = HYP047_MAIN_REF[level]
        g1 = "PASS" if r["sharpe"] > ref["sharpe"] else "FAIL"
        g2 = "PASS" if r["max_drawdown"] > ref["max_drawdown"] else "FAIL"
        print(f"  ${level:>10,.0f}  Sharpe={r['sharpe']:.4f} ({g1} mot HYP-047:s {ref['sharpe']:.4f})  "
              f"MaxDD={r['max_drawdown']:.2%} ({g2} mot {ref['max_drawdown']:.2%})  "
              f"CAGR={r['cagr']:+.2%}  Calmar={r['calmar']:.3f}  "
              f"({r['n_stress_rebalances']}/{r['n_rebalances']} STRESS-ombalanseringar)")

    print("\n=== HYP-048: OOS-2025 ===")
    oos_results = []
    spy_oos = spy_raw.loc[OOS_START:FULL_END_WITH_OOS]
    mom_ls_oos = mom_ls_raw.loc[OOS_START:FULL_END_WITH_OOS]
    bear_oos = bear_catcher.loc[OOS_START:FULL_END_WITH_OOS]
    for level in levels:
        hyp037_oos_pv = pd.read_csv(HYP037_OOS_RESULTS / f"portfolio_value_oos_2025_{level}.csv",
                                     index_col=0, parse_dates=True)["portfolio_value"]
        combined_oos, regime_log_oos = combine_regime_weighted(
            {"spy": spy_oos, "hyp037": hyp037_oos_pv, "mom_ls": mom_ls_oos, "bear": bear_oos}, stress_series)
        combined_oos.to_csv(RESULTS_DIR / f"portfolio_value_oos2025_combined_{level}.csv", header=["portfolio_value"])

        r = {"capital_level": level, "oos_2025_sharpe": sharpe(combined_oos),
             "oos_2025_max_drawdown": max_drawdown(combined_oos),
             "oos_2025_total_return": float(combined_oos.iloc[-1] / combined_oos.iloc[0] - 1) if len(combined_oos) > 1 else None,
             "n_days": len(combined_oos)}
        oos_results.append(r)
        ref_oos = HYP047_OOS_REF[level]
        g3 = "PASS" if r["oos_2025_sharpe"] > ref_oos else "FAIL"
        print(f"  ${level:>10,.0f}  OOS-Sharpe={r['oos_2025_sharpe']:.4f} ({g3} mot HYP-047:s {ref_oos:.4f} enl. lasta kriteriet)  "
              f"OOS-avkastning={r['oos_2025_total_return']:+.2%}  OOS-MaxDD={r['oos_2025_max_drawdown']:.2%}  "
              f"({r['n_days']} dagar)")

    import json
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump({
            "main": main_results, "oos_2025": oos_results,
            "hyp047_locked_criterion_ref": {"main": HYP047_MAIN_REF, "oos_2025": HYP047_OOS_REF},
            "hyp047_actual_summary_json_ref": {"main": HYP047_MAIN_ACTUAL, "oos_2025": HYP047_OOS_ACTUAL},
            "leg_correlations_ex_hyp037": corr_df.corr().to_dict(),
        }, f, indent=2, default=str)

    print("\nKLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
