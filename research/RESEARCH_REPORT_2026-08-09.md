# Forskningsrapport: Mini Hedge Fund-projektet

**Datum:** 2026-08-09
**Status:** Ögonblicksbild — K=46, referensimplementation HYP-047
**Mottagare:** Extern AI-granskning (primär), CEO (sekundär)
**Metod för granskning:** repo-access rekommenderas framför att läsa denna text isolerat — se del 3 för pekare till källfiler. Den granskande AI:n bör vara adversariell, inte bekräftande: varje siffra nedan går att verifiera mot `research/hypothesis_registry/*.yaml` och git-historiken.

---

## Del 1: Resultat och varför

### 1.1 Utgångspunkten

Projektet startade som ett test av om en beta-neutral OLS-pariserhandelsstrategi (**v6**, redan validerad på large-cap 2010–2024: Sharpe ~0.55, CAGR ~4.8%, MaxDD ~-8.6%) behåller sin edge på small-cap-aktier ($100M–$2B börsvärde), på tesen att stora institutioner är kapacitetsbegränsade där — inte en informationsasymmetri-tes.

Tre direkta pariserhandelsreplikationer (HYP-008/009/011) misslyckades. Det ledde inte till att projektet lades ner, utan till en pivot: istället för att jaga en enskild small-cap-signal, testades om en **portföljkombination** av flera oberoende byggstenar kunde nå CEO:s uttalade grundmål — konstant CAGR >10 %/år **och** Sharpe >1. Det är den kombinationsspåret som till slut bar frukt.

### 1.2 Ejay — det första, viktiga misslyckandet

Parallellt testades ett internt signalkvalitetsmått, "Ejay" (senare visat matematiskt ekvivalent med Kelly-kriteriet), i sju oberoende varianter. Alla dog av samma grundorsak: cirkularitet — måttet förklarade inget utöver ren z-score-styrka, och viktade/oviktade varianter var för högt korrelerade för att vara oberoende bevis. Ejay återöppnades en gång till (HYP-040, CEO:s eget TA-mönster-förslag) och dog en nionde gång, av samma mönster. Ejay är stängt.

Detta är inte en fotnot — det är skälet till att hela pre-registrerings- och K-räkningsdisciplinen (spec §2) finns. Utan den hade sju-nio falska positiva kunnat plockas ut i efterhand och presenteras som "fungerande".

### 1.3 Det upprepade mönstret: exponeringstiming vs. urval/viktning

Ett tydligt, upprepat mönster växte fram genom registret:

- **Exponeringstiming-mekanismer** (när man är exponerad, inte vad man äger): **ursprungligen 4 av 5 vid respektive testtillfälle** (HYP-017, HYP-023, HYP-037, HYP-047 PASSADE; HYP-045 FAILADE) — **men 3 av 5 enligt dagens status**, eftersom HYP-037 formellt ändrades till `failed` 2026-08-09 (se del 3.1/3.2). Historiskt PASS och nuvarande status är inte samma sak, och rapportens tidigare version blandade ihop dem — rättat 2026-08-09 efter extern granskning. Räkna alla fem, inte bara framgångarna, annars överdrivs mönstret ändå.
- **Urvals-/viktningsförsök** (byta VAD man äger inom en redan vald pool) har misslyckats **9 av 9 gånger**, per registrets egna löpande räkningar i `_counter.yaml`: HYP-030 (momentum-krasch-rebound), HYP-031 (beta-hedge mot IWM), HYP-032 (Kelly-sizing), BATCH-001 (5 stop-loss-varianter, räknat som ett), HYP-033 (book-to-market), HYP-034 (stale-price-filter), HYP-036 (sektorneutral ranking), HYP-038 (likviditetsviktad allokering), HYP-042 (kortsiktig reversal — det sämsta enskilda resultatet i hela registrets historia, MaxDD -98 till -99 %, och därmed den starkaste datapunkten i denna bucket).

**Viktig reservation, tillagd efter gårdagens granskning (se del 3):** detta mönster är äkta men bygger på ett litet sample (5 vs. 9 observationer), och sökprocessen är inte neutral — senare kandidater föreslogs delvis **för att** tidigare timing-idéer redan lyckats, vilket kan förstärka mönstret artificiellt snarare än att bara bekräfta det. Behandla det som en stark hypotes om varför projektet fungerat, inte som ett statistiskt bevisat faktum.

### 1.4 Vägen till dagens referensimplementation

1. **HYP-017 → HYP-021 → HYP-023 → HYP-037**: idiosynkratisk volatilitet + SPY-kraschöverlägg, förfinat i tre steg (sektorspecifik trigger, sedan villkorat återinträde). HYP-037 blev referens 2026-08-01.
2. **HYP-039** (2026-08-04): första kombinationshypotesen — naiv 50/50 SPY + HYP-037. Korrelation SPY/HYP-037 uppmätt till -0,003 (praktiskt taget noll) FÖRE låsning. Sharpe 1,02/1,03/0,99, MaxDD -22 % (mot SPY:s egna -33,7 %). **Första gången CEO:s grundmål nåddes.**
3. **HYP-043** (2026-08-06): tredje ben, en egenbyggd (inte ETF-proxy) momentum long/short-svit. Ursprungligen den starkaste kombinationen i registret (Sharpe 1,05, MaxDD -15,6 %) — **men se del 3: denna slutsats höll inte vid full friktionskorrigering, upptäckt 2026-08-07 och slutgiltigt bekräftat 2026-08-08.**
4. **HYP-044/045/046** (2026-08-07): tre raka misslyckade försök till fjärde ben (PEAD/SUE-faktor, kraschöverlägg på kombinationen, och en sammanslagning av de två) — samtliga med hög DSR (genuina, inte slumpmässiga) men otillräckliga mot det redan höga kravet. HYP-046 gav dock registrets bästa MaxDD någonsin (-9,7 %) trots FAIL på Sharpe — ett konkret exempel på Sharpe/MaxDD-avvägning, inte ett varningstecken.
5. **HYP-047** (2026-08-07, CEO-beslut om referensstatus 2026-08-08): en offensiv, trendföljande SPY-kortposition (under 200-dagars glidande medelvärde) som fjärde ben — tjänar aktivt pengar i nedgångar istället för att bara gå till kontanter. Sourced från en 4-AI-brainstorm. **PASSADE på alla fyra villkor, alla tre kapitalnivåer**, och slog även den redan friktionskorrigerade HYP-043-baslinjen tydligt. Byggdes med egen, korrekt friktion på momentum L/S-benet från start (`compute_momentum_ls_sleeve_with_spread`, återanvände aldrig HYP-043:s ofullständiga variant).

**Viktigt förtydligande (tillagt efter extern granskning 2026-08-09):** "referensimplementation" betyder att HELA fyrbenskombinationen, testad som en egen enhet, klarar SITT EGET kriterium — inte att varje enskild komponent (SPY, HYP-037, momentum L/S, bear catcher) individuellt klarar sitt eget separata, historiska kriterium. HYP-037 (en av fyra ben) har idag status `failed` på sitt eget villkor (se del 3). Det är inte ett brott mot förbudet i spec §5b mot att kombinera icke-signifikanta strategier — HYP-037 var giltigt PASSED när HYP-047 byggdes och testades (2026-08-07), och blev FAIL först vid en senare, separat korrigering (2026-08-08/09) av dess EGEN jämförelse mot HYP-023. HYP-047:s egen kombinerade prestanda byggde på HYP-037:s faktiska avkastningsserie (senare även omkörd med korrigerad data, se del 3.1) som en diversifierande komponent, inte på slutsatsen att HYP-037 "vinner" mot något — precis som HYP-039 aldrig krävde att HYP-037 slår HYP-023. Men språket "referensimplementation" bör läsas med den nyansen i åtanke, inte som att alla fyra ben är oantastliga var för sig.

### 1.5 Dagens siffror för HYP-047

Två giltiga körningar, båda PASS: originalresultatet (låst 2026-08-07) och en oberoende, fullt korrigerad omkörning (2026-08-08, se del 3). Visas separat nedan istället för som ett spann, eftersom Calmar och OOS-Sharpe rör sig i olika riktningar mellan de två körningarna och ett aggregerat intervall döljer det.

| Nivå | Sharpe (orig → korr) | MaxDD (orig → korr) | Calmar (orig → korr) | OOS-2025 Sharpe (orig → korr) |
|---|---|---|---|---|
| $100k | 1,156 → 1,126 | -7,44 % → -8,67 % | 1,17 → 0,97 | 1,546 → 1,710 |
| $1M | 1,164 → 1,127 | -7,30 % → -8,45 % | 1,18 → 1,01 | 1,494 → 1,720 |
| $10M | 1,099 → 1,102 | -7,23 % → -8,20 % | 1,08 → 0,99 | 1,468 → 1,780 |

DSR vid K=46: 0,96–0,98 för originalkörningen; **0,9716/0,9719/0,9651 för den korrigerade körningen** (uträknat 2026-08-09 efter extern granskning påpekade att detta saknades — fortsatt mycket högt, gapet var en dokumentationslucka, inte ett oroande resultat när det väl räknades).

**Notera:** MaxDD och Calmar är genomgående något sämre i den korrigerade körningen — den korrigerade pipelinen är strängare, inte snällare, mot HYP-047. Sharpe- och OOS-villkoren håller ändå med marginal på båda körningarna. Efter korrigering är HYP-047 inte längre bäst i registret på MaxDD/Calmar — den (FAILADE) HYP-046 har bättre korrigerad MaxDD (-8,09 % vid $100k, se del 3.1).

Validerad mot: huvudperioden (2010–2024) och genuin blind OOS-2025 (inkl. en verklig SPY-krasch april 2025) för **hela** fyrbensportföljen. En tredje datapunkt — historiska kriser 2000–02 och 2008 — finns också, men gäller bara **bear catcher-benet isolerat** (100 % egen notional), inte hela HYP-047: +63,78 % under 2000–02 mot SPY:s -33,85 %, +40,25 % under 2008 mot SPY:s -43,41 % (`scripts/diagnostic_bear_catcher_extended_history.py`). Motsvarande pre-2010-data för HYP-037-benet och momentum L/S-sviten finns inte i repot, så hur hela HYP-047 skulle presterat 2000–02/2008 är okänt — detta ska läsas som stöd för ett av fyra ben, inte som en tredje fullständig validering av strategin.

---

## Del 2: Metoden — en återanvändbar process

Det som gör HYP-047 till mer än "en strategi som råkade fungera" är processen som ledde dit. Tre delar är värda att beskriva som återanvändbar metod, inte bara historik:

### 2.1 Pre-registrering + K-räkning + Deflated Sharpe Ratio

Ingen backtest körs utan ett låst, skrivet `pass_fail_criterion` (skrivet av CEO manuellt i chatt, aldrig av en agent). Varje tested variant — även misslyckade — ökar en global räknare `k_total`. Deflated Sharpe Ratio (Bailey & López de Prado) beräknas mot detta K, inte mot den enskilda backtestens egen Sharpe. Detta är direkt motiverat av Ejay-episoden: utan K-räkning hade 7–9 misslyckade varianter kunnat gömmas.

### 2.2 Multi-AI-brainstorm som kandidatgenerator

Från och med HYP-044 användes externa AI-konsultationer för att generera kandidatidéer. **Rättelse (efter granskning av denna rapport 2026-08-09):** ett tidigare utkast beskrev detta som en "strikt engångs, icke-adaptiv batch" och åberopade CLAUDE.md:s formella "Batch Hypothesis Generation"-regel. Det är fel på två sätt. Dels är den formella batch-proceduren (alla kandidater låsta som ETT block, K ökar med N samtidigt) bara använd en gång i hela registret — BATCH-001 (fem stop-loss-varianter). Dels, viktigare: HYP-047 söktes explicit fram **efter tre raka FAIL (044/045/046)** — en ny AI-konsultation beställd just för att tidigare kandidater misslyckats är per definition en resultatstyrd sökprocess på metanivå, samma mönster som Batch-regeln finns för att förhindra på kandidatnivå.

Det som ÄR sant, och som räddar detta från att vara ett upprepat Ejay-mönster: varje enskild kandidat pre-registrerades och K-räknades för sig, med sitt eget låsta kriterium skrivet innan resultatet sågs — så statistiken (DSR mot löpande K) räknar korrekt in varje försök, lyckat eller inte. Vad som INTE är skyddat är den mjuka, mänskliga signalen i VILKEN typ av mekanism som föreslås näst (se reservationen i 1.3) — det är en kvarstående, öppet redovisad svaghet, inte en löst problem.

- HYP-044: första externa 5-AI-brainstorm → PEAD/SUE-kandidaten, efter att redan kända dödläge (insiderköp, kortsiktig reversal) filtrerats bort.
- HYP-047: 4-AI-brainstorm efter tre raka FAIL (044/045/046) → trendföljande "crisis alpha"-mekanism (Hurst/Ooi/Pedersen-traditionen), testad efter en diagnostik som explicit mätte falsklarmsfrekvens över hela perioden (36 episoder, 34 träffar/2 falsklarm) för att undvika hindsight-attributionsrisk.

### 2.3 Kostnadsfri diagnostik före låsning

Innan en kandidat låses som pre-registrerad hypotes (och därmed kostar K) körs ofta billig, icke-K-kostande diagnostik: regimbetingad stresstest, korrelation mot befintliga ben, falsklarmsfrekvens över hela perioden. Detta filtrerar bort svaga kandidater utan att "betala" för dem i multipeltestningsräkningen — men är i sig ett potentiellt sårbart steg (se del 3, punkt om urvalsprocessens neutralitet).

### 2.4 Kombinationsreglerna (spec §5b)

Att kombinera hypoteser är explicit förbjudet som genväg runt individuellt misslyckande. Legitim kombination kräver: korrelationsmatris på avkastningsserier FÖRE låsning, naiv likaviktning (aldrig in-sample-optimerad), OOS-testning, och egen K-kostnad per distinkt kombinationsmetod. **Rättelse (2026-08-09):** ett tidigare utkast hävdade att denna regel höll fullt ut genom hela kedjan HYP-039 till HYP-047. Det stämmer för HYP-039/041/043/044, men inte för HYP-046: dess registerpost hade vid låsning bara en kvalitativ motivering ("mekaniskt olika, ingen överlappning") — den kvantitativa korrelationssiffran (-0,093/-0,004/-0,015, se del 3.1) räknades ut först i efterhand, av gårdagens granskning. Ett dokumenterat, om än litet, avsteg från §5b:s bokstav, inte en teoretisk risk.

---

## Del 3: Aktuell status och öppna frågor

### 3.1 Fallstudie: den oberoende granskningen 2026-08-08

Innan denna rapport skrevs kördes en adversariell audit av hela registret — inte för att bekräfta att allt var bra, utan för att aktivt leta efter brott mot projektets egna regler. Metod: tre helt blinda, oberoende AI-granskare, samma checklista, ingen samordning, repo-access (inte bara sammanfattningar).

**Konvergenta fynd (hittade oberoende av flera granskare, därför hög tillförlitlighet):**

1. **Deflated Sharpe Ratio räknades aldrig om** för redan aktiva hypoteser när K växte, trots att detta är en explicit hård regel (`agents/overfitting_detector/ROLE.md`). HYP-017/021/023/037/039/041/043 visade DSR beräknat mot ett K som var lägre — i vissa fall mindre än hälften — av dagens 46.
2. **En känd look-ahead-bias i universumkonstruktionen** (aktieantal tidsstämplat med periodslut-datum istället för SEC-inlämningsdatum, ~20,8 % av ticker-månads-medlemskap påverkat) hade en korrigering byggd redan 2026-08-05, men den gjordes **aldrig till produktionsdefault** — alla strategier körde fortfarande på den kända biasade filen.
3. **En känd datakvalitetsbugg** (konstant orimlig adjusted_close/close-kvot, ~9,5 % av universum) var bara manuellt kopierad in i senare hypoteser (HYP-042–047), aldrig centraliserad i den delade `data_hygiene.py` eller portad till referenskedjan.
4. **Noll transaktionskostnad vid ombalansering** mellan ben i samtliga sju kombinationshypoteser, trots principen "friktion från dag ett" (spec §2).
5. **HYP-043:s redan kända friktionsgap** (saknad bid-ask-spreadkostnad i momentum L/S-sviten, upptäckt 2026-08-07) fanns bara dokumenterat i andra hypotesers prosa, aldrig i dess egen registerpost.

**Åtgärdat, samma dag, med samma disciplin som redan etablerad i registret** (daterade tilläggsnoter, aldrig tyst omskriven historik, egen commit per hypotes, ingen ny K-kostnad eftersom detta är buggkorrigering av redan testade hypoteser, inte nya hypoteser):

- DSR omräknad mot K=46 för de sju berörda hypoteserna.
- Look-ahead-fixen och adjusted_close-fixen portade till produktionskod för HYP-037/039/041/043/044/045/046/047.
- En enhetlig 10bps ombalanseringskostnad tillagd i alla sju kombinationshypoteser.
- HYP-043 fick fem tilläggsnoter (DEL A–E) som dokumenterar hela kedjan av fynd, avslutat med en fullt kombinerad omkörning (alla fyra fixar samtidigt).
- HYP-046 fick sin tidigare saknade kvantitativa korrelationsmatris (PEAD/SUE-sviten mot övriga tre ben: -0,093/-0,004/-0,015 — bekräftade den kvalitativa "icke-överlappande"-motiveringen, men räknades ut efter låsning, inte före den — se rättelsen i del 2.4).

**Resultatet av full korrigering, hypotes för hypotes (avgörande $100k-nivå):**

| Hypotes | Sharpe vid $100k (original → korrigerad) | Verdict korrigerad pipeline |
|---|---|---|
| HYP-037 (bas) | 0,737 → 0,726 (håller, håller även vid $1M/$10M: 0,741→0,759) | Villkor 1 PASS. Villkor 2 (MaxDD vs HYP-023): **FAIL/PASS/FAIL** vid $100k/$1M/$10M mot en konsekvent korrigerad HYP-023-baslinje (se not) — inte "FAIL på alla tre" som en tidigare version av denna tabell sa |
| HYP-039 | 1,019 → 1,017 | **PASS oförändrat** |
| HYP-041 | 0,998 → 0,988 | FAIL oförändrat |
| HYP-043 | 1,046 → **0,876** (alla fyra fixar kombinerade) | **FAIL, entydigt** (var PASS) |
| HYP-044 | 1,012 → 0,953 | FAIL oförändrat |
| HYP-045 | 0,994 → 0,985 | FAIL oförändrat (samma rakbladstunna nära-miss) |
| HYP-046 | 0,948 → 0,894 | FAIL oförändrat, MaxDD ännu bättre (-8,09 %, bäst i registret **efter korrigering**) |
| **HYP-047 (flaggskepp)** | 1,156 → 1,126 | **PASS på alla fyra villkor, alla tre nivåer — ingen flip** (MaxDD/Calmar dock något sämre korrigerat, se del 1.5) |

**Slutsats av fallstudien:** flaggskeppsresultatet (HYP-047) står på fast grund — verifierat både genom att den ursprungliga låsta registerposten är helt oförändrad (noll rader borttagna, endast tillägg) och genom en oberoende, fullt korrigerad omkörning som ger samma slutsats. Men grunden under det (HYP-037, HYP-043) var svagare än registret tidigare visade. Det här är inte en invändning mot projektet — det är exakt vad disciplinen är designad att hitta, och den hittade det.

### 3.2 Kvarstående kända luckor (öppna, inte dolda)

- **HYP-023 korrigerades 2026-08-09** (var den sista kända luckan, stängd samma dag som denna sammanfattning skrevs). Även HYP-023 försämras av korrigeringen (MaxDD -25,46/-19,29/-13,16 % → -26,07/-23,59/-14,12 %). Jämfört mot en nu konsekvent korrigerad baslinje blir HYP-037:s villkor 2 **FAIL/PASS/FAIL** (vid $100k/$1M/$10M) istället för det tidigare "FAIL på alla tre nivåer" — marginalerna är rakbladstunna (0,13pp och 0,05pp) snarare än breda. HYP-037:s status förblir korrekt `failed` (villkoret måste hålla på alla tre nivåer), men skillnaden mellan PASS och FAIL är nu synligt liten, inte ett tydligt underkännande.
- **HYP-037:s OOS-2025 kördes inte om** under den korrigerade pipelinen (avgränsning i gårdagens uppdrag, disclosed explicit).
- **`status`-fälten för HYP-037 och HYP-043 ändrades formellt till "failed" 2026-08-09** (CEO-beslut, se respektive registerpost) — de klarar inte längre sina egna låsta kriterier under den fullt korrigerade pipelinen. De ursprungliga siffrorna i `capital_level_results` är oförändrade (historik skrivs inte om); bara statusbedömningen är uppdaterad. HYP-039 är därmed den senaste hypotesen i kedjan som fortfarande passerar på egna meriter före HYP-047, och HYP-023 är grunden HYP-039 med flera faktiskt vilar på.
- **Forward paper trading är fortfarande datablockerad**, inte strategiblockerad — EODHD:s täckning för small/micro-cap-tickers ligger veckor till månader efter i realtid. All validering ovan (huvudperiod, OOS-2025, historiska kriser) är historisk data. OOS-2025 är den bästa tillgängliga approximationen av genuin framåtvalidering, men är det inte i egentlig mening.
- **Mönstret i 1.3 (timing 4/5 vs urval 0/9)** bygger på litet sample och en potentiellt icke-neutral sökprocess — se reservationen ovan.
- **Multi-AI-brainstorm-processen (del 2.2) är K-skyddad på kandidatnivå men inte på metanivå** — vilken typ av mekanism som föreslås näst påverkas av vad som redan lyckats/misslyckats (HYP-047 söktes uttryckligen efter tre raka FAIL). Ingen mekanism i registret räknar eller korrigerar för denna mjukare form av sökstyrning.
- **`scripts/diagnostic_bear_catcher_extended_history.py`** (kris-valideringen i del 1.5) saknade tidigare en tilläggsnot i registret och en commit, till skillnad från allt annat i denna rapport — åtgärdat 2026-08-09, se källpekare nedan.
- **Diagnostik-innan-låsning kan i sig vara en mjuk urvalsprocess** (påpekat av extern granskning 2026-08-09): HYP-047:s bear catcher-mekanism testades mot sin egen historiska falsklarmsfrekvens över HELA perioden (36 episoder) INNAN hypotesen låstes. Detta följer samma "kostnadsfri diagnostik"-mönster som används konsekvent i registret (se del 2.3) och mekanismen i sig (200-dagars trendföljning) är en väletablerad, extern teknik — inte parameteranpassad mot detta dataset. Men principiellt är gränsen mellan "kostnadsfri screening av om en känd mekanismtyp är rimlig" och "in-sample-validering som borde räknas" inte knivskarp, och K/DSR skyddar bara mot multipeltestning av FAKTISKT LÅSTA hypoteser, inte mot vilken mekanismTYP som väljs att föreslås näst. Ingen mekanism i registret räknar eller korrigerar för denna typ av sökstyrning.
- **Kort tillgänglighet (short availability) är fortfarande aldrig implementerad** — bara lånekostnad (`borrow_cost`) och bid-ask-spread modelleras. Det är ett projektbrett gap som funnits sedan start (CLAUDE.md flaggar det som ett "stubbat" fält), inte specifikt för HYP-047, men bör inte glömmas bort i en rapport som betonar friktionsdisciplin.
- **Ordningen mellan HYP-043:s friktionsfynd och HYP-047:s låsning, båda 2026-08-07, går inte att fullt verifiera i git-historiken** eftersom HYP-044 till HYP-047 committades som ett enda block (se konvergenta fynd, gårdagens granskning) — det går alltså inte att med säkerhet utesluta att HYP-047:s hårdkodade jämförelsepunkt (den friktionskorrigerade HYP-043-baslinjen) formulerades med kännedom om samma dags friktionsfynd. Detta var redan känt som ett granskningsspårsproblem (del 3.1, konvergent fynd om commit-kollaps) men kopplingen till just detta scenario gjordes inte explicit förrän extern granskning 2026-08-09 påpekade den.
- **Small-cap-kapacitetsfrågan** (kärntesen — att edgen finns för att stora institutioner är kapacitetsbegränsade, inte informationsasymmetri) testas fortfarande bara indirekt via kapitalnivåkänslighet ($100k/$1M/$10M), aldrig direkt.

### 3.3 Källpekare för granskning

- `research/hypothesis_registry/*.yaml` — samtliga 39 hypotesposter, inkl. dagens tilläggsnoter
- `research/hypothesis_registry/_counter.yaml` — K-räknare + narrativ logg
- `strategies/HYP-047/backtest.py`, `strategies/HYP-043/backtest.py` — produktionskod, inkl. gårdagens fixar
- `strategies/common/data_hygiene.py` — centraliserad datasanering
- `scripts/deflated_sharpe_ratio.py`, `scripts/recompute_dsr_k46.py` — DSR-metod och omräkningsverktyg
- `scripts/diagnostic_bear_catcher_extended_history.py` — kris-valideringen (2000–02, 2008) för bear catcher-benet isolerat
- Git-historiken 2026-08-08 (commits `7d43610` till `90bd7fd`) — hela gransknings- och fixkedjan, en commit per logisk ändring
- Git-historiken 2026-08-09 — rättelser till denna rapport efter en andra, oberoende trepersoners granskning av rapporttexten själv (samma metod som 2026-08-08, riktad mot rapporten istället för mot registret)
- 2026-08-09, ytterligare en runda: två genuint externa AI-tjänster (Gemini, ChatGPT) granskade rapporten utan repo-access, enligt `research/EXTERNAL_REVIEW_BRIEF.md`. Gav upphov till de senaste rättelserna ovan (3/5-korrigeringen, DSR för korrigerad HYP-047-körning, förtydligandet om "referensimplementation", samt de tre nya öppna metodfrågorna direkt ovan). En sakligt felaktig invändning (att K-sekvensen 015–023 inte går ihop) verifierades och avfärdades — K-sekvensen är korrekt, granskaren blandade ihop en tidigare, legitim DSR-omräkning (2026-07-30) med hypotesens egen plats i K-ordningen.
