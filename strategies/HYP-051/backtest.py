"""
HYP-051: Tvarsnittsdispersion som exponeringsregim pa momentum L/S-sviten.

Se research/hypothesis_registry/HYP-051-dispersion-regim-momentum-overlay.yaml
for det lasta kriteriet. Sjatte hypotesen testad fran BATCH-002.

MEKANISM (lockad): daglig TVARSNITTS-standardavvikelse av samtliga
eligible-namns dagliga avkastningar (INTE ett enskilt index tidsserie-
vol - ett genuint tvarsnittsmatt, berknat separat varje handelsdag over
manadens eligible-universum). Rullande 2-ars (504 handelsdagars)
percentil av detta matt. TRIGGER: nar dagens dispersion faller under
sin egen 20:e percentil, HALVERAS bade long- och kortbenets exponering
i momentum L/S-sviten tills dispersionen ater overstiger 20:e
percentilen. Kontrolleras VARJE handelsdag, appliceras vid NASTA
handelsdag efter trigger (samma 1-dags exekveringslag som resten av
registrets krasch-/regim-overlayer). Sviten i ovrigt HELT OFORANDRAD
(samma 12-1-manaders signal, decilstorlek, kvartalsvis ombalansering,
friktion som HYP-043:s redan korrigerade, spreadinklusive DEL E-variant
- se den filens compute_momentum_ls_sleeve, USE_SPREAD_COST=True).

INGEN NY PRISDATA BEHOVS UTOVER VAD SVITEN REDAN LADDAR: dispersions-
matten berknas fran SAMMA close_adj-matris och SAMMA manatliga
eligible-universum som redan byggs for momentumsignalen - ingen extra
inlasning.

Funktionen nedan AR EN AVSIKTLIG KOPIA av HYP-043:s
compute_momentum_ls_sleeve (samma monster som HYP-047:s
compute_momentum_ls_sleeve_with_spread redan etablerade: varje
konsumerande hypotes bygger sin EGEN lokala version snarare an att
importera en delad funktion fran en annan hypotes-mapp) - dels for att
scripts/validate_friction_usage.py (Risk Manager-grinden) kraver att
BADA friktionsfunktionerna faktiskt anropas I DENNA FIL, dels for att
overlayn maste in i sjalva dag-loopen (kan inte lagga pa i efterhand
ovanpa en redan sparad avkastningsserie, eftersom exponeringen andras
INTRADAG-till-dag, inte bara vid ombalanseringar).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

STRATEGY_DIR = Path(__file__).resolve().parent
STRATEGIES_ROOT = STRATEGY_DIR.parent
REPO_ROOT = STRATEGIES_ROOT.parent
DATA_DIR = REPO_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
RESULTS_DIR = STRATEGY_DIR / "results"

HYP037_DIR = STRATEGIES_ROOT / "HYP-037"
HYP043_RESULTS = STRATEGIES_ROOT / "HYP-043" / "results_corrected_2026-08-08"

ORIGINAL_UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_by_month_filed_date.json"
EXTENSION_UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_2025_extension_filed_date.json"

sys.path.insert(0, str(HYP037_DIR))
import backtest as hyp037  # noqa: E402
from friction import borrow_cost, corwin_schultz_spread  # noqa: E402

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
from rebalancing import snap_rebalance_dates  # noqa: E402
from data_hygiene import mask_implausible_adjusted_close_ratio  # noqa: E402

REBAL_FREQ = "QE"
MOM_LOOKBACK_DAYS = 252
MOM_SKIP_DAYS = 21
DECILE_FRACTION = 0.10
BORROW_ANNUAL_RATE = 0.03
RF_ANNUAL = 0.02

DISPERSION_PERCENTILE_WINDOW = 504   # 2 ar, trailing
DISPERSION_TRIGGER_PERCENTILE = 0.20  # under 20:e percentilen -> LAG dispersion
OVERLAY_MULTIPLIER = 0.5              # halverad nettoexponering under LAG-tillstand

OOS_START = "2025-01-01"
FULL_END_MAIN = "2024-12-31"
FULL_END_WITH_OOS = "2025-12-31"


def compute_spread_matrix(high, low):
    spread = {}
    for t in high.columns:
        spread[t] = corwin_schultz_spread(high[t].values, low[t].values)
    return pd.DataFrame(spread, index=high.index)


def compute_cross_sectional_dispersion(daily_ret: pd.DataFrame, universe_by_month: dict,
                                        month_keys: list, month_dates: pd.DatetimeIndex,
                                        tidx: dict) -> pd.Series:
    """Daglig tvarsnitts-std (ddof=1) av avkastningarna for MANADENS
    eligible-universum (INTE hela historiska tickerlistan) - en genuin
    tvarsnittsmatt per dag, inte en tidsserie-vol for ett enskilt index.
    Grupperar per manad for prestanda (178 manader i stallet for en
    Python-loop per dag)."""
    idx = daily_ret.index
    day_month_pos = month_dates.searchsorted(idx, side="right") - 1
    day_month_pos = np.clip(day_month_pos, 0, len(month_dates) - 1)

    dispersion = pd.Series(np.nan, index=idx)
    for pos in np.unique(day_month_pos):
        key = month_keys[pos]
        eligible = [t for t in universe_by_month.get(key, []) if t in tidx]
        if len(eligible) < 20:
            continue
        day_mask = day_month_pos == pos
        sub = daily_ret.loc[idx[day_mask], eligible]
        dispersion.loc[idx[day_mask]] = sub.std(axis=1, ddof=1, skipna=True)
    return dispersion


def rolling_percentile(s: pd.Series, window: int) -> pd.Series:
    """Andel av de trailing `window` observationerna (INKL. dagens egen,
    samma konvention som redan anvands av registrets ovriga regim-
    triggar) som ar STRIKT mindre an dagens varde - ett tal i [0, 1)."""
    def _pct_rank(x):
        return (x[:-1] < x[-1]).mean() if len(x) > 1 else np.nan
    return s.rolling(window, min_periods=window).apply(_pct_rank, raw=True)


def compute_momentum_ls_sleeve_with_overlay(universe_by_month: dict):
    tickers = sorted({t for tks in universe_by_month.values() for t in tks})
    close, close_adj, high, low, volume = hyp037.load_price_matrices(tickers, hyp037.FULL_START, FULL_END_WITH_OOS)

    close, high, low = hyp037.clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    implausible = hyp037.flag_implausible_liquidity(close, volume, max_market_cap=hyp037.MAX_MARKET_CAP,
                                                      window=hyp037.ADV_WINDOW, multiplier=1.0)
    close_adj = close_adj.mask(implausible)
    close_adj = mask_implausible_adjusted_close_ratio(close, close_adj)

    print("  Berknar Corwin-Schultz-spread-matris (momentum L/S)...")
    spread_df = compute_spread_matrix(high, low)

    momentum = close_adj.shift(MOM_SKIP_DAYS) / close_adj.shift(MOM_LOOKBACK_DAYS) - 1
    daily_ret = close_adj.pct_change()

    tidx = {t: i for i, t in enumerate(close.columns)}
    month_keys = sorted(universe_by_month.keys())
    month_dates = pd.to_datetime(month_keys)

    print("  Berknar daglig tvarsnittsdispersion over eligible-universumet...")
    dispersion = compute_cross_sectional_dispersion(daily_ret, universe_by_month, month_keys, month_dates, tidx)
    dispersion_pctile = rolling_percentile(dispersion, DISPERSION_PERCENTILE_WINDOW)
    low_dispersion_state = dispersion_pctile < DISPERSION_TRIGGER_PERCENTILE
    # 1-dags exekveringslag: gardagens tillstand styr dagens exponering
    overlay_active = low_dispersion_state.shift(1).fillna(False)

    calendar_dates = close.resample(REBAL_FREQ).last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[MOM_LOOKBACK_DAYS])
                                     & (calendar_dates <= close.index[-1])]
    snapped = snap_rebalance_dates(calendar_dates, close.index)
    rebal_map = dict(zip(snapped["execution_date"], snapped["calendar_label"]))
    rebal_set = set(snapped["execution_date"])
    start_idx = close.index.get_indexer([snapped["execution_date"].iloc[0]])[0]
    trade_dates = close.index[start_idx:]

    long_names, short_names = [], []
    pv_list = [1.0]
    pv_no_overlay_list = [1.0]
    n_overlay_active_days = 0

    for date_i in range(start_idx, len(close.index)):
        date = close.index[date_i]
        rebalance_cost = 0.0

        if date in rebal_set:
            month_key = rebal_map[date].strftime("%Y-%m-%d")
            eligible = [t for t in universe_by_month.get(month_key, []) if t in tidx]
            mom_today = momentum.loc[date, eligible].dropna()
            if len(mom_today) >= 20:
                ranked = mom_today.sort_values()
                n_decile = max(1, int(len(ranked) * DECILE_FRACTION))
                new_short = list(ranked.index[:n_decile])
                new_long = list(ranked.index[-n_decile:])

                long_spreads = spread_df.loc[date, new_long].dropna() if new_long else pd.Series(dtype=float)
                short_spreads = spread_df.loc[date, new_short].dropna() if new_short else pd.Series(dtype=float)
                avg_long_spread = float(long_spreads.mean()) if len(long_spreads) else 0.0
                avg_short_spread = float(short_spreads.mean()) if len(short_spreads) else 0.0
                rebalance_cost = 0.5 * (avg_long_spread / 2) + 0.5 * (avg_short_spread / 2)

                long_names, short_names = new_long, new_short

        if date_i > start_idx and (long_names or short_names):
            long_r = daily_ret.loc[date, long_names].mean() if long_names else 0.0
            short_r = daily_ret.loc[date, short_names].mean() if short_names else 0.0
            long_r = 0.0 if np.isnan(long_r) else long_r
            short_r = 0.0 if np.isnan(short_r) else short_r

            mult = OVERLAY_MULTIPLIER if bool(overlay_active.get(date, False)) else 1.0
            if mult < 1.0:
                n_overlay_active_days += 1
            daily_borrow = borrow_cost(position_value=mult * 0.5, holding_days=1, annual_rate=BORROW_ANNUAL_RATE)

            period_ret = mult * 0.5 * long_r - mult * 0.5 * short_r - daily_borrow + (RF_ANNUAL / 252) - rebalance_cost
            pv_list.append(pv_list[-1] * (1 + period_ret))

            daily_borrow_no = borrow_cost(position_value=0.5, holding_days=1, annual_rate=BORROW_ANNUAL_RATE)
            period_ret_no = 0.5 * long_r - 0.5 * short_r - daily_borrow_no + (RF_ANNUAL / 252) - rebalance_cost
            pv_no_overlay_list.append(pv_no_overlay_list[-1] * (1 + period_ret_no))
        else:
            pv_list.append(pv_list[-1])
            pv_no_overlay_list.append(pv_no_overlay_list[-1])

    print(f"  Overlay aktiv (halverad exponering) {n_overlay_active_days} av {len(trade_dates) - 1} handelsdagar "
          f"({n_overlay_active_days / max(1, len(trade_dates) - 1):.1%})")

    return (pd.Series(pv_list[1:], index=trade_dates),
            pd.Series(pv_no_overlay_list[1:], index=trade_dates))


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
    print("Laddar universum (huvudserie + 2025-utokning, sammanslaget)...")
    with ORIGINAL_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_orig = json.load(f)
    with EXTENSION_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_2025 = json.load(f)
    universe_merged = {**universe_orig, **universe_2025}

    print("Bygger momentum L/S-sviten MED och UTAN dispersionsoverlay (en genomgang racker for bade huvudtest och OOS)...")
    pv_overlay, pv_no_overlay = compute_momentum_ls_sleeve_with_overlay(universe_merged)
    RESULTS_DIR.mkdir(exist_ok=True)
    pv_overlay.to_csv(RESULTS_DIR / "momentum_ls_sleeve_with_overlay_pv.csv", header=["portfolio_value"])
    pv_no_overlay.to_csv(RESULTS_DIR / "momentum_ls_sleeve_no_overlay_recomputed_pv.csv", header=["portfolio_value"])

    # Referens: HYP-043:s egna, redan sparade, fullt korrigerade isolerade
    # svit-serie (DEL E-pipelinen, USE_SPREAD_COST=True i produktionskoden)
    # - anvands som DEN OFFICIELLA "UTAN overlay"-referensen kriteriet
    # pekar pa, INTE den lokalt aterberknade (som bara ar en determinism-
    # kontroll, sparas separat ovan for spårbarhet).
    ref_no_overlay_full = pd.read_csv(HYP043_RESULTS / "momentum_ls_sleeve_pv.csv", index_col=0, parse_dates=True)["portfolio_value"]

    print("\n=== HYP-051: huvudperiod (2010-2024) ===")
    pv_overlay_main = pv_overlay.loc[:FULL_END_MAIN]
    pv_no_overlay_main = pv_no_overlay.loc[:FULL_END_MAIN]
    ref_main = ref_no_overlay_full.loc[:FULL_END_MAIN]

    r_overlay = {"sharpe": sharpe(pv_overlay_main), "cagr": cagr(pv_overlay_main),
                 "max_drawdown": max_drawdown(pv_overlay_main), "calmar": calmar(pv_overlay_main),
                 "n_days": len(pv_overlay_main)}
    r_ref = {"sharpe": sharpe(ref_main), "cagr": cagr(ref_main),
             "max_drawdown": max_drawdown(ref_main), "calmar": calmar(ref_main), "n_days": len(ref_main)}
    r_no_overlay_recomputed = {"sharpe": sharpe(pv_no_overlay_main), "max_drawdown": max_drawdown(pv_no_overlay_main)}

    g1 = "PASS" if r_overlay["sharpe"] > r_ref["sharpe"] else "FAIL"
    g2 = "PASS" if r_overlay["max_drawdown"] > r_ref["max_drawdown"] else "FAIL"
    print(f"  MED overlay:  Sharpe={r_overlay['sharpe']:.4f}  MaxDD={r_overlay['max_drawdown']:.2%}  "
          f"CAGR={r_overlay['cagr']:+.2%}  Calmar={r_overlay['calmar']:.3f}")
    print(f"  UTAN overlay (HYP-043:s referens): Sharpe={r_ref['sharpe']:.4f}  MaxDD={r_ref['max_drawdown']:.2%}  "
          f"CAGR={r_ref['cagr']:+.2%}  Calmar={r_ref['calmar']:.3f}")
    print(f"  (lokal aterberkning UTAN overlay, determinismkontroll: Sharpe={r_no_overlay_recomputed['sharpe']:.4f}  "
          f"MaxDD={r_no_overlay_recomputed['max_drawdown']:.2%})")
    print(f"  Villkor 1 (Sharpe MED > UTAN): {g1}")
    print(f"  Villkor 2 (MaxDD MED inte samre an UTAN): {g2}")

    print("\n=== HYP-051: OOS-2025 (informativt, ej gating enligt kriteriet) ===")
    pv_overlay_oos = pv_overlay.loc[OOS_START:FULL_END_WITH_OOS]
    ref_oos = ref_no_overlay_full.loc[OOS_START:FULL_END_WITH_OOS]
    r_overlay_oos = {"sharpe": sharpe(pv_overlay_oos), "max_drawdown": max_drawdown(pv_overlay_oos),
                      "total_return": float(pv_overlay_oos.iloc[-1] / pv_overlay_oos.iloc[0] - 1)}
    r_ref_oos = {"sharpe": sharpe(ref_oos), "max_drawdown": max_drawdown(ref_oos),
                 "total_return": float(ref_oos.iloc[-1] / ref_oos.iloc[0] - 1)}
    print(f"  MED overlay:  OOS-Sharpe={r_overlay_oos['sharpe']:.4f}  OOS-MaxDD={r_overlay_oos['max_drawdown']:.2%}  "
          f"OOS-avkastning={r_overlay_oos['total_return']:+.2%}")
    print(f"  UTAN overlay: OOS-Sharpe={r_ref_oos['sharpe']:.4f}  OOS-MaxDD={r_ref_oos['max_drawdown']:.2%}  "
          f"OOS-avkastning={r_ref_oos['total_return']:+.2%}")

    # Kapitalnivainvariant (samma som HYP-043/047:s egen momentum L/S-svit
    # - ingen ADV-kapacitetsspärr i denna konstruktion, se docstring) -
    # samma resultat rapporteras for alla tre nivaer, konsistent med
    # etablerad praxis for denna sviten.
    levels = [100_000, 1_000_000, 10_000_000]
    per_level = {lvl: {"main": r_overlay, "main_ref_no_overlay": r_ref, "oos_2025": r_overlay_oos,
                        "oos_2025_ref_no_overlay": r_ref_oos, "condition_1_pass": g1 == "PASS",
                        "condition_2_pass": g2 == "PASS"} for lvl in levels}

    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump({"per_capital_level": per_level,
                   "no_overlay_recomputed_determinism_check": r_no_overlay_recomputed}, f, indent=2, default=str)

    print("\nKLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
