# Strategispec: HYP-032 — Traditionell Kelly-sizing med signalstyrka

**Källhypotes:** `/research/hypothesis_registry/HYP-032-kelly-sizing-signalstyrka.yaml`
**Input-krav bekräftade:** `status: pre-registered` ✅, `pass_fail_criterion` ifyllt ✅ (låst 2026-07-31, explicit CEO-beslut att återöppna Ejay/Kelly för ett sista test).

## 1. Kodbas

Baserad på `/strategies/HYP-023/backtest.py`. Enda ändringen: viktningen
inom den redan valda decilen (equal-weight → Kelly-viktat).

## 2. Kelly-formel (i rebalanseringsblocket)

```python
eligible_vols = np.array([v for v, _, _ in scores if not np.isnan(v)])
cs_mean, cs_std = eligible_vols.mean(), eligible_vols.std()

kelly_weights = {}
for v, t, _ in scores[:n_top]:
    z = (v - cs_mean) / cs_std if cs_std > 0 else 0.0
    edge = max(0.0, -z)
    kelly_weights[t] = edge / (v * v) if v > 0 else 0.0

# normalisera, tak pa 3x likaviktad andel, normalisera om
```

Vid köp av nya namn: `target_dollar_per_name = cash * (kelly_weights[t] /
sum(kelly_weights[nya namn]))` istället för `cash / len(new_names)`.
Kapacitetsspärren (10% av 20-dagars ADV) gäller därefter, oförändrad.

## 3. Resultat

FAILED, men nyanserat — se `HYP-032`:s `result_summary`. MaxDD förbättrades
på alla tre nivåer; Sharpe klarade golvet vid $1M/$10M men inte $100k.
Diagnos: kapacitetsspärren binder mer vid högre kapital och tvingar
tillbaka koncentrationen mot likaviktning, vilket "räddar" resultatet där
den binder men inte vid $100k där den sällan gör det. Inte samma
dödsorsak som de ursprungliga 7 Ejay-varianterna (cirkularitet) — en ny
lärdom. Ejay/Kelly-linjen stängd igen, kräver nytt CEO-beslut.
