# Strategispec: HYP-022 — Branschtak (bank/finans) på HYP-017

**Källhypotes:** `/research/hypothesis_registry/HYP-022-branschtak-hyp017.yaml`
**Input-krav bekräftade:** `status: pre-registered` ✅, `pass_fail_criterion` ifyllt ✅ (låst 2026-07-30).

## 1. Kodbas

Kopiera `/strategies/HYP-017/backtest.py` till `/strategies/HYP-022/backtest.py`
(INTE HYP-018 — den innehåller ett stop-loss-tillägg som FAILED och inte
är del av referensimplementationen). Allt oförändrat (signal, universum,
friktion, hedge, kapacitetsspärr, krasch-overlay, de tre motorfixarna).
Enda tillägget: ett branschtak på bank-/finanssektorns andel av de
valda namnen vid varje kvartalsvis ombalansering.

## 2. Sektorklassificering

Ny delad modul `strategies/common/sector.py`:
`load_bank_financial_flags(tickers)` → `{ticker: bool}`, baserat på
substring-matchning av nyckelorden `bancorp, savings, bank, thrift,
financial, trust` mot bolagsnamnet i `data/cache/smallcap_classification.jsonl`.
Samma metod som redan avslöjade 27.3%-mot-7.0%-fyndet.

## 3. Branschtak — implementation

Vid decilvalet i `run_backtest` (samma ställe där `scores` sorteras
efter lägst idio-vol och `target_tickers` byggs):

```python
BANK_CAP_FRACTION = 0.15  # 2x basuniversumets 7.0%, avrundat

n_top = max(1, int(len(scores) * DECILE_FRACTION)) if scores else 0
bank_cap_count = int(n_top * BANK_CAP_FRACTION)

target_tickers = set()
bank_selected = 0
for v, t, cp in scores:
    if len(target_tickers) >= n_top:
        break
    if bank_flags.get(t, False):
        if bank_selected >= bank_cap_count:
            continue  # hoppa över, ersätts längre ner i kön
        bank_selected += 1
    target_tickers.add(t)
```

Icke-bank-kandidater påverkas inte. En bankkandidat som skulle bryta
mot taket hoppas bara över — den tar inte plats i portföljen den
ombalanseringen. `bank_flags` beräknas en gång (statisk per ticker,
oberoende av datum) via `load_bank_financial_flags(tickers)` innan
backtest-loopen körs.

## 4. Vad att logga/kontrollera i resultaten

Utöver Sharpe/MaxDD (villkor 1–2 i pass_fail_criterion):

- **Villkor 3 (mekanisk verifiering):** vid varje ombalanseringsdatum,
  räkna `bank_selected / len(target_tickers)` och bekräfta ≤ 15% på
  samtliga ombalanseringar. Skriv till
  `strategies/HYP-022/results/sector_check_<capital>.csv`.
- **Villkor 4 (mars 2023-episod):** räkna portföljvärdets avkastning
  2023-02-01 till 2023-05-01 vid $100k-nivån, jämför direkt mot
  HYP-017:s -14.8% på samma fönster.

## 5. Kapitalnivåer och validering

Identiskt med HYP-017: `[100000, 1000000, 10000000]`. Kör
`scripts/validate_hypothesis.py` mot HYP-022:s YAML och få exit 0
innan körning.
