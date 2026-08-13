"""
HYP-061: Volatilitetsmalsattning (HYP-056:s exakta mekanik) pa 5-coin
likaviktad crypto-korg.

Se research/hypothesis_registry/HYP-061-crypto-basket-vol-targeting.yaml
for det lasta kriteriet. Andra hypotesen i BATCH-003.

MEKANISM (lockad): BASELINE_BASKET (delad med HYP-062/063, se
strategies/common/crypto_data.py::build_baseline_basket) + veckovis
volatilitetsskalning: skala=MIN(1.0, mal/dagens-60d-vol), mal=730-dagars
(2-ars) rullande TRAILING MEDIAN, golv 0.3.

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

VOL_WINDOW = 60
MEDIAN_WINDOW = 730  # 2 ar, 365-dagars kalenderbas (crypto handlas alla dagar)
SCALE_FLOOR = 0.3
SCALE_CAP = 1.0
DSR_N_TRIALS = 62


def compute_vol_scale(raw_ret: pd.Series):
    vol60 = raw_ret.rolling(VOL_WINDOW).std() * np.sqrt(cd.ANNUALIZATION_DAYS)
    median730 = vol60.rolling(MEDIAN_WINDOW).median()

    calendar_dates = raw_ret.resample("W").last().index
    snapped = snap_rebalance_dates(calendar_dates, raw_ret.index)
    decision_dates = sorted(set(snapped["execution_date"]))

    scale_daily = pd.Series(index=raw_ret.index, dtype=float)
    log_rows = []
    current_scale = 1.0
    for date in raw_ret.index:
        if date in decision_dates:
            target = median730.get(date, np.nan)
            current = vol60.get(date, np.nan)
            if pd.notna(target) and pd.notna(current) and current > 0:
                s = min(SCALE_CAP, target / current)
                s = max(SCALE_FLOOR, s)
            else:
                s = 1.0
            current_scale = s
            log_rows.append({"date": date, "vol60": current, "median730": target, "scale": current_scale})
        scale_daily.loc[date] = current_scale

    return scale_daily, pd.DataFrame(log_rows)


def apply_scale(raw_ret: pd.Series, scale: pd.Series, rf_annual=cd.RF_ANNUAL) -> pd.Series:
    values, dates = [1.0], [raw_ret.index[0]]
    for i in range(len(raw_ret)):
        date = raw_ret.index[i]
        r = raw_ret.iloc[i]
        r = 0.0 if pd.isna(r) else r
        f = scale.get(date, 1.0)
        blended = f * r + (1 - f) * (rf_annual / cd.ANNUALIZATION_DAYS)
        values.append(values[-1] * (1 + blended))
        dates.append(date)
    return pd.Series(values[1:], index=dates[1:])


def main():
    price_data = {t: cd.load_crypto(t) for t in cd.TICKERS}
    basket = cd.build_baseline_basket(price_data)
    raw_ret = basket.pct_change().dropna()

    scale_daily, decision_log = compute_vol_scale(raw_ret)
    scaled = apply_scale(raw_ret, scale_daily)

    boundary = pd.Timestamp(cd.OOS_START)
    basket_main = basket.loc[basket.index < boundary]
    scaled_main = scaled.loc[scaled.index < boundary]
    basket_oos_raw = basket.loc[basket.index >= boundary]
    scaled_oos_raw = scaled.loc[scaled.index >= boundary]
    basket_oos = basket_oos_raw / basket_oos_raw.iloc[0]
    scaled_oos = scaled_oos_raw / scaled_oos_raw.iloc[0]

    basket_main.to_csv(RESULTS_DIR / "portfolio_value_baseline_main.csv", header=["portfolio_value"])
    scaled_main.to_csv(RESULTS_DIR / "portfolio_value_scaled_main.csv", header=["portfolio_value"])
    decision_log.to_csv(RESULTS_DIR / "weekly_scale_log.csv", index=False)

    sh_scaled, sh_base = cd.sharpe(scaled_main), cd.sharpe(basket_main)
    cagr_scaled, cagr_base = cd.cagr(scaled_main), cd.cagr(basket_main)
    md_scaled, md_base = cd.max_drawdown(scaled_main), cd.max_drawdown(basket_main)

    dsr_info = deflated_sharpe_ratio_from_returns(
        scaled_main.pct_change().dropna().values, n_trials=DSR_N_TRIALS,
        risk_free_per_period=cd.RF_ANNUAL / cd.ANNUALIZATION_DAYS)
    dsr = dsr_info["deflated_sharpe_ratio"]

    main_log = decision_log[decision_log["date"] < boundary]
    disclosure = {
        "n_decisions": int(len(main_log)),
        "avg_scale": float(main_log["scale"].mean()) if len(main_log) else None,
        "min_scale": float(main_log["scale"].min()) if len(main_log) else None,
        "pct_weeks_below_1": float((main_log["scale"] < 1.0).mean()) if len(main_log) else None,
    }

    print("=== HYP-061: volatilitetsmalsattning pa 5-coin crypto-korg ===\n")
    print(f"MED OVERLAY  (main): Sharpe={sh_scaled:.4f}  CAGR={cagr_scaled:+.2%}  MaxDD={md_scaled:.2%}  DSR(K={DSR_N_TRIALS})={dsr:.4f}")
    print(f"BASELINE_BASKET (main, utan overlay): Sharpe={sh_base:.4f}  CAGR={cagr_base:+.2%}  MaxDD={md_base:.2%}\n")
    print(f"Disclosure: snitt-skala={disclosure['avg_scale']:.3f}  lagsta-skala={disclosure['min_scale']:.3f}  "
          f"andel veckor<1.0={disclosure['pct_weeks_below_1']:.1%}  ({disclosure['n_decisions']} veckobeslut)\n")

    sh_scaled_oos, sh_base_oos = cd.sharpe(scaled_oos), cd.sharpe(basket_oos)
    print(f"OOS-2025: med overlay Sharpe={sh_scaled_oos:.4f} (avkastning {scaled_oos.iloc[-1]-1:+.2%})  "
          f"baseline Sharpe={sh_base_oos:.4f} (avkastning {basket_oos.iloc[-1]-1:+.2%})\n")

    cond1 = sh_scaled >= 0.55
    cond2 = sh_scaled > sh_base
    cond3 = md_scaled > md_base
    overall = "PASSED" if (cond1 and cond2 and cond3) else "FAILED"

    print("=== SLUTBEDOMNING ===")
    print(f"  Villkor 1 (Sharpe >= 0,55): {sh_scaled:.4f} -> {'PASS' if cond1 else 'FAIL'}")
    print(f"  Villkor 2 (Sharpe > baseline {sh_base:.4f}): {sh_scaled:.4f} -> {'PASS' if cond2 else 'FAIL'}")
    print(f"  Villkor 3 (MaxDD battre an baseline {md_base:.2%}): {md_scaled:.2%} -> {'PASS' if cond3 else 'FAIL'}")
    print(f"  => {overall}\n")

    summary = {
        "with_overlay": {"sharpe": sh_scaled, "cagr": cagr_scaled, "max_drawdown": md_scaled, "dsr": dsr},
        "baseline_basket": {"sharpe": sh_base, "cagr": cagr_base, "max_drawdown": md_base},
        "oos_2025": {"with_overlay_sharpe": sh_scaled_oos, "with_overlay_return": float(scaled_oos.iloc[-1] - 1),
                     "baseline_sharpe": sh_base_oos, "baseline_return": float(basket_oos.iloc[-1] - 1)},
        "exposure_scale_disclosure": disclosure,
        "dsr_n_trials": DSR_N_TRIALS,
        "pass_fail": {"condition_1_sharpe_floor": bool(cond1), "condition_2_vs_baseline": bool(cond2),
                       "condition_3_maxdd_vs_baseline": bool(cond3), "overall": overall},
    }
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
