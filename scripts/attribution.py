"""
Attributionsrapport - separerar "ar det genuin alfa eller nagot annat
som skapar problemet" for en redan testad hypotes (2026-08-01, CEO-
beslut). Aggs av Performance Analyst/Risk Manager-rollerna.

MOTIV: varje backtest hittills har bara rapporterat EN hopklumpad
Sharpe/MaxDD for hela paketet (signal + beta-hedge + friktion +
kapacitetsspärr + ev. overlay). Det gor det omojligt att se, utan en
manuell engangsinsats (som faktorregressionen som gjordes for HYP-023
2026-07-31), om en svag/stark totalsiffra beror pa sjalva
signalkvaliteten eller pa nagot annat i "forpackningen" - t.ex. en
strategi med genuint bra alfa som rakar bli hart traffad av en enskild
sektor (branschkoncentration, som HYP-017:s 27.3%-mot-7.0%-bankfynd).

Denna modul gor TRE redan enskilt anvanda tekniker i detta projekt till
en STANDARDISERAD, ateranvandbar rapport som kors mot VILKEN SOM HELST
redan kord hypotes utan att röra dess (lasta) backtest-kod:

1. FAKTORREGRESSION mot Fama-French 5 + momentum (generaliserad fran
   paper_trading/HYP-023/factor_regression.py) - isolerar "kand
   faktorexponering" fran "egen, oforklarad alfa".
2. SEKTOREXPONERING over hallna namn (SIC-baserad, samma metod som
   avslojade HYP-017:s bankkoncentration, generaliserad fran binar
   bank/finans till ALLA SIC-branschgrupper) - flaggar automatiskt om
   nagon bransch ar overrepresenterad mot basuniversumet, i stallet for
   att bara upptackas via en manuell efterhandskoll.
3. FRIKTIONSDRAG per trade (fran trade_log:ens redan loggade gross_ret
   vs ret-kolumner, som ALLA hypoteser i detta register redan sparar) -
   isolerar hur mycket av en svag nettosiffra som beror pa
   friktionskostnad snarare an sjalva signalens tra ffsakerhet.

ANVANDNING:
  python scripts/attribution.py HYP-023
  python scripts/attribution.py HYP-023 --levels 100000 1000000

KAND BEGRANSNING (redovisas, inte dold): denna rapport kan INTE isolera
en overlay/hedges EGET bidrag som en separat Sharpe-siffra - portfoljvardet
i pv-serien har redan hedge_pnl inbakat, och trade_log innehaller bara
diskreta in-/utgangar, inte dagliga marknadsvarderingar. En fullstandig
sadan nedbrytning kraver att FRAMTIDA backtest.py-motorer sparar en
extra, separat komponentserie (stock-P&L/hedge-P&L/friktionskostnad var
for sig) - INTE nagot som retroaktivt laggs till i redan lasta,
rapporterade hypotesers kod. Se moduldocstringens slutkommentar for
konventionen framtida hypoteser kan folja om detta vaxer till ett krav.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
FF_DIR = REPO_ROOT / "data" / "cache" / "famafrench"
SIC_FILE = REPO_ROOT / "data" / "cache" / "sic_classification.jsonl"
STRATEGIES_DIR = REPO_ROOT / "strategies"

sys.path.insert(0, str(STRATEGIES_DIR / "common"))
from sector import load_ticker_major_group  # noqa: E402

DEFAULT_LEVELS = [100_000, 1_000_000, 10_000_000]


# ════════════════════════════════════════════════════════════
#  1. FAKTORREGRESSION (generaliserad fran paper_trading/HYP-023/factor_regression.py)
# ════════════════════════════════════════════════════════════
def load_ff_factors() -> pd.DataFrame:
    ff5 = pd.read_csv(FF_DIR / "F-F_Research_Data_5_Factors_2x3_daily.csv", skiprows=3)
    ff5.columns = ["date"] + list(ff5.columns[1:])
    ff5 = ff5[ff5["date"].astype(str).str.match(r"^\d{8}$", na=False)]
    ff5["date"] = pd.to_datetime(ff5["date"].astype(str), format="%Y%m%d")
    ff5 = ff5.set_index("date")
    for c in ff5.columns:
        ff5[c] = pd.to_numeric(ff5[c], errors="coerce") / 100.0

    mom = pd.read_csv(FF_DIR / "F-F_Momentum_Factor_daily.csv", skiprows=13)
    mom = mom.iloc[:, :2]
    mom.columns = ["date", "MOM"]
    mom = mom[mom["date"].astype(str).str.match(r"^\d{8}$", na=False)]
    mom["date"] = pd.to_datetime(mom["date"].astype(str), format="%Y%m%d")
    mom = mom.set_index("date")
    mom["MOM"] = pd.to_numeric(mom["MOM"], errors="coerce") / 100.0

    return ff5.join(mom, how="inner")


def _ols_with_stats(y: np.ndarray, X: np.ndarray, factor_names: list) -> dict:
    """Standard OLS med t-statistik. X FORVANTAS redan ha en
    konstant-kolumn forst (for alfa/intercept). Vanlig OLS, INTE
    Newey-West-korrigerad for autokorrelation - samma kanda reservation
    som redan flaggades i HYP-023:s egen faktorregression."""
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


def factor_regression(pv: pd.Series, ff: pd.DataFrame) -> dict:
    ret = pv.pct_change().dropna()
    joined = pd.concat([ret.rename("strategy"), ff], axis=1, join="inner").dropna()
    if len(joined) < 60:
        return {"error": f"for fa overlappande observationer med Fama-French-data ({len(joined)})"}

    y = (joined["strategy"] - joined["RF"]).values
    factor_names = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "MOM"]
    X = np.column_stack([np.ones(len(joined))] + [joined[f].values for f in factor_names])
    res = _ols_with_stats(y, X, factor_names)

    alpha_daily = res["alpha"]["coef"]
    return {
        "n_obs": res["n_obs"],
        "alpha_daily": alpha_daily,
        "alpha_annual": (1 + alpha_daily) ** 252 - 1,
        "alpha_t_stat": res["alpha"]["t_stat"],
        "alpha_significant": abs(res["alpha"]["t_stat"]) > 2,
        "r_squared": res["r_squared"],
        "factor_loadings": {f: res[f] for f in factor_names},
    }


# ════════════════════════════════════════════════════════════
#  2. SEKTOREXPONERING (SIC-baserad, generaliserad fran den binara
#     bank/finans-metoden som avslojade HYP-017:s koncentrationsfynd)
# ════════════════════════════════════════════════════════════
def load_sic_lookup() -> tuple:
    """Returnerar (ticker -> 2-siffrig SIC-huvudgrupp, huvudgrupp ->
    representativ branschbeskrivning). ticker_to_major kommer fran
    strategies/common/sector.py::load_ticker_major_group() - SAMMA
    funktion HYP-036 anvander for sin sektorneutrala rankning, med
    flit, sa diagnostik och strategikod aldrig kan glida isar.
    Beskrivningen valjs har separat som den VANLIGASTE sic_description
    bland ALLA kanda tickers i huvudgruppen - en stabil, ateranvandbar
    etikett, bara for lasbarhet i rapporten."""
    all_tickers_with_sic = []
    major_desc_votes = {}
    with SIC_FILE.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            sic = row.get("sic")
            if not sic:
                continue
            all_tickers_with_sic.append(row["ticker"])
            # Samma buggfix som strategies/common/sector.py::load_ticker_major_group
            # (kodgranskning 2026-08-05) - nollutfyll fore trunkering, annars tappas
            # inledande nollan for SIC-koder under 1000 (Division A).
            major = f"{int(sic):04d}"[:2]
            major_desc_votes.setdefault(major, Counter())[row.get("sic_description", "")] += 1

    ticker_to_major = load_ticker_major_group(all_tickers_with_sic)
    major_to_label = {mg: votes.most_common(1)[0][0] for mg, votes in major_desc_votes.items()}
    return ticker_to_major, major_to_label


def load_universe_by_month() -> dict:
    universe_file = REPO_ROOT / "data" / "cache" / "smallcap_universe_by_month.json"
    with universe_file.open(encoding="utf-8") as f:
        return json.load(f)


def base_universe_for_window(universe_by_month: dict, start, end) -> set:
    """
    BUGGFIX (kodgranskning 2026-08-05): tidigare (load_base_universe_tickers,
    borttagen) slog denna funktion ihop VARJE manad 2010-2024 till en enda
    statisk mangd, oavsett vilken period hypotesen faktiskt handlade i.
    Om small-cap-universumets branschsammansattning forskjutits over de 14
    aren (troligt) blir VARJE tidigare rapporterad "Nx overrepresenterad"-
    siffra jamford mot fel periods bas-rate - sarskilt for hypoteser som
    bara handlar en delmangd av hela perioden (t.ex. en genuin OOS-2025-
    korning, eller en framtida kortare backtest). Fix: bas-universumet
    begransas nu till exakt de kalendermanader som ligger inom hypotesens
    egen handelsperiod (portfoljvarde-seriens forsta/sista datum),
    identiskt fonster som det som faktiskt jamfors mot."""
    tickers = set()
    for month_key, month_tickers in universe_by_month.items():
        month_date = pd.Timestamp(month_key)
        if start <= month_date <= end:
            tickers.update(month_tickers)
    return tickers


def sector_exposure(trade_log: pd.DataFrame, ticker_to_major: dict, major_to_label: dict,
                     base_universe: set) -> dict:
    """
    Portfoljvikt per sektor = andel av total DOLLAR-KOSTNAD (trade_log:ens
    'cost'-kolumn) som gick till namn i den sektorn - samma metod som
    avslojade HYP-017:s 27.3%-bankexponering (fast generaliserad till
    ALLA sektorer, inte bara bank/finans). Faller tillbaka till
    OVIKTAT antal trades om 'cost' saknas (t.ex. HYP-008:s
    par-handels-motor, som inte loggar dollarstorlek per ben).

    Basuniversum-jamforelsen anvander universumet UNDER hypotesens egen
    handelsperiod (se base_universe_for_window - fixat 2026-08-05, tidigare
    anvandes hela 2010-2024 slaget ihop oavsett handelsperiod).
    """
    has_cost = "cost" in trade_log.columns and trade_log["cost"].notna().any()
    weight_col = "cost" if has_cost else None

    tl = trade_log.copy()
    tl["major_group"] = tl["ticker"].map(ticker_to_major)
    tl["major_group"] = tl["major_group"].fillna("XX")  # okand/ej klassificerad
    major_to_label = {**major_to_label, "XX": "Okand/ej SIC-klassificerad"}

    if weight_col:
        by_sector = tl.groupby("major_group")[weight_col].sum()
        held_pct = (by_sector / by_sector.sum()).sort_values(ascending=False)
        weight_method = "dollarkostnad (trade_log['cost'])"
    else:
        by_sector = tl.groupby("major_group").size()
        held_pct = (by_sector / by_sector.sum()).sort_values(ascending=False)
        weight_method = "OVIKTAT antal trades (cost saknas i denna hypotes trade_log)"

    base_major = pd.Series({t: ticker_to_major.get(t, "XX") for t in base_universe})
    base_pct = base_major.value_counts(normalize=True)

    rows = []
    for mg, pct in held_pct.items():
        rows.append({
            "sic_major_group": mg,
            "label": major_to_label.get(mg, "?"),
            "pct_of_portfolio": float(pct),
            "pct_of_base_universe": float(base_pct.get(mg, 0.0)),
            "overrepresentation_ratio": float(pct / base_pct.get(mg, np.nan)) if base_pct.get(mg, 0.0) > 0 else None,
        })

    return {"weight_method": weight_method, "sectors": rows}


# ════════════════════════════════════════════════════════════
#  3. FRIKTIONSDRAG (fran trade_log:ens redan loggade gross_ret vs ret)
# ════════════════════════════════════════════════════════════
def friction_drag(trade_log: pd.DataFrame) -> dict:
    if len(trade_log) == 0:
        return {"error": "tom trade_log"}
    drag = trade_log["gross_ret"] - trade_log["ret"]
    result = {
        "n_trades": len(trade_log),
        "mean_gross_ret": float(trade_log["gross_ret"].mean()),
        "mean_net_ret": float(trade_log["ret"].mean()),
        "mean_drag_pp": float(drag.mean() * 100),
        "median_drag_pp": float(drag.median() * 100),
    }
    if "cost" in trade_log.columns and trade_log["cost"].notna().any():
        dollar_drag = (drag * trade_log["cost"]).sum()
        total_cost_base = trade_log["cost"].sum()
        result["dollar_weighted_drag_pct_of_turnover"] = float(dollar_drag / total_cost_base * 100) if total_cost_base else None
    return result


# ════════════════════════════════════════════════════════════
#  RAPPORT
# ════════════════════════════════════════════════════════════
def run_report(hyp_id: str, level: int, ff: pd.DataFrame, ticker_to_major: dict, major_to_label: dict,
                universe_by_month: dict) -> dict:
    results_dir = STRATEGIES_DIR / hyp_id / "results"
    pv_path = results_dir / f"portfolio_value_{level}.csv"
    tl_path = results_dir / f"trade_log_{level}.csv"

    if not pv_path.exists() or not tl_path.exists():
        return {"capital_level": level, "error": f"saknar resultatfiler i {results_dir}"}

    pv = pd.read_csv(pv_path, index_col=0, parse_dates=True)["portfolio_value"]
    tl = pd.read_csv(tl_path, parse_dates=["date"]) if tl_path.stat().st_size > 0 else pd.DataFrame()

    # Bas-universum begransat till DENNA hypotes egen handelsperiod - se
    # base_universe_for_window (buggfix 2026-08-05, tidigare hela 2010-2024).
    base_universe = base_universe_for_window(universe_by_month, pv.index.min(), pv.index.max())

    report = {"capital_level": level}
    report["factor_regression"] = factor_regression(pv, ff)
    report["friction_drag"] = friction_drag(tl) if len(tl) else {"error": "tom trade_log"}
    report["sector_exposure"] = sector_exposure(tl, ticker_to_major, major_to_label, base_universe) if len(tl) else {"error": "tom trade_log"}
    return report


def print_report(hyp_id: str, report: dict):
    level = report["capital_level"]
    print(f"\n{'=' * 70}\n{hyp_id} @ ${level:,.0f}\n{'=' * 70}")

    fr = report.get("factor_regression", {})
    if "error" in fr:
        print(f"  Faktorregression: {fr['error']}")
    else:
        sig = "SIGNIFIKANT" if fr["alpha_significant"] else "ej signifikant"
        print(f"  Faktorregression (Fama-French 5 + momentum, n={fr['n_obs']} dagar):")
        print(f"    Alfa: {fr['alpha_annual']:+.2%}/år (t={fr['alpha_t_stat']:+.2f}, {sig})  R²={fr['r_squared']:.3f}")
        loadings = ", ".join(f"{k}={v['coef']:+.2f}(t={v['t_stat']:+.1f})" for k, v in fr["factor_loadings"].items())
        print(f"    Loadings: {loadings}")

    fd = report.get("friction_drag", {})
    if "error" in fd:
        print(f"  Friktionsdrag: {fd['error']}")
    else:
        print(f"  Friktionsdrag ({fd['n_trades']} trades): snitt {fd['mean_drag_pp']:+.2f}pp/trade "
              f"(brutto {fd['mean_gross_ret']:+.2%} -> netto {fd['mean_net_ret']:+.2%})")
        if fd.get("dollar_weighted_drag_pct_of_turnover") is not None:
            print(f"    Dollarviktat drag: {fd['dollar_weighted_drag_pct_of_turnover']:+.2f}% av omsatt kapital")

    se = report.get("sector_exposure", {})
    if "error" in se:
        print(f"  Sektorexponering: {se['error']}")
    else:
        print(f"  Sektorexponering ({se['weight_method']}), topp 5 mot basuniversum:")
        for row in se["sectors"][:5]:
            ratio = f"{row['overrepresentation_ratio']:.1f}x" if row["overrepresentation_ratio"] else "n/a"
            flag = " <-- OVERREPRESENTERAD" if row["overrepresentation_ratio"] and row["overrepresentation_ratio"] > 1.5 else ""
            print(f"    SIC {row['sic_major_group']} {row['label'][:40]:40s}  "
                  f"portfolj={row['pct_of_portfolio']:.1%}  universum={row['pct_of_base_universe']:.1%}  "
                  f"({ratio}){flag}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hyp_id", help="t.ex. HYP-023")
    parser.add_argument("--levels", type=int, nargs="+", default=None,
                         help=f"kapitalnivaer, default {DEFAULT_LEVELS} (bara de som har resultatfiler)")
    args = parser.parse_args()

    print("Laddar Fama-French-faktorer, SIC-klassificering, basuniversum...")
    ff = load_ff_factors()
    ticker_to_major, major_to_label = load_sic_lookup()
    universe_by_month = load_universe_by_month()

    levels = args.levels or DEFAULT_LEVELS
    all_reports = []
    for level in levels:
        report = run_report(args.hyp_id, level, ff, ticker_to_major, major_to_label, universe_by_month)
        all_reports.append(report)
        if "error" in report:
            print(f"\n{args.hyp_id} @ ${level:,.0f}: {report['error']}")
        else:
            print_report(args.hyp_id, report)

    out_dir = STRATEGIES_DIR / args.hyp_id / "results"
    out_path = out_dir / "attribution_report.json"
    if out_dir.exists():
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(all_reports, f, indent=2, ensure_ascii=False, default=str)
        print(f"\nKLART. Sparat till {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
