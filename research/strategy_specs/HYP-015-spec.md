# Strategispec: HYP-015 — Idiosynkratisk volatilitet på small-cap

**Skriven av:** Strategy Builder (`/agents/strategy_builder/ROLE.md`)
**Källhypotes:** `/research/hypothesis_registry/HYP-015-idiosynkratisk-volatilitet.yaml`
**Input-krav bekräftade:** `status: pre-registered` ✅, `pass_fail_criterion`
ifyllt ✅ (låst 2026-07-29 av CEO). Detta är en spec, INTE körbar kod —
Coder implementerar från den.

---

## 1. Universum

Identiskt med HYP-014: **$100M–$2B börsvärde, EODHD All-World**, samma
`smallcap_universe_by_month.json`, samma period 2011–2024.

## 2. Kodbas att utgå från

Kopiera `/strategies/HYP-014/backtest.py` till `/strategies/HYP-015/backtest.py`
(INTE editera HYP-014 i efterhand — det är redan testat och FAILED, dess
resultat ska stå kvar orörda). Signalfunktionen är den enda metodiska
skillnaden; resten av motorn (friktion, hedge, kapacitetsspärr, kvartalsvis
ombalansering) är oförändrad.

## 3. Signal — enda metodikskillnaden mot HYP-014

| Steg | HYP-014 (total vol) | HYP-015 (idiosynkratisk vol) |
|---|---|---|
| Beräkna | `compute_realized_vol(close, 120)` = std av `close.pct_change()` | Residual = daglig aktieavkastning − beta × daglig SPY-avkastning, ANVÄND beta från redan befintlig `compute_beta()` (126-dagars fönster, klippt [-5,5]); signal = std av residualen, samma 120-dagars fönster |
| Rangordning | Lägsta decil av total std | Lägsta decil av residual-std |
| Ombalansering | Kvartalsvis (QE) | Kvartalsvis (QE), oförändrat |

Implementation: `beta_df` beräknas redan i HYP-014:s kod (används för
hedgen) — återanvänd SAMMA `beta_df`, beräkna inte en andra gång.
Residual-serien: `resid = stock_ret - beta_df * hedge_ret` (elementvis,
samma vektoriserade mönster som befintlig kod), sedan
`resid.rolling(120).std()`.

## 4. Motorfixar som MÅSTE vara aktiva (per låst kriterium — inte valfria)

Dessa tre gäller lika för HYP-016 och ska implementeras EN gång i
`strategies/common/` (redan gjort 2026-07-29), inte separat per hypotes:

1. **Ombalanseringsdatum:** använd `strategies/common/rebalancing.py::snap_rebalance_dates()`
   i stället för att direkt matcha `resample("QE").last().index` mot
   handelskalendern. Kom ihåg: `execution_date` (snappad) styr LOOP-logiken
   (`if date == execution_date`), men `calendar_label` (ursprunglig,
   osnappad) är vad som ska användas för `universe_by_month.get(...)`-
   uppslagningen, eftersom den filen är byggd med kalender-månadsslut som
   nycklar.
2. **Adjusted close:** ladda `adjusted_close`-kolumnen (redan i cachen)
   och använd DEN för `stock_ret`/`hedge_ret`/residual-beräkningen. Fortsätt
   använda rå `close` för positionsvärde/exekvering (som idag).
3. **Likviditets-rimlighetsfilter:** kör
   `strategies/common/data_hygiene.py::flag_implausible_liquidity(close, volume, max_market_cap=2_000_000_000, window=20, multiplier=1.0)`
   EFTER `clean_price_matrix()`, maska `close`/`high`/`low` till NaN där
   flaggan är True (samma mönster som `no_trade`-masken i
   `clean_price_matrix`).

## 5. Kapitalnivåer och friktion

Identiskt med HYP-014: `[100000, 1000000, 10000000]`, Corwin-Schultz-spread
+ 3% årlig borrow-kostnad AKTIV (importeras OCH anropas — `validate_hypothesis.py`
kontrollerar detta kodmässigt via `validate_friction_usage.py`).

## 6. Rekommenderad kodstruktur för Coder

```
/strategies/HYP-015/
  backtest.py    # kopia av HYP-014/backtest.py, signal bytt (steg 3),
                 # motorfixarna (steg 4) inbakade i load/clean-stegen
  results/       # Backtesters output per kapitalnivå
```

Coder måste köra
`python scripts/validate_hypothesis.py research/hypothesis_registry/HYP-015-idiosynkratisk-volatilitet.yaml`
och få exit code 0 innan Backtester får exekvera koden.
