# Strategispec: HYP-023 — Sektorspecifik krasch-trigger (bank/finans) på HYP-017

**Källhypotes:** `/research/hypothesis_registry/HYP-023-sektor-krasch-trigger-hyp017.yaml`
**Input-krav bekräftade:** `status: pre-registered` ✅, `pass_fail_criterion` ifyllt ✅ (låst 2026-07-30).

## 1. Kodbas

Kopiera `/strategies/HYP-017/backtest.py` till `/strategies/HYP-023/backtest.py`
(INTE HYP-018/022 — de innehåller tillägg som FAILED och inte är del av
referensimplementationen). Allt oförändrat (signal, universum, friktion,
hedge, kapacitetsspärr, SPY-krasch-overlay, de tre motorfixarna). Enda
tillägget: en andra, sektorspecifik krasch-trigger.

## 2. Bank-/finanskomposit

Återanvänd `strategies/common/sector.py::load_bank_financial_flags`.
Ny funktion: för varje handelsdag, likaviktat medelvärde av dagliga
avkastningar över alla bank-/finansklassificerade tickers i **månadens
hela eligible-universum** (`universe_by_month`, samma källa som
decilvalet) — inte bara innehavda namn.

```python
bank_tickers_by_month = {
    month: [t for t in tickers if bank_flags.get(t, False)]
    for month, tickers in universe_by_month.items()
}
```

Kompositens dagliga avkastning beräknas som likaviktat medel av
`close_adj.pct_change()` över den mängden tickers, forward-fillad
mellan månadsgränser (samma eligible-lista gäller tills nästa månads
universum-uppdatering).

## 3. Sektor-krasch-trigger — implementation

Ny, DAGLIG kontroll, EFTER SPY-overlayens kontroll i samma loop-iteration
(samma ordning som HYP-018:s stop-loss):

```python
SECTOR_CRASH_LOOKBACK_DAYS = 10    # samma som SPY-overlayen
SECTOR_CRASH_TRIGGER_RET = -0.10   # samma som SPY-overlayen
SECTOR_CRASH_HAIRCUT_FRACTION = 0.40  # samma som SPY-overlayen

# ... (SPY-overlay-blocket körs först, oförändrat) ...

sector10 = bank_composite_10d_ret_v[date_i]
if not np.isnan(sector10) and sector10 < SECTOR_CRASH_TRIGGER_RET and not sector_haircut_active:
    for t in list(holdings.keys()):
        if not bank_flags.get(t, False):
            continue  # bara bank-/finansinnehav, INTE hela portföljen
        # ... samma haircut-mekanik som SPY-overlayen, skalat till 40% ...
    sector_haircut_active = True
elif not np.isnan(sector10) and sector10 >= SECTOR_CRASH_TRIGGER_RET:
    sector_haircut_active = False
```

Viktigt: skär ENDAST bank-/finansinnehav, inte hela portföljen (till
skillnad från SPY-overlayen). Eget `sector_haircut_active`-tillstånd,
oberoende av SPY-overlayens `haircut_active`. Ingen automatisk
återbyggnad — sker vid nästa ordinarie kvartalsrebalans.

## 4. Vad att logga/kontrollera i resultaten

- Antal distinkta sektor-trigger-episoder över 2011-2024, och om mars
  2023 är bland dem (bekräftar att mekanismen faktiskt greps in vid
  målhändelsen).
- Jämför trigger-frekvens mot SPY-overlayens (känd risk: bankkompositen
  kan vara mer volatil och trigga oftare/brusigare).
- Villkor 2 (MaxDD): jämför direkt mot HYP-017:s egna -26.96%/-19.77%/-13.39%.
- Villkor 3 (mars 2023): räkna 2023-02-01 till 2023-05-01-fönstrets
  avkastning på alla tre kapitalnivåer, jämför mot HYP-017:s -14.8% (100k).

## 5. Kapitalnivåer och validering

Identiskt med HYP-017: `[100000, 1000000, 10000000]`. Kör
`scripts/validate_hypothesis.py` mot HYP-023:s YAML och få exit 0
innan körning.
