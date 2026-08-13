# Strategispec: BATCH-001 (HYP-025 till HYP-029) — Stop-loss-tröskelvarianter på HYP-023

**Källhypoteser:** `/research/hypothesis_registry/HYP-025-stoploss-30pct.yaml` till `HYP-029-stoploss-15pct.yaml`
**Governance:** se `CLAUDE.md`, avsnitt "Batch Hypothesis Generation" (tillagt 2026-07-31) — alla fem kandidater skrevs och låstes som ETT block innan en enda backtest kördes.

## 1. Kodbas

Kopiera `/strategies/HYP-023/backtest.py` (nuvarande referensimplementation) till `/strategies/HYP-02{5,6,7,8,9}/backtest.py`. Allt oförändrat (idio-vol-signal, SPY-krasch-overlay, sektor-krasch-trigger, friktion/hedge/kapacitetsspärr, motorfixar). Enda tillägget per kandidat: ett tredje lager, ett per-position stop-loss, EFTER både SPY-overlayen och sektor-triggern i samma loop-iteration (samma ordning som HYP-018 använde för sin enda overlay).

## 2. Parametrisering per kandidat

| Kandidat | `STOP_LOSS_THRESHOLD` | `STOP_LOSS_CONFIRM_DAYS` |
|---|---|---|
| HYP-025 | -0.30 | 1 |
| HYP-026 | -0.35 | 1 |
| HYP-027 | -0.25 | 1 |
| HYP-028 | -0.20 | 3 |
| HYP-029 | -0.15 | 1 |

## 3. Stop-loss — implementation (identisk mekanik i alla fem, bara konstanterna skiljer)

```python
STOP_LOSS_THRESHOLD = ...   # se tabell
STOP_LOSS_CONFIRM_DAYS = ...  # se tabell

stop_loss_days_below = {}  # state, initieras tomt, sätts till 0 vid ny position

# ... (SPY-overlay och sektor-trigger körs först, oförändrade) ...

for t in list(holdings.keys()):
    ti = tidx[t]
    cp = prices_v[date_i, ti]
    if np.isnan(cp):
        continue
    ret_since_entry = cp / holdings[t]["entry"] - 1
    if ret_since_entry < STOP_LOSS_THRESHOLD:
        stop_loss_days_below[t] = stop_loss_days_below.get(t, 0) + 1
    else:
        stop_loss_days_below[t] = 0

    if stop_loss_days_below.get(t, 0) >= STOP_LOSS_CONFIRM_DAYS:
        # stäng hela positionen, samma friktionsmekanik som övriga exits
        ...
        stop_loss_days_below.pop(t, None)
```

`STOP_LOSS_CONFIRM_DAYS` nollställs om priset återhämtar sig över tröskeln någon dag under fönstret — kravet är på PÅFÖLJANDE dagar, inte kumulativa.

## 4. Kapitalnivåer och validering

`[100000, 1000000, 10000000]` för alla fem. Kör `scripts/validate_hypothesis.py` mot respektive YAML och få exit 0 innan körning — samtliga fem validerades OK innan en enda backtest kördes, i den ordningen batch-reglerna kräver.

## 5. Resultat

Se HYP-025:s `result_summary` för den fullständiga jämförelsetabellen över alla fem kandidater. Sammanfattning: alla fem FAILED, på samma strukturella sätt (förbättring vid $100k, marginell försämring vid $1M, blandat vid $10M) oberoende av tröskeldjup eller bekräftelsekrav.
