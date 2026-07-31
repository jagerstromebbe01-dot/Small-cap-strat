# Strategispec: HYP-030 — Momentum-krasch-trigger (förlorar-rebound)

**Källhypotes:** `/research/hypothesis_registry/HYP-030-momentum-krasch-rebound-trigger.yaml`
**Input-krav bekräftade:** `status: pre-registered` ✅, `pass_fail_criterion` ifyllt ✅ (låst 2026-07-31).

## 1. Kodbas

Baserad på `/strategies/HYP-016/backtest.py` (12-1-månaders momentum,
toppdecil, friktion/hedge/kapacitetsspärr, de tre motorfixarna) — UTAN
HYP-016:s tvåpass-volatilitetsskalning (den mekanismen redan FAILED).

## 2. Förlorar-komposit

Ny funktion `compute_loser_composite_returns`: för varje kalendermånad,
hitta bottendecilen (lägst 12-1-momentum) av månadens eligible-universum
via samma `mom_df`-uppslagning som huvudsignalen använder, bygg ett
likaviktat kompositindex av deras dagliga avkastningar — samma
förenklade månadsnyckel-metod som HYP-023:s bank-/finanskomposit.

## 3. Trigger

`LOSER_REBOUND_TRIGGER_RET = 0.10` (MOTSATT tecken mot SPY-overlayens
-10% — trigger vid UPPGÅNG, inte nedgång), `LOSER_REBOUND_LOOKBACK_DAYS
= 10`, `LOSER_REBOUND_HAIRCUT_FRACTION = 0.40` — samma magnitud/fönster
som SPY-overlayen, medvetet återanvänt. Skär HELA portföljen (ingen
sektor-liknande delmängd att rikta in sig på, till skillnad från
HYP-023).

## 4. Resultat

FAILED kraftigt — se `HYP-030`:s `result_summary` för full diagnos.
Kompositen triggade 80 gånger på 14 år (mot 5-8 för SPY-/sektor-
overlayerna), och MaxDD blev SÄMRE än den redan dokumenterade
odiagnostiserade baslinjen. Mekanismen fångar rutinmässig small-cap-
volatilitet i redan pressade bolag, inte genuina kraschrebounder.
Momentum-familjen (HYP-012/016/030) betraktas nu som stängd.
