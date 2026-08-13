#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes - ingen K-kostnad, rör INTE registret):
Information Coefficient (IC) för HYP-037:s idiosynkratisk-vol-signal -
begärd av CEO 2026-08-05 efter feedback från en andra AI (se
[[project_lowvol_research_report_planned]] i minnet).

VAD IC MÄTER: hur bra rankar signalen FRAMTIDA avkastning, oberoende av
hela resten av backtest-maskineriet (friktion, hedge, krasch-overlays,
kapacitetsspärrar). Detta isolerar SIGNALEN från "förpackningen" -
komplement till attribution.py:s faktorregression, som isolerar alfa
från KÄNDA faktorer men inte säger nåt om signalens egen träffsäkerhet.

METOD (standard kvant-praxis, Spearman rank-korrelation - robust mot
extremvärden, antar ingen linjäritet):
  Vid VARJE kvartalsvis ombalanseringsdatum (samma snappade datum som
  HYP-037:s egen backtest-loop, samma ELIGIBLE-universum per månad):
    1. Ta HELA det valbara universumet (INTE bara den handlade decilen -
       IC ska mäta signalens rangordningsformåga över hela spektrumet,
       annars mäter man bara "är decil 1 bättre än sig själv").
    2. Signal = idiosynkratisk volatilitet den dagen (samma vol_df som
       backtest.py självt använder för rankningen).
    3. Framtida avkastning = adjusted_close-avkastning FRÅN detta datum
       TILL nästa ombalanseringsdatum (~ett kvartal framåt) - och,
       för IC-DECAY, även vid kortare/längre horisonter (21/42/63/126/
       252 handelsdagar framåt) från SAMMA signaldatum.
    4. Spearman-korrelation(signal, framtida avkastning) för den perioden.
  IC-serien (en per ombalanseringstillfälle, ~58 st) sammanfattas som:
    Mean IC, Std IC, IC-IR (Mean/Std - en "Sharpe" för själva signalen),
    t-stat (Mean IC / (Std IC / sqrt(N))), och andel perioder med
    "rätt tecken" (negativ - se TECKENKONVENTION nedan).

TECKENKONVENTION: HYP-037 köper LÄGSTA idio-vol-decilen (satsar på att
LÄGRE vol -> BÄTTRE framtida avkastning, den klassiska low-vol-
anomalin). En IC med NEGATIVT tecken (hög vol -> låg framtida avkastning)
bekräftar alltså signalen i den riktning strategin faktiskt utnyttjar -
INTE positivt tecken. Detta är motsatt den vanligaste konventionen i
kvant-litteraturen (dar "signal" ofta redan ar definierad sa att hogre
signal = hogre forvantad avkastning) - flaggas har explicit för att
undvika missforstand vid tolkning.

Skriver INGENTING till registret eller till strategies/HYP-037/results/.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

STRATEGY_DIR = Path(__file__).resolve().parent.parent / "strategies" / "HYP-037"
sys.path.insert(0, str(STRATEGY_DIR))
import backtest as hyp037  # noqa: E402

# Horisonter for IC-decay, i handelsdagar (~1/2/3(=en ombalansering)/6/12 manader)
DECAY_HORIZONS_DAYS = {"1 manad": 21, "2 manader": 42, "1 kvartal (ombalansering)": 63,
                        "2 kvartal": 126, "1 ar": 252}


def compute_rebalance_dates(close, universe_by_month):
    """Identisk logik till run_backtest()'s egen ombalanseringsschema -
    samma snappade datum, samma VOL_MIN_HISTORY-gräns."""
    calendar_dates = close.resample(hyp037.REBAL_FREQ).last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[hyp037.VOL_MIN_HISTORY])
                                     & (calendar_dates <= close.index[-1])]
    snapped = hyp037.snap_rebalance_dates(calendar_dates, close.index)
    return snapped  # DataFrame: calendar_label, execution_date


def eligible_tickers_for(date, calendar_label, universe_by_month, tidx):
    month_key = calendar_label.strftime("%Y-%m-%d")
    return [t for t in universe_by_month.get(month_key, []) if t in tidx]


def main():
    print("Laddar universum, prismatriser, signal (samma pipeline som HYP-037:s egen backtest)...")
    tickers, universe_by_month = hyp037.load_universe()
    close, close_adj, high, low, volume = hyp037.load_price_matrices(tickers, hyp037.FULL_START, hyp037.FULL_END)
    hedge = hyp037.load_hedge(hyp037.FULL_START, hyp037.FULL_END)

    close, high, low = hyp037.clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    implausible = hyp037.flag_implausible_liquidity(close, volume, max_market_cap=hyp037.MAX_MARKET_CAP,
                                                      window=hyp037.ADV_WINDOW, multiplier=1.0)
    close_adj = close_adj.mask(implausible)

    beta_df = hyp037.compute_beta(close_adj, hedge, hyp037.BETA_WINDOW)
    vol_df = hyp037.compute_idiosyncratic_vol(close_adj, hedge, beta_df, hyp037.VOL_LOOKBACK_DAYS)

    tidx = {t: i for i, t in enumerate(close.columns)}
    snapped = compute_rebalance_dates(close, universe_by_month)
    rebal_dates = snapped["execution_date"].tolist()
    rebal_labels = snapped["calendar_label"].tolist()
    print(f"  {len(rebal_dates)} ombalanseringstillfällen ({rebal_dates[0].date()} till {rebal_dates[-1].date()})\n")

    # ── Huvud-IC: signal vid rebalans T -> avkastning T till T+1 (nasta ombalansering) ──
    main_ic_series = []
    n_names_per_period = []

    for i in range(len(rebal_dates) - 1):
        date, label = rebal_dates[i], rebal_labels[i]
        next_date = rebal_dates[i + 1]
        eligible = eligible_tickers_for(date, label, universe_by_month, tidx)
        if len(eligible) < 10:
            continue

        vol_today = vol_df.loc[date, eligible]
        entry_px = close_adj.loc[date, eligible]
        exit_px = close_adj.loc[next_date, eligible]
        fwd_ret = exit_px / entry_px - 1

        valid = vol_today.notna() & fwd_ret.notna() & (entry_px > 0)
        if valid.sum() < 10:
            continue

        ic, _ = spearmanr(vol_today[valid], fwd_ret[valid])
        if not np.isnan(ic):
            main_ic_series.append({"date": date, "ic": ic, "n": int(valid.sum())})
            n_names_per_period.append(int(valid.sum()))

    ic_df = pd.DataFrame(main_ic_series)
    mean_ic = ic_df["ic"].mean()
    std_ic = ic_df["ic"].std()
    ic_ir = mean_ic / std_ic if std_ic > 0 else float("nan")
    t_stat = mean_ic / (std_ic / np.sqrt(len(ic_df))) if std_ic > 0 else float("nan")
    pct_correct_sign = (ic_df["ic"] < 0).mean()  # se TECKENKONVENTION i modul-docstring

    print("=" * 90)
    print("HUVUD-IC (signal vid ombalansering T -> avkastning T till T+1, ~1 kvartal)")
    print("=" * 90)
    print(f"  Antal perioder:        {len(ic_df)}")
    print(f"  Namn per period:       min={min(n_names_per_period)}  max={max(n_names_per_period)}  "
          f"snitt={np.mean(n_names_per_period):.0f}")
    print(f"  Mean IC:               {mean_ic:+.4f}  (negativt = signalen fungerar i avsedd riktning)")
    print(f"  Std IC:                {std_ic:.4f}")
    print(f"  IC-IR (Mean/Std):      {ic_ir:+.4f}")
    print(f"  t-stat:                {t_stat:+.3f}  ({'signifikant vid 5%' if abs(t_stat) > 1.96 else 'EJ signifikant vid 5%'})")
    print(f"  Andel perioder 'rätt tecken' (negativ IC): {pct_correct_sign:.1%}")
    print(f"  Min/Max enskild period-IC: {ic_df['ic'].min():+.4f} / {ic_df['ic'].max():+.4f}")

    # ── IC-decay: samma signaldatum, olika framatblickande horisonter ──
    print("\n" + "=" * 90)
    print("IC-DECAY (samma signal vid varje ombalanseringsdatum, olika horisonter framåt)")
    print("=" * 90)
    for label_h, horizon_days in DECAY_HORIZONS_DAYS.items():
        decay_ic_series = []
        for i in range(len(rebal_dates)):
            date = rebal_dates[i]
            date_i = close_adj.index.get_loc(date)
            if date_i + horizon_days >= len(close_adj.index):
                continue
            future_date = close_adj.index[date_i + horizon_days]
            calendar_label = rebal_labels[i]
            eligible = eligible_tickers_for(date, calendar_label, universe_by_month, tidx)
            if len(eligible) < 10:
                continue

            vol_today = vol_df.loc[date, eligible]
            entry_px = close_adj.loc[date, eligible]
            exit_px = close_adj.loc[future_date, eligible]
            fwd_ret = exit_px / entry_px - 1

            valid = vol_today.notna() & fwd_ret.notna() & (entry_px > 0)
            if valid.sum() < 10:
                continue
            ic, _ = spearmanr(vol_today[valid], fwd_ret[valid])
            if not np.isnan(ic):
                decay_ic_series.append(ic)

        if decay_ic_series:
            arr = np.array(decay_ic_series)
            print(f"  {label_h:<28} ({horizon_days:>3} dagar)  n={len(arr):>3}  "
                  f"Mean IC={arr.mean():+.4f}  Std={arr.std():.4f}  IC-IR={arr.mean()/arr.std() if arr.std()>0 else float('nan'):+.4f}")

    print("\n" + "=" * 90)
    print("TOLKNINGSGUIDE (standard kvant-tumregler, ANVÄND FÖRSIKTIGT - inga fasta sanningar):")
    print("  |Mean IC| > 0.05 anses ofta anvandbart, > 0.10 starkt, i akademisk/professionell praxis.")
    print("  IC-IR > 0.5 anses ofta bra signalkvalitet (motsvarar grovt en 'signal-Sharpe').")
    print("  Om IC-decay visar att korrelationen INTE forsvagas markant mellan kortare och langre")
    print("  horisonter kan det tyda pa att kvartalsvis ombalansering inte fangar signalens fulla")
    print("  livslangd optimalt - ELLER bara att signalen ar trog (idio-vol andras langsamt) - inte")
    print("  entydigt i endera riktningen utan vidare tolkning.")
    print("=" * 90)
    return 0


if __name__ == "__main__":
    sys.exit(main())
