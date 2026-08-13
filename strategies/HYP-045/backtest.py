"""
HYP-045: Krasch-overlay pa de idag oskyddade benen (SPY + momentum L/S)
i den naiva tredelade HYP-043-kombinationen.

Se research/hypothesis_registry/HYP-045-krasch-overlay-spy-momentum-ben.yaml
for det lasta kriteriet. Femte kombinationshypotesen i projektet, per
spec §5b - denna gang INTE ett nytt 4:e ben utan en MODIFIERING av hur
tva av de tre redan befintliga benen beter sig under stress.

BAKGRUND: en attributionsanalys 2026-08-07 (samma dag) visade att 8.0%
av HYP-043-kombons dagar (5 redan kanda krisepisoder: 2011 skuldtak,
2015 Black Monday, 2018 julafton, 2020 covid, 2022 bjornmarknad) star
for -26.76% kumulativ avkastning, medan de ovriga 92% av dagarna gav
+463.58%. HYP-037-benet har REDAN en egen krasch-overlay (SPY-drawdown-
trigger) inbyggd - men SPY-benet (ratt, ohedgat) och momentum L/S-benet
(ingen overlay alls) star HELT oskyddade under exakt dessa perioder,
trots att de tillsammans ar 2/3 av kapitalet.

MEKANISM: aterananvander HYP-037:s EXAKT redan lasta triggerparametrar
(CRASH_LOOKBACK_DAYS=10, CRASH_TRIGGER_RET=-0.10, CRASH_HAIRCUT_
FRACTION=0.40, RECOVERY_FRACTION=0.50) - INGEN ny parametersokning.
Tillampas pa SPY-benet och momentum L/S-benet (HYP-037-benet ORORT,
har redan sin egen separata overlay).

DOKUMENTERAD FORENKLING (nodvandig anpassning, INTE en dold
parameterandring): HYP-037:s egen mekanism har en asymmetrisk
fordrojning (omedelbar nedskarning, men aterbyggnad forst vid NASTA
ORDINARIE DECIL-OMBALANSERING, plus ett likviditetsnormaliseringsvillkor
baserat pa aktiedecilens egen spread) - bada dessa detaljer ar
specifika for en enskild-aktie-decil-struktur och saknar naturlig
motsvarighet for en enskild ETF (SPY) eller en aggregerad L/S-svit.
Denna version aterbygger DIREKT (samma dag) nar prisaterhamtnings-
villkoret (RECOVERY_FRACTION) uppfylls, ingen separat likviditetsgrind.

FRIKTION: momentum L/S-sviten byggs har MED bade borrow_cost OCH
genuin corwin_schultz_spread-kostnad fran start (lardomen fran HYP-043/
044:s friktionsgap, se research/hypothesis_registry/_counter.yaml).
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
RESULTS_DIR = STRATEGY_DIR / "results_corrected_2026-08-08"

HYP037_DIR = STRATEGIES_ROOT / "HYP-037"
HYP037_RESULTS = HYP037_DIR / "results_corrected_2026-08-08"
HYP037_OOS_RESULTS = REPO_ROOT / "paper_trading" / "HYP-037" / "oos_2025_results"

# GRANSKNINGSFYND 2026-08-08: filed-datum-korrigerade universumfiler, se
# HYP-037/HYP-043:s identiska kommentarer.
ORIGINAL_UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_by_month_filed_date.json"
EXTENSION_UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_2025_extension_filed_date.json"

sys.path.insert(0, str(HYP037_DIR))
import backtest as hyp037  # noqa: E402
from friction import borrow_cost, corwin_schultz_spread  # noqa: E402

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
from rebalancing import snap_rebalance_dates  # noqa: E402
from data_hygiene import mask_implausible_adjusted_close_ratio  # noqa: E402

REBAL_FREQ = "QE"
WEIGHT_EACH = 1.0 / 3.0

# GRANSKNINGSFYND 2026-08-08: se HYP-039:s identiska kommentar om
# portfoljniva-ombalanseringskostnad (10bps pa omallokerat belopp).
REBALANCE_COST_BPS = 0.0010

MOM_LOOKBACK_DAYS = 252
MOM_SKIP_DAYS = 21
DECILE_FRACTION = 0.10
BORROW_ANNUAL_RATE = 0.03
RF_ANNUAL = 0.02

OOS_START = "2025-01-01"
FULL_END_WITH_OOS = "2025-12-31"

# Friktionskorrigerad HYP-043-baslinje (scripts/diagnostic_hyp043_friction_robustness.py,
# 2026-08-07) - INTE de ursprungligen lasta 1.0457/1.0498/0.9864, se moduldocstring.
HYP043_FRICTION_CORRECTED_REF = {
    100_000: {"sharpe": 0.8926, "max_drawdown": -0.1558},
    1_000_000: {"sharpe": 0.8940, "max_drawdown": -0.1568},
    10_000_000: {"sharpe": 0.8217, "max_drawdown": -0.1429},
}
HYP039_OOS_REF = {100_000: 0.9185, 1_000_000: 0.8116, 10_000_000: 0.7932}


def compute_spread_matrix(high, low):
    spread = {}
    for t in high.columns:
        spread[t] = corwin_schultz_spread(high[t].values, low[t].values)
    return pd.DataFrame(spread, index=high.index)


def compute_momentum_ls_sleeve_with_spread(universe_by_month: dict) -> pd.Series:
    tickers = sorted({t for tks in universe_by_month.values() for t in tks})
    close, close_adj, high, low, volume = hyp037.load_price_matrices(tickers, hyp037.FULL_START, FULL_END_WITH_OOS)

    close, high, low = hyp037.clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    implausible = hyp037.flag_implausible_liquidity(close, volume, max_market_cap=hyp037.MAX_MARKET_CAP,
                                                      window=hyp037.ADV_WINDOW, multiplier=1.0)
    close_adj = close_adj.mask(implausible)
    close_adj = mask_implausible_adjusted_close_ratio(close, close_adj)

    print("  Berknar Corwin-Schultz-spread-matris...")
    spread_df = compute_spread_matrix(high, low)

    momentum = close_adj.shift(MOM_SKIP_DAYS) / close_adj.shift(MOM_LOOKBACK_DAYS) - 1
    daily_ret = close_adj.pct_change()

    tidx = {t: i for i, t in enumerate(close.columns)}
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
            daily_borrow = borrow_cost(position_value=0.5, holding_days=1, annual_rate=BORROW_ANNUAL_RATE)
            period_ret = 0.5 * long_r - 0.5 * short_r - daily_borrow + (RF_ANNUAL / 252) - rebalance_cost
            pv_list.append(pv_list[-1] * (1 + period_ret))
        else:
            pv_list.append(pv_list[-1])

    return pd.Series(pv_list[1:], index=trade_dates)


def compute_overlay_fraction_series(spy_close: pd.Series) -> pd.Series:
    """Daglig 'andel investerad'-serie (1.0 normalt, HYP-037:s
    CRASH_HAIRCUT_FRACTION under en aktiv krasch-episod), aterananvander
    HYP-037:s EXAKT redan lasta trigger-/aterhamtningsparametrar. Se
    moduldocstring om den dokumenterade forenklingen (omedelbar
    aterbyggnad, ingen likviditetsgrind - bada saknar naturlig
    motsvarighet for en enskild ETF/aggregerad svit)."""
    spy10 = spy_close.pct_change(hyp037.CRASH_LOOKBACK_DAYS)
    n = len(spy_close)
    fraction = np.ones(n)
    reduced = False
    crash_trough = None
    crash_start = None

    for i in range(n):
        r = spy10.iloc[i]
        price = float(spy_close.iloc[i])

        if not reduced:
            if not np.isnan(r) and r < hyp037.CRASH_TRIGGER_RET:
                reduced = True
                crash_trough = price
                start_i = max(0, i - hyp037.CRASH_LOOKBACK_DAYS)
                crash_start = float(spy_close.iloc[start_i])
        else:
            crash_trough = min(crash_trough, price)
            recovered_enough = price >= crash_trough + hyp037.RECOVERY_FRACTION * (crash_start - crash_trough)
            if recovered_enough:
                reduced = False

        fraction[i] = hyp037.CRASH_HAIRCUT_FRACTION if reduced else 1.0

    return pd.Series(fraction, index=spy_close.index)


def apply_overlay(raw_pv: pd.Series, fraction: pd.Series, rf_annual=RF_ANNUAL) -> pd.Series:
    """Blandar en rå avkastningsserie med riskfri ranta enligt
    fraction-serien (1.0 = full exponering, 0.40 = HYP-037:s haircut)."""
    df = pd.concat([raw_pv.rename("pv"), fraction.rename("frac")], axis=1, join="inner").dropna()
    raw_ret = df["pv"].pct_change()
    values = [1.0]
    for i in range(1, len(df)):
        f = df["frac"].iloc[i]
        r = raw_ret.iloc[i]
        r = 0.0 if np.isnan(r) else r
        blended = f * r + (1 - f) * (rf_annual / 252)
        values.append(values[-1] * (1 + blended))
    return pd.Series(values[1:], index=df.index[1:])


def load_spy(start=None, end=None):
    s = hyp037.load_hedge(hyp037.FULL_START, FULL_END_WITH_OOS)
    if start is not None or end is not None:
        s = s.loc[start:end]
    return s


def combine_thirds(spy_pv, hyp037_pv, mom_ls_pv, start_capital=1.0):
    df = pd.concat([spy_pv.rename("spy"), hyp037_pv.rename("hyp037"), mom_ls_pv.rename("mom_ls")],
                    axis=1, join="inner").dropna()
    spy_ret = df["spy"].pct_change()
    hyp_ret = df["hyp037"].pct_change()
    mom_ret = df["mom_ls"].pct_change()

    calendar_dates = df.resample(REBAL_FREQ).last().index
    snapped = snap_rebalance_dates(calendar_dates, df.index)
    rebal_set = set(snapped["execution_date"])

    spy_leg = start_capital * WEIGHT_EACH
    hyp_leg = start_capital * WEIGHT_EACH
    mom_leg = start_capital * WEIGHT_EACH
    values, dates = [], []

    for i in range(1, len(df)):
        date = df.index[i]
        r_spy, r_hyp, r_mom = spy_ret.iloc[i], hyp_ret.iloc[i], mom_ret.iloc[i]
        if not np.isnan(r_spy):
            spy_leg *= (1 + r_spy)
        if not np.isnan(r_hyp):
            hyp_leg *= (1 + r_hyp)
        if not np.isnan(r_mom):
            mom_leg *= (1 + r_mom)
        total = spy_leg + hyp_leg + mom_leg
        if date in rebal_set:
            target_spy = total * WEIGHT_EACH
            target_hyp = total * WEIGHT_EACH
            target_mom = total * WEIGHT_EACH
            turnover = abs(target_spy - spy_leg) + abs(target_hyp - hyp_leg) + abs(target_mom - mom_leg)
            total -= turnover * REBALANCE_COST_BPS
            spy_leg = total * WEIGHT_EACH
            hyp_leg = total * WEIGHT_EACH
            mom_leg = total * WEIGHT_EACH
        values.append(total)
        dates.append(date)

    return pd.Series(values, index=dates)


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

    print("Bygger momentum L/S-sviten (MED spreadkostnad) over HELA 2010-2025...")
    mom_ls_raw = compute_momentum_ls_sleeve_with_spread(universe_merged)
    print(f"  {len(mom_ls_raw)} dagar\n")

    spy_raw = load_spy()

    print("Berknar krasch-overlay-fraction-serien (aterananvander HYP-037:s parametrar)...")
    fraction = compute_overlay_fraction_series(spy_raw)
    n_days_reduced = int((fraction < 1.0).sum())
    print(f"  {n_days_reduced} av {len(fraction)} dagar med reducerad exponering ({n_days_reduced/len(fraction):.1%})\n")

    print("Tillampar overlay pa SPY-benet och momentum L/S-benet...")
    spy_protected = apply_overlay(spy_raw, fraction)
    mom_ls_protected = apply_overlay(mom_ls_raw, fraction)
    RESULTS_DIR.mkdir(exist_ok=True)
    spy_protected.to_csv(RESULTS_DIR / "spy_protected_pv.csv", header=["portfolio_value"])
    mom_ls_protected.to_csv(RESULTS_DIR / "mom_ls_protected_pv.csv", header=["portfolio_value"])

    levels = [100_000, 1_000_000, 10_000_000]

    print("\n=== HYP-045: huvudbacktest (2010-2024) ===")
    main_results = []
    for level in levels:
        hyp037_pv = pd.read_csv(HYP037_RESULTS / f"portfolio_value_{level}.csv",
                                 index_col=0, parse_dates=True)["portfolio_value"]
        combined = combine_thirds(spy_protected, hyp037_pv, mom_ls_protected)
        combined.to_csv(RESULTS_DIR / f"portfolio_value_combined_{level}.csv", header=["portfolio_value"])

        r = {"capital_level": level, "sharpe": sharpe(combined), "cagr": cagr(combined),
             "max_drawdown": max_drawdown(combined), "calmar": calmar(combined), "n_days": len(combined)}
        main_results.append(r)
        ref = HYP043_FRICTION_CORRECTED_REF[level]
        g1 = "PASS" if r["sharpe"] >= 1.0 else "FAIL"
        g2 = "PASS" if r["sharpe"] > ref["sharpe"] else "FAIL"
        g3 = "PASS" if r["max_drawdown"] > ref["max_drawdown"] else "FAIL"
        print(f"  ${level:>10,.0f}  Sharpe={r['sharpe']:.4f} ({g1} >=1.0; {g2} mot HYP-043-friktionskorr.:s {ref['sharpe']:.4f})  "
              f"MaxDD={r['max_drawdown']:.2%} ({g3} mot {ref['max_drawdown']:.2%})  "
              f"CAGR={r['cagr']:+.2%}  Calmar={r['calmar']:.3f}")

    print("\n=== HYP-045: OOS-2025 ===")
    oos_results = []
    spy_oos = spy_protected.loc[OOS_START:FULL_END_WITH_OOS]
    mom_ls_oos = mom_ls_protected.loc[OOS_START:FULL_END_WITH_OOS]
    for level in levels:
        hyp037_oos_pv = pd.read_csv(HYP037_OOS_RESULTS / f"portfolio_value_oos_2025_{level}.csv",
                                     index_col=0, parse_dates=True)["portfolio_value"]
        combined_oos = combine_thirds(spy_oos, hyp037_oos_pv, mom_ls_oos)
        combined_oos.to_csv(RESULTS_DIR / f"portfolio_value_oos2025_combined_{level}.csv", header=["portfolio_value"])

        r = {"capital_level": level, "oos_2025_sharpe": sharpe(combined_oos),
             "oos_2025_max_drawdown": max_drawdown(combined_oos),
             "oos_2025_total_return": float(combined_oos.iloc[-1] / combined_oos.iloc[0] - 1) if len(combined_oos) > 1 else None,
             "n_days": len(combined_oos)}
        oos_results.append(r)
        ref39 = HYP039_OOS_REF[level]
        g4 = "PASS" if r["oos_2025_sharpe"] > ref39 else "FAIL"
        print(f"  ${level:>10,.0f}  OOS-Sharpe={r['oos_2025_sharpe']:.4f} ({g4} mot HYP-039:s {ref39:.4f})  "
              f"OOS-avkastning={r['oos_2025_total_return']:+.2%}  OOS-MaxDD={r['oos_2025_max_drawdown']:.2%}  "
              f"({r['n_days']} dagar)")

    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump({"main": main_results, "oos_2025": oos_results, "n_days_reduced": n_days_reduced}, f, indent=2, default=str)

    print("\nKLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
