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

---

## [Datum, 2026-07-28]

**Källa:** Shleifer, A., & Vishny, R. W. (1997). "The Limits of
Arbitrage." Journal of Finance, 52(1), 35-55.

**Kort beskrivning:** Klassisk teoretisk artikel som visar att
arbitrage i verkligheten utförs av ett fåtal specialiserade,
professionella förvaltare som handlar med andras kapital (inte sitt
eget), snarare än av en anonym massa "rationella arbitrageurer" som i
läroboksmodeller. Eftersom dessa förvaltares kapitalbas beror på hur
investerare uppfattar deras löpande resultat, kan de tvingas stänga
positioner just när mispricing är som störst (t.ex. vid tillfälliga
förluster som utlöser inlösenkrav), vilket gör att arbitrage kan
förbli ofullständigt - särskilt i tillgångar som redan är volatila,
har begränsad likviditet, eller kräver mycket specialiserat kapital
för att handlas i skala.

**Varför relevant:** Ger en kompletterande mekanism till Berk & Green
(2004, se ovan) för VARFÖR kapacitetsbegränsning kan lämna kvar edge i
small-cap: det handlar inte bara om att skickliga förvaltares alfa
konkurreras bort i jämvikt via kapitalinflöden, utan också om att
professionella arbitrageurers agentur-problem (förvaltat kapital,
inlösenrisk) gör dem strukturellt ovilliga eller oförmögna att delta i
just de segment - lågt likvida, volatila small-cap-namn - där
mispricing annars skulle kunna bestå längst. Kopplar även till
Do & Faff (2010, se ovan) fynd att kvarvarande parhandels-edge
koncentreras till volatila/illikvida segment: Shleifer & Vishny ger en
teoretisk grund för VARFÖR just dessa segment är de professionella
arbitrageurerna undviker, snarare än en slump. Relevant om en framtida
hypotes vill formulera urvalskriterier bortom enbart börsvärde (t.ex.
kombinerat med likviditets- eller volatilitetsmått) för att fånga var
denna typ av edge rimligen borde finnas kvar.

---

**Arkiverad:** true

## [Datum, 2026-07-28]

**Källa:** D'Avolio, G. (2002). "The Market for Borrowing Stock."
Journal of Financial Economics, 66(2-3), 271-306.

**Kort beskrivning:** Empirisk studie av den amerikanska aktielånemarknaden
som visar att de flesta aktier är lätta och billiga att låna ("general
collateral"), men att en mindre delmängd - "specials" - har kraftigt
förhöjda lånekostnader och begränsat utbud. Dessa specials är
systematiskt koncentrerade till aktier med lägre börsvärde, lägre
institutionellt ägande och högre volatilitet. Studien visar också att
långivare kan återkalla utlånade aktier ("recall risk"), vilket kan
tvinga en blankare att stänga positionen i förtid oavsett om tesen
fortfarande gäller.

**Varför relevant:** Detta är en direkt, konkret mekanism för den
friktion som spec avsnitt 2 punkt 3 kräver ska modelleras från början
(short availability, borrow cost) - inte en abstrakt kapacitetsmekanism
som Berk & Green eller Shleifer & Vishny (se ovan), utan empirisk
dokumentation av att just mindre bolag har systematiskt dyrare och mer
osäker tillgång till blankningsben. Detta är särskilt relevant för v6,
som är en beta-neutral parhandelsstrategi där varje position har ett
blankningsben: om short-benet i en small-cap-baserad parhandel
regelbundet hamnar bland "specials" (hög lånekostnad, recall-risk), kan
det urholka eller helt äta upp en Sharpe-förbättring som annars ser
lönsam ut i en backtest utan denna friktion inräknad. Relevant om en
framtida hypotes vill kvantifiera hur mycket av ett eventuellt small-cap-
edge som är en artefakt av att inte modellera borrow-kostnad och
recall-risk korrekt, snarare än verklig, realiserbar avkastning.

---

## [Datum, 2026-07-28]

**Källa:** Gatev, E., Goetzmann, W. N., & Rouwenhorst, K. G. (2006). "Pairs
Trading: Performance of a Relative-Value Arbitrage Rule." Review of
Financial Studies, 19(3), 797-827.

**Kort beskrivning:** Den ursprungliga och mest citerade empiriska studien
av distansbaserad ("distance method") parhandel - exakt den familj av
strategi som v6-kärnan bygger på. Författarna bildar par genom att
minimera summan av kvadrerade avstånd mellan normaliserade prisserier
under en formationsperiod, handlar sedan avvikelser från det historiska
spreadet under en efterföljande handelsperiod, och visar signifikant
positiv riskjusterad avkastning över lång amerikansk aktiedata
(1962-2002), även efter rimliga antaganden om transaktionskostnader. De
visar också att en stor del av lönsamheten kommer från par bildade inom
samma bransch/undergrupp, och tolkar en del av avkastningen som
kompensation för att bära en form av "limits of arbitrage"-risk snarare
än ren riskfri arbitrage.

**Varför relevant:** Detta är grundstudien för hela strategifamiljen som
v6 tillhör, och kompletterar Do & Faff (2010, se ovan) - som studerar hur
lönsamheten föll över tid - genom att visa en möjlig förklaring till
VARFÖR metoden fungerade från början (branschmatchning vid parbildning,
avkastning som kompensation för arbitrage-risk snarare än gratislunch).
Om en framtida hypotes vill undersöka small-cap-parhandel igen kan Gatev
et al.:s betoning på branschmatchning i parbildningssteget vara ett
konkret metodval att testa (t.ex. begränsa par till samma
bransch/undergrupp) snarare än att para ihop aktier enbart baserat på
pris-distans över hela small-cap-universumet - vilket enligt Do & Faff
(2010) kan vara en del av förklaringen till varför edgen urholkats över
tid.

---

## [Datum, 2026-07-28]

**Källa:** Frazzini, A., Israel, R., & Moskowitz, T. J. (2012, working
paper, University of Chicago Booth School of Business / AQR Capital
Management). "Trading Costs of Asset Pricing Anomalies."

**Kort beskrivning:** Använder verkliga, realiserade handelsdata från en
stor institutionell förvaltare (inte modellerade/uppskattade
transaktionskostnader) för att mäta faktisk genomförandekostnad för ett
brett antal kända anomalier, inklusive storlekseffekten. Författarna
visar att pris-impact (market impact) - inte bara bid-ask-spreaden -
dominerar den verkliga kostnaden, att denna impact växer olinjärt med
handelsstorlek relativt genomsnittlig daglig volym, och att den är
kraftigt koncentrerad till just de minsta och minst likvida aktierna.
En konsekvens är att många anomaliers "papper-Sharpe" i akademiska
studier kraftigt överskattar vad som faktiskt är implementerbart i
skala, medan kostnaden vid blygsam kapitalstorlek ofta är betydligt
lägre än den naiva bid-ask-baserade uppskattningen antyder.

**Varför relevant:** Kompletterar D'Avolio (2002, se ovan) - som
dokumenterar friktion på blankningsbenet (borrow cost, recall risk) -
med motsvarande empirisk dokumentation för själva handelsutförandet
(price impact) på båda benen i en parhandel, vilket är precis den typ
av friktion spec avsnitt 2 punkt 3 kräver ska modelleras från början.
Den olinjära relationen mellan impact och handelsstorlek relativt
daglig volym ger en konkret, empiriskt grundad mekanism för VARFÖR
edgen kan degradera med kapitalstorlek - direkt kopplat till projektets
krav på att testa `tested_capital_levels` vid $100k/$1M/$10M snarare än
att anta ett binärt "fungerar/fungerar inte". Relevant om en framtida
hypotes vill bygga en explicit impact-kostnadsmodell (skalad mot
genomsnittlig daglig volym per aktie) i stället för en platt
kostnadsantagande per trade.
