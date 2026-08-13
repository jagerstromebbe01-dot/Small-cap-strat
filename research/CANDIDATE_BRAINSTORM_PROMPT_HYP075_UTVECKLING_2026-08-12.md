# Brainstorm-prompt: hur utvecklar vi HYP-075 till det bästa möjliga? (2026-08-12)

Klistra in detta i en ny, oberoende konversation med en extern AI (Gemini, ChatGPT, Grok, eller annan). Kör det i en helt egen konversation. Kör gärna samma prompt mot flera olika AI:er separat — konvergens mellan oberoende källor har historiskt varit den starkaste urvalssignalen i det här projektet.

---

## Bakgrund

Jag driver ett systematiskt "mini hedge fund"-forskningsprojekt med sträng pre-registrerings- och multipeltestningsdisciplin (varje testad idé ökar en global räknare K, för närvarande **K=75**, och Deflated Sharpe Ratio räknas mot K). Universum: amerikanska small-cap-aktier, $100M–$2B börsvärde, daglig OHLCV-data + SEC EDGAR (både strukturerad XBRL-data och nu även filnings-metadata via submissions-API:et — formtyp, filingdatum, 8-K-item-koder). Ingen options- eller terminsdata. Kärntesen: stora institutioner är kapacitetsbegränsade i small-cap-segmentet.

**Referensportfölj (fyra ben + volatilitetsmålsättning):** köp-och-håll-index + idiosynkratisk-volatilitets-strategi med kraschöverlägg + egenbyggd momentum long/short-svit + trendföljande indexkort-position under 200-dagars glidande medelvärde, plus en volatilitetsmålsättnings-overlay ovanpå helheten. Sharpe ~1,22, MaxDD ~-6%.

## Historien om HYP-072 → HYP-075 (läs noga, undvik att föreslå sådant som redan testats)

**HYP-072 (Dilution Pipeline, PASSED 2026-08-12):** en helt ny, femte-bens-kandidat, ortogonal mot de fyra befintliga benen (korrelation ≈ 0 mot alla). Mekanism: månatlig ombalansering, SHORT namn med "aktiv shelf-användning" (≥2 S-3-familjefilingar — S-3/S-3-A/S-3ASR/424B3/424B5 — inom trailing 12 månader, varav ≥1 inom trailing 6 månader), LONG "rena" namn (0 S-3-familjefilingar inom trailing 24 månader). Ekonomisk tes: anticiperat, ännu ej realiserat framtida aktieutbud är en direkt prissättningsmekanism — existerande ägare möter en förutsägbar potentiell säljare. Sharpe 0,77, MaxDD -6,2% vid $100k.

**Diagnosticerad svaghet (samma dag):** en betydande del av edgen var koncentrerad till EN position (tickern BRTXD, en verifierat äkta men extrem micro-cap-rally, +25625% på en enda ombalanseringsperiod, augusti 2020) och en enda vecka i augusti 2020. Kurtosis på den dagliga avkastningsserien var 366 (mot 3,0 för normalfördelning). DSR (Deflated Sharpe Ratio, K=71) var bara 0,72 vid $100k och föll till 0,34 vid $10M.

**Tre riktade förbättringsförsök testades samma dag (var för sig, egen K, dömda mot HYP-072:s egna redan uppmätta tal):**
1. **HYP-075 (positionstak, PASSED)** — symmetriskt, upprepbart tak: om en position (long ELLER short) mer än TREDUBBLAS i värde sedan senaste entry/trimning, trimma tillbaka till referensvärdet nästa handelsdag. **Detta är hypotesen vi nu vill utveckla vidare.** Resultat: Sharpe 0,81 (upp från 0,77), MaxDD -6,05%, kurtosis **7,7** (ner från 366 — 48x lägre, i praktiken normalfördelningsnivå), Sharpe exklusive hela 2020 = 0,77 (upp från 0,49). BRTXD-tradet kapades från +25625% till +533%.
2. **HYP-076 (engångs-vinsthemtagning, PASSED)** — sälj 50% av en long-position FÖRSTA gången den dubblas, rör inte resten. Högre rå Sharpe (0,86) men mindre kurtosis-förbättring (169, eftersom halva positionen fortfarande fick rida vidare).
3. **HYP-077 (kontinuerlig shelf-intensitet + decilrangordning, FAILED)** — ersatte den binära tröskeln med en tidsviktad kontinuerlig poäng och decilrangordning. Misslyckades: decilbegränsningen smalnade OAVSIKTLIGT av "ren"-gruppen från ~350 till ~70 namn/månad (bottendecilen bestod till 100% av score=0-namn), vilket ÖKADE koncentrationen istället för att minska den. **Undvik förslag som bygger på att ersätta den binära tröskeln med en snävare decil/rank-baserad urvalsregel av samma typ.**

**HYP-078 (naiv 80/20-kombination HYP-056+HYP-075, PASSED samma dag):** som femte ben (naiv vikt, korrelation kontrollerad först: -0,04 till +0,11 mot de fyra befintliga benen) förbättrar HYP-075 den REDAN starka referensportföljen på BÅDE Sharpe (1,22 → 1,38) OCH MaxDD (-5,9% → -4,2%) samtidigt — en äkta, additiv förbättring, inte bara en riskreducering som råkar se bra ut på ett mått.

**En kvarstående, olöst kuriositet:** trots att HYP-075 slår HYP-072 på nästan alla mått (Sharpe, MaxDD, kurtosis, ex-2020-Sharpe), är HYP-075:s DSR (0,55 vid $100k, K=74) LÄGRE än HYP-072:s (0,72). Orsak: att klippa de extrema VINSTERNA gjorde avkastningsfördelningen mer NEGATIVT skev (skew -1,96 mot HYP-072:s +13,95), vilket DSR-formeln straffar. Om ni har tankar om detta — är det ett äkta problem med DSR som verktyg i den här specifika situationen, eller ett äkta observandum om att positionstaket byter en typ av svansrisk mot en annan?

## Vad jag vill ha av er

Ni ska INTE föreslå en ny, oberoende alfakälla (det är en annan brainstorm-omgång) — ni ska specifikt hjälpa till att **utveckla HYP-075 till det bästa möjliga**, inom dess redan etablerade ekonomiska mekanism (anticiperat aktieutbud + symmetriskt positionstak). Tänk brett kring:

1. **Kompletterande riskhantering** som INTE redan testats (positionstak och engångs-vinsthemtagning är redan gjorda) — t.ex. sektor-/branschkoncentrationstak, korrelationsbaserad positionsstorlek, eller andra sätt att hantera svansrisk som inte bara är "ännu en tröskelvariant" av samma tak.
2. **Bättre utnyttjande av redan tillgänglig SEC-data** — vi har nu (sen 2026-08-12) både companyfacts-XBRL:et OCH submissions-API:ets formtyp+item-koder. Finns det ett sätt att göra shelf-signalen mer precis (t.ex. skilja på ATM-program vs. fasta erbjudanden, eller väga in HUR MYCKET kapacitet som registrerats relativt float — obs: kräver sannolikt att faktiskt läsa filingtexten, en dyrare, ej byggd kapacitet, så flagga datakänslighet ärligt) utan att det blir en ren efterhandsanpassning till redan sedda resultat?
3. **Kapacitets-/skalbarhetsfrågor** — Sharpen faller med kapitalnivå (0,81 → 0,71 → 0,64 vid HYP-075). Finns det en princip-baserad (inte efterhandsanpassad) förändring av positionsstorlekslogiken som skulle kunna dämpa detta, t.ex. en annan ADV-kapacitetsspärr eller ett annat sätt att fördela kapital mellan short- och long-benet?
4. **DSR-kuriositeten ovan** — om ni har ett skarpt perspektiv på skevhet vs. kurtosis-avvägningen.
5. **Robusthetsdimensioner vi inte testat än** — t.ex. sensitivitet för exakt vilka S-3-formtyper som räknas, eller om resultatet håller om man exkluderar den mest extrema BRANSCHEN (inte bara den mest extrema tickern).

**Krav på varje förslag:**
- Systematiskt, regelbaserat, INGA fria parametrar kvar att välja efter att ha sett resultat.
- Konkret mekanism + tydlig ekonomisk eller statistisk motivering.
- Explicit ärlighet om datakänslighet (byggbart med redan hämtad data, eller kräver ny hämtning?).
- **VIKTIGT (projektets kärndisciplin):** detta ska vara EN enda, icke-adaptiv batch av förslag — ni har INTE sett några backtest-resultat för era egna förslag (det är omöjligt, de är inte kört än), och skriver därför fulla, låsbara mekanismer direkt, inte "vi testar X och justerar sen". Jag (CEO) läser alla förslag, väljer manuellt vilka som ska pre-registreras och låsas, och KÖR SEDAN samtliga i batchen — även de som ni själva tror är svagare. Ingen selektiv rapportering av bara vinnare.

**Format:** 3–6 kandidater. För varje: namn, mekanism (låst, inga fria parametrar), motivering, datakänslighetsnot, och en kort not om varför den INTE bara är en kosmetisk variant av HYP-075/076/077.
