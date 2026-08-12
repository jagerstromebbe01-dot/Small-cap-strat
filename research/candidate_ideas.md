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

**Arkiverad:** true

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

**Arkiverad:** true

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

**Arkiverad:** true

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

---

**Arkiverad:** true

## [Datum, 2026-07-29]

**Källa:** Ang, A., Hodrick, R. J., Xing, Y., & Zhang, X. (2006). "The
Cross-Section of Volatility and Expected Returns." Journal of Finance,
61(1), 259-299.

**Kort beskrivning:** Visar att det är den IDIOSYNKRATISKA
volatiliteten - residualvolatiliteten efter att marknadsbetan räknats
bort via en faktormodell - snarare än TOTAL realiserad volatilitet, som
är den robusta, starkare formen av lågvolatilitetsanomalin. Aktier med
hög idiosynkratisk volatilitet har historiskt haft anmärkningsvärt lägre
genomsnittlig framtida avkastning, ett resultat som är svårförklarat
inom standardmodeller och renare än sorteringar på total std.

**Varför relevant:** HYP-014 (low-volatility-faktorn på small-cap,
testad 2026-07-29) sorterade på TOTAL realiserad volatilitet och gav
det hittills bästa resultatet av alla K=13 testade hypoteser (Sharpe
0.39/0.39/0.21, DSR 0.35-0.37) - men fortfarande FAILED. Ang et al. ger
en konkret, väldokumenterad, annorlunda signal att testa i stället:
residualen efter att marknadsbetan (redan beräknad via `compute_beta()`
i delad kod) dragits bort, snarare än total std - inte en omkörning av
samma sak, utan en specifik metodskillnad med egen litteraturgrund.
OBS (upptäckt vid granskning 2026-07-29): HYP-014:s befintliga
backtest-motor har en ombalanseringsbugg (kalenderdatum från
`resample().last()` matchas mot handelskalendern, och ~32% av
kvartalsslut hoppas tyst över när de faller på en icke-handelsdag) som
lät en felklassificerad ticker (ESSA) rida igenom ett datafel
okontrollerat i 9 månader och dominera det rapporterade resultatet
(dess enda trade stod för hela skillnaden mellan Sharpe 0.39 och 0.21
exkl. bästa traden). En idiosynkratisk-vol-uppföljare bör byggas på en
FIXAD ombalanseringsmotor, inte ärva samma defekt.

---

## [Datum, 2026-07-29]

**Källa:** Barroso, P., & Santa-Clara, P. (2015). "Momentum has its
Moments." Journal of Financial Economics, 116(1), 111-120. Se även
Daniel, K., & Moskowitz, T. J. (2016). "Momentum Crashes." Journal of
Financial Economics, 122(2), 221-247.

**Kort beskrivning:** Daniel & Moskowitz dokumenterar att
momentumstrategier drabbas av sällsynta men extrema "krascher" -
kraftiga, kortvariga reverseringar, typiskt strax efter marknadsbottnar
när tidigare förlorare rekylerar kraftigt medan momentumportföljen är
kort dem. Barroso & Santa-Clara visar att man kan eliminera merparten
av denna svansrisk, med bibehållen genomsnittlig avkastning, genom att
skala positionsstorleken OMVÄNT mot momentumportföljens EGEN nyligen
realiserade volatilitet (inte marknadens) - dvs minska exponeringen när
portföljen själv blivit ovanligt volatil, ett tecken på att en krasch
är nära förestående.

**Varför relevant:** HYP-012 (cross-sectional momentum 12-1 mån på
small-cap, testad 2026-07-29) misslyckades INTE på grund av avsaknad av
genomsnittlig edge (rå Sharpe var faktiskt positivt vid $100k/$1M:
0.16/0.12) utan på grund av katastrofal maxdrawdown (-72% till -78%) -
exakt den typ av svansrisk Daniel & Moskowitz beskriver, och exakt den
mekanism Barroso & Santa-Clara adresserar direkt. Detta är alltså inte
"testa momentum igen" utan en riktad fix mot en redan diagnostiserad
felorsak. OBS (upptäckt vid granskning 2026-07-29): samma
ombalanseringsbugg som i HYP-014 finns även i HYP-012:s backtest-motor
(~29% av månadsslut hoppas tyst över), och det dominerande vinsttradet
(ARDMQ, +3923% på en månad) ser ut att vara en icke split-justerad
omvänd aktiesplit snarare än en riktig kursrörelse - samma mekanism som
möjliggjorde ESSA-fallet ovan gav sannolikt en konstlat hög rapporterad
Sharpe även här. En vol-hanterad-momentum-uppföljare bör byggas på en
fixad ombalanseringsmotor OCH kontrollera att prisserien är
split-justerad, inte bara återanvända befintlig infrastruktur
oförändrad.

---

## [Datum, 2026-07-30]

**Källa:** Daniel, K., & Moskowitz, T. J. (2016). "Momentum Crashes."
Journal of Financial Economics, 122(2), 221-247 (samma källa som redan
citerad ovan för HYP-016, men en annan del av dess mekanism).

**Kort beskrivning:** Daniel & Moskowitz visar att de värsta momentum-
kraschperioderna inte nödvändigtvis sammanfaller med när marknaden
faller snabbt, utan uppstår när tidigare FÖRLORARE studsar kraftigt
tillbaka strax efter en marknadsbotten (momentumportföljen är kort
dessa, eller i alla fall inte lång dem, och missar/förlorar på studsen).
Det är en annan signatur än en generell, snabb marknadsnedgång.

**Varför relevant:** Testade 2026-07-30 (diagnostik, se
scripts/diagnostic_momentum_crash_overlay.py) om HYP-017:s SPY-krasch-
overlay (triggar på SPY:s egen 10-dagars-nedgång < -10%) även skulle
tämja HYP-012/016:s momentum-signals MaxDD-problem. Svar: nej -
MaxDD rörde sig praktiskt taget inte (-76.6% med overlay mot -76.6%
utan). Det bekräftar att momentums kraschmekanism är en ANNAN än den
generella marknadspanik som drabbade lågvol-signalen (HYP-015/017) -
overlayen bevakar fel sak för just momentum. En framtida momentum-
uppföljare skulle behöva en signal som specifikt bevakar rebound hos
tidigare förlorare (t.ex. avkastningen för BOTTENdecilen av samma
momentum-rankning, inte SPY-index), inte en generell marknadsnedgångs-
trigger. Inte byggt eller testat - bara en riktad idé grundad i en
konkret, redan observerad negativ diagnostik.

---

## [Datum, 2026-08-09] — bredare sökrunda, sex kandidater

CEO-beslut 2026-08-09: nästa hypotesrunda får bredare scope (nya
alfasignaler/mekanismtyper, inte bara parametervarianter inom redan
bevisade mekanismer - se AskUserQuestion-svaret samma dag). Nedan är
Claudes EGNA, oberoende genererade kandidater (skrivna INNAN några
externa AI-svar setts, för att undvika adaptiv snedvridning - samma
disciplin som redan etablerad för multi-AI-brainstormar). Ingen K-
kostnad - dessa är förslag, inte pre-registrerade hypoteser.

Undviker medvetet: låg-vol L/S, kvalitet L/S, 52-veckors-högsta L/S,
generiska trendföljningsvarianter, bred CTA-korg, merger-arb - alla
redan diagnostiskt avfärdade under HYP-044:s kandidatsökning
2026-08-07 (se project-minnesanteckningen "HYP-044 candidate search").
Undviker även allt Kelly-viktat (Ejay är stängt, nio döda varianter).

**Källa:** Egen idé (Claude, 2026-08-09)

**Kort beskrivning (kandidat 1 — makroregim-timing utan prisbaserad trigger):** Använd VIX-terminskurvans lutning (spot-VIX minus 3-månaders VIX-futures, eller enklare: VIX-nivå relativt sitt eget 1-års rullande percentil) som en ANNAN typ av kraschtrigger än de redan använda SPY-pris-baserade (10-dagars-avkastning). Samma haircut-mekanik som redan validerad (HYP-017/023/037/047), men triggad av ett marknadsstämnings-/riskaversionsmått istället för realiserad prisrörelse.

**Varför relevant:** De fyra lyckade timing-mekanismerna använder alla SAMMA underliggande signal (SPY:s egen realiserade avkastning). VIX-terminsstrukturen är känd för att invertera (backwardation) INNAN och UNDER stress, vilket kan ge en tidigare eller kompletterande signal än ett rent lagg-baserat pris-mått. Kräver extern datakälla (CBOE VIX-data, inte i EODHD-cachen idag) - datafeasibility måste kollas innan lasning.

---

**Källa:** Egen idé (Claude, 2026-08-09)

**Kort beskrivning (kandidat 2 — blankningsintresse som ALFA-signal, inte bara friktion):** D'Avolio (2002, redan citerad ovan) dokumenterar att "specials" (dyra/svåra att låna aktier) koncentreras till mindre, mer illikvida bolag. Testa om HÖGT och STIGANDE short interest / days-to-cover i sig är en signal (kort de mest blankade namnen, eller tvärtom undvik dem i en long-portfölj) - inte bara en kostnadsjustering av en redan vald position.

**Varför relevant:** Detta skiljer sig strukturellt från alla redan testade urvalssignaler (som alla varit pris-/redovisningsbaserade) genom att direkt mäta ANDRA sofistikerade aktörers positionering - en mer direkt koppling till kapacitetsbegränsningstesen än något redan testat. Kräver short-interest-data (tvåveckorsfrekvens från FINRA/börser) - måste verifieras om EODHD tillhandahåller detta för small-cap-universumet.

---

**Källa:** Sloan, R. G. (1996). "Do Stock Prices Fully Reflect Information in Accruals and Cash Flows about Future Earnings?" The Accounting Review, 71(3), 289-315.

**Kort beskrivning (kandidat 3 — accrual-anomalin):** Bolag med höga periodiseringar (accruals - vinst som inte stöds av kassaflöde) tenderar att ha sämre framtida avkastning än bolag vars vinst är kassaflödesgrundad. En etablerad, väldokumenterad anomali - strukturellt annorlunda från PEAD/SUE (som redan testats och misslyckats två gånger, HYP-020/044) eftersom den mäter VINSTKVALITET, inte vinstöverraskning.

**Varför relevant:** Redovisningsdata (kassaflöde vs. resultaträkning) finns sannolikt redan tillgänglig via samma SEC EDGAR-pipeline som byggdes för HYP-020:s PEAD-signal - låg extra datakostnad. En genuint annan mekanism än de två redan misslyckade redovisningssignalerna (book-to-market, PEAD), inte en variant av dem.

---

**Källa:** Egen idé (Claude, 2026-08-09), inspirerad av det redan etablerade registermönstret

**Kort beskrivning (kandidat 4 — kvalitet som GATE för timing-aggressivitet, inte som urvalssignal):** Istället för att använda en kvalitetskomposit (lönsamhet/skuldsättning/stabilitet) för att VÄLJA aktier (redan avfärdat, se HYP-044-sökningen) - använd den för att MODULERA hur aggressivt en redan validerad timing-mekanism (t.ex. bear catcher-triggern) agerar. Exempel: djupare haircut vid trigger för portföljens lågkvalitetssegment, mildare för högkvalitetssegmentet.

**Varför relevant:** Direkt konsekvens av registrets eget starkaste mönster (timing fungerar, urval inte) - testar INTE kvalitet som en ny selektionsfaktor (redan dött spår) utan som en modifierare av en REDAN bevisad mekanismtyp. Strukturellt en ny sorts kombination, inte bara ännu en likaviktad portfölj av kända delar.

---

**Källa:** Egen idé (Claude, 2026-08-09), löst inspirerad av volatilitetsmålsättning i managed futures/crypto-kvantstrategier

**Kort beskrivning (kandidat 5 — portföljbred volatilitetsmålsättning som EGEN timing-mekanism):** Barroso & Santa-Clara (2015, redan citerad ovan) skalar EN signals (momentums) positionsstorlek mot dess egen realiserade volatilitet. Generalisera detta till att skala HELA HYP-047-portföljens exponering mot dess EGEN rullande realiserade volatilitet (inte någon enskild signals) - minska exponering när portföljen redan blivit ovanligt volatil, oavsett vad som orsakar det.

**Varför relevant:** Vol-targeting är en väletablerad teknik i managed futures och crypto-kvantstrategier (varifrån HYP-047:s bear catcher-mekanism ursprungligen hämtades, Hurst/Ooi/Pedersen-traditionen) men har inte testats på PORTFÖLJNIVÅ i detta register - bara indirekt via prisbaserade kraschtriggers. En strukturellt annan typ av riskhantering (kontinuerlig skalning, inte binär haircut/no-haircut).

---

**Källa:** Egen idé (Claude, 2026-08-09)

**Kort beskrivning (kandidat 6 — analytikeruppskattningars spridning som osäkerhetsproxy):** Hög spridning bland analytikers vinstprognoser (forecast dispersion) för ett bolag har i akademisk litteratur kopplats till lägre framtida avkastning (Diether, Malloy & Scherbina 2002) - tolkat som att hög oenighet/osäkerhet i sig är en riskfaktor institutioner undviker, vilket kan koppla direkt till kapacitetsbegränsningstesen (färre bevakande analytiker + högre oenighet = mer institutionellt undvikande = mer kapacitetsutrymme).

**Varför relevant:** En helt annan datakälla (analytikerkonsensus/-spridning, inte pris eller redovisning) än allt tidigare testat. HÖG DATAOSÄKERHET: small-cap-bolag i detta börsvärdesband har ofta MYCKET gles eller obefintlig analytikerbevakning - måste verifieras separat om EODHD har tillräcklig täckning innan detta är ens genomförbart. Flaggas explicit som den mest osäkra kandidaten datamässigt.

---

## [Datum, 2026-08-12] — cross-AI-konvergensanalys, "genuint ny alfa"-runda

CEO klistrade in samma "GENUINT NY ALFA (inte overlay)"-brainstormprompt
(se `research/CANDIDATE_BRAINSTORM_PROMPT_NY_ALFA_2026-08-11.md`) i tre
oberoende externa AI-konversationer OCH i denna Claude-session direkt.
Claude hann INTE leverera ett eget blint förslag innan de tre externa
svaren klistrades in i chatten - så det här är INTE ett fjärde
oberoende konvergensdatapunkt i BATCH-002-bemärkelse. Det är i stället
en verklighetskontroll av de tre externa svaren mot registret (K=68
vid tidpunkten) och mot faktisk kodbas-infrastruktur, vilket ingen av
de externa källorna hade tillgång till.

**Konvergenskluster (2+ källor, inklusive Claudes egen avbrutna
riktning):**
1. Framtida utspädning/shelf-overhang (S-3/ATM) - två externa källor
   oberoende + Claudes egen riktning.
2. Revisorsbyte/going-concern/filing-stress-kaskad - tre externa
   källor (olika djup) + Claudes egen riktning.
3. Risk Factors-textlikhet (Item 1A, cosine/Jaccard) - två externa
   källor, identisk konstruktion.
4. Amihud-impact/likviditetschocks-reversal - tre externa källor.
5. Turn-of-month-kalendereffekt - en extern källa + Claudes egen
   riktning.
6. Utdelningsinitiering/-indragning - en extern källa + Claudes egen
   riktning.

**Kritisk korrigering (registret vet något de externa källorna inte
vet):** en extern källa avfärdade explicit en januari-/skatteförlust-
variant som "utdöende anomaly, hög risk att slösa K"; en annan
behandlade den som en fotnot. Ingen av dem hade tillgång till
registret - **HYP-053 (skatteförlust-reversering, januarieffekten)
testade nästan exakt denna mekanism 2026-08-09 och PASSADE** (Sharpe
1,57/1,40/1,00 vid 100k/1M/10M, se HYP-053:s registerpost). Svag DSR
(0,30/0,24/0,12) pga kort aktivt fönster och redan högt K vid
låsningstillfället - men mekanismen är INTE bevisat döende, den är
redan validerad. Relevant för alla framtida kandidater i samma
familj: kontrollera korrelation mot HYP-053:s aktiva fönster innan
en ny variant registreras, annars riskeras dubbeltestning av samma
mekanism under ett nytt namn.

**Varningsflagga (konvergens ≠ ny mark):** Amihud-impact/likviditets-
chock-reversal-klustret konvergerade hos alla tre externa källor, men
registret har redan TRE oberoende misslyckanden i närliggande
mekanismer: HYP-013 (reversal), HYP-042 (reversal, MaxDD -98/-99%),
och särskilt HYP-050 (volymchock + litet prisutslag → long) som
FAILADE katastrofalt (Sharpe -1,24, MaxDD -98%) trots att
distress-filtret fungerade som avsett vid entry - positionerna
kollapsade ändå under hållperioden. Tekniskt skild konstruktion
(kräver ett prisutslag att fade:a, inte "inget utslag"), men tre
oberoende dödsfall i samma familj väger tyngre än extern konvergens
utan registertillgång.

**Infrastrukturverklighet (kontrollerat mot `data/sec_edgar_adapter.py`,
`data/fetch_issuance_history.py`, `data/fetch_buyback_history.py`):**
all befintlig SEC-infrastruktur pratar uteslutande mot `companyfacts`-
XBRL-API:et (strukturerade numeriska taggar). Ingenting i repot läser
idag filnings-index (formtyp+datum) eller faktisk dokumenttext.
Verifierat via webbsökning 2026-08-12: `data.sec.gov/submissions/
CIK##########.json` innehåller ett strukturerat `items`-fält för
8-K-inlämningar (t.ex. "4.01" för revisorsbyte, "4.02" för
non-reliance/omräkning) samt fullständig historik av `form`+
`filingDate` (inkl. NT 10-K/NT 10-Q, 10-K/A, S-3, 424B5) - INGEN NLP
krävs för formtyp- eller item-kod-baserade signaler. Textbaserade
förslag (Risk Factors-likhet, going-concern-språk, osäkerhets-
ordlistor, pressmeddelande-sentiment) kräver däremot en helt ny,
väsentligt dyrare kapacitet (faktisk dokumenttexthämtning), inte
byggd än.

**Beslut samma dag:** tre kandidater valdes ut och pre-registrerades
direkt (se HYP-072, HYP-073, HYP-074) baserat på ovanstående - alla tre
byggbara på antingen den nya, verifierade `submissions`-API-formtyp/
item-signalen (ingen NLP) eller på redan befintlig OHLCV/adjusted_close-
infrastruktur. Textklustret (Risk Factors-likhet m.fl.) parkerades
medvetet - högst extern konvergens men högst byggkostnad, bör
utvärderas i en egen, ostressad session efter att de billigare
kandidaterna gett resultat.
