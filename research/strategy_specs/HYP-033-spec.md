# Strategispec: HYP-033 — Book-to-Market (rå signal)

**Källhypotes:** `/research/hypothesis_registry/HYP-033-book-to-market-decil.yaml`
**Input-krav bekräftade:** `status: pre-registered` ✅, `pass_fail_criterion` ifyllt ✅ (låst 2026-07-31).

## 1. Kodbas

Baserad på `/strategies/HYP-024/backtest.py` (SPY-beta-hedge, friktion,
kapacitetsspärr, de tre motorfixarna, rå signal utan krasch-overlay) —
UTAN bankexkludering (till skillnad från HYP-024: Book-to-Market är
meningsfullt även för finansbolag).

## 2. Ny data

`data/fetch_value_factor_history.py`: per ticker, StockholdersEquity OCH
aktieantal (`EntityCommonStockSharesOutstanding`/`CommonStockSharesOutstanding`),
BÅDA från samma 10-K (matchat på `end`-datum). Output:
`data/cache/value_factor_by_ticker.jsonl`.

`load_value_factor_data()` / `value_factor_asof()`: samma as-of-mönster
som HYP-024, senaste FILED värde strikt före ombalanseringsdatumet.

## 3. Signal

```python
market_cap = current_price * shares_outstanding_asof
book_to_market = stockholders_equity_asof / market_cap
```

Sorterar FALLANDE (`reverse=True`) — HÖGST book-to-market (billigast)
först. Topp-decilen väljs, samma mekanik som övriga faktortester.

## 4. Kapitalnivåer och validering

`[100000, 1000000, 10000000]`. Kör `scripts/validate_hypothesis.py` mot
HYP-033:s YAML och få exit 0 innan körning.
