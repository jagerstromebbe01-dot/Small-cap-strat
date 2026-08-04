#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes - ingen K-kostnad, ingen pass_fail_criterion):
delperiods-robusthet for HYP-037:s faktorregressionsalfa. Fragan:
haller alfat ihop over BADA halvorna av 2011-2024, eller drivs det av
en enda delperiod (t.ex. bara covid-aterhamtningen eller bara de tidiga
aren)? Anvander samma OLS-metod som scripts/attribution.py, bara
tillampad pa tva delfonster istallet for hela serien i klump.
"""

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from attribution import load_ff_factors, factor_regression  # noqa: E402

STRATEGY_DIR = REPO_ROOT / "strategies" / "HYP-037" / "results"

SPLIT_DATE = "2017-12-31"  # ungefar mitten av 2011-2024, delar serien i tva ungefar lika langa halvor


def main():
    print("Laddar Fama-French-faktorer...")
    ff = load_ff_factors()

    for level in [100_000, 1_000_000, 10_000_000]:
        pv = pd.read_csv(STRATEGY_DIR / f"portfolio_value_{level}.csv", index_col=0, parse_dates=True)["portfolio_value"]

        first_half = pv.loc[:SPLIT_DATE]
        second_half = pv.loc[SPLIT_DATE:]

        print(f"\n{'=' * 70}")
        print(f"HYP-037 @ ${level:,.0f}")
        print(f"{'=' * 70}")

        for label, sub_pv in [("2011-01-01 till 2017-12-31", first_half), ("2018-01-01 till 2024-12-31", second_half)]:
            res = factor_regression(sub_pv, ff)
            if "error" in res:
                print(f"  {label}: {res['error']}")
                continue
            sig = "SIGNIFIKANT" if res["alpha_significant"] else "EJ signifikant"
            print(f"  {label} (n={res['n_obs']} dagar):")
            print(f"    Alfa: {res['alpha_annual']:+.2%}/år (t={res['alpha_t_stat']:+.2f}, {sig})  R²={res['r_squared']:.3f}")

    print("\nKLART.")


if __name__ == "__main__":
    sys.exit(main())
