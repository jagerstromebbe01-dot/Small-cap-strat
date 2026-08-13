# Strategispec: HYP-024 — Rörelselönsamhet (topp-decil, rå signal)

**Källhypotes:** `/research/hypothesis_registry/HYP-024-rorelselonsamhet-decil.yaml`
**Input-krav bekräftade:** `status: pre-registered` ✅, `pass_fail_criterion` ifyllt ✅ (låst 2026-07-31).

## 1. Kodbas

Kopiera `/strategies/HYP-017/backtest.py` (INTE HYP-014 — den föregår de
tre motorfixarna) till `/strategies/HYP-024/backtest.py`. Behåll: data-
sanering, `adjusted_close`, `flag_implausible_liquidity`,
`snap_rebalance_dates`, SPY-beta-hedge, friktion, kapacitetsspärr. Ta
bort: idiosynkratisk-vol-signalen och HELA SPY-krasch-overlayen (detta
är en rå signal-test utan riskverktyg).

## 2. Ny data

`data/cache/profitability_by_ticker.jsonl` (byggd av
`data/fetch_profitability_history.py`): per ticker, listor av årliga
(`fp=FY`, `form=10-K`) `operating_income`- och `assets`-observationer
med `end`/`val`/`filed`.

Ny funktion i `strategies/HYP-024/backtest.py`:

```python
def load_profitability_signal(tickers, date_index):
    """Per ticker: sorterad lista av (filed_date, opinc/assets-kvot).
    Vid varje datum: senaste FILED varde FORE (ej PA) det datumet."""
```

Bygg en `profitability_df` (datum × ticker) genom att för varje ticker
matcha varje `operating_income`-observations `end`-datum mot närmast
föregående `assets`-observation med SAMMA `end`-datum (samma 10-K,
samma boksluts-slutdatum) och forward-filla kvoten från `filed`-datumet
framåt tills nästa 10-K filas — samma "as-of"-princip som
`fetch_eps_history.py` använder för SUE.

## 3. Universum-begränsning

Återanvänd `strategies/common/sector.py::load_bank_financial_flags`.
Vid varje ombalansering: `eligible = [t for t in universe_by_month[...]
if t in tidx and not bank_flags.get(t, False)]` — bank-/finansnamn
exkluderas helt innan decilvalet görs (inte bara nedviktade).

## 4. Decilval

Motsatt riktning mot HYP-014/015/017: `scores.sort(reverse=True)` —
HÖGST rörelselönsamhet först. Annars identisk mekanik (lika viktat,
kapacitetsspärrat) med befintlig motor.

## 5. Kapitalnivåer och validering

`[100000, 1000000, 10000000]`. Kör `scripts/validate_hypothesis.py` mot
HYP-024:s YAML och få exit 0 innan körning.
