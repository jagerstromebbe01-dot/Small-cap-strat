# Strategispec: HYP-031 — Beta-hedge mot IWM istället för SPY

**Källhypotes:** `/research/hypothesis_registry/HYP-031-iwm-beta-hedge.yaml`
**Input-krav bekräftade:** `status: pre-registered` ✅, `pass_fail_criterion` ifyllt ✅ (låst 2026-07-31).

## 1. Bakgrund

Föreslaget efter extern AI-konsultation: HYP-023 handlar $100M–$2B-bolag
men neutraliserar marknadsbeta mot SPY (mega-cap) — potentiell basis-risk.
IWM (Russell 2000) föreslogs som ett mer representativt hedge-instrument.
Skiljer sig från HYP-021 (som testade att byta SIGNALENS referensindex,
inte hedge-instrumentet).

## 2. Kodbas

Baserad på `/strategies/HYP-023/backtest.py`. Två separata serier istället
för en delad `hedge`-variabel:
- `spy` — kalender, idio-vol-signalens residualisering (`beta_df_signal`),
  SPY-krasch-overlayens trigger. OFÖRÄNDRAT från HYP-023.
- `iwm` — ny. Egen `beta_hedge_df` (`compute_beta(close_adj, iwm, ...)`),
  används ENDAST i `run_backtest`s hedge-P&L-beräkning
  (`long_beta * hedge_avkastning`).

`run_backtest` tar nu två parametrar istället för en: `hedge` (blev IWM)
och nytt `crash_ref` (SPY, för krasch-overlayens trigger specifikt).

## 3. Resultat

FAILED — se `HYP-031`:s `result_summary`. Sharpe oförändrat, men MaxDD
blev sämre på alla tre nivåer (störst vid $10M, 1.87pp). Basis-risk-
hypotesen fick inte stöd. HYP-023 förblir referens med SPY som hedge.
