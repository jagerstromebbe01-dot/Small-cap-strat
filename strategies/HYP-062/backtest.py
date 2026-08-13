"""
HYP-062: Tvarsnittsrotation, topp-K=2 av 5 coins efter 90-dagars trend,
manadsvis.

Se research/hypothesis_registry/HYP-062-crypto-crosssectional-rotation.yaml
for det lasta kriteriet. Tredje hypotesen i BATCH-003.

MEKANISM (lockad): manadsvis ombalansering. Rangordna 5 coins efter
trailing 90-kalenderdagars kumulativ avkastning. TVA lika stora slots
(50% var). Varje slot -> hogst rankade EJ redan tilldelade coin MED
positiv 90-dagars avkastning, annars kontant for den slotten.

DSR: n_trials=62 for HELA BATCH-003, se HYP-060:s docstring for motivering.
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
RESULTS_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
import crypto_data as cd  # noqa: E402
from rebalancing import snap_rebalance_dates  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from deflated_sharpe_ratio import deflated_sharpe_ratio_from_returns  # noqa: E402

MOMENTUM_WINDOW = 90
N_SLOTS = 2
SLOT_WEIGHT = 1.0 / N_SLOTS
DSR_N_TRIALS = 62


def run_rotation(price_data: dict) -> pd.Series:
    closes = pd.DataFrame({t: price_data[t]["close"] for t in cd.TICKERS}).dropna()
    common_start = closes.index[0]
    closes = closes.loc[common_start:]

    trailing_ret = closes.pct_change(MOMENTUM_WINDOW)

    calendar_dates = closes.resample("ME").last().index
    snapped = snap_rebalance_dates(calendar_dates, closes.index)
    rebal_dates = sorted(set(snapped["execution_date"]))

    weights = pd.Series(0.0, index=cd.TICKERS)
    equity = 1.0
    values, dates = [], []
    prev_close = None

    for date in closes.index:
        row = closes.loc[date]
        if prev_close is not None:
            asset_ret = (row / prev_close - 1.0).fillna(0.0)
            equity *= (1.0 + float((weights * asset_ret).sum()))

        if date in rebal_dates and date in trailing_ret.index:
            scores = trailing_ret.loc[date].dropna()
            positive = scores[scores > 0].sort_values(ascending=False)
            chosen = list(positive.index[:N_SLOTS])
            target = pd.Series(0.0, index=cd.TICKERS)
            for t in chosen:
                target[t] = SLOT_WEIGHT

            for t in cd.TICKERS:
                delta = abs(target[t] - weights[t])
                if delta > 1e-12:
                    h, l = price_data[t].loc[date, "high"], price_data[t].loc[date, "low"]
                    equity *= (1.0 - cd.transition_cost(h, l, delta))
            weights = target

        values.append(equity)
        dates.append(date)
        prev_close = row

    return pd.Series(values, index=dates)


def main():
    price_data = {t: cd.load_crypto(t) for t in cd.TICKERS}
    strat = run_rotation(price_data)
    baseline = cd.build_baseline_basket(price_data)
    baseline = baseline.reindex(strat.index).ffill()
    baseline = baseline / baseline.iloc[0]

    boundary = pd.Timestamp(cd.OOS_START)
    strat_main = strat.loc[strat.index < boundary]
    base_main = baseline.loc[baseline.index < boundary]
    strat_oos_raw = strat.loc[strat.index >= boundary]
    base_oos_raw = baseline.loc[baseline.index >= boundary]
    strat_oos = strat_oos_raw / strat_oos_raw.iloc[0]
    base_oos = base_oos_raw / base_oos_raw.iloc[0]

    strat_main.to_csv(RESULTS_DIR / "portfolio_value_main.csv", header=["portfolio_value"])
    strat_oos.to_csv(RESULTS_DIR / "portfolio_value_oos2025.csv", header=["portfolio_value"])

    sh_strat, sh_base = cd.sharpe(strat_main), cd.sharpe(base_main)
    cagr_strat, cagr_base = cd.cagr(strat_main), cd.cagr(base_main)
    md_strat, md_base = cd.max_drawdown(strat_main), cd.max_drawdown(base_main)

    dsr_info = deflated_sharpe_ratio_from_returns(
        strat_main.pct_change().dropna().values, n_trials=DSR_N_TRIALS,
        risk_free_per_period=cd.RF_ANNUAL / cd.ANNUALIZATION_DAYS)
    dsr = dsr_info["deflated_sharpe_ratio"]

    print("=== HYP-062: tvarsnittsrotation topp-2 av 5 crypto-coins ===\n")
    print(f"STRATEGI  (main): Sharpe={sh_strat:.4f}  CAGR={cagr_strat:+.2%}  MaxDD={md_strat:.2%}  DSR(K={DSR_N_TRIALS})={dsr:.4f}")
    print(f"BASELINE_BASKET (main): Sharpe={sh_base:.4f}  CAGR={cagr_base:+.2%}  MaxDD={md_base:.2%}\n")

    sh_strat_oos, sh_base_oos = cd.sharpe(strat_oos), cd.sharpe(base_oos)
    print(f"OOS-2025: strategi Sharpe={sh_strat_oos:.4f} (avkastning {strat_oos.iloc[-1]-1:+.2%})  "
          f"baseline Sharpe={sh_base_oos:.4f} (avkastning {base_oos.iloc[-1]-1:+.2%})\n")

    cond1 = sh_strat >= 0.55
    cond2 = sh_strat > sh_base
    cond3 = md_strat >= -0.50
    overall = "PASSED" if (cond1 and cond2 and cond3) else "FAILED"

    print("=== SLUTBEDOMNING ===")
    print(f"  Villkor 1 (Sharpe >= 0,55): {sh_strat:.4f} -> {'PASS' if cond1 else 'FAIL'}")
    print(f"  Villkor 2 (Sharpe > baseline {sh_base:.4f}): {sh_strat:.4f} -> {'PASS' if cond2 else 'FAIL'}")
    print(f"  Villkor 3 (MaxDD >= -50%): {md_strat:.2%} -> {'PASS' if cond3 else 'FAIL'}")
    print(f"  => {overall}\n")

    summary = {
        "strategy": {"sharpe": sh_strat, "cagr": cagr_strat, "max_drawdown": md_strat, "dsr": dsr},
        "baseline_basket": {"sharpe": sh_base, "cagr": cagr_base, "max_drawdown": md_base},
        "oos_2025": {"strategy_sharpe": sh_strat_oos, "strategy_return": float(strat_oos.iloc[-1] - 1),
                     "baseline_sharpe": sh_base_oos, "baseline_return": float(base_oos.iloc[-1] - 1)},
        "dsr_n_trials": DSR_N_TRIALS,
        "pass_fail": {"condition_1_sharpe_floor": bool(cond1), "condition_2_vs_baseline": bool(cond2),
                       "condition_3_maxdd": bool(cond3), "overall": overall},
    }
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
