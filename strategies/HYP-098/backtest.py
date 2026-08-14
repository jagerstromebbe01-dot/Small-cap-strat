"""
HYP-098 (BATCH-004, 2/4 accrual): skalning mot totala tillgångar,
long/short. Se
research/hypothesis_registry/HYP-098-accrual-tillgangar-longshort.yaml
för det låsta kriteriet. Motorn (strategies/common/accrual_engine.py)
är DELAD med HYP-097/099/100 - kopiera INTE.
"""
import json
import sys
from pathlib import Path

STRATEGY_DIR = Path(__file__).resolve().parent
STRATEGIES_ROOT = STRATEGY_DIR.parent
REPO_ROOT = STRATEGIES_ROOT.parent
RESULTS_DIR = STRATEGY_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
import accrual_engine as ae  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from deflated_sharpe_ratio import deflated_sharpe_ratio_from_returns  # noqa: E402

SCALING = "assets"
CONSTRUCTION = "long_short"
DSR_N_TRIALS = 95


def main():
    print(f"=== HYP-098: Accrual (skalning={SCALING}, konstruktion={CONSTRUCTION}) ===\n")

    print("Laddar universum...")
    tickers, universe_by_month = ae.load_universe()
    print(f"  {len(tickers)} unika tickers.\n")

    print("Laddar prismatriser...")
    close, close_adj, high, low, volume = ae.load_price_matrices(tickers, ae.FULL_START, ae.FULL_END)
    hedge = ae.load_hedge(ae.FULL_START, ae.FULL_END)

    print("Sanerar prisdata (inkl. permanenta prisnivåbrott, se accrual_engine.py 2026-08-14-tillägg)...")
    close, close_adj, high, low = ae.clean_and_prepare_prices(close, close_adj, high, low, volume)

    print("Estimerar beta och spread...")
    beta_df = ae.compute_beta(close_adj, hedge, ae.BETA_WINDOW)
    spread_df = ae.compute_spread_matrix(high, low)

    print(f"Laddar accrual-data (skalning={SCALING})...")
    accrual_data = ae.load_accrual_data(SCALING)
    print(f"  {len(accrual_data)} av {len(tickers)} tickers har användbar accrual-data.\n")

    levels = [100_000, 1_000_000, 10_000_000]
    results = []
    for level in levels:
        print(f"--- Kapitalnivå ${level:,.0f} ---")
        pv, tl, beta_log = ae.run_backtest(close, close_adj, hedge, accrual_data, SCALING, CONSTRUCTION,
                                            beta_df, spread_df, volume, universe_by_month, level)
        pv.to_csv(RESULTS_DIR / f"portfolio_value_{level}.csv", header=["portfolio_value"])
        tl.to_csv(RESULTS_DIR / f"trade_log_{level}.csv", index=False)
        beta_log.to_csv(RESULTS_DIR / f"beta_exposure_{level}.csv", index=False)

        sh, md, cg, cm = ae.sharpe(pv), ae.max_drawdown(pv), ae.cagr(pv), ae.calmar(pv)
        dsr = deflated_sharpe_ratio_from_returns(pv.pct_change().dropna().values, n_trials=DSR_N_TRIALS,
                                                  risk_free_per_period=ae.RF_ANNUAL / 252)["deflated_sharpe_ratio"]
        avg_net_beta = float(beta_log["net_beta_dollar"].mean()) if len(beta_log) else None

        cond1, cond2 = sh > 0.70, md >= -0.30
        overall = "PASS" if (cond1 and cond2) else "FAIL"
        print(f"  Sharpe={sh:.4f} (>0.70:{'PASS' if cond1 else 'FAIL'})  MaxDD={md:.2%} (>=-30%:{'PASS' if cond2 else 'FAIL'})  "
              f"CAGR={cg:+.2%}  Calmar={cm:.2f}  DSR(K={DSR_N_TRIALS})={dsr:.4f} -> {overall}")
        print(f"  Snitt netto-$-beta-exponering: {avg_net_beta}\n")

        results.append({"capital_level": level, "sharpe": sh, "max_drawdown": md, "cagr": cg, "calmar": cm,
                         "dsr": dsr, "n_trades": len(tl), "avg_net_beta_dollar": avg_net_beta,
                         "pass_fail": {"sharpe": bool(cond1), "maxdd": bool(cond2), "overall": overall}})

    overall_100k = results[0]["pass_fail"]["overall"]
    print(f"=== SLUTBEDÖMNING (gating $100k) === {overall_100k}")

    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump({"scaling": SCALING, "construction": CONSTRUCTION, "results": results,
                    "overall": overall_100k}, f, indent=2, default=str)
    print("Sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
