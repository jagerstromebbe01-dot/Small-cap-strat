# HYP-008 — Råresultat (mall, ej ifylld)

**OBS:** Detta är enbart formatet för hur resultaten ska presenteras när
backtesten är klar. Inga siffror ännu, ingen DSR-beräkning, ingen
pass/fail-tolkning — det görs tillsammans med CEO efter granskning av
rådatan.

Två periodvarianter visas sida vid sida eftersom HYP-008:s `notes`-fält
flaggar glesare datatäckning 2010-2012 (känd begränsning, se
hypotesregistret) — att se båda gör det möjligt att bedöma om resultatet
drivs av den perioden eller är konsekvent över hela intervallet.

## Sammanfattningstabell

| Mått | 100k (2010-24) | 100k (2013-24) | 1M (2010-24) | 1M (2013-24) | 10M (2010-24) | 10M (2013-24) |
|---|---|---|---|---|---|---|
| CAGR | — | — | — | — | — | — |
| Sharpe (rå) | — | — | — | — | — | — |
| Calmar | — | — | — | — | — | — |
| Max Drawdown | — | — | — | — | — | — |
| Win rate | — | — | — | — | — | — |
| Profit factor | — | — | — | — | — | — |
| Antal trades | — | — | — | — | — | — |
| Sharpe (bästa trade exkluderad) | — | — | — | — | — | — |
| Calmar (bästa trade exkluderad) | — | — | — | — | — | — |

## Jämförelse mot large-cap-basen (redan validerad, för referens)

| Mått | Large-cap v6 (2010-2024) |
|---|---|
| Sharpe | ~0.55 |
| Calmar | ~0.56 |
| CAGR | ~4.8% |
| MaxDD | ~-8.6% |
| Win rate | ~59.5% |

## Kriteriets krav (för protokollet, ingen bedömning görs här)

Per HYP-008:s låsta `pass_fail_criterion` — PASS kräver ALLA på SAMTLIGA
tre kapitalnivåer:
1. Sharpe efter friktion >= 0.55 OCH >= 0.70 (absolut golv)
2. Calmar >= 0.56 OCH >= 0.60 (absolut golv)
3. Kriteriet i (1) håller även efter bästa traden exkluderad

## Observationer att notera vid genomläsning (ej slutsatser)

- Skiljer sig 2010-2012 markant från 2013-2024? (den flaggade
  begränsningen i notes-fältet)
- Var (om alls) degraderar prestandan mellan kapitalnivåerna -
  kapacitetsspärren (max 10% av 20-dagars snittvolym) är den enda
  mekanism som kan orsaka skillnad mellan nivåerna.
- Antal trades per nivå - påverkas kapacitetsspärren hur ofta en
  position ens kan öppnas, inte bara dess storlek?
