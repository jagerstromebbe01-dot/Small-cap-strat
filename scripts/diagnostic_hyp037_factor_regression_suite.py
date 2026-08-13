#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes - ingen K-kostnad, rör INTE registret):
faktorregressionssvit för HYP-037 - CAPM, Fama-French 3, Fama-French 5,
Carhart 4-faktor - begärd av CEO 2026-08-05 efter feedback från en andra
AI (se [[project_lowvol_research_report_planned]] i minnet).

FRÅGA: överlever HYP-037:s alfa ÄVEN när man kontrollerar för alltmer
kända riskfaktorer? Om alfat dör när t.ex. RMW (lönsamhet) eller HML
(value) läggs till, är "idiosynkratisk lågvolatilitet" kanske bara en
känd faktor i förklädnad - INTE en distinkt signal. scripts/attribution.py
kör redan FF5+momentum en gång (samma data, samma metod) - detta skript
bygger ut det till en FULL STEGVIS SVIT (CAPM -> FF3 -> FF5 -> Carhart)
för att se VAR (om nagonstans) alfat forsvagas, inte bara sluttillstandet.

q-faktor-modellen (Hou/Xue/Zhang: Mkt, ME, I/A, ROE) kravs INTE har -
separat datakalla (global-q.org), inte cachad lokalt. Kan laggas till
separat om CEO vill ha den ocksa.

Skriver INGENTING till registret. Ren diagnostik.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
from attribution import _ols_with_stats, load_ff_factors  # noqa: E402

REPO_ROOT = SCRIPTS_DIR.parent

MODELS = {
    "CAPM":            ["Mkt-RF"],
    "Fama-French 3":   ["Mkt-RF", "SMB", "HML"],
    "Fama-French 5":   ["Mkt-RF", "SMB", "HML", "RMW", "CMA"],
    "Carhart 4-faktor": ["Mkt-RF", "SMB", "HML", "MOM"],
}


def run_model(pv: pd.Series, ff: pd.DataFrame, factor_names: list) -> dict:
    ret = pv.pct_change().dropna()
    joined = pd.concat([ret.rename("strategy"), ff], axis=1, join="inner").dropna()
    y = (joined["strategy"] - joined["RF"]).values
    X = np.column_stack([np.ones(len(joined))] + [joined[f].values for f in factor_names])
    return _ols_with_stats(y, X, factor_names)


def print_result(model_name: str, res: dict):
    alpha = res["alpha"]
    alpha_annual = (1 + alpha["coef"]) ** 252 - 1
    sig = "***SIGNIFIKANT***" if abs(alpha["t_stat"]) > 2 else "ej signifikant"
    print(f"\n--- {model_name} ---")
    print(f"  Alfa: {alpha_annual:+.2%}/år  (t={alpha['t_stat']:+.2f}, {sig})  "
          f"R²={res['r_squared']:.3f}  n={res['n_obs']}")
    for name, stats in res.items():
        if name in ("alpha", "r_squared", "n_obs"):
            continue
        sig_f = "*" if abs(stats["t_stat"]) > 2 else " "
        print(f"    {name:<8} coef={stats['coef']:+.3f}  t={stats['t_stat']:+.2f} {sig_f}")


def main():
    print("Laddar Fama-French/Carhart-faktorer (redan cachade)...")
    ff = load_ff_factors()
    print(f"  {len(ff)} dagar faktordata.\n")

    print("=" * 90)
    print("FAKTORREGRESSIONSSVIT: HYP-037 (villkorat overlay-aterintrade)")
    print("=" * 90)

    alpha_summary = []
    for level in [100_000, 1_000_000, 10_000_000]:
        pv_path = REPO_ROOT / "strategies" / "HYP-037" / "results" / f"portfolio_value_{level}.csv"
        pv = pd.read_csv(pv_path, index_col=0, parse_dates=True)["portfolio_value"]

        print(f"\n{'#' * 90}\nKapitalnivå: ${level:,.0f}\n{'#' * 90}")
        for model_name, factor_names in MODELS.items():
            res = run_model(pv, ff, factor_names)
            print_result(model_name, res)
            alpha_summary.append({
                "level": level, "model": model_name,
                "alpha_annual": (1 + res["alpha"]["coef"]) ** 252 - 1,
                "t_stat": res["alpha"]["t_stat"], "r_squared": res["r_squared"],
            })

    print("\n\n" + "=" * 90)
    print("SAMMANFATTNING: överlever alfat genom hela sviten? (t-stat per modell och nivå)")
    print("=" * 90)
    summary_df = pd.DataFrame(alpha_summary)
    pivot_t = summary_df.pivot(index="model", columns="level", values="t_stat").reindex(MODELS.keys())
    pivot_a = summary_df.pivot(index="model", columns="level", values="alpha_annual").reindex(MODELS.keys())
    print("\nt-stat per modell/nivå (|t|>2 = signifikant):")
    print(pivot_t.round(2).to_string())
    print("\nAlfa (årligt) per modell/nivå:")
    print(pivot_a.map(lambda x: f"{x:+.2%}").to_string())

    print("\n" + "=" * 90)
    print("TOLKNING: om t-stat forblir >2 (absolutbelopp) genom HELA sviten, fran CAPM till")
    print("Carhart, overlever alfat aven nar man kontrollerar for storlek/value/lonsamhet/")
    print("investeringsmonster/momentum - ett starkt argument mot att signalen bara ar en")
    print("kand faktor i forkladnad. Om alfat FALLER UNDER signifikans nar en SPECIFIK faktor")
    print("laggs till (t.ex. RMW i FF5), pekar det mot att just DEN faktorn forklarar en del")
    print("av vad som ser ut som HYP-037:s egen edge.")
    print("=" * 90)
    return 0


if __name__ == "__main__":
    sys.exit(main())
