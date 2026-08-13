"""
HYP-093 (BATCH-004, 1/4 textlikhet): cosine/TF-IDF-likhet, eget
long/short-ben. Se
research/hypothesis_registry/HYP-093-riskfactors-cosine-sjatteben.yaml
för det låsta kriteriet. Motorn (strategies/common/text_similarity_engine.py,
strategies/common/accrual_engine.py) är DELAD med HYP-094/095/096 -
kopiera INTE.
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
import text_similarity_engine as tse  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from deflated_sharpe_ratio import deflated_sharpe_ratio_from_returns  # noqa: E402

METRIC = "cosine"
CONSTRUCTION = "own_leg"
DSR_N_TRIALS = 95


def main():
    print(f"=== HYP-093: Risk Factors-textlikhet (metric={METRIC}, konstruktion={CONSTRUCTION}) ===\n")

    print("Laddar universum...")
    tickers, universe_by_month = ae.load_universe()
    print(f"  {len(tickers)} unika tickers.\n")

    print("Laddar prismatriser...")
    close, close_adj, high, low, volume = ae.load_price_matrices(tickers, ae.FULL_START, ae.FULL_END)
    hedge = ae.load_hedge(ae.FULL_START, ae.FULL_END)

    print("Sanerar prisdata...")
    close, high, low = ae.clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    implausible = ae.flag_implausible_liquidity(close, volume, max_market_cap=ae.MAX_MARKET_CAP,
                                                 window=ae.ADV_WINDOW, multiplier=1.0)
    close = close.mask(implausible)
    close_adj = close_adj.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)

    print("Estimerar beta och spread...")
    beta_df = ae.compute_beta(close_adj, hedge, ae.BETA_WINDOW)
    spread_df = ae.compute_spread_matrix(high, low)

    print(f"Laddar textlikhetsdata (metric={METRIC})...")
    sim_data = tse.load_text_similarity_data(METRIC)
    print(f"  {len(sim_data)} av {len(tickers)} tickers har användbar textlikhetsdata.\n")

    levels = [100_000, 1_000_000, 10_000_000]
    results = []
    for level in levels:
        print(f"--- Kapitalnivå ${level:,.0f} ---")
        pv, tl, beta_log = tse.run_backtest(close, close_adj, hedge, sim_data, CONSTRUCTION,
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
        json.dump({"metric": METRIC, "construction": CONSTRUCTION, "results": results,
                    "overall": overall_100k}, f, indent=2, default=str)
    print("Sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
