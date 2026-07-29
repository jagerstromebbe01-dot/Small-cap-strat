# Strategispec: HYP-009 — friktionsablation av HYP-008

**Skriven av:** Strategy Builder (`/agents/strategy_builder/ROLE.md`)
**Källhypotes:** `/research/hypothesis_registry/HYP-009-friction-ablation.yaml`
**Input-krav bekräftade:** `status: pre-registered` ✅, `pass_fail_criterion`
ifyllt ✅ (låst 2026-07-28 av CEO, se YAML-filens kommentar). Detta är en
spec, INTE körbar kod — Coder implementerar från den.

Denna spec skriver INGET till, och läser bara ifrån, hypotesens YAML-fil.
`pass_fail_criterion`, `status`, `tested_capital_levels` och `k_total_hypotheses_before_this`
lämnas orörda — de är CEO:s/Overfitting Detectors område.

---

## 0. Vad HYP-009 är — ren ablation, inte en ny strategi

HYP-009 är en **metodologisk ablation av HYP-008**, inte en ny alfa-idé.
Syftet är diagnostiskt: isolera om HYP-008:s FAILED-resultat (Sharpe
-0.41 till -0.45 på samtliga tre kapitalnivåer, se
`HYP-008-v6-smallcap-replication.yaml::result_summary`) berodde på
friktionskostnaderna eller om signalen/universumet saknar edge redan
före kostnader.

Konsekvens för denna spec: **allt** i HYP-008:s implementation återanvänds
identiskt — universum, signaler, parametrar, kapacitetsspärr — och den
ENDA tillåtna skillnaden är att friktionskostnaderna neutraliseras till
noll enligt den exakta metod som är utskriven i `pass_fail_criterion`.
Ingenting annat får skilja sig; annars är det inte längre en ablation
utan en ny, oregistrerad hypotes.

## 1. Universum

Identiskt med HYP-008 (hypotesens `universe`/`small_cap_definition`,
och per definition oförändrat i en ablation): **$100M–$2B börsvärde,
EODHD All-World som datakälla**, period **2011–2024** (samma period-fält
som redan användes i HYP-008-körningen; se `data_range` i HYP-009:s
YAML).

- Samma dynamiska universumskälla som HYP-008 använde:
  `data/cache/smallcap_universe_by_month.json` (byggd av
  `data/build_smallcap_universe.py`) — INTE en nyskapad universumsfil.
- Samma cachade EODHD-prisdata: `data/cache/ohlcv/`.
- Samma kända begränsning som redan flaggades i HYP-008-specen
  (senast-kända-börsvärde istället för historiskt börsvärde per
  handelsdag) gäller fortsatt här — den är en egenskap hos
  universumskällan, inte något ablationen ändrar.

## 2. Signaler — identiska med HYP-008 (som i sin tur är v6-kärnan, orörd)

Ingen signallogik ändras. Återanvänds oförändrad från
`/strategies/HYP-008/backtest.py`, som i sin tur kopierade
`/reference_code/v6_core_large_cap.py` orört:

| Steg | Källa | Parametrar (identiska, ändras inte) |
|---|---|---|
| Par-identifiering | `identify_pairs()` | `COINT_WINDOW=252`, `MIN_PAIRS=3`, `CORR_THRESH=0.70`, `MAX_PAIRS=8`, månadsvis |
| Z-score | `compute_zscore()` | `ZSCORE_WINDOW=63` |
| Beta/hedge | `compute_beta()` | `BETA_WINDOW=126`, hedge-instrument SPY |
| Entry/exit | `run_backtest()` | `TRADE_Z_THRESH=1.5`, exit vid `\|z\|<0.3`, `STOP_LOSS=0.06` |
| Positionsstorlek | `run_backtest()` | `FIXED_FRAC=0.05` |
| Max samtidiga positioner | `run_backtest()` | `MAX_POS=12` |

**Volymbaserad kapacitetsspärr (`MAX_ADV_PCT=0.10`, HYP-008 rad 84)
förblir AKTIV och oförändrad** — hypotesens `pass_fail_criterion` säger
uttryckligen att den mäter handelsbarhet, inte kostnad, och därför inte
ska nollställas tillsammans med de två friktionsfälten.

## 3. Kodmodul som återanvänds — och den EXAKTA ändringen

**Bas:** `/strategies/HYP-008/backtest.py`, kopierad till
`/strategies/HYP-009/backtest.py` (kopiera enligt samma princip som
`/reference_code/`-filer: HYP-008-koden ändras aldrig i efterhand,
bevaras som verifierbar bas för denna ablation).

**Friktionsmodulen `strategies/common/friction.py` återanvänds OFÖRÄNDRAD**
— per modulens egen docstring ska den bara ändras vid ett nytt CEO-beslut
om själva friktionsmetodiken, vilket detta inte är. Ablationen sker i
`/strategies/HYP-009/backtest.py`, inte i `friction.py`.

Kriteriet specificerar implementationen ordagrant; sammanfattat till två
konkreta kodställen (motsvarande HYP-008:s rad ~380 och spread-
appliceringen kring rad ~267/340–380):

1. **Borrow-kostnad:** `borrow_cost(position_value=..., holding_days=...,
   annual_rate=0.0)` — samma anropsställe som i HYP-008
   (`BORROW_ANNUAL_RATE`), men värdet sätts till `0.0` istället för
   `0.03`. Funktionen ska fortfarande anropas, inte hoppas över.
2. **Bid-ask-spread:** `corwin_schultz_spread(...)` beräknas EXAKT som i
   HYP-008 (samma high/low-fönster, samma resultat i `spread_df`) — men
   när spreaden appliceras som kostnad (halva vid öppning, halva vid
   stängning) multipliceras den kostnadstermen med `0` innan den
   adderas till trade-kostnaden. Beräkningen av själva spreaden får inte
   tas bort eller hoppas över — bara dess kostnadseffekt nollställs.

Motivering (från kriteriet): `validate_friction_usage.py` kontrollerar
AST-nivå att båda funktionerna både importeras OCH anropas i
strategifilen — om de bara plockas bort ur koden istället för att
nollställas skulle den kontrollen fela, och ablationen skulle dessutom
inte längre bevisa något (då vet man inte om frånvaron av kostnad kom
från att koden faktiskt räknar noll eller bara aldrig körde
kostnadsvägen).

**Rekommenderad implementation för Coder:** en modulnivå-konstant, t.ex.
`FRICTION_ABLATION = True` eller direkt `BORROW_ANNUAL_RATE = 0.0` och en
`SPREAD_COST_MULTIPLIER = 0.0` som multiplicerar spread-kostnadstermen —
namngivningen är Coders val, kravet här är bara VAD som ska hända, inte
den exakta variabelnamngivningen.

## 4. Vad som INTE ändras

- Ingen ny signal, inget nytt filter, ingen ny parameter för
  par-identifiering, z-score, beta eller position sizing.
- Ingen ändring av `MAX_ADV_PCT`/kapacitetsspärren.
- Ingen ändring av universum, period, eller datakälla.
- Bästa-trade-exkluderad-kontrollen (HYP-008 punkt 5/kriteriets
  robusthetsmått) återanvänds identiskt om Coder finner det relevant att
  rapportera den även här — kriteriet för HYP-009 kräver den dock inte
  uttryckligen (PASS/FAIL i HYP-009 är rent Sharpe-baserat, se YAML).

## 5. Kapitalnivåer

Identiskt med HYP-008: kör vid `tested_capital_levels: [100000, 1000000,
10000000]` (samma `--capital`/`--all-levels`-gränssnitt som
`/strategies/HYP-008/backtest.py` redan har).

## 6. Kända blockerare (ärvda från HYP-008, gäller fortsatt)

1. Samma begränsning kring senast-kända (ej historiskt) börsvärde per
   ticker som redan flaggades i HYP-008-specen §1 — oförändrad av denna
   ablation.
2. Detta är, per kriteriet självt, ett **diagnostiskt** test — ett PASS
   betyder INTE att strategin är lönsam att handla, bara att signalen har
   teoretisk edge före kostnader. Reporting/Performance Analyst ska inte
   framställa ett PASS här som en produktionsgodkänd strategi.

## 7. Rekommenderad kodstruktur för Coder

```
/strategies/HYP-009/
  backtest.py   # kopia av HYP-008/backtest.py, friktion nollställd
                # enligt §3 ovan, importerar och anropar
                # strategies/common/friction.py oförändrad
  results/      # Backtesters output per kapitalnivå
```

Coder måste köra
`python scripts/validate_hypothesis.py research/hypothesis_registry/HYP-009-friction-ablation.yaml`
och få exit code 0, samt
`python scripts/validate_friction_usage.py strategies/HYP-009/backtest.py`
och få ett godkänt resultat (import + anrop av båda
friktionsfunktionerna bekräftat) — innan Backtester får exekvera något
av ovanstående.
