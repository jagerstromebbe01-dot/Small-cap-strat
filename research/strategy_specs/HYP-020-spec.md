# Strategispec: HYP-020 — PEAD via SUE

**Källhypotes:** `/research/hypothesis_registry/HYP-020-pead-via-sue.yaml`
**Input-krav bekräftade:** `status: pre-registered` ✅, `pass_fail_criterion` ifyllt ✅ (låst 2026-07-30).

## 1. Ny datakälla — byggd denna session

`data/fetch_eps_history.py`: hämtar EPS (`EarningsPerShareBasic`, fallback
`Diluted`) MED filingsdatum per ticker via SEC EDGAR `companyfacts`-API
(per-CIK, återanvänder redan byggd ticker→CIK-mappning från
`data/cache/smallcap_classification.jsonl` — löser INTE CIK-matchning på
nytt). Testat mot bulk-`frames`-API:et först — det saknar filingsdatum,
duger inte för PEAD. Output: `data/cache/eps_by_ticker.jsonl`.

## 2. Kodbas

Kopiera `/strategies/HYP-015/backtest.py` till `/strategies/HYP-020/backtest.py`.
Universum, friktion, hedge, kapacitetsspärr, motorfixar — allt
oförändrat. Skillnader mot HYP-015:
- `REBAL_FREQ`: `"ME"` (månatlig) i stället för `"QE"` — PEAD roterar
  snabbare än lågvol/storlek, samma konvention som HYP-012:s momentum.
- Signal: SUE i stället för idiosynkratisk vol (se nedan).
- Sortering: `scores.sort(reverse=True)` — HÖGST SUE (mest positiv
  överraskning), motsatt riktning mot HYP-014/015/019:s "lägst av
  måttet"-konvention.

## 3. SUE-beräkning — `load_sue_signal()`

Per ticker: gruppera EPS-observationer per `(fy, fp)`, ta EARLIEST
`filed`-datum per grupp (ursprunglig rapport, inte omräkningar).
`SUE_raw = EPS[fy,fp] - EPS[fy-1,fp]` (matchat på fiskalkvartal, inte
kalenderdatum — fungerar även för icke-kalenderår). Standardisera med
std av de senaste 8 kvartalens `SUE_raw` (kräver minst 4 tidigare
observationer). Snappa filingsdatumet till FÖRSTA handelsdag PÅ ELLER
EFTER (inte närmaste FÖREGÅENDE — en händelse kan bara påverka
framtiden). Bygg en daglig, framåtfylld DataFrame med `ffill(limit=63)`
(≈3 månader) — ett SUE-värde äldre än det räknas som inaktuellt.

## 4. Vad som INTE ska vara med

Ingen krasch-overlay, stop-loss, eller vol-skalning — rent signaltest,
matchar HYP-012/013/014/015/019:s utvärderingsstil.

## 5. Kapitalnivåer och validering

`[100000, 1000000, 10000000]`. Kör
`scripts/validate_hypothesis.py research/hypothesis_registry/HYP-020-pead-via-sue.yaml`
och få exit 0 innan körning.

## 6. Kända begränsningar (för protokollet)

- SUE kräver minst 4-5 års EPS-historik per bolag innan ett standardiserat
  värde alls kan beräknas — nyare/nyligen noterade small-caps kommer
  systematiskt sakna signal tidigt i sin historia. Detta är en känd,
  oundviklig begränsning av den säsongsbaserade SUE-metoden (kräver inte
  analytikerkonsensus, men kräver egen historik), inte ett fel.
- Många bolag rapporterar inte ett separat "Q4"-kvartal i XBRL (bara
  helår, `fp="FY"`) — dessa bolags Q4-kvartal saknar därför ett eget SUE-
  värde i denna implementation. Flaggat, inte löst här.
