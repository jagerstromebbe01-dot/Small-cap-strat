# Överlämningsprompt: fortsättning av small-cap-forskningsprojektet (2026-08-13)

Klistra in detta i en ny konversation i samma repo (samma katalog, `CLAUDE.md` läses in automatiskt av Claude Code). Detta är INTE en extern-AI-brainstormprompt (jämför `CANDIDATE_BRAINSTORM_PROMPT_*.md`) - det är en ren kontext-överlämning så en ny konversation kan fortsätta exakt där den här slutade, utan att behöva återuppleva hela resonemangskedjan.

---

## VIKTIGT FÖRST: `CLAUDE.md` är sannolikt föråldrad

`CLAUDE.md`s "Current state"-avsnitt beskriver troligen fortfarande en äldre referensportfölj (fyra ben + volatilitetsmålsättning, K i 60-talet). Den bilden stämmer INTE längre - se "Nuvarande läge" nedan för den faktiska, senaste bilden. `CLAUDE.md` bör uppdateras för att spegla detta (spec-dokumentets egen regel: "If you deviate from the spec, update the spec itself") - inte gjort ännu, en bra första uppgift i den nya konversationen om inget annat är mer akut.

## Vad hände 2026-08-12 till 2026-08-13 (i korthet)

En cross-AI-konvergensbrainstorm (Grok/ChatGPT/Gemini) för "genuint ny alfa, inte ännu en exponeringstiming-overlay" ledde till **HYP-072** (Dilution Pipeline - short bolag med aktiv shelf-registreringsaktivitet / long "rena" bolag, SEC submissions-API, ny signal, PASSED). Diagnos visade koncentrationsrisk (kurtosis 366, en enda augusti-2020-vecka dominerade). En kedja av riktade förbättringar följde:

- **HYP-075** (symmetriskt positionstak, PASSED, slog HYP-072 på nästan allt)
- **HYP-079** (+ branschkoncentrationstak, PASSED, ny starkaste variant - kurtosis ner till 8,8)
- Sex vidare försök (HYP-082 t.o.m. HYP-086: enskilda kombinationer, korrelationsbudget, sqrt-ADV-viktning, 8-K-katalysatortiming) - **alla FAILED**, HYP-079 höll ställningen
- **HYP-081**: naiv 80/20-kombination av HYP-079 med den då gällande referensportföljen (HYP-056) - **PASSED tydligt** (Sharpe 1,38 mot HYP-056:s 1,22, MaxDD -4,2% mot -5,9%). **CEO-BESLUT: HYP-081 är nu referensimplementationen.**
- DSR omräknad för hela referenskedjan mot dagens K (var kraftigt eftersläpande, senast uppdaterad vid K=46). HYP-081 fick DSR 0,99-1,00 - bland det högsta i hela registret.
- CEO frågade hur man når CAGR >15% (uttalat mål sedan tidigare, aldrig nått). Svar: hävstång med marginalanrop, samma redan validerade mekanism som tidigare testats (HYP-059, HYP-065), nu applicerad på den nya, säkrare HYP-081-basen.
- **HYP-087** (2,5x hävstång på HYP-081): PASSED med god marginal (Sharpe 1,16, CAGR 14,3%, MaxDD -11,6%, NOLL marginalanrop). Disclosure vid 3,0x visade CAGR 16,4% utan att kollapsa (till skillnad från tidigare försök på den äldre basen, som kollapsade vid 3x).
- **HYP-088** (3,0x hävstång, formellt låst): PASSED (Sharpe 1,14, CAGR 16,4%, MaxDD -14,1%, NOLL marginalanrop). **CEO valde 3,0x som hävstångsstandard.**

## Stresstestet som ändrade bilden

Eftersom marginalanropsmekanismen ALDRIG faktiskt triggat över 15 år av riktig data (0 anrop på alla nivåer) byggdes ett syntetiskt stresstest (`scripts/diagnostic_hyp088_synthetic_stress_test.py`, sedan utökat till `scripts/diagnostic_hyp088_stress_test_all_levels.py`) - körde den EXAKTA, redan låsta koden mot konstruerade, extrema scenarier (inte riktig data, ingen K-kostnad).

**Tre fynd, i registret under HYP-088:s "TILLÄGG"-kommentarer:**
1. Trigger-, slippage- och återlåningslogik fungerar korrekt (verifierat).
2. En DELVIS återhämtning som inte tydligt passerar återlåningsgränsen (-5%) kan lämna strategin fast vid ~1,0x hävstång **på obestämd tid**, även i en lugn marknad efteråt.
3. **Viktigast:** i ett scenario värre än något i 2010-2025 (-35% underliggande nedgång, ingen snabb studs) blev den faktiska drawdownen **-43%** vid 3,0x - långt över det låsta -20%-taket. -20%-villkoret höll i backtesten bara för att inget så extremt någonsin hände under just den perioden.
4. **Uppföljning över hela hävstångsskalan (1,5x/2,0x/2,5x/3,0x):** överraskande liten skillnad i det extrema scenariot (1,5x gav -38,9%, 3,0x gav -43,3% - bara 4,4 procentenheter skillnad, trots halva hävstången). **Förklaring:** mekanismens golv (`DELEVER_FLOOR`) är alltid 1,0x, aldrig lägre - så vid en tillräckligt LÅNG, djup underliggande nedgång (som ALDRIG hänt i HYP-081:s historia; dess egen värsta MaxDD någonsin är -4,2%) rider alla nivåer ut resten av nedgången likadant efter att marginalanropet löst ut. Hävstångsnivån avgör mest hur mycket som händer INNAN triggern (litet), inte EFTER (stort, dominerar).

## Nuvarande läge (fakta, inte tolkning)

- **K = 85** (se `research/hypothesis_registry/_counter.yaml`).
- **Referensimplementation:** HYP-081 (obelånad, femte-bens-kombination). Historiskt: Sharpe 1,38, CAGR 7,9%, MaxDD -4,2%, DSR 0,99-1,00.
- **Hävstångslager (valt, men ej känslomässigt avgjort):** HYP-088 (3,0x). Historiskt: Sharpe 1,14, CAGR 16,4%, MaxDD -14,1%, NOLL marginalanrop över 15 år. Syntetiskt värsta scenario: -43,35%.
- HYP-087 (2,5x) finns kvar som ett dokumenterat, testat, PASSED alternativ (historiskt MaxDD -11,6%, syntetiskt värsta scenario -41,3% - inte heller mycket bättre, se fynd 4 ovan).

## Den olösta frågan - detta är kärnan i "vägen framåt"

CEO uttryckte, efter att ha sett -43%-fyndet: **"detta gör mig osäker på om jag faktiskt vill tradea den i verkligheten då -43% är mkt"** - en välgrundad, inte överdriven, reaktion. Sista genomgången (fynd 4) visade att problemet inte i första hand är "vilken hävstångsnivå" (1,5x skyddar knappt bättre än 3,0x i det extrema fallet) utan **hävstång-eller-inte, givet just den här mekanismens design** (golv vid 1,0x, inget genuint kontantskydd).

Tre reella vägar, ingen ren teknisk fråga:

1. **Ingen hävstång alls.** Handla HYP-081 obelånad. Säkert, redan starkt (Sharpe 1,38), men når inte det uttalade 15%+-CAGR-målet.
2. **Acceptera hävstångens svansrisk medvetet**, med vetskap om att nivåvalet (1,5x-3,0x) inte skyddar särskilt mycket mot just detta extremscenario - välj då hellre på Sharpe/CAGR-avvägning (som redan dokumenterad i HYP-087 vs HYP-088) än på en illusion om att en lägre nivå är mycket säkrare.
3. **Designa en ny mekanism** som kan deleverera UNDER 1,0x (delvis genuin kontantväxling, inte bara tillbaka till obelånat golv) - INTE byggd eller testad än, skulle bli en egen, ny, separat pre-registrerad hypotes med eget K.

**Ingen av dessa har valts.** Det är där konversationen ska fortsätta.

## Övriga öppna trådar (lägre prioritet, nämnda tidigare samma dag)

- `CLAUDE.md` bör uppdateras för att spegla dagens faktiska referenskedja (se "VIKTIGT FÖRST" ovan).
- Paper trading är fortfarande blockerad av samma EODHD-datatäckningsproblem som i augusti (small-cap-priser för glesa/föråldrade för genuin forward-validering) - okänt om det löst sig, inte kollat på ett tag.
- HYP-072-familjen (dilution pipeline) verkar ha planat ut efter sex misslyckade förbättringsförsök (082-086) - antingen acceptera HYP-079 som slutgiltig, eller leta efter en helt ny, oberoende alfakälla härnäst.

## Vad jag vill att du gör i den nya konversationen

Fortsätt EXAKT där den här slutade - hjälp mig tänka igenom (inte sälj in åt någotdera hållet) hävstångsbeslutet ovan, i mitt eget tempo. Om jag istället vill hoppa till ett av de andra trådarna, följ det. Du behöver INTE läsa om hela historiken ovan i detalj - den är här som facit om du behöver kolla en specifik siffra eller varför ett beslut togs, inte som något du ska sammanfatta tillbaka till mig.
