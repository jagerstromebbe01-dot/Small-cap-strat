#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes an - ingen K-kostnad): bygger en enkel
beta-neutral momentum long/short-svit (long topp-decil, kort botten-
decil, 12-1-manaders momentum, klassisk akademisk konvention -
Jegadeesh/Titman) over small-cap-universumet, och beraknar dess
korrelation mot SPY och HYP-037 - FORE nagon vikt eller kriterium las,
samma disciplin som HYP-039/041/042:s egna forhandskontroller (spec §5b).

EXTRA FORSIKTIGHET (CEO:s uttryckliga instruktion 2026-08-06, efter
tva datakvalitetsbuggar hittades under HYP-042-bygget samma dag):
  1. Samma "konstant orimlig adjusted_close/close-kvot"-filter som
     fixade ABWND-buggen (>100x eller <0.01x) - inbyggt FRAN START har,
     inte upptackt via en smoke-test-krasch i efterhand.
  2. Sanity-check av HELA avkastningsfordelningen (inte bara
     korrelationstalet) innan nagot rapporteras - om nagot enskilt
     kvartal/period ser orimligt ut, undersoks det INNAN korrelationen
     tolkas.

MEKANISM (forslag, INTE annu last): kvartalsvis (samma frekvens/
snappade datum som resten av registret), rangordna eligible small-cap-
universumet efter 12-1-manaders momentum (avkastning fran 252 till 21
handelsdagar sedan - UTESLUTER senaste manaden, klassisk konvention for
att undvika kortsiktig reversal-kontamination, sarskilt relevant efter
HYP-042:s fynd samma dag). LONG topp-decilen, KORT botten-decilen,
DOLLAR-NEUTRALT (lika stor notional pa bada benen - en forenkling for
denna forhandskontroll, en riktig beta-neutral viktning skulle vara en
del av sjalva kriteriet om detta gar vidare).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

STRATEGY_DIR = Path(__file__).resolve().parent.parent / "strategies" / "HYP-037"
sys.path.insert(0, str(STRATEGY_DIR))
import backtest as hyp037  # noqa: E402

MOM_LOOKBACK_DAYS = 252
MOM_SKIP_DAYS = 21
DECILE_FRACTION = 0.10
REBAL_FREQ = "QE"


def compute_rebalance_dates(close):
    calendar_dates = close.resample(REBAL_FREQ).last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[MOM_LOOKBACK_DAYS])
                                     & (calendar_dates <= close.index[-1])]
    return hyp037.snap_rebalance_dates(calendar_dates, close.index)


def main():
    print("Laddar universum, prismatriser (samma pipeline som HYP-037)...")
    tickers, universe_by_month = hyp037.load_universe()
    close, close_adj, high, low, volume = hyp037.load_price_matrices(tickers, hyp037.FULL_START, hyp037.FULL_END)
    hedge = hyp037.load_hedge(hyp037.FULL_START, hyp037.FULL_END)

    print("Sanerar prisdata (standardfilter + ny konstant-kvot-sarhet)...")
    close, high, low = hyp037.clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    implausible = hyp037.flag_implausible_liquidity(close, volume, max_market_cap=hyp037.MAX_MARKET_CAP,
                                                      window=hyp037.ADV_WINDOW, multiplier=1.0)
    close_adj = close_adj.mask(implausible)

    # SAMMA sarhet som fixade ABWND-buggen i HYP-042 - inbyggd fran start har.
    ratio = (close_adj / close).replace([np.inf, -np.inf], np.nan)
    implausible_ratio = (ratio > 100) | (ratio < 0.01)
    n_affected = int(implausible_ratio.any(axis=0).sum())
    print(f"  {n_affected} tickers hade en orimlig adjusted_close/close-kvot - maskade.")
    close_adj = close_adj.mask(implausible_ratio)

    print("Beräknar 12-1-manaders momentumsignal...")
    momentum = close_adj.shift(MOM_SKIP_DAYS) / close_adj.shift(MOM_LOOKBACK_DAYS) - 1

    tidx = {t: i for i, t in enumerate(close.columns)}
    snapped = compute_rebalance_dates(close)
    rebal_dates = snapped["execution_date"].tolist()
    rebal_labels = snapped["calendar_label"].tolist()
    print(f"  {len(rebal_dates)} ombalanseringstillfällen\n")

    period_ls_returns = []
    period_dates = []
    period_diagnostics = []

    for i in range(len(rebal_dates) - 1):
        date, label = rebal_dates[i], rebal_labels[i]
        next_date = rebal_dates[i + 1]
        month_key = label.strftime("%Y-%m-%d")
        eligible = [t for t in universe_by_month.get(month_key, []) if t in tidx]
        if len(eligible) < 20:
            continue

        mom_today = momentum.loc[date, eligible].dropna()
        if len(mom_today) < 20:
            continue

        ranked = mom_today.sort_values()
        n_decile = max(1, int(len(ranked) * DECILE_FRACTION))
        losers = ranked.index[:n_decile]
        winners = ranked.index[-n_decile:]

        entry_px = close_adj.loc[date]
        exit_px = close_adj.loc[next_date]
        fwd_ret = (exit_px / entry_px - 1)

        long_ret = fwd_ret[winners].dropna()
        short_ret = fwd_ret[losers].dropna()
        if len(long_ret) < 3 or len(short_ret) < 3:
            continue

        # Sanity-check: kapa extrema enskilda-namn-avkastningar INNAN de
        # far paverka period-genomsnittet (samma princip som decil-
        # monotonicitets-diagnostikens MAX_PLAUSIBLE_PERIOD_RETURN,
        # tidigare samma dag) - >500% pa ett kvartal ar per definition
        # ett kvarvarande datafel, inte en riktig position.
        long_ret = long_ret[long_ret.abs() <= 5.0]
        short_ret = short_ret[short_ret.abs() <= 5.0]
        if len(long_ret) < 3 or len(short_ret) < 3:
            continue

        ls_ret = long_ret.mean() - short_ret.mean()  # long minus short, dollar-neutralt
        period_ls_returns.append(ls_ret)
        period_dates.append(next_date)
        period_diagnostics.append({"date": date, "n_long": len(long_ret), "n_short": len(short_ret),
                                    "long_mean": long_ret.mean(), "short_mean": short_ret.mean()})

    diag_df = pd.DataFrame(period_diagnostics)
    print("Sanity-check pa period-avkastningarna INNAN korrelation beraknas:")
    print(f"  Antal perioder: {len(period_ls_returns)}")
    print(f"  Long-ben snitt/period:  min={diag_df['long_mean'].min():.3f}  max={diag_df['long_mean'].max():.3f}")
    print(f"  Short-ben snitt/period: min={diag_df['short_mean'].min():.3f}  max={diag_df['short_mean'].max():.3f}")
    ls_series_check = pd.Series(period_ls_returns)
    print(f"  L/S-spread/period:      min={ls_series_check.min():.3f}  max={ls_series_check.max():.3f}  "
          f"median={ls_series_check.median():.3f}")
    if ls_series_check.abs().max() > 1.0:
        print("  VARNING: minst en period har L/S-spread >100% - granska innan resultatet tolkas!")
    else:
        print("  Inga uppenbara kvarvarande extremvärden - rimligt att fortsätta.")
    print()

    # Bygg en kumulativ pv-serie av kvartalsvisa L/S-spreadar for korrelationsberakning
    ls_pv = (1 + pd.Series(period_ls_returns, index=period_dates)).cumprod()

    spy = hyp037.load_hedge(hyp037.FULL_START, hyp037.FULL_END)  # SPY adjusted_close
    h37 = pd.read_csv(STRATEGY_DIR / "results" / "portfolio_value_100000.csv",
                       index_col=0, parse_dates=True)["portfolio_value"]

    # Korrelation pa KVARTALSVISA avkastningar (samma frekvens som L/S-serien sjalv ar
    # beraknad pa - undviker att blanda dagliga och kvartalsvisa skalor)
    spy_q = spy.reindex(period_dates, method="ffill").pct_change()
    h37_q = h37.reindex(period_dates, method="ffill").pct_change()
    ls_q = ls_pv.pct_change()

    df = pd.concat([ls_q.rename("Momentum_LS"), spy_q.rename("SPY"), h37_q.rename("HYP037")], axis=1).dropna()
    print(f"Jamforbara kvartal: {len(df)}\n")
    print("Korrelationsmatris (kvartalsvisa avkastningar):")
    print(df.corr().round(4))

    def sharpe_q(r):
        return float(np.sqrt(4) * r.mean() / r.std()) if r.std() > 0 else float("nan")

    print(f"\nMomentum L/S-sviten egen (kvartalsvis annualiserad) Sharpe: {sharpe_q(df['Momentum_LS']):.4f}")

    ls_pv.to_csv(Path(__file__).resolve().parent.parent / "data" / "cache" / "momentum_ls_sleeve_pv.csv",
                 header=["portfolio_value"])
    print("\nSparad till data/cache/momentum_ls_sleeve_pv.csv for ateranvandning om detta blir en hypotes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
