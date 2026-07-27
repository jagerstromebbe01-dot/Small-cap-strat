# HYP-008 — Råresultat (fullständig körning, ej tolkad)

**Körd:** 2026-07-27. Period: 2011-01-03 till 2024-12-31 (252 dagars
uppvärmning gör att handel startar 2011, inte 2010). Alla tre
kapitalnivåer, friktion (Corwin-Schultz-spread + 3% borrow) och
volymbaserad kapacitetsspärr aktiva enligt tidigare specifikation.

**INGEN DSR-beräkning gjord. INGEN pass/fail-bedömning gjord.** Detta är
enbart rådata för gemensam genomgång.

## Sammanfattningstabell

| Mått | 100k (2011-24) | 100k (2013-24) | 1M (2011-24) | 1M (2013-24) | 10M (2011-24) | 10M (2013-24) |
|---|---|---|---|---|---|---|
| CAGR | -2.47% | -2.85% | -2.39% | -2.77% | -1.91% | -2.06% |
| Sharpe (rå) | -0.41 | -0.45 | -0.41 | -0.44 | -0.45 | -0.47 |
| Calmar | -0.057 | -0.065 | -0.056 | -0.065 | -0.051 | -0.055 |
| Max Drawdown | -43.5% | -43.5% | -42.9% | -42.9% | -37.8% | -37.8% |
| Win rate | 45.6% | 44.1% | 45.6% | 44.1% | 45.8% | 44.4% |
| Profit factor | 0.840 | 0.877 | 0.840 | 0.877 | 0.844 | 0.886 |
| Antal trades | 962 | 467 | 962 | 467 | 963 | 468 |
| Sharpe (bästa trade exkluderad) | -0.438 | — | -0.433 | — | -0.483 | — |
| Calmar (bästa trade exkluderad) | -0.063 | — | -0.061 | — | -0.057 | — |

*(Bästa-trade-exkluderad beräknades bara för hela 2011-2024-perioden,
inte separat för 2013-2024-delmängden — kan räknas om vid behov.)*

## Jämförelse mot large-cap-basen (redan validerad, för referens)

| Mått | Large-cap v6 (2010-2024) | HYP-008, 10M (2011-2024) |
|---|---|---|
| Sharpe | ~0.55 | -0.45 |
| Calmar | ~0.56 | -0.05 |
| CAGR | ~4.8% | -1.9% |
| MaxDD | ~-8.6% | -37.8% |
| Win rate | ~59.5% | 45.8% |

## Observationer (beskrivande, ingen slutsats dragen)

- **2010-2012 vs 2013-2024:** resultaten är genomgående något SÄMRE i
  2013-2024-delmängden än i hela perioden på alla tre nivåer (t.ex.
  Sharpe 100k: -0.41 hela perioden vs -0.45 för 2013-2024) — den
  flaggade databegränsningen för tidiga år förklarar alltså INTE ett
  bättre resultat som annars göms; om något är det marginellt sämre
  utan den perioden.
- **Kapitalnivåer:** Sharpe/Calmar skiljer sig marginellt mellan
  100k/1M/10M (kapacitetsspärren har en liten men mätbar effekt,
  konsekvent med att den fungerar som avsett) snarare än att vara
  identiska (vilket de skulle varit utan kapacitetsspärren).
- Antal trades är i det närmaste identiskt mellan 100k och 1M (962 vs
  962) men skiljer sig marginellt vid 10M (963) — värt att notera vid
  vidare granskning.

## Kriteriets krav (för protokollet, ingen bedömning görs här)

Per HYP-008:s låsta `pass_fail_criterion` — PASS kräver ALLA på SAMTLIGA
tre kapitalnivåer: (1) Sharpe efter friktion >= 0.55 och >= 0.70 (golv),
(2) Calmar >= 0.56 och >= 0.60 (golv), (3) håller även efter bästa
traden exkluderad. Ingen bedömning av dessa krav mot resultaten ovan
görs i denna rapport.
