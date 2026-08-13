# Strategispec: HYP-016 — Volatilitets-hanterad momentum på small-cap

**Skriven av:** Strategy Builder (`/agents/strategy_builder/ROLE.md`)
**Källhypotes:** `/research/hypothesis_registry/HYP-016-vol-hanterad-momentum.yaml`
**Input-krav bekräftade:** `status: pre-registered` ✅, `pass_fail_criterion`
ifyllt ✅ (låst 2026-07-29 av CEO). Detta är en spec, INTE körbar kod —
Coder implementerar från den.

---

## 1. Universum

Identiskt med HYP-012: **$100M–$2B börsvärde, EODHD All-World**, samma
`smallcap_universe_by_month.json`, samma period 2011–2024.

## 2. Kodbas att utgå från

Kopiera `/strategies/HYP-012/backtest.py` till `/strategies/HYP-016/backtest.py`
(INTE editera HYP-012 i efterhand — redan testat och FAILED, resultat ska
stå kvar orörda). Momentumsignalen (12-1 månader, toppdecil, månatlig
ombalansering) är OFÖRÄNDRAD. Den enda metodikskillnaden är
volatilitets-skalning av bruttoexponeringen.

## 3. Signal — oförändrad mot HYP-012

12-1-månaders kumulativ avkastning (exkl. senaste månaden), lång toppdecilen,
månatlig ombalansering (ME), samma kapacitetsspärr (`MAX_ADV_PCT=0.10`).

## 4. Volatilitets-skalning — enda tillägget (Barroso & Santa-Clara 2015)

Exakt specifikation, per låst kriterium (inga fria parametrar att justera
efter att resultat setts):

1. Beräkna momentumportföljens EGNA dagliga avkastningar (portföljvärdes-
   serien FÖRE skalning — dvs som om HYP-012:s ursprungliga, ej vol-hanterade
   version kördes parallellt, rent internt för att driva skalningsfaktorn).
2. `realized_vol_t` = rullande 126-handelsdagars std av dessa dagliga
   avkastningar, annualiserad (`* sqrt(252)`).
3. `target_vol` = FAST 20% annualiserat (konstant, INTE skattad från denna
   backtests egna fullsampel-resultat — se kriteriets motivering mot
   framåtblick).
4. `scale_t = clip(target_vol / realized_vol_(t-1), 0.2, 2.0)` — notera
   `t-1`: skalningen för dag/månad t använder ENDAST realiserad volatilitet
   fram till FÖREGÅENDE period, ingen look-ahead.
5. Den faktiska portföljens bruttoexponering (andel av kapital allokerad
   till momentumpositionerna) multipliceras med `scale_t` vid varje
   ombalansering. Kapital som inte allokeras (när `scale_t < 1`) ligger kvar
   i kassa till `RF_ANNUAL`, precis som ovriga hypoteser — ingen separat
   hävstång tas upp när `scale_t > 1` utöver vad kassan/positionerna redan
   tillåter (om `scale_t > 1` skulle kräva mer kapital än tillgängligt,
   klipp till vad som faktiskt går att allokera; notera detta i
   `result_summary` om det inträffar ofta).

Implementation: enklast som ett efterhandssteg ovanpå den redan beräknade,
oskalade dagliga portföljavkastningsserien — inte en omskrivning av
positionsstorlekslogiken i sig.

## 5. Motorfixar som MÅSTE vara aktiva (delade med HYP-015, redan byggda 2026-07-29)

1. **Ombalanseringsdatum:** `strategies/common/rebalancing.py::snap_rebalance_dates()`
   i stället för rå `resample("ME").last().index`-matchning. `execution_date`
   styr loopen, `calendar_label` styr `universe_by_month`-uppslagningen.
2. **Adjusted close:** använd `adjusted_close` för momentumberäkningen
   (12-1-månadersavkastningen). Detta är särskilt viktigt här — HYP-012:s
   dominerande trade (ARDMQ, +3923%/månad) visade sig vara en icke
   split-justerad 1-för-40 omvänd split som `adjusted_close` redan korrigerar
   för i cachen. Fortsätt använda rå `close` för positionsvärde/exekvering.
3. **Likviditets-rimlighetsfilter:**
   `strategies/common/data_hygiene.py::flag_implausible_liquidity(close, volume, max_market_cap=2_000_000_000, window=20, multiplier=1.0)`
   efter `clean_price_matrix()`, samma maskningsmönster som HYP-015.

## 6. Kapitalnivåer och friktion

Identiskt med HYP-012: `[100000, 1000000, 10000000]`, Corwin-Schultz-spread
+ 3% årlig borrow-kostnad AKTIV (kodmässigt kontrollerad av
`validate_friction_usage.py` via `validate_hypothesis.py`).

## 7. Rapportering — MaxDD måste redovisas explicit per nivå

Kriteriets andra pass-villkor (MaxDD bättre än −50% på alla tre nivåer) är
lika viktigt som Sharpe-villkoret — redovisa båda tydligt i
`result_summary`, inte bara Sharpe. Om Sharpe klarar tröskeln men MaxDD inte
gör det på någon nivå är HELA hypotesen FAIL, inte ett delvis godkännande.

## 8. Rekommenderad kodstruktur för Coder

```
/strategies/HYP-016/
  backtest.py    # kopia av HYP-012/backtest.py, vol-skalning tillagd (steg 4),
                 # motorfixarna (steg 5) inbakade i load/clean-stegen
  results/       # Backtesters output per kapitalnivå
```

Coder måste köra
`python scripts/validate_hypothesis.py research/hypothesis_registry/HYP-016-vol-hanterad-momentum.yaml`
och få exit code 0 innan Backtester får exekvera koden.
