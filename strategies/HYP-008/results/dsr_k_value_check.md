# DSR/K-värde-kontroll (läsning, ingen körning mot riktiga resultat)

**Fråga:** Kommer Deflated Sharpe Ratio-beräkningen använda rätt K-värde
(ska bli K=8: de 7 döda ejay-varianterna + HYP-008 själv)?

## Vad koden faktiskt gör

`scripts/deflated_sharpe_ratio.py`s funktioner
(`deflated_sharpe_ratio()`, `deflated_sharpe_ratio_from_returns()`) tar
**`n_trials` som ett explicit argument** — skriptet läser INTE
automatiskt något värde från `_counter.yaml` eller HYP-008:s YAML-fil.
Det är medvetet generiskt/testbart (bekräftat i sanity-checken med K=1,
7, 8, 50, 200 mot syntetisk data — matematiken är verifierad korrekt:
DSR sjunker monotont när K stiger för samma underliggande Sharpe).

## Vilket K-värde som SKA användas när det väl körs

- `research/hypothesis_registry/_counter.yaml`: `k_total: 7` (oförändrat,
  korrekt — uppdateras enligt Overfitting Detector-rollen först EFTER
  att en hypotes testats, och HYP-008 är inte testad än).
- HYP-008:s eget fält `k_total_hypotheses_before_this: 7`.
- Per docstringen i `deflated_sharpe_ratio()`: `n_trials =
  k_total_hypotheses_before_this + 1` (denna hypotes räknas med) = **8**.

Så: **K=8 är det korrekta värdet**, och koden är förberedd för att ta
emot det - men den GARANTERAR det inte automatiskt.

## Ett gap värt att notera (inte åtgärdat nu, bara flaggat)

Det finns ingen kod-spärr som förhindrar att någon (agent eller CEO)
råkar anropa `deflated_sharpe_ratio(..., n_trials=<fel tal>)` av misstag
- till skillnad från `validate_hypothesis.py`, som är en hård,
automatisk spärr. Detta är alltså beroende av att den som kör
beräkningen (Overfitting Detector-rollen) läser `k_total` korrekt från
registret för hand, inte ett mekaniskt tvång.

**Rekommendation för senare (inget beslut taget, väntar på CEO):**
en liten wrapper-funktion som läser `k_total_hypotheses_before_this`
direkt från hypotesens YAML-fil och beräknar `n_trials` automatiskt,
istället för att låta anroparen skriva in talet manuellt varje gång -
skulle stänga detta gap. Föreslås, inte byggt.

## Status just nu

Inget kört mot riktiga HYP-008-resultat. Detta är enbart en kodgranskning
i väntan på att backtesten blir klar.
