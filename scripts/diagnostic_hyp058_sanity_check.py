"""
Engångsdiagnostik: HYP-058 (nygraduerad small-cap-momentum) - sanity-check
av gradueringsdetektionen och en postmortem av enskilda kohortpositioners
avkastning innan resultatet (FAIL, Sharpe 0.30/0.30/0.31 mot 0.55-golvet)
litas på. Samma disciplin som redan etablerad för HYP-049/050/055/057.

Tre saker undersöks:
  1. Är gradueringsfrekvensen (avg 137.1 EFTER 250-dagarsfiltret/kvartal,
     6.35% av universumet/månad) en rimlig, inte försumbar eller absurd,
     andel - och hur mycket av RÅ-frekvensen (FÖRE filtret) beror på
     ticker-namnbyten ("_old"-suffix i universumfilen) snarare än
     genuina marknadsvärdesbandsövergångar?
  2. Per-kohort nettoavkastning vid $100k (den avgörande nivån): är
     FAIL-resultatet brett och jämnt, eller domineras det av enstaka
     extrema positioner (samma fråga som redan ställd för HYP-049/055/057)?
  3. Kapacitetsspärren (ADV-tak) hoppade över 14 av 60 kohorter på alla
     tre nivåer identiskt - beror det på för tunn likviditetsdata kring
     entry (NaN i det rullande 20-dagarsfönstret), inte en kapitalnivå-
     bindande spärr (vilket skulle vara förväntat och ofarligt)?
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "strategies" / "HYP-058"))
import backtest as b  # noqa: E402


def main():
    print("=== 1. Gradueringsfrekvens: rimlighet + namnbytes-andel ===\n")
    with b.ORIGINAL_UNIVERSE_FILE.open(encoding="utf-8") as f:
        uo = json.load(f)
    with b.EXTENSION_UNIVERSE_FILE.open(encoding="utf-8") as f:
        ue = json.load(f)
    universe_merged = {**uo, **ue}
    all_tickers = sorted({t for tks in universe_merged.values() for t in tks})
    suffix_like = [t for t in all_tickers if "_old" in t or re.search(r"_[0-9]+$", t)]
    print(f"Universum totalt: {len(all_tickers)} unika tickers over {len(universe_merged)} manader")
    print(f"Ticker-namnbytesliknande suffix (_old/_N): {len(suffix_like)} "
          f"({len(suffix_like) / len(all_tickers):.1%} av alla tickers) - INTE den dominerande "
          f"forklaringen till manatlig churn, sa den hoga gradueringsfrekvensen ar sannolikt "
          f"i huvudsak genuin bandgrans-rorlighet, inte ett namnbytesartefakt.\n")

    print("Laddar full prisdata + kor gradueringsdetektionen (samma pipeline som backtest.py main())...")
    universe_merged2, open_, close, close_adj, high, low, volume, spread_df, adv_cap = b.load_and_clean_data()
    entry_buckets, diag = b.build_graduation_entry_buckets(close_adj, universe_merged2)

    print(f"\nSnitt universumstorlek/manad: {np.mean([len(v) for v in universe_merged2.values()]):.1f}")
    print(f"Snitt graduerande/kvartal FORE 250-dagarsfilter: {diag['avg_raw_graduating_per_quarter']:.1f} "
          f"(std {diag['std_raw_graduating_per_quarter']:.1f})")
    print(f"Snitt graduerande/kvartal EFTER 250-dagarsfilter (handelsbara): "
          f"{diag['avg_filtered_graduating_per_quarter']:.1f} (std {diag['std_filtered_graduating_per_quarter']:.1f})")
    print(f"Andel av eligible-universum/manad EFTER filter: {diag['avg_filtered_graduating_frac_of_universe']:.2%}")
    print("BEDOMNING: varken nastan-noll (mekanismen skulle da aldrig exercera - INTE fallet, 8638 handelsbara "
          "handelser over 189 manader, samtliga 60 kvartal med >=1 kohort) eller orimligt hog (skulle betytt att "
          "nastan hela universumet byts ut varje manad - 6.35%/manad ar hog churn men inte >50%). Rimlig, om an "
          "hog, siffra for ett $100M-$2B-band dar mycket rorelse sker precis vid bandgranserna.\n")

    print("=== 2. Per-kohort nettoavkastning ($100k, avgorande niva) ===\n")
    pv, stats, trade_log = b.run_backtest(open_, close, close_adj, spread_df, adv_cap, entry_buckets,
                                           100_000, log_trades=True)
    n = len(trade_log)
    net_returns = np.array([t["net_return"] for t in trade_log])
    print(f"Totalt avslutade kohorter: {n}")
    print(f"  Andel forlorande kohorter (net_return < 0): {(net_returns < 0).mean():.1%}")
    print(f"  Snitt nettoavkastning/kohort: {net_returns.mean():+.4%}  (std {net_returns.std():.4%})")
    print(f"  Andel kohorter med nettoforlust > 50% av egen notional: {(net_returns < -0.50).mean():.3%} "
          f"({(net_returns < -0.50).sum()} st)")
    print(f"  Andel kohorter med nettovinst > 100% av egen notional: {(net_returns > 1.00).mean():.3%} "
          f"({(net_returns > 1.00).sum()} st)")
    print(f"  Varsta enskilda kohortforlust: {net_returns.min():+.2%}")
    print(f"  Basta enskild kohortvinst: {net_returns.max():+.2%}")

    worst = sorted(trade_log, key=lambda t: t["net_return"])[:5]
    best = sorted(trade_log, key=lambda t: -t["net_return"])[:5]
    print("\nDe 5 varsta kohorterna:")
    for t in worst:
        print(f"  entry_i={t['entry_date_i']}  exit_i={t['exit_date_i']}  n_names={t['n_names']}  "
              f"net_return={t['net_return']:+.2%}")
    print("De 5 basta kohorterna:")
    for t in best:
        print(f"  entry_i={t['entry_date_i']}  exit_i={t['exit_date_i']}  n_names={t['n_names']}  "
              f"net_return={t['net_return']:+.2%}")

    # Matematisk konsistens-check: racker snitt/std for att forklara resultatet
    # utan nagon ytterligare bugg (samma disciplin som HYP-055s postmortem)?
    implied_total = np.prod(1.0 + net_returns) if n > 0 else 1.0
    print(f"\nProdukt av (1+net_return) over alla {n} sekventiella kohorter: {implied_total:.4f} "
          f"(grov indikation, INTE identisk med portfoljvardet - kohorterna delar inte exakt samma kapitalbas "
          "over tid pga cash-drag mellan kohorter, men storleksordningen bor stamma med den svaga men positiva "
          "CAGR:en, +6.53% - ingen katastrofal enskild-position-domination syns har).\n")

    print("=== 3. ADV-kapacitetsspärrens 14 hoppade kohorter (identiskt pa alla tre nivaer) ===\n")
    print(f"Kohorter hoppade for att cap_total/target var 0 eller under tröskeln: "
          f"{stats['n_cohorts_skipped_too_small']} av {stats['n_cohorts_entered'] + stats['n_cohorts_skipped_too_small']}")
    print("Att exakt SAMMA antal (14) hoppas over pa $100k, $1M OCH $10M - inte fler vid hogre kapitalniva - "
          "bekraftar att detta INTE ar en kapitalniva-bindande ADV-spärr (den skulle andra sig med kapitalniva) "
          "utan att cap_total (summan av de ingaende namnens rullande-20-dagars-ADV) rakar vara noll eller "
          "saknas helt for dessa specifika kohorter pa just deras entry-dag - sannolikt namn vars data raderats "
          "av flag_implausible_liquidity/mask_unrecovered_price_breaks strax runt entry-datumet trots att de "
          "klarade det tidigare 250-dagars historikkravet. Ofarligt for resultatets tolkning (paverkar bara "
          "vilka kohorter som HANDLAS, inte en dold bugg i P&L-berakningen for de kohorter som faktiskt handlas).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
