#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes - ingen K-kostnad, rör INTE registret):
decil-monotonicitet för HYP-037:s idiosynkratisk-vol-signal - begärd av
CEO 2026-08-05, komplement till IC-diagnostiken
(diagnostic_hyp037_information_coefficient.py) och faktorregressionssviten.

FRÅGA: HYP-037 köper bara DECIL 1 (lägst vol) mot resten. Om
idiosynkratisk volatilitet är en genuin, kontinuerlig riskfaktor borde
avkastningen falla ungefär MONOTONT fran decil 1 till decil 10 - inte
bara "decil 1 battre an resten klumpat ihop". Detta ar standardpraxis i
akademiska faktor-papers (se t.ex. Ang/Hodrick/Xing/Zhang 2006).

METOD: aterananvander SAMMA cross-sektionella data-uppstallning som
IC-diagnostiken (samma ombalanseringsdatum, samma eligible-universum,
samma vol_df, samma framatblickande avkastning till nasta ombalansering)
- men istallet for en korrelation delas universumet i 10 lika stora
grupper (deciler) per period, och medelavkastningen per decil over ALLA
perioder rapporteras.

Skriver INGENTING till registret. Ren diagnostik.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

STRATEGY_DIR = Path(__file__).resolve().parent.parent / "strategies" / "HYP-037"
sys.path.insert(0, str(STRATEGY_DIR))
import backtest as hyp037  # noqa: E402

N_DECILES = 10

# Rimlighetsfilter (upptackt 2026-08-05: tickern SSN visade en period-
# avkastning pa +5 639 751% pa adjusted_close, 2017-09-29->2017-12-29 -
# ett prisfel i OHLCV-cachen, sannolikt en trasig split-justering, INTE
# en verklig rorelse). Detta paverkar ALDRIG HYP-037:s egna, redan
# rapporterade resultat (SSN hamnade i en decil strategin aldrig handlar),
# bara den HAR bredare diagnostiken som tittar pa alla tio decilerna.
# Samma anda som redan etablerade skydd i data_hygiene.py/
# flag_implausible_liquidity - extrema, orealistiska enskilda-periods-
# rorelser exkluderas explicit istallet for att tyst forvranga snittet.
MAX_PLAUSIBLE_PERIOD_RETURN = 5.0  # 500% pa ett kvartal - generost, men utesluter datafel


def compute_rebalance_dates(close, universe_by_month):
    calendar_dates = close.resample(hyp037.REBAL_FREQ).last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[hyp037.VOL_MIN_HISTORY])
                                     & (calendar_dates <= close.index[-1])]
    snapped = hyp037.snap_rebalance_dates(calendar_dates, close.index)
    return snapped


def eligible_tickers_for(calendar_label, universe_by_month, tidx):
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
    hedge_ret = hedge.pct_change()

    tidx = {t: i for i, t in enumerate(close.columns)}
    snapped = compute_rebalance_dates(close, universe_by_month)
    rebal_dates = snapped["execution_date"].tolist()
    rebal_labels = snapped["calendar_label"].tolist()
    print(f"  {len(rebal_dates)} ombalanseringstillfällen\n")

    # decile -> lista av (period-avkastning, hedgad period-avkastning)
    decile_period_returns = {d: [] for d in range(1, N_DECILES + 1)}
    decile_period_returns_hedged = {d: [] for d in range(1, N_DECILES + 1)}

    for i in range(len(rebal_dates) - 1):
        date, label = rebal_dates[i], rebal_labels[i]
        next_date = rebal_dates[i + 1]
        eligible = eligible_tickers_for(label, universe_by_month, tidx)
        if len(eligible) < N_DECILES * 5:
            continue

        vol_today = vol_df.loc[date, eligible]
        entry_px = close_adj.loc[date, eligible]
        exit_px = close_adj.loc[next_date, eligible]
        fwd_ret = exit_px / entry_px - 1
        beta_today = beta_df.loc[date, eligible]

        valid = (vol_today.notna() & fwd_ret.notna() & beta_today.notna() & (entry_px > 0)
                 & (fwd_ret.abs() <= MAX_PLAUSIBLE_PERIOD_RETURN))
        if valid.sum() < N_DECILES * 5:
            continue

        vol_v = vol_today[valid]
        ret_v = fwd_ret[valid]
        beta_v = beta_today[valid]

        # SPY-avkastning over samma period, for beta-hedgad avkastning per decil
        hedge_period_ret = float(hedge.loc[next_date] / hedge.loc[date] - 1)

        ranks = vol_v.rank(method="first")
        n = len(ranks)
        decile_assignment = np.ceil(ranks / n * N_DECILES).astype(int).clip(1, N_DECILES)

        for d in range(1, N_DECILES + 1):
            mask = decile_assignment == d
            if mask.sum() == 0:
                continue
            avg_ret = ret_v[mask].mean()
            avg_beta = beta_v[mask].mean()
            hedged_ret = avg_ret - avg_beta * hedge_period_ret
            decile_period_returns[d].append(avg_ret)
            decile_period_returns_hedged[d].append(hedged_ret)

    print("=" * 100)
    print("DECIL-MONOTONICITET: genomsnittlig avkastning per idio-vol-decil (1=lägst vol, 10=högst)")
    print("=" * 100)
    print(f"{'Decil':<8}{'N perioder':<12}{'Snitt raw avk/period':<22}{'Annualiserad (raw)':<20}"
          f"{'Snitt beta-hedgad avk/period':<28}{'Annualiserad (hedgad)':<20}")

    rows = []
    for d in range(1, N_DECILES + 1):
        raw = np.array(decile_period_returns[d])
        hedged = np.array(decile_period_returns_hedged[d])
        if len(raw) == 0:
            continue
        raw_mean = raw.mean()
        hedged_mean = hedged.mean()
        raw_annual = (1 + raw_mean) ** 4 - 1  # ~4 perioder/ar (kvartalsvis)
        hedged_annual = (1 + hedged_mean) ** 4 - 1
        rows.append((d, len(raw), raw_mean, raw_annual, hedged_mean, hedged_annual))
        tag = " <- HYP-037 KOPER DENNA" if d == 1 else ""
        print(f"{d:<8}{len(raw):<12}{raw_mean:<22.4%}{raw_annual:<20.2%}"
              f"{hedged_mean:<28.4%}{hedged_annual:<20.2%}{tag}")

    hedged_annuals = [r[5] for r in rows]
    diffs = np.diff(hedged_annuals)
    n_monotonic_violations = int((diffs > 0).sum())  # ska vara NEGATIVA (fallande) om monotont
    print(f"\nMonotonicitets-check (beta-hedgad, annualiserad): antal ICKE-fallande steg mellan "
          f"intilliggande deciler = {n_monotonic_violations}/{len(diffs)} "
          f"({'HELT MONOTONT FALLANDE' if n_monotonic_violations == 0 else 'ej perfekt monotont'})")

    print("\n" + "=" * 90)
    print("TOLKNING: om avkastningen faller ungefar monotont fran decil 1 till decil 10 (fa/inga")
    print("'hopp' i fel riktning) styrker det att idiosynkratisk volatilitet ar en genuin,")
    print("kontinuerlig riskfaktor - inte bara en artefakt av var exakt trosklen for 'lagsta")
    print("decilen' rakar hamna. Enstaka smaa avvikelser (1-2 icke-fallande steg av 9) ar normalt")
    print("och inte ett varningstecken - en helt jamn, spikfri platafall vore ovanligt aven for")
    print("en genuin faktor, given brus i enskilda deciler med farre namn.")
    print("=" * 90)
    return 0


if __name__ == "__main__":
    sys.exit(main())
