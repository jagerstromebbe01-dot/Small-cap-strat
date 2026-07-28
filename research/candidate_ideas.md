# Candidate Ideas

Icke-bindande förslag från Hypothesis Miner. En post här är INTE en
pre-registrerad hypotes och har INGEN status i multipel-testnings-räkningen
(K). Den blir bara en riktig hypotes om CEO manuellt lyfter in den i
`/research/hypothesis_registry/` med ett låst `pass_fail_criterion`.

Mall per post:

```
## [Datum, ÅÅÅÅ-MM-DD]

**Källa:** [paper/text/teori, med länk eller referens om möjligt]

**Kort beskrivning:** [vad idén går ut på, 2-4 meningar]

**Varför relevant:** [koppling till detta projekts hypoteser, t.ex.
kapacitetsbegränsning i small-cap, eller en annan mekanism]
```

---

## [Datum, 2026-07-27]

**Källa:** Do, B., & Faff, R. (2010). "Does Simple Pairs Trading Still
Work?" Financial Analysts Journal, 66(4), 47-62.

**Kort beskrivning:** Studerar lönsamheten av enkel, distansbaserad
parhandel (samma familj av strategi som v6-kärnan) över en längre
tidsperiod och finner att den genomsnittliga överavkastningen minskat
över tid i takt med att fler aktörer replikerat metoden, samtidigt som
lönsamheten som återstår tenderar att koncentreras till perioder och
segment med hög volatilitet och sämre likviditet - inte jämnt
utspridd över hela marknaden.

**Varför relevant:** HYP-008 (v6-kärnan replikerad på small-cap)
misslyckades nyligen (FAILED, 2026-07-27) med negativ Sharpe på alla
kapitalnivåer. Do & Faffs fynd - att kvarvarande parhandels-edge
koncentreras till volatila/illikvida segment snarare än att small-cap
generellt skulle vara ett sådant segment - ger en möjlig förklaring:
kapacitetsbegränsning (stora fonder får inte plats) och "svårhandlat
segment" (hög volatilitet/låg likviditet) är inte nödvändigtvis samma
sak. Om en framtida hypotes vill undersöka parhandel igen, kan den
behöva rikta in sig på volatilitet/likviditet specifikt snarare än
enbart börsvärde som urvalskriterium.

---

## [Datum, 2026-07-28]

**Källa:** Berk, J. B., & Green, R. C. (2004). "Mutual Fund Flows and
Performance in Rational Markets." Journal of Political Economy, 112(6),
1269-1295.

**Kort beskrivning:** Bygger en rationell jämviktsmodell där kapital
strömmar till fonder/förvaltare som visat god historisk avkastning, men
där varje förvaltares strategi har avtagande skalavkastning (decreasing
returns to scale) - ju mer kapital som förvaltas i strategin, desto mer
urholkas alfa genom marknadspåverkan (market impact) och minskad
kapacitet. I jämvikt flödar kapital in tills förväntat alfa netto efter
avgifter pressas ner mot noll, oavsett hur skicklig förvaltaren
ursprungligen var. Modellen förutsäger alltså INTE att skickliga
förvaltare ger hög framtida avkastning till investerare, utan att
kapacitetsbegränsningen i sig är den mekanism som håller marknaden
ungefär effektiv.

**Varför relevant:** Detta är den teoretiska grundmekanismen bakom
projektets huvudhypotes om small-cap: att stora institutioner inte kan
allokera meningsfullt kapital till illikvida small-cap-namn utan att
själva äta upp edgen via market impact, vilket skulle kunna lämna kvar
outnyttjad edge för mindre, kapacitetsobegränsade aktörer. Berk & Greens
modell ger ett formellt ramverk för att tänka på VILKEN storlek på edge
som rimligen borde finnas kvar givet en given kapacitetsbegränsning
(kopplat till projektets krav på `tested_capital_levels` vid $100k/$1M/
$10M) - snarare än att bara anta att "small-cap = mindre konkurrens =
mer edge" utan att kvantifiera mekanismen. Kan vara relevant om en
framtida hypotes vill modellera hur mycket edge som borde finnas kvar
vid olika kapitalnivåer, snarare än att bara testa binärt om edgen
existerar.
