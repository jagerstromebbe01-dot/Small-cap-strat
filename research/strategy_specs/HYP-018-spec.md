# Strategispec: HYP-018 — Per-position stop-loss på HYP-017

**Källhypotes:** `/research/hypothesis_registry/HYP-018-stop-loss-pa-krasch-overlay.yaml`
**Input-krav bekräftade:** `status: pre-registered` ✅, `pass_fail_criterion` ifyllt ✅ (låst 2026-07-30).

## 1. Kodbas

Kopiera `/strategies/HYP-017/backtest.py` till `/strategies/HYP-018/backtest.py`.
Allt oförändrat (signal, universum, friktion, hedge, kapacitetsspärr,
krasch-overlay). Enda tillägget: per-position stop-loss.

## 2. Stop-loss — implementation

Ny, DAGLIG kontroll, EFTER krasch-overlayens kontroll i samma loop-iteration:

```python
STOP_LOSS_THRESHOLD = -0.20

# ... (krasch-overlay-blocket körs först, oförändrat från HYP-017) ...

for t in list(holdings.keys()):
    ti = tidx[t]
    cp = prices_v[date_i, ti]   # adjusted_close - konsekvent med entry/shares
    if np.isnan(cp):
        continue
    ret_since_entry = cp / holdings[t]["entry"] - 1
    if ret_since_entry < STOP_LOSS_THRESHOLD:
        proceeds = holdings[t]["shares"] * cp
        exit_spread = spread_v[date_i, ti]
        if not np.isnan(exit_spread):
            proceeds -= proceeds * (exit_spread / 2)
        cash += proceeds
        trade_log.append({"date": date, "ticker": t,
                           "ret": proceeds / holdings[t]["cost"] - 1,
                           "type": "stop_loss_exit", "cost": holdings[t]["cost"]})
        del holdings[t]
```

Viktigt: HELA positionen stängs (till skillnad från krasch-overlayens
partiella nedskärning). Inget återköp förrän nästa ordinarie
kvartalsrebalans.

## 3. Kapitalnivåer och validering

Identiskt med HYP-017: `[100000, 1000000, 10000000]`. Kör
`scripts/validate_hypothesis.py` mot HYP-018:s YAML och få exit 0 innan
körning.

## 4. Vad att kolla i resultaten

Utöver Sharpe/MaxDD: räkna `stop_loss_exit`-trades separat i trade-loggen
och kolla om 2020-06-30-fallet (BHLB/EBSB/HTBK/GWB/BRKL_old) nu triggas
tidigare än kvartalsutgången — det är den konkreta händelsen hypotesen
är riktad mot.
