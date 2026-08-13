"""
HYP-060: BTC solo, 200-dagars trendfilter (long/kontant) mot buy-and-hold.

Se research/hypothesis_registry/HYP-060-btc-trendfilter-200dma.yaml for
det lasta kriteriet. Forsta hypotesen i BATCH-003 (spot-only crypto).

MEKANISM (lockad): close > SMA_200 -> 100% BTC, annars 100% kontant
(RF_ANNUAL=2%/ar). Friktion: halva Corwin-Schultz-spreaden (BTC:s egen
high/low) + 0,15% exchange-avgift vid varje overgang.

DSR: n_trials=62 for HELA BATCH-003 (INTE k_total_hypotheses_before_this+1
per enskild hypotes) - eftersom fyra kandidater laste SAMTIDIGT ur samma
sokprocess (spec: "k_total increments by N... not one at a time"), racknas
alla fyra som en gemensam multipel-testnings-familj vid utvarderingen av
VAR OCH EN av dem, inte bara de fore den i registerordning.
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

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from deflated_sharpe_ratio import deflated_sharpe_ratio_from_returns  # noqa: E402

SMA_WINDOW = 200
DSR_N_TRIALS = 62


def apply_trend_filter(df: pd.DataFrame) -> pd.Series:
    close = df["close"]
    sma = close.rolling(SMA_WINDOW).mean()
    in_trend = (close > sma).fillna(False)

    equity = 1.0
    values, dates = [], []
    prev_close = None
    prev_state = None

    for date in close.index[SMA_WINDOW:]:
        state = bool(in_trend.loc[date])
        if prev_close is not None:
            if prev_state:
                ret = close.loc[date] / prev_close - 1.0
            else:
                ret = cd.RF_ANNUAL / cd.ANNUALIZATION_DAYS
            equity *= (1.0 + ret)
        if prev_state is not None and state != prev_state:
            h, l = df.loc[date, "high"], df.loc[date, "low"]
            equity *= (1.0 - cd.transition_cost(h, l, 1.0))
        values.append(equity)
        dates.append(date)
        prev_close = close.loc[date]
        prev_state = state

    return pd.Series(values, index=dates)


def buy_and_hold(df: pd.DataFrame, start_date) -> pd.Series:
    close = df.loc[start_date:, "close"]
    return close / close.iloc[0]


def main():
    df = cd.load_crypto("BTC-USD.CC")
    strat = apply_trend_filter(df)
    bh = buy_and_hold(df, strat.index[0])
    bh = bh.reindex(strat.index)

    boundary = pd.Timestamp(cd.OOS_START)
    strat_main = strat.loc[strat.index < boundary]
    strat_oos_raw = strat.loc[strat.index >= boundary]
    strat_oos = strat_oos_raw / strat_oos_raw.iloc[0]

    bh_main = bh.loc[bh.index < boundary]
    bh_oos_raw = bh.loc[bh.index >= boundary]
    bh_oos = bh_oos_raw / bh_oos_raw.iloc[0]

    strat_main.to_csv(RESULTS_DIR / "portfolio_value_main.csv", header=["portfolio_value"])
    strat_oos.to_csv(RESULTS_DIR / "portfolio_value_oos2025.csv", header=["portfolio_value"])

    sh_strat, sh_bh = cd.sharpe(strat_main), cd.sharpe(bh_main)
    cagr_strat, cagr_bh = cd.cagr(strat_main), cd.cagr(bh_main)
    md_strat, md_bh = cd.max_drawdown(strat_main), cd.max_drawdown(bh_main)

    dsr_info = deflated_sharpe_ratio_from_returns(
        strat_main.pct_change().dropna().values, n_trials=DSR_N_TRIALS,
        risk_free_per_period=cd.RF_ANNUAL / cd.ANNUALIZATION_DAYS)
    dsr = dsr_info["deflated_sharpe_ratio"]

    print("=== HYP-060: BTC solo 200-dagars trendfilter vs buy-and-hold ===\n")
    print(f"STRATEGI  (main): Sharpe={sh_strat:.4f}  CAGR={cagr_strat:+.2%}  MaxDD={md_strat:.2%}  DSR(K={DSR_N_TRIALS})={dsr:.4f}")
    print(f"BUY&HOLD  (main): Sharpe={sh_bh:.4f}  CAGR={cagr_bh:+.2%}  MaxDD={md_bh:.2%}\n")

    sh_strat_oos, sh_bh_oos = cd.sharpe(strat_oos), cd.sharpe(bh_oos)
    print(f"OOS-2025: strategi Sharpe={sh_strat_oos:.4f} (avkastning {strat_oos.iloc[-1]-1:+.2%})  "
          f"buy&hold Sharpe={sh_bh_oos:.4f} (avkastning {bh_oos.iloc[-1]-1:+.2%})\n")

    cond1 = sh_strat >= 0.55
    cond2 = sh_strat > sh_bh
    cond3 = md_strat >= -0.50
    overall = "PASSED" if (cond1 and cond2 and cond3) else "FAILED"

    print("=== SLUTBEDOMNING ===")
    print(f"  Villkor 1 (Sharpe >= 0,55): {sh_strat:.4f} -> {'PASS' if cond1 else 'FAIL'}")
    print(f"  Villkor 2 (Sharpe > buy-and-hold {sh_bh:.4f}): {sh_strat:.4f} -> {'PASS' if cond2 else 'FAIL'}")
    print(f"  Villkor 3 (MaxDD >= -50%): {md_strat:.2%} -> {'PASS' if cond3 else 'FAIL'}")
    print(f"  => {overall}\n")

    summary = {
        "strategy": {"sharpe": sh_strat, "cagr": cagr_strat, "max_drawdown": md_strat, "dsr": dsr},
        "buy_and_hold": {"sharpe": sh_bh, "cagr": cagr_bh, "max_drawdown": md_bh},
        "oos_2025": {"strategy_sharpe": sh_strat_oos, "strategy_return": float(strat_oos.iloc[-1] - 1),
                     "buy_and_hold_sharpe": sh_bh_oos, "buy_and_hold_return": float(bh_oos.iloc[-1] - 1)},
        "dsr_n_trials": DSR_N_TRIALS,
        "pass_fail": {"condition_1_sharpe_floor": bool(cond1), "condition_2_vs_buy_hold": bool(cond2),
                       "condition_3_maxdd": bool(cond3), "overall": overall},
    }
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
