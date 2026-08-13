"""
HYP-068: Volatilitetsmålsättning (HYP-056:s exakta mekanik) på HYP-066:s
återköpsdecil.

Se research/hypothesis_registry/HYP-068-voltargeting-hyp066.yaml för det
lasta kriteriet. Andra kandidaten i BATCH-004 (se HYP-067:s registerpost
för diagnostikmotiveringen).

INGEN NY BACKTEST-MOTOR: ren exponeringsskalning ovanpa HYP-066:s redan
berknade, SPY-beta-hedgade portfoljvardesserier (strategies/HYP-066/results/
portfolio_value_full_{level}.csv - REDAN kontinuerlig 2010-01-01 till
2025-12-31, till skillnad fran HYP-047/056 som behovde kedja tva separata
filer for kontinuitet over main/OOS-gransen).

Samma mekanik som HYP-056: veckovis, 60-dagars realiserad vol vs 504-
dagars (2-ars) rullande TRAILING MEDIAN, skala=MIN(1.0, mal/nu), golv 0.3.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

STRATEGY_DIR = Path(__file__).resolve().parent
STRATEGIES_ROOT = STRATEGY_DIR.parent
REPO_ROOT = STRATEGIES_ROOT.parent
RESULTS_DIR = STRATEGY_DIR / "results"

HYP066_RESULTS = STRATEGIES_ROOT / "HYP-066" / "results"

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
from rebalancing import snap_rebalance_dates  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from deflated_sharpe_ratio import deflated_sharpe_ratio_from_returns  # noqa: E402

VOL_WINDOW = 60
MEDIAN_WINDOW = 504  # 2 ar, handelsdagar (samma som HYP-056, aktier - INTE crypto-batchens 730 kalenderdagar)
SCALE_FLOOR = 0.3
SCALE_CAP = 1.0
DECISION_FREQ = "W"

RF_ANNUAL = 0.02
OOS_START = "2025-01-01"

# HYP-066:s egna redan lasta resultat (jamforelsepunkten for villkor 2/3)
HYP066_MAIN_REF = {
    100_000: {"sharpe": 0.3072, "max_drawdown": -0.6685},
    1_000_000: {"sharpe": 0.3079, "max_drawdown": -0.7090},
    10_000_000: {"sharpe": 0.3393, "max_drawdown": -0.7264},
}

DSR_N_TRIALS = 67  # k_total_hypotheses_before_this (65) + BATCH-004:s 2 = 67, delad av bada batch-medlemmarna


def load_hyp066_full(level: int) -> pd.Series:
    return pd.read_csv(HYP066_RESULTS / f"portfolio_value_full_{level}.csv",
                        index_col=0, parse_dates=True)["portfolio_value"]


def compute_vol_scale(raw_ret: pd.Series):
    vol60 = raw_ret.rolling(VOL_WINDOW).std() * np.sqrt(252)
    median504 = vol60.rolling(MEDIAN_WINDOW).median()

    calendar_dates = raw_ret.resample(DECISION_FREQ).last().index
    snapped = snap_rebalance_dates(calendar_dates, raw_ret.index)
    decision_dates = sorted(set(snapped["execution_date"]))

    scale_daily = pd.Series(index=raw_ret.index, dtype=float)
    log_rows = []
    current_scale = 1.0
    for date in raw_ret.index:
        if date in decision_dates:
            target = median504.get(date, np.nan)
            current = vol60.get(date, np.nan)
            if pd.notna(target) and pd.notna(current) and current > 0:
                s = min(SCALE_CAP, target / current)
                s = max(SCALE_FLOOR, s)
            else:
                s = 1.0
            current_scale = s
            log_rows.append({"date": date, "vol60": current, "median504": target, "scale": current_scale})
        scale_daily.loc[date] = current_scale

    return scale_daily, pd.DataFrame(log_rows)


def apply_scale(raw_ret: pd.Series, scale: pd.Series, rf_annual=RF_ANNUAL) -> pd.Series:
    values = [1.0]
    dates = [raw_ret.index[0]]
    for i in range(len(raw_ret)):
        date = raw_ret.index[i]
        r = raw_ret.iloc[i]
        r = 0.0 if pd.isna(r) else r
        f = scale.get(date, 1.0)
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


def main():
    levels = [100_000, 1_000_000, 10_000_000]
    print("=== HYP-068: volatilitetsmalsattning pa HYP-066:s aterkopsdecil ===\n")

    main_results, oos_results, disclosure_by_level = [], [], {}

    for level in levels:
        pv_full = load_hyp066_full(level)
        r_full = pv_full.pct_change().dropna()

        scale_daily, decision_log = compute_vol_scale(r_full)
        scaled_full = apply_scale(r_full, scale_daily)

        boundary = pd.Timestamp(OOS_START)
        scaled_main = scaled_full.loc[scaled_full.index < boundary]
        scaled_oos_raw = scaled_full.loc[scaled_full.index >= boundary]
        scaled_oos = scaled_oos_raw / scaled_oos_raw.iloc[0]

        scaled_main.to_csv(RESULTS_DIR / f"portfolio_value_scaled_main_{level}.csv", header=["portfolio_value"])
        scaled_oos.to_csv(RESULTS_DIR / f"portfolio_value_scaled_oos2025_{level}.csv", header=["portfolio_value"])
        if level == levels[0]:
            decision_log.to_csv(RESULTS_DIR / "weekly_scale_log.csv", index=False)

        main_log = decision_log[decision_log["date"] < boundary]
        disclosure_by_level[level] = {
            "n_decisions": int(len(main_log)),
            "avg_scale": float(main_log["scale"].mean()) if len(main_log) else None,
            "min_scale": float(main_log["scale"].min()) if len(main_log) else None,
            "pct_weeks_below_1": float((main_log["scale"] < 1.0).mean()) if len(main_log) else None,
        }

        r = {"capital_level": level, "sharpe": sharpe(scaled_main), "cagr": cagr(scaled_main),
             "max_drawdown": max_drawdown(scaled_main), "calmar": calmar(scaled_main), "n_days": len(scaled_main)}
        dsr_info = deflated_sharpe_ratio_from_returns(
            scaled_main.pct_change().dropna().values, n_trials=DSR_N_TRIALS, risk_free_per_period=RF_ANNUAL / 252)
        r["dsr"] = dsr_info["deflated_sharpe_ratio"]
        main_results.append(r)

        ref = HYP066_MAIN_REF[level]
        g1 = r["sharpe"] >= 0.55
        g2 = r["sharpe"] > ref["sharpe"]
        g3 = r["max_drawdown"] > ref["max_drawdown"]
        print(f"  ${level:>10,.0f}  Sharpe={r['sharpe']:.4f} (golv:{'PASS' if g1 else 'FAIL'}, "
              f"vs HYP-066 {ref['sharpe']:.4f}:{'PASS' if g2 else 'FAIL'})  "
              f"MaxDD={r['max_drawdown']:.2%} (vs {ref['max_drawdown']:.2%}:{'PASS' if g3 else 'FAIL'})  "
              f"CAGR={r['cagr']:+.2%}  DSR(K={DSR_N_TRIALS})={r['dsr']:.4f}")

        oos_r = {"capital_level": level, "oos_2025_sharpe": sharpe(scaled_oos),
                 "oos_2025_max_drawdown": max_drawdown(scaled_oos),
                 "oos_2025_total_return": float(scaled_oos.iloc[-1] / scaled_oos.iloc[0] - 1) if len(scaled_oos) > 1 else None}
        oos_results.append(oos_r)
        dl = disclosure_by_level[level]
        print(f"              OOS-Sharpe={oos_r['oos_2025_sharpe']:.4f}  "
              f"OOS-avkastning={oos_r['oos_2025_total_return']:+.2%}  "
              f"Disclosure: snitt-skala={dl['avg_scale']:.3f}  lagsta={dl['min_scale']:.3f}  "
              f"andel<1.0={dl['pct_weeks_below_1']:.1%}\n")

    conds = []
    for r in main_results:
        lvl = r["capital_level"]
        ref = HYP066_MAIN_REF[lvl]
        c1 = r["sharpe"] >= 0.55
        c2 = r["sharpe"] > ref["sharpe"]
        c3 = r["max_drawdown"] > ref["max_drawdown"]
        conds.append((lvl, c1, c2, c3))

    overall = "PASSED" if all(c1 and c2 and c3 for _, c1, c2, c3 in conds) else "FAILED"

    print("=== SLUTBEDOMNING (alla tre villkor maste halla PA ALLA TRE NIVAER) ===")
    for lvl, c1, c2, c3 in conds:
        print(f"  ${lvl:>10,.0f}  V1(golv)={'PASS' if c1 else 'FAIL'}  V2(vs HYP-066 Sharpe)={'PASS' if c2 else 'FAIL'}  "
              f"V3(vs HYP-066 MaxDD)={'PASS' if c3 else 'FAIL'}")
    print(f"  => {overall}\n")

    summary = {
        "main": main_results, "oos_2025": oos_results, "hyp066_main_ref": HYP066_MAIN_REF,
        "exposure_scale_disclosure": disclosure_by_level, "dsr_n_trials": DSR_N_TRIALS,
        "pass_fail": {"per_level": [{"level": l, "c1_floor": bool(c1), "c2_vs_sharpe": bool(c2), "c3_vs_maxdd": bool(c3)}
                                     for l, c1, c2, c3 in conds],
                      "overall": overall},
    }
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
