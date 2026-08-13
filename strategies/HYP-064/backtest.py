"""
HYP-064: Drawdown-triggad nedskalning (-25%/25%-haircut) pa 5-coin crypto-korg.

Se research/hypothesis_registry/HYP-064-crypto-drawdown-trigger-derisking.yaml
for det lasta kriteriet, INKL. de tva oppet redovisade metodologiska
reservationerna (parametrar valda fran rutnat EFTER att ha sett Calmar-
utfall; bara 3-4 oberoende triggningar) - resultatet ska betraktas som
PROVISORISKT aven om det formellt PASSAR, per CEO-instruktion INNAN
lasning.

MEKANISM (lockad): BASELINE_BASKET (delad med HYP-061/062/063). Track
strategins EGEN levererade equity-kurvas drawdown fran rullande hogsta-
vattenmarke. Vid 100% exponering: drawdown<=-25% -> 25% exponering
SAMMA DAG. Vid 25% exponering: drawdown atehamtat forbi -10% -> 100%.

FRIKTION (NY jamfort med diagnostiken - saknades dar, tillagd har for
det formella testet): halva Corwin-Schultz-spreaden (snitt over de 5
coins, likaviktat, samma som basketens egen sammansattning) + 0,15%
exchange-avgift, pa notional som flyttas vid VARJE overgang.

DSR: n_trials=64 (k_total_hypotheses_before_this 62 + BATCH-003:s 4 +
denna sjalv = 62+1=63 vore standardkonventionen, men denna hypotes
laste EFTER BATCH-003 (k_total_hypotheses_before_this=62 i registret,
dvs EFTER batchens 58->62-hopp) - foljer HYP-056/059:s etablerade
"k_total_hypotheses_before_this + 1"-konvention.
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
from friction import corwin_schultz_spread  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from deflated_sharpe_ratio import deflated_sharpe_ratio_from_returns  # noqa: E402

TRIGGER_THRESHOLD = -0.25
HAIRCUT = 0.25
RE_ENTRY = -0.10
DSR_N_TRIALS = 63  # k_total_hypotheses_before_this (62) + 1, samma konvention som HYP-056/059


def avg_half_spread(price_data: dict, date) -> float:
    spreads = []
    for t in cd.TICKERS:
        if date not in price_data[t].index:
            continue
        h, l = price_data[t].loc[date, "high"], price_data[t].loc[date, "low"]
        s = corwin_schultz_spread(np.array([h, h]), np.array([l, l]))
        spreads.append(float(np.nan_to_num(s[-1], nan=0.0)))
    return (np.mean(spreads) / 2.0) if spreads else 0.0


def run_strategy(basket: pd.Series, price_data: dict) -> dict:
    raw_ret = basket.pct_change().fillna(0.0)
    equity = 1.0
    hwm = 1.0
    exposure = 1.0
    values, dates = [], []
    events = []

    for date, r in raw_ret.items():
        port_ret = exposure * r + (1 - exposure) * (cd.RF_ANNUAL / cd.ANNUALIZATION_DAYS)
        equity *= (1 + port_ret)
        hwm = max(hwm, equity)
        drawdown = (equity - hwm) / hwm

        if exposure == 1.0 and drawdown <= TRIGGER_THRESHOLD:
            half_spread = avg_half_spread(price_data, date)
            notional_moved = 1.0 - HAIRCUT
            equity *= (1.0 - notional_moved * (half_spread + cd.EXCHANGE_FEE))
            exposure = HAIRCUT
            events.append({"type": "TRIGGER", "date": str(date.date()), "drawdown": round(drawdown, 4)})
            hwm = max(hwm, equity)
            drawdown = (equity - hwm) / hwm
        elif exposure < 1.0 and drawdown > RE_ENTRY:
            half_spread = avg_half_spread(price_data, date)
            notional_moved = 1.0 - HAIRCUT
            equity *= (1.0 - notional_moved * (half_spread + cd.EXCHANGE_FEE))
            exposure = 1.0
            events.append({"type": "REENTRY", "date": str(date.date()), "drawdown": round(drawdown, 4)})

        values.append(equity)
        dates.append(date)

    return {"equity": pd.Series(values, index=dates), "events": events}


def main():
    price_data = {t: cd.load_crypto(t) for t in cd.TICKERS}
    basket = cd.build_baseline_basket(price_data)

    boundary = pd.Timestamp(cd.OOS_START)
    basket_main = basket.loc[basket.index < boundary]
    basket_oos_raw = basket.loc[basket.index >= boundary]
    basket_oos = basket_oos_raw / basket_oos_raw.iloc[0]

    res_main = run_strategy(basket_main, price_data)
    strat_main = res_main["equity"]

    basket_full = basket
    res_full = run_strategy(basket_full, price_data)
    strat_full = res_full["equity"]
    strat_oos_raw = strat_full.loc[strat_full.index >= boundary]
    strat_oos = strat_oos_raw / strat_oos_raw.iloc[0]

    strat_main.to_csv(RESULTS_DIR / "portfolio_value_main.csv", header=["portfolio_value"])
    strat_oos.to_csv(RESULTS_DIR / "portfolio_value_oos2025.csv", header=["portfolio_value"])
    pd.DataFrame(res_main["events"]).to_csv(RESULTS_DIR / "trigger_events_main.csv", index=False)

    sh_strat, sh_base = cd.sharpe(strat_main), cd.sharpe(basket_main)
    cagr_strat, cagr_base = cd.cagr(strat_main), cd.cagr(basket_main)
    md_strat, md_base = cd.max_drawdown(strat_main), cd.max_drawdown(basket_main)
    cal_strat, cal_base = cd.calmar(strat_main), cd.calmar(basket_main)

    dsr_info = deflated_sharpe_ratio_from_returns(
        strat_main.pct_change().dropna().values, n_trials=DSR_N_TRIALS,
        risk_free_per_period=cd.RF_ANNUAL / cd.ANNUALIZATION_DAYS)
    dsr = dsr_info["deflated_sharpe_ratio"]

    n_triggers = sum(1 for e in res_main["events"] if e["type"] == "TRIGGER")
    days_defensive = sum(1 for d in strat_main.index if _is_defensive(res_main["events"], d))
    pct_defensive = days_defensive / len(strat_main)

    print("=== HYP-064: drawdown-triggad nedskalning pa 5-coin crypto-korg ===\n")
    print(f"STRATEGI (main): Sharpe={sh_strat:.4f}  CAGR={cagr_strat:+.2%}  MaxDD={md_strat:.2%}  "
          f"Calmar={cal_strat:.3f}  DSR(K={DSR_N_TRIALS})={dsr:.4f}")
    print(f"BASELINE_BASKET (main): Sharpe={sh_base:.4f}  CAGR={cagr_base:+.2%}  MaxDD={md_base:.2%}  Calmar={cal_base:.3f}\n")
    print(f"Disclosure: {n_triggers} triggningar, {pct_defensive:.1%} av dagarna i defensivt lage\n")
    for e in res_main["events"]:
        print(f"  {e['type']:<8} {e['date']}  drawdown={e['drawdown']:.2%}")
    print()

    sh_strat_oos, sh_base_oos = cd.sharpe(strat_oos), cd.sharpe(basket_oos)
    print(f"OOS-2025: strategi Sharpe={sh_strat_oos:.4f} (avkastning {strat_oos.iloc[-1]-1:+.2%})  "
          f"baseline Sharpe={sh_base_oos:.4f} (avkastning {basket_oos.iloc[-1]-1:+.2%})\n")

    cond1 = sh_strat >= 0.55
    cond2 = cal_strat > cal_base
    cond3 = cal_strat > 1.5
    overall = "PASSED" if (cond1 and cond2 and cond3) else "FAILED"

    print("=== SLUTBEDOMNING ===")
    print(f"  Villkor 1 (Sharpe >= 0,55): {sh_strat:.4f} -> {'PASS' if cond1 else 'FAIL'}")
    print(f"  Villkor 2 (Calmar > baseline {cal_base:.3f}): {cal_strat:.3f} -> {'PASS' if cond2 else 'FAIL'}")
    print(f"  Villkor 3 (Calmar > 1,5): {cal_strat:.3f} -> {'PASS' if cond3 else 'FAIL'}")
    print(f"  => {overall}\n")
    print("PAMINNELSE: aven vid PASS ar detta PROVISORISKT (parametrar valda fran rutnat "
          "efter Calmar-utfall + bara 3-4 oberoende triggningar) - se registerpostens reservationer.")

    summary = {
        "strategy": {"sharpe": sh_strat, "cagr": cagr_strat, "max_drawdown": md_strat, "calmar": cal_strat, "dsr": dsr},
        "baseline_basket": {"sharpe": sh_base, "cagr": cagr_base, "max_drawdown": md_base, "calmar": cal_base},
        "oos_2025": {"strategy_sharpe": sh_strat_oos, "strategy_return": float(strat_oos.iloc[-1] - 1),
                     "baseline_sharpe": sh_base_oos, "baseline_return": float(basket_oos.iloc[-1] - 1)},
        "disclosure": {"n_triggers": n_triggers, "pct_days_defensive": pct_defensive, "events": res_main["events"]},
        "dsr_n_trials": DSR_N_TRIALS,
        "pass_fail": {"condition_1_sharpe_floor": bool(cond1), "condition_2_calmar_vs_baseline": bool(cond2),
                       "condition_3_calmar_absolute": bool(cond3), "overall": overall},
    }
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


def _is_defensive(events, date) -> bool:
    exposure = 1.0
    for e in events:
        if pd.Timestamp(e["date"]) > date:
            break
        exposure = 0.25 if e["type"] == "TRIGGER" else 1.0
    return exposure < 1.0


if __name__ == "__main__":
    sys.exit(main())
