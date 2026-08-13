#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes an - ingen K-kostnad, INGET last kriterium):
"vad skulle handa om PEAD/SUE laggs till som ett 4:e, likaviktat fjardedels-
ben ovanpa den redan godkanda HYP-043-kombinationen (SPY+HYP-037+
momentum L/S)?" CEO bad om att kora PEAD/SUE-kandidaten vidare efter att
dess korrelationsegenskaper (se diagnostic_hyp044_pead_and_issuance.py)
visade sig battre an AI-brainstormens oro, trots svag egen Sharpe (0.22).

Detta ar EN diagnostisk kombinationskoll, INTE en pre-registrerad HYP-044
- om resultatet ser lovande ut kravs fortfarande CEO-lasning av ett
pass_fail_criterion innan nagot raknas som ett riktigt testresultat,
samma disciplin som HYP-039/041/043.

Fjardedelsvikt (25% vardera), kvartalsvis ombalansering, samma
snap_rebalance_dates-metod som HYP-039/041/043 sjalva anvander.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
STRATEGIES_ROOT = REPO_ROOT / "strategies"

sys.path.insert(0, str(STRATEGIES_ROOT / "HYP-037"))
import backtest as hyp037  # noqa: E402

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
from rebalancing import snap_rebalance_dates  # noqa: E402

REBAL_FREQ = "QE"
WEIGHT_EACH = 0.25

HYP039_REF = {
    100_000: {"sharpe": 1.0191, "max_drawdown": -0.2203},
    1_000_000: {"sharpe": 1.0300, "max_drawdown": -0.2216},
    10_000_000: {"sharpe": 0.9879, "max_drawdown": -0.2003},
}
HYP043_REF = {
    100_000: {"sharpe": 1.0457, "max_drawdown": -0.1558},
    1_000_000: {"sharpe": 1.0498, "max_drawdown": -0.1568},
    10_000_000: {"sharpe": 0.9864, "max_drawdown": -0.1429},
}


def combine_quarters(series_dict: dict, start_capital=1.0):
    df = pd.concat({k: v.rename(k) for k, v in series_dict.items()}, axis=1, join="inner").dropna()
    rets = df.pct_change()

    calendar_dates = df.resample(REBAL_FREQ).last().index
    snapped = snap_rebalance_dates(calendar_dates, df.index)
    rebal_set = set(snapped["execution_date"])

    legs = {k: start_capital * WEIGHT_EACH for k in series_dict}
    values, dates = [], []

    for i in range(1, len(df)):
        date = df.index[i]
        for k in legs:
            r = rets[k].iloc[i]
            if not np.isnan(r):
                legs[k] *= (1 + r)
        total = sum(legs.values())
        if date in rebal_set:
            for k in legs:
                legs[k] = total * WEIGHT_EACH
        values.append(total)
        dates.append(date)

    return pd.Series(values, index=dates)


def sharpe(s, rf=0.02):
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
    spy = hyp037.load_hedge(hyp037.FULL_START, hyp037.FULL_END)
    mom_ls = pd.read_csv(STRATEGIES_ROOT / "HYP-043" / "results" / "momentum_ls_sleeve_pv.csv",
                          index_col=0, parse_dates=True).iloc[:, 0]
    pead = pd.read_csv(REPO_ROOT / "data" / "cache" / "diag_pead_sue_ls_sleeve_pv.csv",
                        index_col=0, parse_dates=True).iloc[:, 0]

    levels = [100_000, 1_000_000, 10_000_000]
    print("=== 4-vags likaviktad diagnostikkombination: SPY + HYP-037 + MomentumLS + PEAD/SUE ===\n")
    for level in levels:
        hyp037_pv = pd.read_csv(STRATEGIES_ROOT / "HYP-037" / "results" / f"portfolio_value_{level}.csv",
                                 index_col=0, parse_dates=True)["portfolio_value"]
        combo = combine_quarters({"spy": spy, "hyp037": hyp037_pv, "mom_ls": mom_ls, "pead": pead})

        sh, md, cg, cm = sharpe(combo), max_drawdown(combo), cagr(combo), calmar(combo)
        ref39, ref43 = HYP039_REF[level], HYP043_REF[level]
        print(f"${level:>10,.0f}  Sharpe={sh:.4f}  CAGR={cg:+.2%}  MaxDD={md:.2%}  Calmar={cm:.3f}  "
              f"({len(combo)} dagar)")
        print(f"    vs HYP-039 (Sharpe {ref39['sharpe']:.4f}, MaxDD {ref39['max_drawdown']:.2%}): "
              f"Sharpe {'BATTRE' if sh > ref39['sharpe'] else 'SAMRE'}, "
              f"MaxDD {'BATTRE' if md > ref39['max_drawdown'] else 'SAMRE'}")
        print(f"    vs HYP-043 (Sharpe {ref43['sharpe']:.4f}, MaxDD {ref43['max_drawdown']:.2%}): "
              f"Sharpe {'BATTRE' if sh > ref43['sharpe'] else 'SAMRE'}, "
              f"MaxDD {'BATTRE' if md > ref43['max_drawdown'] else 'SAMRE'}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
