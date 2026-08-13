# Brainstorm-prompt: nya kandidatidéer för small-cap-forskningsprojektet (uppdaterad 2026-08-11)

Klistra in detta i en ny, oberoende konversation med en extern AI (Gemini, ChatGPT, Grok, eller annan). Kör det i en helt egen konversation, inte i samma tråd som någon tidigare granskning. Kör gärna samma prompt mot flera olika AI:er separat — konvergens mellan oberoende källor har historiskt varit den starkaste urvalssignalen i det här projektet.

---

## Bakgrund

Jag driver ett systematiskt "mini hedge fund"-forskningsprojekt med sträng pre-registrerings- och multipeltestningsdisciplin (varje testad idé ökar en global räknare K, för närvarande **K=67**, och Deflated Sharpe Ratio räknas mot K för att undvika falska positiva från att testa för många varianter). Universum: amerikanska small-cap-aktier, $100M–$2B börsvärde, daglig OHLCV-data (öppen/hög/låg/stäng/justerad stäng/volym), ingen options- eller terminsdata tillgänglig. SEC EDGAR (gratis, strukturerad XBRL-data + fulltext-dokument) är också tillgängligt och redan använt för insiderköp, EPS/vinstöverraskning, lönsamhet, aktieantal och återköp. Kärntesen: stora institutioner är kapacitetsbegränsade i detta segment (kan inte allokera meningsfullt kapital utan att äta upp sin egen edge via marknadspåverkan), vilket kan lämna kvar edge för mindre aktörer — INTE en tes om informationsasymmetri.

**Redan bekräftat FUNGERAR** (upprepat, oberoende mönster genom 67 testade hypoteser): mekanismer som styr NÄR man är exponerad mot marknaden (kraschtriggade exponeringsminskningar, trendföljande overlägg, volatilitetsmålsättning) har lyckats betydligt oftare än mekanismer som styr VAD man äger inom en redan vald grupp aktier (faktorviktning, stop-loss-varianter, likviditetsviktning, Kelly-sizing har nästan alla misslyckats — stop-loss-familjen står nu på 0/6 oberoende försök).

**Redan testat och MISSLYCKATS** (undvik att föreslå raka upprepningar av dessa utan en tydligt ny vinkel):
- Klassisk pariserhandel (v6-strategin replikerad på small-cap)
- Ren cross-sectional momentum long-only (katastrofal drawdown vid reverseringar)
- Kortsiktig reversal (10-dagars) — small-cap-"förlorare" är ofta genuint kollapsande bolag, inte överreagerade
- PEAD/earnings surprise (SUE) som fristående signal och som 4:e ben i en portfölj
- Book-to-market, rörelselönsamhet, insiderköp (SEC Form 4), **återköpsintensitet** ($ återköpt/marknadsvärde — genuin edge i bruttoavkastning men för hög idiosynkratisk risk, varken stop-loss eller volatilitetsmålsättning kunde rädda den, se nedan)
- Kelly-sizing, sektortak, likviditetsviktad allokering, sektorneutral ranking, beta-hedge mot annat index, stale-price-filter, SEX oberoende varianter av per-position-stop-loss (alla FAILADE — fångar genuina blow-ups men kapar lika mycket normal återhämtning)
- Sektorlikviditets-lead-lag (båda riktningarna testade, positiv OCH negativ spridning — båda FAILADE, positiv mindre katastrofalt)
- Nygraduerad small-cap-momentum (ticker växer FRÅN micro-cap in i small-cap-bandet)
- Ett internt signalkvalitetsmått baserat på Kelly-kriteriet ("Ejay") — dog i nio oberoende varianter av cirkularitet. **Föreslå INGET som i grunden är en Kelly-viktad signalstyrka.**
- **Crypto som ny tillgångsklass** (spot-only, BTC/ETH/LTC/XRP/DOGE) — trendfilter, tvärsnittsrotation, volatilitetsmålsättning, drawdown-triggad nedskalning, allt testat, allt FAILADE eller missade rakbladstunt mot en ovanligt stark 2015-2024 buy-and-hold-baseline (flera sekulära bullcykler gjorde ren hold svårslagen)
- Hävstång (med realistisk marginalanrop/tvingad nedskalning-friktion) på de två starkaste portföljerna — ger ett genuint men måttligt lyft (CAGR från ~8,5% till ~11-15% beroende på bas), inte tillräckligt för att nå det uttalade målet på egen hand

**Nuvarande referensimplementation (2026-08-11):** HYP-056 — en volatilitetsmålsättningsoverlay (60-dagars realiserad vol vs 2-års rullande median, skala aldrig över 1.0, golv 0.3) ovanpå en fyrbent basportfölj (köp-och-håll-index + idiosynkratisk-volatilitets-strategi med kraschöverlägg + egenbyggd momentum long/short-svit + trendföljande indexkort-position under 200-dagars glidande medelvärde). Sharpe ~1,19-1,22, MaxDD ~-5,9% till -6,0%, CAGR ~8,3%.

**CEO:s uttalade mål:** CAGR > 15%, gärna > 20%, med Sharpe > 1,0 bibehållet. Det målet är INTE nått ännu — bästa hittills är en hävstångsvariant som når CAGR ~15,2% vid EN av tre kapitalnivåer, med Sharpe strax över 1,0.

## Vad jag vill ha av dig

Det här är en **bred** sökning den här gången — inte bara parametervarianter på det som redan fungerar. Jag vill ha:

1. **Helt nya alfasignaler eller mekanismtyper** vi inte testat än — gärna med koppling till kapacitetsbegränsningstesen ovan, men behöver inte vara det.
2. **Nya sätt att KOMBINERA redan validerade byggstenar** — inte bara likaviktade portföljer av redan kända delar, utan strukturellt annorlunda sätt att kombinera dem.
3. **Idéer lånade från andra tillgångsslag** om du ser en rimlig, motiverad övergångslogik. OBS: crypto som HELT NY tillgångsklass är redan testat brett (se ovan) — men om du har en SPECIFIK mekanism inom crypto vi inte redan provat (t.ex. något som inte är trendfilter/rotation/vol-targeting/drawdown-trigger), eller en annan tillgångsklass helt (råvaror, valuta, managed futures-stilar) är det fortfarande öppet.
4. **Textbaserade signaler från SEC-filings** (10-K/10-Q-sentiment, tonförändringar, läsbarhet) — feasibility-verifierad (fulltext-dokument går att hämta gratis) men aldrig byggd, ett större men fullt genomförbart projekt om någon av er vill utveckla konceptet mer konkret.

**Krav på varje förslag:**
- Måste vara **systematiskt, regelbaserat** — ingen diskretionär bedömning.
- Ange en konkret, om än inte slutgiltig, mekanism (vad mäts, vilken tröskel/riktning, hur ofta ombalanseras det).
- En kort ekonomisk motivering för VARFÖR det skulle finnas edge, inte bara att det "brukar fungera".
- Notera om det är rimligt att bygga med bara daglig OHLCV-data + SEC EDGAR för small-cap-aktier, eller om det kräver data vi sannolikt inte har (optionsdata, terminskurvor, sentimentdata från tredje part) — flagga det öppet, avfärda inte idén bara för det, men var ärlig.
- Förvänta dig INTE att idén ska "vinna" — de flesta testade idéer i detta projekt har misslyckats, och det är förväntat och helt okej. Jag vill ha kvantitet och variation, inte en enda perfekt idé.

**Format:** 5–8 kandidater. För varje: namn, 2–4 meningars mekanismbeskrivning, ekonomisk motivering, hur den skiljer sig från det redan testade ovan, och en kort datakänslighetsnot.

Var gärna djärv. Konventionella idéer inom det redan beprövade mönstret (exponeringstiming) är också välkomna, men jag vill se minst några som går utanför det.
