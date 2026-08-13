"""
Kvalitetskontroll (2026-07-31, CEO-beslut, "gratis kontroll" - INGEN
K-kostnad, andrar INGET last resultat): regresserar HYP-023:s DAGLIGA
avkastning mot Fama-French 5-faktormodellen (Mkt-RF, SMB, HML, RMW, CMA)
plus momentum (MOM/UMD) for att se om resultatet ar EGEN alfa efter
kontroll for kanda, redan dokumenterade faktorexponeringar - inte bara
en forklädd exponering mot storlek, vardefaktor, lonsamhet eller
momentum som vi rakar fanga.

Data: Kenneth French Data Library (publikt, akademiskt standardkallor,
dagliga faktoravkastningar i procent) - data/cache/famafrench/
(F-F_Research_Data_5_Factors_2x3_daily.csv, F-F_Momentum_Factor_daily.csv).

Egen OLS (statsmodels ej installerat) - standard regression med
t-statistik fran residualvariansen, ingen extern regressionslibrary.

Kor pa BADA: (a) hela den kanda 2011-2024-backtesten (den "officiella"
last-resultat-serien), och (b) den utokade 2011-2025-serien (inkl.
2025-OOS-perioden fran oos_backtest_2025.py) for jamforelse.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PAPER_DIR = Path(__file__).resolve().parent
FF_DIR = REPO_ROOT / "data" / "cache" / "famafrench"
HYP023_RESULTS = REPO_ROOT / "strategies" / "HYP-023" / "results"
OOS_RESULTS = PAPER_DIR / "oos_2025_results"


def load_ff_factors():
    ff5 = pd.read_csv(FF_DIR / "F-F_Research_Data_5_Factors_2x3_daily.csv", skiprows=3)
    ff5.columns = ["date"] + list(ff5.columns[1:])
    ff5 = ff5[ff5["date"].astype(str).str.match(r"^\d{8}$", na=False)]
    ff5["date"] = pd.to_datetime(ff5["date"].astype(str), format="%Y%m%d")
    ff5 = ff5.set_index("date")
    for c in ff5.columns:
        ff5[c] = pd.to_numeric(ff5[c], errors="coerce") / 100.0  # procent -> andel

    mom = pd.read_csv(FF_DIR / "F-F_Momentum_Factor_daily.csv", skiprows=13)
    mom = mom.iloc[:, :2]
    mom.columns = ["date", "MOM"]
    mom = mom[mom["date"].astype(str).str.match(r"^\d{8}$", na=False)]
    mom["date"] = pd.to_datetime(mom["date"].astype(str), format="%Y%m%d")
    mom = mom.set_index("date")
    mom["MOM"] = pd.to_numeric(mom["MOM"], errors="coerce") / 100.0

    return ff5.join(mom, how="inner")


def ols_with_stats(y: np.ndarray, X: np.ndarray, factor_names: list):
    """Standard OLS med t-statistik - X FORVANTAS redan innehalla en
    konstant-kolumn forst (for alfa/intercept)."""
    n, k = X.shape
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = n - k
    sigma2 = float(resid @ resid) / dof
    XtX_inv = np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(sigma2 * XtX_inv))
    t_stats = beta / se
    ss_res = float(resid @ resid)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot

    results = {}
    for i, name in enumerate(["alpha"] + factor_names):
        results[name] = {"coef": float(beta[i]), "se": float(se[i]), "t_stat": float(t_stats[i])}
    results["r_squared"] = r2
    results["n_obs"] = n
    return results


def run_regression(pv_path: Path, ff: pd.DataFrame, label: str):
    pv = pd.read_csv(pv_path, parse_dates=["date"], index_col="date")["portfolio_value"]
    ret = pv.pct_change().dropna()

    joined = pd.concat([ret.rename("strategy"), ff], axis=1, join="inner").dropna()
    if len(joined) < 60:
        print(f"  {label}: for fa overlappande observationer ({len(joined)}), hoppar over")
        return None

    y = (joined["strategy"] - joined["RF"]).values  # overskott over riskfri ranta
    factor_names = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "MOM"]
    X = np.column_stack([np.ones(len(joined))] + [joined[f].values for f in factor_names])

    res = ols_with_stats(y, X, factor_names)

    alpha_daily = res["alpha"]["coef"]
    alpha_annual = (1 + alpha_daily) ** 252 - 1
    alpha_t = res["alpha"]["t_stat"]

    print(f"\n  === {label} (n={res['n_obs']} dagar) ===")
    print(f"  Alfa (dagligt): {alpha_daily:+.5f}  ->  arligt: {alpha_annual:+.2%}  (t-stat: {alpha_t:+.2f}, "
          f"{'SIGNIFIKANT' if abs(alpha_t) > 2 else 'ej signifikant'} pa ~5%-niva)")
    print(f"  R²: {res['r_squared']:.3f}  (andel av variansen som forklaras av kanda faktorer)")
    print("  Faktorladdningar (beta, t-stat):")
    for f in factor_names:
        c = res[f]
        flag = "**" if abs(c["t_stat"]) > 2 else "  "
        print(f"    {f:8s}: {c['coef']:+.3f}  (t={c['t_stat']:+.2f}) {flag}")

    return {"label": label, "alpha_daily": alpha_daily, "alpha_annual": alpha_annual, "alpha_t_stat": alpha_t,
            "r_squared": res["r_squared"], "n_obs": res["n_obs"],
            "factor_loadings": {f: res[f] for f in factor_names}}


def main():
    print("Laddar Fama-French 5-faktorer + momentum (Kenneth French Data Library)...")
    ff = load_ff_factors()
    print(f"  {len(ff)} dagliga observationer, {ff.index.min().date()} till {ff.index.max().date()}.\n")

    all_results = []
    print("Kor regression pa HYP-023...")
    for level in [100_000, 1_000_000, 10_000_000]:
        r1 = run_regression(HYP023_RESULTS / f"portfolio_value_{level}.csv", ff,
                             f"HYP-023 officiell backtest (2011-2024), ${level:,.0f}")
        if r1:
            all_results.append(r1)

        oos_path = OOS_RESULTS / f"portfolio_value_full_{level}.csv"
        if oos_path.exists():
            r2 = run_regression(oos_path, ff, f"HYP-023 utokad serie (2011-2025, inkl. OOS), ${level:,.0f}")
            if r2:
                all_results.append(r2)

    import json
    out_path = Path(__file__).resolve().parent / "factor_regression_results.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nKLART. Sparat till {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
