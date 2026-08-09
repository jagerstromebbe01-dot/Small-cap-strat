# Brainstorm-prompt: nya kandidatidéer för small-cap-forskningsprojektet

Klistra in detta i en ny, oberoende konversation med en extern AI (Gemini, ChatGPT, eller annan). Kör det i en helt egen konversation, inte i samma tråd som någon tidigare granskning.

---

## Bakgrund

Jag driver ett systematiskt "mini hedge fund"-forskningsprojekt med sträng pre-registrerings- och multipeltestningsdisciplin (varje testad idé ökar en global räknare K, och Deflated Sharpe Ratio räknas mot K för att undvika falska positiva från att testa för många varianter). Universum: amerikanska small-cap-aktier, $100M–$2B börsvärde, daglig OHLCV-data (öppen/hög/låg/stäng/justerad stäng/volym), ingen options- eller terminsdata tillgänglig. Kärntesen: stora institutioner är kapacitetsbegränsade i detta segment (kan inte allokera meningsfullt kapital utan att äta upp sin egen edge via marknadspåverkan), vilket kan lämna kvar edge för mindre aktörer — INTE en tes om informationsasymmetri.

**Redan bekräftat FUNGERAR** (upprepat, oberoende mönster genom ~46 testade hypoteser): mekanismer som styr NÄR man är exponerad mot marknaden (kraschtriggade exponeringsminskningar, trendföljande overlägg) har lyckats betydligt oftare än mekanismer som styr VAD man äger inom en redan vald grupp aktier (faktorviktning, stop-loss-varianter, likviditetsviktning, Kelly-sizing har nästan alla misslyckats).

**Redan testat och MISSLYCKATS** (undvik att föreslå raka upprepningar av dessa utan en tydligt ny vinkel):
- Klassisk pariserhandel (v6-strategin replikerad på small-cap)
- Ren cross-sectional momentum long-only (katastrofal drawdown vid reverseringar)
- Kortsiktig reversal (10-dagars) — small-cap-"förlorare" är ofta genuint kollapsande bolag, inte överreagerade
- PEAD/earnings surprise (SUE) som fristående signal (svag, om än defensivt intressant under kriser)
- Book-to-market, rörelselönsamhet, insiderköp (SEC Form 4)
- Kelly-sizing, sektortak, likviditetsviktad allokering, sektorneutral ranking, beta-hedge mot annat index, stale-price-filter, fem varianter av stop-loss-trösklar
- Ett internt signalkvalitetsmått baserat på Kelly-kriteriet ("Ejay") — dog i nio oberoende varianter av cirkularitet. **Föreslå INGET som i grunden är en Kelly-viktad signalstyrka.**

**Nuvarande starkaste resultat:** en fyrbent portfölj (köp-och-håll-index + en idiosynkratisk-volatilitets-strategi med kraschöverlägg + en egenbyggd momentum long/short-svit + en trendföljande indexkort-position under 200-dagars glidande medelvärde).

## Vad jag vill ha av dig

Det här är en **bred** sökning den här gången — inte bara parametervarianter på det som redan fungerar (den typen av avgränsad sökning har redan gjorts). Jag vill ha:

1. **Helt nya alfasignaler eller mekanismtyper** vi inte testat än — gärna med koppling till kapacitetsbegränsningstesen ovan, men behöver inte vara det.
2. **Nya sätt att KOMBINERA redan validerade byggstenar** — inte bara likaviktade portföljer av redan kända delar (det är redan gjort sju gånger), utan strukturellt annorlunda sätt att kombinera dem.
3. **Idéer lånade från andra tillgångsslag** om du ser en rimlig, motiverad övergångslogik — t.ex. om något från crypto, råvaror, valuta eller managed futures har en mekanism som borde generalisera till small-cap-aktier. Motivera VARFÖR den skulle överföras, inte bara att den fungerat någon annanstans.

**Krav på varje förslag:**
- Måste vara **systematiskt, regelbaserat** — ingen diskretionär bedömning.
- Ange en konkret, om än inte slutgiltig, mekanism (vad mäts, vilken tröskel/riktning, hur ofta ombalanseras det).
- En kort ekonomisk motivering för VARFÖR det skulle finnas edge, inte bara att det "brukar fungera".
- Notera om det är rimligt att bygga med bara daglig OHLCV-data för small-cap-aktier, eller om det kräver data vi sannolikt inte har (optionsdata, terminskurvor, sentimentdata) — flagga det öppet, avfärda inte idén bara för det, men var ärlig.
- Förvänta dig INTE att idén ska "vinna" — de flesta testade idéer i detta projekt har misslyckats, och det är förväntat och helt okej. Jag vill ha kvantitet och variation, inte en enda perfekt idé.

**Format:** 5–8 kandidater. För varje: namn, 2–4 meningars mekanismbeskrivning, ekonomisk motivering, hur den skiljer sig från det redan testade ovan, och en kort datakänslighetsnot.

Var gärna djärv. Konventionella idéer inom det redan beprövade mönstret (exponeringstiming) är också välkomna, men jag vill se minst några som går utanför det.
