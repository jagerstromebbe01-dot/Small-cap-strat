# Strategispec: HYP-017 — SPY-krasch-overlay på idiosynkratisk volatilitet

**Källhypotes:** `/research/hypothesis_registry/HYP-017-spy-krasch-overlay-idio-vol.yaml`
**Input-krav bekräftade:** `status: pre-registered` ✅, `pass_fail_criterion` ifyllt ✅ (låst 2026-07-29).

## 1. Kodbas

Kopiera `/strategies/HYP-015/backtest.py` till `/strategies/HYP-017/backtest.py`.
Signal, universum, friktion, hedge, kapacitetsspärr, motorfixar (1-3) — allt
oförändrat. Enda tillägget: krasch-overlayen.

## 2. Krasch-overlay — implementation

Ny, DAGLIG kontroll inuti huvudloopen i `run_backtest()` (inte bara vid
`if date in rebal_set`):

```python
spy_10d_ret = hedge.pct_change(10)   # SPY:s egen 10-dagars kumulativa avkastning (adjusted_close)
haircut_active = False  # state-flagga per körning

for date_i in ...:
    ...
    if spy_10d_ret[date_i] < -0.10 and not haircut_active:
        # sälj pro rata ner till 40% av dagens marknadsvärde, en gång per episod
        for t, h in holdings.items():
            sälj (1 - 0.40) av h["shares"], samma spread-friktion som rebalance_exit
        haircut_active = True
    elif spy_10d_ret[date_i] >= -0.10:
        haircut_active = False  # triggern är inte längre aktiv - men INGEN återköp här,
                                  # det sker bara vid nästa ordinarie kvartalsrebalans
```

Viktigt: `haircut_active` styr bara OM nedskärningen utlöses (en gång per
sammanhängande episod under -10%), INTE återställning av exponering —
återställning sker enbart via den befintliga kvartalsvisa
decil-ombalanseringen (ingen ny köp-logik behövs).

## 3. Trade-logg

Logga overlay-sälj som en egen typ (`"crash_overlay_exit"`, partiell — bara
en andel av `shares` säljs, positionen finns kvar med reducerat antal
aktier) i stället för `"rebalance_exit"` (som alltid stänger hela
positionen) — så Backtestern/Performance Analyst kan skilja dem åt i
efterhand.

## 4. Kapitalnivåer och validering

Identiskt med HYP-015: `[100000, 1000000, 10000000]`. Kör
`scripts/validate_hypothesis.py` mot HYP-017:s YAML och få exit 0 innan
körning.
