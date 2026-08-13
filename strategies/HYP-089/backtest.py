"""
HYP-089: Marknadsneutral crypto - tvärsnitts-residual mot rullande
90-dagars OLS-betahedge mot BTC, dynamiskt likviditetsfiltrerat
universum. Se
research/hypothesis_registry/HYP-089-crypto-marknadsneutral-tvarsnitt.yaml
för det fullständigt låsta kriteriet - denna fil implementerar det
exakt, ingen fri parameter som inte redan är motiverad där (kommentarer
nedan markerade KONVENTION pekar tillbaka på registerpostens egna
motiveringar).
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
from rebalancing import snap_rebalance_dates  # noqa: E402
from data_hygiene import clean_price_matrix, mask_unrecovered_price_breaks  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from deflated_sharpe_ratio import deflated_sharpe_ratio_from_returns  # noqa: E402

CANDIDATES = [
    "BTC", "ETH", "LTC", "XRP", "DOGE", "XLM", "XMR", "DASH", "ETC", "ADA",
    "LINK", "BCH", "TRX", "EOS", "VET", "FIL", "MANA", "XTZ", "ZEC", "ATOM",
    "ALGO", "AAVE", "AVAX", "NEAR", "SAND", "ICP", "SOL", "DOT",
]  # UNI/MATIC medvetet exkluderade - stale data, se registerposten

MIN_HISTORY_DAYS = 730
MAX_GAP_DAYS = 5
MIN_DOLLAR_VOLUME = 5_000_000  # CEO-LÅST
VOLUME_WINDOW = 90
BETA_WINDOW_DAYS = 90
MIN_PAIRS_FOR_OLS = 60  # rimlighetsgolv, inget fritt val i den mening som paverkar rankingen
MIN_UNIVERSE_SIZE = 6  # CEO-LÅST golv (registerposten)
MAX_ADV_PCT = 0.10  # KONVENTION: samma kapacitetsspärr som HYP-023 (MAX_ADV_PCT)
UNIVERSE_REVIEW_FREQ = "QE"
DECISION_FREQ = "W"

RF_ANNUAL = cd.RF_ANNUAL
ANN_DAYS = cd.ANNUALIZATION_DAYS
MAIN_END = pd.Timestamp(cd.MAIN_END)
OOS_START = pd.Timestamp(cd.OOS_START)

DSR_N_TRIALS = 86  # k_total_hypotheses_before_this (85) + 1


# ───────────────────────── datainladdning ─────────────────────────

def build_master_data(tickers):
    raw = {tk: cd.load_crypto(f"{tk}-USD.CC") for tk in tickers}
    all_dates = sorted(set().union(*[df.index for df in raw.values()]))
    idx = pd.DatetimeIndex(all_dates)
    close = pd.DataFrame({tk: raw[tk]["close"].reindex(idx) for tk in tickers}, index=idx)
    high = pd.DataFrame({tk: raw[tk]["high"].reindex(idx) for tk in tickers}, index=idx)
    low = pd.DataFrame({tk: raw[tk]["low"].reindex(idx) for tk in tickers}, index=idx)
    volume = pd.DataFrame({tk: raw[tk]["volume"].reindex(idx) for tk in tickers}, index=idx)

    # DATASANERING (KONVENTION: återanvänder strategies/common/data_hygiene.py
    # oförändrad, samma modul som redan används på small-cap-sidan - INTE en
    # ny crypto-specifik regel). Upptäckt vid första körningen: VET hade en
    # ~99% "engångsdrop" 2018-08-04 (VEN->VET-token-redenomination, aldrig
    # återhämtad till den gamla prisnivån) som gav MaxDD=-100%/Sharpe=-6 om
    # den fick vara kvar orenad - exakt samma statistiska signatur som
    # modulens redan dokumenterade SSN-fall (permanent, aldrig återhämtad
    # nivåförändring). Samma policy tillämpas här som redan är etablerad för
    # small-cap: kan inte skiljas från ett äkta leverantörsdatafel från bara
    # prisserien, så hela historiken efter brottpunkten maskas - medvetet,
    # inte ett försök att "rädda" VET-datan med tickerspecifik kunskap.
    close, high, low = clean_price_matrix(close, high, low, volume=volume)
    close = mask_unrecovered_price_breaks(close)
    high = high.where(close.notna())
    low = low.where(close.notna())

    valid_dates = {tk: close[tk].dropna().index for tk in tickers}
    return close, high, low, volume, valid_dates, idx


def build_eligibility_data(valid_dates, tickers, max_gap_days=MAX_GAP_DAYS):
    info = {}
    for tk in tickers:
        vd = valid_dates[tk]
        first_date = vd.min()
        s = pd.Series(vd, index=vd)  # for asof-uppslagning av narmaste giltiga datum <= d
        diffs = vd.to_series().diff().dt.days
        gap_end_dates = pd.DatetimeIndex(vd[1:][diffs.values[1:] > max_gap_days])
        info[tk] = {"first_date": first_date, "asof": s, "gap_end_dates": gap_end_dates}
    return info


def is_eligible(tk, d, elig_info, dollar_vol):
    info = elig_info[tk]
    if (d - info["first_date"]).days < MIN_HISTORY_DAYS:
        return False
    nearest = info["asof"].asof(d)
    if pd.isna(nearest) or (d - nearest).days > MAX_GAP_DAYS:
        return False
    window_start = d - pd.Timedelta(days=MIN_HISTORY_DAYS)
    gaps_in_window = info["gap_end_dates"][(info["gap_end_dates"] > window_start) & (info["gap_end_dates"] <= d)]
    if len(gaps_in_window) > 0:
        return False
    dv = dollar_vol[tk].asof(d)
    if pd.isna(dv) or dv < MIN_DOLLAR_VOLUME:
        return False
    return True


# ───────────────────────── universum (kvartalsvis) ─────────────────────────

def build_quarterly_universe(idx, elig_info, dollar_vol, tickers):
    """Returnerar en lista av (execution_date, universe_set) - universumet
    UPPDATERAS bara vid ett omvärderingstillfälle om minst MIN_UNIVERSE_SIZE
    mynt kvalificerar; annars behålls föregående (CEO-LÅST golv-regel)."""
    calendar_dates = pd.Series(range(len(idx)), index=idx).resample(UNIVERSE_REVIEW_FREQ).last().index
    snapped = snap_rebalance_dates(calendar_dates, idx)
    review_dates = sorted(set(snapped["execution_date"]))

    schedule = []
    current_universe = set()
    for d in review_dates:
        candidate_universe = {tk for tk in tickers if tk != "BTC" and is_eligible(tk, d, elig_info, dollar_vol)}
        if len(candidate_universe) >= MIN_UNIVERSE_SIZE:
            current_universe = candidate_universe
        schedule.append((d, set(current_universe)))
    return schedule


def universe_at(schedule, d):
    active = set()
    for review_date, universe in schedule:
        if review_date <= d:
            active = universe
        else:
            break
    return active


# ───────────────────────── signal (veckovis tvärsnitt) ─────────────────────────

def compute_weekly_scores(ret, universe, d, btc_col="BTC"):
    window_start = d - pd.Timedelta(days=BETA_WINDOW_DAYS)
    btc = ret[btc_col]
    scores = {}
    for tk in universe:
        pair = pd.concat([btc, ret[tk]], axis=1, keys=["btc", "coin"]).loc[window_start:d].dropna()
        if len(pair) < MIN_PAIRS_FOR_OLS:
            continue
        beta, alpha = np.polyfit(pair["btc"].values, pair["coin"].values, 1)
        if d not in ret.index or pd.isna(ret.at[d, tk]) or pd.isna(ret.at[d, btc_col]):
            continue
        residual = ret.at[d, tk] - (alpha + beta * ret.at[d, btc_col])
        scores[tk] = residual
    return scores


def tertile_split(scores):
    if len(scores) < MIN_UNIVERSE_SIZE:
        return [], []
    ordered = sorted(scores.items(), key=lambda kv: kv[1])
    n_third = len(ordered) // 3
    if n_third < 1:
        return [], []
    long_legs = [t for t, _ in ordered[:n_third]]
    short_legs = [t for t, _ in ordered[-n_third:]]
    return long_legs, short_legs


# ───────────────────────── backtest-motor ─────────────────────────

def run_backtest(close, high, low, dollar_vol, ret, schedule, idx, capital_level, start_date, end_date):
    calendar_dates = pd.Series(range(len(idx)), index=idx).resample(DECISION_FREQ).last().index
    snapped = snap_rebalance_dates(calendar_dates, idx)
    decision_dates = sorted(set(snapped["execution_date"]))
    decision_dates = [d for d in decision_dates if start_date <= d <= end_date]

    trading_days = idx[(idx >= start_date) & (idx <= end_date)]

    portfolio_value = 1.0
    values, dates = [], []
    long_w, short_w = {}, {}  # ticker -> capital fraction
    weekly_log = []

    for d in trading_days:
        if d in decision_dates:
            universe = universe_at(schedule, d)
            scores = compute_weekly_scores(ret, universe, d)
            new_long, new_short = tertile_split(scores)

            new_long_w, new_short_w = {}, {}
            n_l, n_s = len(new_long), len(new_short)
            for tk in new_long:
                naive = 1.0 / n_l if n_l else 0.0
                adv = dollar_vol[tk].asof(d)
                cap = (MAX_ADV_PCT * adv / capital_level) if pd.notna(adv) and capital_level > 0 else naive
                new_long_w[tk] = min(naive, cap) if cap > 0 else 0.0
            for tk in new_short:
                naive = 1.0 / n_s if n_s else 0.0
                adv = dollar_vol[tk].asof(d)
                cap = (MAX_ADV_PCT * adv / capital_level) if pd.notna(adv) and capital_level > 0 else naive
                new_short_w[tk] = min(naive, cap) if cap > 0 else 0.0

            # friktion: halva Corwin-Schultz-spreaden + avgift pa ENTERING/EXITING
            # notional (KONVENTION: strategies/common/crypto_data.py::transition_cost)
            prev_positions = {(tk, "L") for tk in long_w} | {(tk, "S") for tk in short_w}
            new_positions = {(tk, "L") for tk in new_long_w} | {(tk, "S") for tk in new_short_w}
            changed = prev_positions.symmetric_difference(new_positions)
            friction_cost = 0.0
            for tk, side in changed:
                w_old = (long_w if side == "L" else short_w).get(tk, 0.0)
                w_new = (new_long_w if side == "L" else new_short_w).get(tk, 0.0)
                delta = abs(w_new - w_old)
                if delta > 0 and d in high.index and pd.notna(high.at[d, tk]) and pd.notna(low.at[d, tk]):
                    friction_cost += cd.transition_cost(high.at[d, tk], low.at[d, tk], delta)
            portfolio_value *= (1.0 - friction_cost)

            long_w, short_w = new_long_w, new_short_w
            weekly_log.append({
                "date": d, "n_universe": len(universe), "n_long": n_l, "n_short": n_s,
                "gross_long": sum(long_w.values()), "gross_short": sum(short_w.values()),
                "friction_cost": friction_cost,
            })

        day_ret = 0.0
        for tk, w in long_w.items():
            r = ret.at[d, tk] if d in ret.index and tk in ret.columns else np.nan
            if pd.notna(r):
                day_ret += w * r
        for tk, w in short_w.items():
            r = ret.at[d, tk] if d in ret.index and tk in ret.columns else np.nan
            if pd.notna(r):
                day_ret -= w * r

        portfolio_value *= (1.0 + day_ret)
        values.append(portfolio_value)
        dates.append(d)

    pv = pd.Series(values, index=dates)
    return pv, pd.DataFrame(weekly_log)


def sharpe(s, rf=RF_ANNUAL):
    r = s.pct_change().dropna()
    return float(np.sqrt(ANN_DAYS) * (r - rf / ANN_DAYS).mean() / r.std()) if r.std() > 0 else 0.0


def max_drawdown(s):
    return float(((s - s.cummax()) / s.cummax()).min())


def cagr(s):
    if len(s) < 2:
        return None
    return float((s.iloc[-1] / s.iloc[0]) ** (ANN_DAYS / len(s)) - 1)


def main():
    print("=== HYP-089: Marknadsneutral crypto, tvärsnitts-residual mot OLS-betahedge ===\n")
    print("Laddar data för", len(CANDIDATES), "kandidater (inkl. BTC som hedge-referens)...")
    close, high, low, volume, valid_dates, idx = build_master_data(CANDIDATES)
    print(f"Master-kalender: {idx[0].date()} till {idx[-1].date()} ({len(idx)} dagar)\n")

    dollar_vol = (close * volume).rolling(VOLUME_WINDOW, min_periods=VOLUME_WINDOW).mean()
    ret = close.pct_change()

    elig_info = build_eligibility_data(valid_dates, CANDIDATES)
    schedule = build_quarterly_universe(idx, elig_info, dollar_vol, CANDIDATES)

    print("Universumets storlek över tid (kvartalsvisa omvärderingar):")
    for d, u in schedule:
        if len(u) > 0:
            print(f"  {d.date()}: {len(u)} mynt kvalificerar")
    print()

    first_active = next((d for d, u in schedule if len(u) >= MIN_UNIVERSE_SIZE), None)
    if first_active is None:
        print("FEL: universumet nådde aldrig golvet på", MIN_UNIVERSE_SIZE, "mynt.")
        return 1

    # Huvudperiodens start: forsta omvarderingsdatum dar minst 8 mynt kvalificerar
    # (registerpostens data_range-falt) - INTE bara golvet pa 6.
    first_8 = next((d for d, u in schedule if len(u) >= 8), None)
    main_start = first_8 if first_8 is not None else first_active
    print(f"Huvudperiod startar {main_start.date()} (första omvärdering med >=8 kvalificerande mynt)\n")

    levels = [100_000, 1_000_000, 10_000_000]
    main_results, oos_results, disclosures = [], [], []

    btc_bh_ret_main = None
    spy = pd.read_csv(REPO_ROOT / "data" / "cache" / "ohlcv" / "SPY.csv", index_col=0, parse_dates=True)
    spy_ret = spy["adjusted_close"].pct_change()

    for level in levels:
        pv_main, log_main = run_backtest(close, high, low, dollar_vol, ret, schedule, idx,
                                          level, main_start, MAIN_END)
        pv_oos, log_oos = run_backtest(close, high, low, dollar_vol, ret, schedule, idx,
                                        level, OOS_START, idx[-1])

        pv_main.to_csv(RESULTS_DIR / f"portfolio_value_main_{level}.csv", header=["portfolio_value"])
        pv_oos.to_csv(RESULTS_DIR / f"portfolio_value_oos2025_{level}.csv", header=["portfolio_value"])
        log_main.to_csv(RESULTS_DIR / f"weekly_log_main_{level}.csv", index=False)

        sh = sharpe(pv_main)
        md = max_drawdown(pv_main)
        cg = cagr(pv_main)
        sh_oos = sharpe(pv_oos) if len(pv_oos) > 2 else None

        strat_ret = pv_main.pct_change().dropna()
        btc_ret_aligned = ret["BTC"].reindex(strat_ret.index)
        spy_ret_aligned = spy_ret.reindex(strat_ret.index)
        corr_btc = float(strat_ret.corr(btc_ret_aligned))
        corr_spy = float(strat_ret.corr(spy_ret_aligned))

        dsr_info = deflated_sharpe_ratio_from_returns(
            strat_ret.values, n_trials=DSR_N_TRIALS, risk_free_per_period=RF_ANNUAL / ANN_DAYS)

        m = {"capital_level": level, "sharpe": sh, "cagr": cg, "max_drawdown": md,
             "dsr": dsr_info["deflated_sharpe_ratio"], "n_days": len(pv_main)}
        main_results.append(m)
        oos_results.append({"capital_level": level, "oos_2025_sharpe": sh_oos,
                             "oos_2025_return": float(pv_oos.iloc[-1] - 1) if len(pv_oos) > 1 else None})
        disclosures.append({
            "capital_level": level,
            "corr_vs_btc": corr_btc, "corr_vs_spy": corr_spy,
            "avg_gross_long": float(log_main["gross_long"].mean()),
            "avg_gross_short": float(log_main["gross_short"].mean()),
            "avg_n_universe": float(log_main["n_universe"].mean()),
            "avg_n_long": float(log_main["n_long"].mean()),
            "avg_n_short": float(log_main["n_short"].mean()),
            "pct_weeks_below_floor": float((log_main["n_universe"] < MIN_UNIVERSE_SIZE).mean()) if len(log_main) else None,
        })

        cond1 = sh > 0.70
        cond2 = md >= -0.25
        overall = "PASS" if (cond1 and cond2) else "FAIL"
        print(f"  ${level:>10,.0f}  Sharpe={sh:.4f} (>0.70: {'PASS' if cond1 else 'FAIL'})  "
              f"MaxDD={md:.2%} (>=-25%: {'PASS' if cond2 else 'FAIL'})  CAGR={cg:+.2%}  "
              f"DSR(K={DSR_N_TRIALS})={dsr_info['deflated_sharpe_ratio']:.4f} -> {overall}")
        print(f"               OOS-2025 Sharpe={sh_oos}  corr(BTC)={corr_btc:.3f}  corr(SPY)={corr_spy:.3f}")
        print(f"               snitt bruttoexp: long={disclosures[-1]['avg_gross_long']:.3f} "
              f"short={disclosures[-1]['avg_gross_short']:.3f}  "
              f"snitt antal mynt: universum={disclosures[-1]['avg_n_universe']:.1f} "
              f"long={disclosures[-1]['avg_n_long']:.1f} short={disclosures[-1]['avg_n_short']:.1f}\n")

    cond1_100k = main_results[0]["sharpe"] > 0.70
    cond2_100k = main_results[0]["max_drawdown"] >= -0.25
    overall = "PASSED" if (cond1_100k and cond2_100k) else "FAILED"

    print("=== SLUTBEDÖMNING (gating vid $100k) ===")
    print(f"  Villkor 1 (Sharpe > 0,70): {main_results[0]['sharpe']:.4f} -> {'PASS' if cond1_100k else 'FAIL'}")
    print(f"  Villkor 2 (MaxDD >= -25%): {main_results[0]['max_drawdown']:.2%} -> {'PASS' if cond2_100k else 'FAIL'}")
    print(f"  => {overall}\n")

    summary = {
        "main": main_results, "oos_2025": oos_results, "disclosures": disclosures,
        "main_start": str(main_start.date()), "main_end": str(MAIN_END.date()),
        "dsr_n_trials": DSR_N_TRIALS,
        "pass_fail": {"condition_1_sharpe": bool(cond1_100k), "condition_2_maxdd": bool(cond2_100k)},
        "overall": overall,
    }
    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
