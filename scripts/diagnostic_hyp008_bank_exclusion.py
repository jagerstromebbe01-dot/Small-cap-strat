#!/usr/bin/env python3
"""
Diagnostik (INTE en ny hypotes - ingen K-kostnad, ingen pass_fail_criterion):
testar om HYP-008:s (v6-karnan, small-cap-parhandel, FAILED - Sharpe
-0.41/-0.41/-0.45 over hela 2011-2024) misslyckande delvis drevs av den
odiagnostiserade bankkoncentrationen scripts/attribution.py hittade
2026-08-01 (strategies/HYP-008/results/attribution_report.json): 49.1%
av portfoljens dollarkostnad i SIC 60 (statliga affarsbanker), 9.05x
overrepresenterat mot basuniversumet. HYP-008:s par-identifiering
(identify_pairs_dynamic, korrelation >=0.70 over ett rullande
252-dagarsfonster, INGEN sektorhansyn) kan ha klustrat kraftigt i
banker eftersom small-cap-banker/thrifts ofta rar-korrelerar starkt med
varandra (gemensam rantekanslighet) utan att deras individuella spread
nodvandigtvis mean-reverterar pa ett 63-dagars z-score-fonster.

METOD (V2, 2026-08-04 - forsta forsoket over HELA 2010-2024 tog >90 min
utan sluttid i sikte, kod=identisk v6-karna som redan ar kand for att
vara icke-vektoriserad/langsam i compute_zscore, sa avbruten): kor
HYP-008:s EXAKTA pipeline TVA GANGER over ett KORTARE fonster
(2018-01-01 till 2024-12-31, ~1 ars uppvarmning for COINT_WINDOW/
ZSCORE_WINDOW + ~6 ars faktisk jamforelseperiod - tacker covid och
2022-bjornmarknaden) - en gang MED banker (kontroll), en gang UTAN
(behandling), BADA over IDENTISKT fonster, for en giltig direkt
jamforelse (INTE en jamforelse mot det registrerade helperiods-
resultatet, som skulle blanda ihop periodeffekt med bankeffekt). Detta
ror INTE HYP-008:s redan sparade, lasta registerresultat - bara en
diagnostik ovanpa, for att avgora om en sektormatchad/sektorexkluderande
par-formationsmetod ar vard att pre-registrera som en riktig, ny hypotes.
"""

import sys
from pathlib import Path

STRATEGY_DIR = Path(__file__).resolve().parent.parent / "strategies" / "HYP-008"
COMMON_DIR = Path(__file__).resolve().parent.parent / "strategies" / "common"
sys.path.insert(0, str(STRATEGY_DIR))
sys.path.insert(0, str(COMMON_DIR))
import numpy as np  # noqa: E402
import backtest as hyp008  # noqa: E402
from sector import load_bank_financial_flags  # noqa: E402

SHORT_START = "2021-01-01"  # ~1 ars uppvarmning + ~3 ars jamforelseperiod (2022-2024) - andra
# forkortningen 2026-08-04 efter att 2018-2024-varianten ocksa tog >100 min utan synligt
# slut (kord med buffrad stdout, sa ingen delframgang syntes - se aven -u-flaggan i
# korkommandot). Kortare an idealt (missar 2011/2015/2018/covid), men ger ett snabbt,
# om an begransat, svar pa om bankexkludering hjalper alls i den period som ar kvar.


def run_variant(label, close, high, low, volume, hedge, universe_by_month):
    tidx = {t: i for i, t in enumerate(close.columns)}
    log_ret = np.log(close).diff()

    print(f"  [{label}] Identifierar par...")
    pairs_by_date = hyp008.identify_pairs_dynamic(close, log_ret, universe_by_month,
                                                    hyp008.COINT_WINDOW, hyp008.MIN_PAIRS,
                                                    hyp008.CORR_THRESH, hyp008.MAX_PAIRS)
    n_pairs_months = sum(1 for v in pairs_by_date.values() if v)
    print(f"  [{label}] {n_pairs_months}/{len(pairs_by_date)} månader med minst ett identifierat par.")

    log_p = np.log(close)
    print(f"  [{label}] Beräknar z-score (det langsamma steget)...")
    zscore_df = hyp008.compute_zscore(close, log_p, pairs_by_date, hyp008.COINT_WINDOW,
                                        hyp008.ZSCORE_WINDOW, tidx)

    beta_df = hyp008.compute_beta(close, hedge, hyp008.BETA_WINDOW)
    spread_df = hyp008.compute_spread_matrix(high, low)

    results = {}
    for level in [100_000, 1_000_000, 10_000_000]:
        pv, tl = hyp008.run_backtest(close, hedge, zscore_df, beta_df, spread_df, volume, level)
        results[level] = {
            "sharpe": hyp008.sharpe(pv),
            "max_drawdown": hyp008.max_drawdown(pv),
            "calmar": hyp008.calmar(pv),
            "trade_stats": hyp008.trade_stats(tl),
        }
    return results


def main():
    print("Laddar universum...")
    tickers, universe_by_month = hyp008.load_universe()

    print("Klassificerar bank-/finansnamn...")
    bank_flags = load_bank_financial_flags(tickers)
    universe_with_banks = universe_by_month
    universe_ex_banks = {
        month: [t for t in tlist if not bank_flags.get(t, False)]
        for month, tlist in universe_by_month.items()
    }
    n_bank = sum(bank_flags.values())
    print(f"  {n_bank} av {len(tickers)} tickers klassade som bank/finans.\n")

    print(f"Laddar prismatriser ({SHORT_START} till {hyp008.FULL_END}, kortare fonster for snabbhet)...")
    close, high, low, volume = hyp008.load_price_matrices(tickers, SHORT_START, hyp008.FULL_END)
    hedge = hyp008.load_hedge(SHORT_START, hyp008.FULL_END)
    print(f"  Prismatris: {close.shape}\n")

    print("--- KONTROLL: MED banker (samma universum som HYP-008 original) ---")
    with_banks = run_variant("MED banker", close, high, low, volume, hedge, universe_with_banks)

    print("\n--- BEHANDLING: UTAN banker ---")
    without_banks = run_variant("UTAN banker", close, high, low, volume, hedge, universe_ex_banks)

    print(f"\n{'=' * 90}")
    print(f"Bada korda over IDENTISKT fonster ({SHORT_START} till {hyp008.FULL_END}) - direkt jamforbart.")
    print(f"{'=' * 90}")
    print(f"{'Kapitalnivå':<15}{'Sharpe MED banker':<20}{'Sharpe UTAN banker':<20}{'Skillnad':<12}")
    print("-" * 90)
    for level in [100_000, 1_000_000, 10_000_000]:
        wb = with_banks[level]
        wob = without_banks[level]
        print(f"${level:<14,.0f}{wb['sharpe']:<20.3f}{wob['sharpe']:<20.3f}{wob['sharpe'] - wb['sharpe']:+.3f}")
        print(f"    MaxDD: {wb['max_drawdown']:.1%} -> {wob['max_drawdown']:.1%}   "
              f"Trades: {wb['trade_stats']['n']} -> {wob['trade_stats']['n']}")

    print("\nKLART.")


if __name__ == "__main__":
    sys.exit(main())
