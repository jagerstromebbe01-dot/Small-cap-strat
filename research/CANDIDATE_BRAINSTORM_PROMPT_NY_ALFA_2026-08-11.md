# Brainstorm-prompt: GENUINT NY ALFA (inte överlägg) — small-cap-forskningsprojektet

Klistra in detta i en ny, oberoende konversation med en extern AI. Kör det i en helt egen konversation, inte i samma tråd som någon tidigare granskning. Kör gärna mot flera AI:er separat — konvergens mellan oberoende källor har historiskt varit den starkaste urvalssignalen i det här projektet.

**VIKTIGT, läs innan du svarar:** en tidigare runda av den här typen av brainstorm gav mest förslag på ANNU ETT exponeringstimings-överlägg ovanpå min befintliga portfölj — tekniskt korrekta svar på frågan jag ställde, men jag insåg efteråt att jag frågade fel fråga. Den här gången vill jag INTE ha fler sätt att skala upp/ner min befintliga portfölj baserat på marknadsregim. Jag vill ha en **helt ny, självständig avkastningskälla** — något som skulle kunna stå som sitt EGET ben i portföljen, med sin egen edge, oberoende av om resten av portföljen är på eller av.

---

## Bakgrund

Jag driver ett systematiskt "mini hedge fund"-forskningsprojekt med sträng pre-registrerings- och multipeltestningsdisciplin (varje testad idé ökar en global räknare K, för närvarande **K=68**, och Deflated Sharpe Ratio räknas mot K). Universum: amerikanska small-cap-aktier, $100M–$2B börsvärde, daglig OHLCV-data. SEC EDGAR (strukturerad XBRL-data + fulltext-dokument) är också tillgängligt och redan använt. Ingen options- eller terminsdata. Kärntesen: stora institutioner är kapacitetsbegränsade i detta segment — INTE en tes om informationsasymmetri.

**Nuvarande referensimplementation:** en fyrbent portfölj (köp-och-håll-index + idiosynkratisk-volatilitets-strategi med kraschöverlägg + egenbyggd momentum long/short-svit + trendföljande indexkort-position under 200-dagars glidande medelvärde), plus en volatilitetsmålsättnings-overlay ovanpå helheten. Sharpe ~1,2, MaxDD ~-6%, CAGR ~8,3%. En hävstångsvariant (med realistisk marginalanrop-friktion) kommer upp mot CAGR ~15% vid en av tre kapitalnivåer, med Sharpe kvar över 1,0 — men det är taket för vad ren hävstång på den befintliga edgen kan ge.

**Det här är exakt vad jag INTE vill ha fler av just nu** (redan väl utforskat, samtliga varianter av "skala om den befintliga portföljen baserat på ett tillstånd/regimmått"):
- Volatilitetsmålsättning, kraschtriggade nedskalningar, trendföljande exponeringsswitchar (redan tre-fyra oberoende PASSADE varianter)
- Regimstyrd ombalansering MELLAN de fyra befintliga benen (testat två gånger, båda FAILADE — HYP-048 och en uppföljning)
- Aggregerade marknadsbreddssignaler som on/off-switch (HY-spread-idé blockerad av datatillgång, nettoemissionsflöde testat, FAILADE nära)
- Hävstång med marginalanrop-friktion (testat på två baser, gav ett begränsat men äkta lyft — taket är nått för den här vägen)

**Redan testat som FRISTÅENDE alfasignal (per-aktie stock-picking) och MISSLYCKATS** — men var snäll och läs varför innan du avfärdar hela kategorin: de flesta av dessa var ganska konventionella, "läroboks"-implementationer av kända faktorer. Jag utesluter INTE stock-picking som kategori, jag vill bara ha något mer kreativt än nästa variant av samma sak:
- Cross-sectional momentum (long-only och long/short), kortsiktig reversal (10 dagar)
- PEAD/earnings surprise (SUE), book-to-market, rörelselönsamhet
- Insiderköp (SEC Form 4, rått), återköpsintensitet ($ återköpt/marknadsvärde — genuint hyfsad bruttoavkastning men för hög idiosynkratisk risk för att kvalificera riskjusterat)
- Sektorlikviditets-lead-lag (båda riktningarna), nygraduerad small-cap-momentum
- Kelly-viktad signalstyrka ("Ejay") — dog i nio oberoende varianter av cirkularitet. **Föreslå INGET Kelly-viktat.**
- Stop-loss-varianter (sex oberoende trösklar, alla FAILADE — det är dock ett riskverktyg, inte en alfakälla, nämns bara för fullständighet)

## Vad jag vill ha av dig DEN HÄR GÅNGEN

**En eller flera helt nya, självständiga avkastningskällor** — signaler eller mekanismer som skulle kunna backtestas och utvärderas HELT PÅ EGEN HAND, oberoende av min befintliga portfölj, och som (om de visar sig ha edge) skulle kunna läggas till som ett FEMTE ben snarare än en modifiering av de fyra befintliga.

Var särskilt kreativ kring:
1. **Mekanismer som genererar avkastning från en ANNAN ekonomisk källa** än de fyra jag redan har (index-drift, idiosynkratisk volatilitetspremie, cross-sectional momentum, marknadstrend). T.ex.: likviditetstillhandahållande, event-driven mispricing, strukturella flöden (inte bara Russell/13F som redan visat sig svåra att få data till — tänk bredare), säsongsmönster, kalendereffekter, marknadsmikrostruktur som en genuin PRISSÄTTNINGSMEKANISM (inte bara en riskfilter).
2. **Signaler från datakällor vi inte fullt utnyttjat än**: SEC-fulltext (vi har bara skrapat ytan — patent, kundkoncentration, ledningsförändringar, revisorsbyten, going-concern-språk), options-implicerad information om den ändå går att komma åt indirekt, alternativa gratis datakällor du känner till.
3. **Idéer från andra tillgångsslag ELLER andra marknader** (internationella small-caps, om det är rimligt datamässigt) med en tydlig, motiverad övergångslogik — inte bara "det fungerar i crypto".
4. Var gärna djärv och strukturellt annorlunda — hellre en idé som kräver mer datajobb men har en genuint ny ekonomisk story, än en säker men urvattnad variant av något redan testat.

**Krav på varje förslag:**
- Systematiskt, regelbaserat — ingen diskretionär bedömning.
- Konkret mekanism: vad mäts, vilken tröskel/riktning, hur ofta ombalanseras det.
- Tydlig ekonomisk motivering för VARFÖR edgen skulle finnas — och specifikt varför den är ORTOGONAL mot mina fyra befintliga ben (inte bara en till variant av trend/momentum/vol).
- Ärlig datakänslighetsnot: byggbart med daglig OHLCV + SEC EDGAR, eller kräver det något vi sannolikt inte har råd med/tillgång till?
- Förvänta dig INTE att idén ska "vinna" — de flesta testade idéer i det här projektet misslyckas, det är förväntat.

**Format:** 5–8 kandidater. För varje: namn, mekanism, ekonomisk motivering (med explicit fokus på VARFÖR den är oberoende av mina befintliga ben), datakänslighetsnot.

Om du efter att ha läst allt ovan ändå landar i att en exponeringstimings-overlay är den bästa idén du har — säg det, men flagga tydligt att det är det, så jag kan välja bort det medvetet istället för att av misstag hamna där igen.
