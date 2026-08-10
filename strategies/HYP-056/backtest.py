"""
HYP-056: Volatilitetsmalsattning (defensiv, ingen havstang) som overlay pa
HYP-047:s redan kombinerade 25/25/25/25-portfolj.

Se research/hypothesis_registry/HYP-056-volatilitetsmalsattning-hyp047-overlay.yaml
for det lasta kriteriet. Nionde kombinationshypotesen i registret.

MEKANISM (lockad, se kriteriet): vid VARJE veckoslut, berkna HYP-047-
portfoljens rullande 60-dagars realiserade volatilitet (annualiserad std
av dagliga avkastningar), jamfor mot samma portfoljs egen rullande 2-ars
(504 handelsdagars) TRAILING MEDIAN-volatilitet (sjalvrefererande mal,
inget godtyckligt fast tal). skala = MIN(1.0, mal/dagens-vol), golv 0.3.
INGEN HAVSTANG - skalan kan aldrig overstiga 1.0 (se registerpostens
egen "EXPLICIT AVGRANSNING"). Overrigt kapital (1-skala) i kontanter,
forraentat till RF_ANNUAL (2%/ar).

INGEN NY BACKTEST-MOTOR: ren exponeringsskalning ovanpa HYP-047:s redan
berknade, oforandrade kombinerade portfoljvardesserier (main 2010-2024,
OOS-2025) - ingen ny small-cap-signal, inget nytt handelsuniversum,
ingen ny prismatris laddas. small_cap_definition deklarerar N/A per
registerpostens egen text -> requires_friction_check i
scripts/hypothesis_gate.py returnerar False for denna fil (samma
undantag som HYP-039/041/043/044/045/046/047/048 redan fatt), sa
validate_friction_usage.py kors INTE mot denna fil.

KALLOR (aterananvander direkt, ingen omberkning):
  strategies/HYP-047/results_corrected_2026-08-08/portfolio_value_combined_{level}.csv
  strategies/HYP-047/results_corrected_2026-08-08/portfolio_value_oos2025_combined_{level}.csv

KONTINUITET OVER MAIN/OOS-GRANSEN (dokumenterad forenkling): HYP-047:s
egen OOS-2025-serie ar ETT OBEROENDE, ateromnormaliserat (borjar om vid
1.0) resultat av combine_quarters() applicerat pa OOS-endast benslicear
(se HYP-047:s egen backtest.py) - INTE en fortsattning av samma
kumulativa vardeserie som main-perioden. For att denna hypotes rullande
60-dagars/504-dagars (2-ars) volatilitetsmatt SKA HA verklig historik
vid ingangen av OOS-2025 (annars skulle 2-arsmedianen aldrig hinna
fyllas under ETT enda OOS-ar, vilket skulle gora overlayn till ett
permanent no-op genom hela OOS-perioden - inte en meningsfull test av
villkor 3), byggs en KONTINUERLIG raavkastningsserie genom att
KEDJA (concat) main-periodens och OOS-periodens redan berknade dagliga
procentuella avkastningar. Detta lamnar EN dags avkastning odokumenterad
vid exakt granspunkten (2024-12-31 -> 2025-01-03, eftersom vardera
serien ateromnormaliseras till 1.0 vid sin egen startpunkt och
forsta-dagens pct_change() darfor tappas i bada) - en forsumbar,
oppet redovisad forenkling (1 dag av ~756 i det relevanta rullande
fonstret vid overgangen, paverkar ett fatal tidiga OOS-veckobeslut med
en forsumbar marginal, paverkar main-periodens EGNA resultat INTE ALLS).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

STRATEGY_DIR = Path(__file__).resolve().parent
STRATEGIES_ROOT = STRATEGY_DIR.parent
REPO_ROOT = STRATEGIES_ROOT.parent
RESULTS_DIR = STRATEGY_DIR / "results"

HYP047_RESULTS = STRATEGIES_ROOT / "HYP-047" / "results_corrected_2026-08-08"

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
from rebalancing import snap_rebalance_dates  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from deflated_sharpe_ratio import deflated_sharpe_ratio_from_returns  # noqa: E402

VOL_WINDOW = 60
MEDIAN_WINDOW = 504  # 2 ars (504 handelsdagar), trailing
SCALE_FLOOR = 0.3
SCALE_CAP = 1.0  # ALDRIG over 1.0 - se registerpostens EXPLICIT AVGRANSNING
DECISION_FREQ = "W"  # veckoslut

RF_ANNUAL = 0.02

OOS_START = "2025-01-01"

# HYP-047:s EGNA lasta korrigerade referensvarden (jamforelsepunkten for
# villkor 1-3, se kriteriet - siffrorna star har EXAKT som de star i det
# lasta kriteriet, inte hamtade om fran summary.json).
HYP047_MAIN_REF = {
    100_000: {"sharpe": 1.126, "max_drawdown": -0.0867},
    1_000_000: {"sharpe": 1.127, "max_drawdown": -0.0845},
    10_000_000: {"sharpe": 1.102, "max_drawdown": -0.0820},
}
HYP047_OOS_REF = {100_000: 1.710, 1_000_000: 1.720, 10_000_000: 1.780}

# HYP-047:s egna FAKTISKA (summary.json) varden - anvands bara for
# diagnostisk kontext i utskriften/result_summary, INTE for sjalva
# PASS/FAIL-bedomningen (den anvander uteslutande de lasta talen ovan).
HYP047_MAIN_ACTUAL = {
    100_000: {"sharpe": 1.1259446684184102, "max_drawdown": -0.08666983724474896},
    1_000_000: {"sharpe": 1.1268489733092988, "max_drawdown": -0.08451883083951889},
    10_000_000: {"sharpe": 1.1023551425152134, "max_drawdown": -0.08196198800420938},
}
HYP047_OOS_ACTUAL = {100_000: 1.7780818267817344, 1_000_000: 1.7244618937814808, 10_000_000: 1.7082216630932494}

DSR_N_TRIALS = 55  # k_total_hypotheses_before_this (54) + 1, per registerpostens egen K


def load_hyp047_combined(level: int) -> pd.Series:
    return pd.read_csv(HYP047_RESULTS / f"portfolio_value_combined_{level}.csv",
                        index_col=0, parse_dates=True)["portfolio_value"]


def load_hyp047_oos(level: int) -> pd.Series:
    return pd.read_csv(HYP047_RESULTS / f"portfolio_value_oos2025_combined_{level}.csv",
                        index_col=0, parse_dates=True)["portfolio_value"]


def compute_vol_scale(raw_ret: pd.Series):
    """
    raw_ret: kontinuerlig daglig avkastningsserie (main kedjad med OOS,
    se docstring ovan).

    Returnerar (scale_daily, decision_log):
      scale_daily: dagligt hallen skala (halls konstant mellan
                   veckoslutsbeslut, INGEN look-ahead - varje beslut
                   anvander bara data t.o.m. och med beslutsdagen).
      decision_log: DataFrame med en rad per FAKTISKT veckoslutsbeslut
                   (date, vol60, median504, scale) - anvands for den
                   obligatoriska disclosuren (snitt/lagsta skala, andel
                   veckor under 1.0).
    """
    vol60 = raw_ret.rolling(VOL_WINDOW).std() * np.sqrt(252)
    median504 = vol60.rolling(MEDIAN_WINDOW).median()

    calendar_dates = raw_ret.resample(DECISION_FREQ).last().index
    snapped = snap_rebalance_dates(calendar_dates, raw_ret.index)
    decision_dates = sorted(set(snapped["execution_date"]))

    scale_daily = pd.Series(index=raw_ret.index, dtype=float)
    log_rows = []
    current_scale = 1.0  # innan 504-dagars historik finns: inget mal kan berknas -> full exponering
    for date in raw_ret.index:
        if date in decision_dates:
            target = median504.get(date, np.nan)
            current = vol60.get(date, np.nan)
            if pd.notna(target) and pd.notna(current) and current > 0:
                s = min(SCALE_CAP, target / current)
                s = max(SCALE_FLOOR, s)
            else:
                s = 1.0  # otillrackligt lang historik annu - ingen skalning mojlig
            current_scale = s
            log_rows.append({"date": date, "vol60": current, "median504": target, "scale": current_scale})
        scale_daily.loc[date] = current_scale

    return scale_daily, pd.DataFrame(log_rows)


def apply_scale(raw_ret: pd.Series, scale: pd.Series, rf_annual=RF_ANNUAL) -> pd.Series:
    """Blandar den raa dagliga avkastningen med kontant riskfri ranta
    enligt skala-serien (1.0 = full exponering, 0.3 = golvet). Identisk
    princip som HYP-037/045s apply_overlay(), bara omskriven for att ta
    en avkastningsserie direkt (raw_ret ar redan en kedjad
    main+OOS-avkastningsserie, ingen enskild vardeserie att pct_change()
    om)."""
    values = [1.0]
    dates = [raw_ret.index[0]]
    for i in range(len(raw_ret)):
        date = raw_ret.index[i]
        r = raw_ret.iloc[i]
        r = 0.0 if pd.isna(r) else r
        f = scale.get(date, 1.0)
        blended = f * r + (1 - f) * (rf_annual / 252)
        values.append(values[-1] * (1 + blended))
        dates.append(date)
    # values har en extra startpunkt (1.0) fore forsta avkastningsdagen
    return pd.Series(values[1:], index=dates[1:])


def sharpe(s, rf=RF_ANNUAL):
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
    levels = [100_000, 1_000_000, 10_000_000]

    print("=== HYP-056: volatilitetsmalsattning (defensiv, ingen havstang) overlay pa HYP-047 ===\n")
    print("Laddar HYP-047:s redan berknade kombinerade portfoljvardesserier "
          f"({HYP047_RESULTS})...\n")

    main_results, oos_results = [], []
    disclosure_by_level = {}

    for level in levels:
        pv_main = load_hyp047_combined(level)
        pv_oos = load_hyp047_oos(level)

        r_main = pv_main.pct_change().dropna()
        r_oos = pv_oos.pct_change().dropna()
        r_full = pd.concat([r_main, r_oos])  # se docstring: en dags avkastning odokumenterad vid granspunkten

        scale_daily, decision_log = compute_vol_scale(r_full)
        scaled_full = apply_scale(r_full, scale_daily)

        boundary = pd.Timestamp(OOS_START)
        scaled_main = scaled_full.loc[scaled_full.index < boundary]
        scaled_oos_raw = scaled_full.loc[scaled_full.index >= boundary]
        scaled_oos = scaled_oos_raw / scaled_oos_raw.iloc[0]  # ateromnormaliserad till 1.0, samma
        # konvention som varje annan OOS-fil i registret - konstant
        # omskalning paverkar varken Sharpe (pct_change-baserad) eller
        # MaxDD (kvotbaserad, skalinvariant), bara CSV-utskriftens startvarde.

        scaled_main.to_csv(RESULTS_DIR / f"portfolio_value_combined_scaled_{level}.csv", header=["portfolio_value"])
        scaled_oos.to_csv(RESULTS_DIR / f"portfolio_value_oos2025_combined_scaled_{level}.csv", header=["portfolio_value"])
        if level == levels[0]:
            decision_log.to_csv(RESULTS_DIR / "weekly_scale_log.csv", index=False)

        # Disclosure (icke-gating): snitt/lagsta skala, andel veckor <1.0.
        # Berknas separat for main-perioden (fore OOS_START) och for hela
        # perioden (main+OOS), for transparens.
        main_log = decision_log[decision_log["date"] < boundary]
        full_log = decision_log
        disclosure_by_level[level] = {
            "main_period": {
                "n_decisions": int(len(main_log)),
                "avg_scale": float(main_log["scale"].mean()) if len(main_log) else None,
                "min_scale": float(main_log["scale"].min()) if len(main_log) else None,
                "pct_weeks_below_1": float((main_log["scale"] < 1.0).mean()) if len(main_log) else None,
            },
            "full_period_incl_oos": {
                "n_decisions": int(len(full_log)),
                "avg_scale": float(full_log["scale"].mean()) if len(full_log) else None,
                "min_scale": float(full_log["scale"].min()) if len(full_log) else None,
                "pct_weeks_below_1": float((full_log["scale"] < 1.0).mean()) if len(full_log) else None,
            },
        }

        # --- Villkor 1+2: main-period, avgorande vid $100k ---
        r = {"capital_level": level, "sharpe": sharpe(scaled_main), "cagr": cagr(scaled_main),
             "max_drawdown": max_drawdown(scaled_main), "calmar": calmar(scaled_main), "n_days": len(scaled_main)}
        dsr_info = deflated_sharpe_ratio_from_returns(
            scaled_main.pct_change().dropna().values, n_trials=DSR_N_TRIALS, risk_free_per_period=RF_ANNUAL / 252)
        r["dsr"] = dsr_info["deflated_sharpe_ratio"]
        main_results.append(r)

        ref = HYP047_MAIN_REF[level]
        g1 = "PASS" if r["sharpe"] > ref["sharpe"] else "FAIL"
        g2 = "PASS" if r["max_drawdown"] > ref["max_drawdown"] else "FAIL"
        print(f"  ${level:>10,.0f}  Sharpe={r['sharpe']:.4f} ({g1} mot HYP-047:s {ref['sharpe']:.4f})  "
              f"MaxDD={r['max_drawdown']:.2%} ({g2} mot {ref['max_drawdown']:.2%})  "
              f"CAGR={r['cagr']:+.2%}  Calmar={r['calmar']:.3f}  DSR(K={DSR_N_TRIALS})={r['dsr']:.4f}")

        # --- Villkor 3: OOS-2025 ---
        oos_r = {"capital_level": level, "oos_2025_sharpe": sharpe(scaled_oos),
                 "oos_2025_max_drawdown": max_drawdown(scaled_oos),
                 "oos_2025_total_return": float(scaled_oos.iloc[-1] / scaled_oos.iloc[0] - 1) if len(scaled_oos) > 1 else None,
                 "n_days": len(scaled_oos)}
        oos_results.append(oos_r)
        ref_oos = HYP047_OOS_REF[level]
        g3 = "PASS" if oos_r["oos_2025_sharpe"] > ref_oos else "FAIL"
        print(f"              OOS-Sharpe={oos_r['oos_2025_sharpe']:.4f} ({g3} mot HYP-047:s {ref_oos:.4f} enl. lasta kriteriet)  "
              f"OOS-avkastning={oos_r['oos_2025_total_return']:+.2%}  OOS-MaxDD={oos_r['oos_2025_max_drawdown']:.2%}")
        ml = disclosure_by_level[level]["main_period"]
        print(f"              Disclosure (main-period): snitt-skala={ml['avg_scale']:.3f}  "
              f"lagsta-skala={ml['min_scale']:.3f}  andel veckor <1.0={ml['pct_weeks_below_1']:.1%} "
              f"({ml['n_decisions']} veckobeslut)\n")

    # --- PASS/FAIL enligt det lasta kriteriet, AVGORANDE vid $100k ---
    lvl = 100_000
    m = main_results[0]
    o = oos_results[0]
    ref = HYP047_MAIN_REF[lvl]
    ref_oos = HYP047_OOS_REF[lvl]
    cond1 = m["sharpe"] > ref["sharpe"]
    cond2 = m["max_drawdown"] > ref["max_drawdown"]
    cond3 = o["oos_2025_sharpe"] > ref_oos
    overall = "PASSED" if (cond1 and cond2 and cond3) else "FAILED"

    print("=== SLUTBEDOMNING (avgorande $100k-niva) ===")
    print(f"  Villkor 1 (Sharpe > HYP-047 {ref['sharpe']}): {m['sharpe']:.4f} -> {'PASS' if cond1 else 'FAIL'}")
    print(f"  Villkor 2 (MaxDD battre an HYP-047 {ref['max_drawdown']:.2%}): {m['max_drawdown']:.2%} -> {'PASS' if cond2 else 'FAIL'}")
    print(f"  Villkor 3 (OOS-Sharpe > HYP-047 {ref_oos}): {o['oos_2025_sharpe']:.4f} -> {'PASS' if cond3 else 'FAIL'}")
    print(f"  => {overall}\n")

    import json
    summary = {
        "main": main_results,
        "oos_2025": oos_results,
        "hyp047_locked_criterion_ref": {"main": HYP047_MAIN_REF, "oos_2025": HYP047_OOS_REF},
        "hyp047_actual_summary_json_ref": {"main": HYP047_MAIN_ACTUAL, "oos_2025": HYP047_OOS_ACTUAL},
        "exposure_scale_disclosure": disclosure_by_level,
        "dsr_n_trials": DSR_N_TRIALS,
        "pass_fail": {
            "condition_1_sharpe": bool(cond1), "condition_2_maxdd": bool(cond2),
            "condition_3_oos_sharpe": bool(cond3), "overall": overall,
        },
    }
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
