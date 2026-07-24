# Mini Hedge Fund – Build Spec v1
*Skapad för att ges till nästa Claude Code-session. Detta dokument är kontraktet — bygg mot det, avvik inte utan att uppdatera det.*

---

## 1. Kontext (så nästa session inte behöver historiken)

- Grundstrategin **v6** (beta-neutral OLS-parhandel, statistisk arbitrage) är validerad på large-cap (2010–2024, yfinance) och robust över flera oberoende test: Sharpe ~0.55, CAGR ~4.8%, MaxDD ~-8.6%, win rate ~59.5%.
- **"Ejay"** (ett internt signalkvalitetsmått, till slut visat matematiskt ekvivalent med Kelly-kriteriet) testades i **7 oberoende varianter** över flera dagar — samtliga dödförklarade genom rigorösa, förutbestämda test (cirkularitet, ingen förbättring efter kontroll för z-score-styrka, ingen förbättring vid filtrering, för hög korrelation mellan viktade/oviktade varianter). Ejay är stängt. Bygg inte vidare på det utan explicit nytt beslut.
- **Ny hypotes:** small-cap-aktier kan ha kvarvarande, exploaterbar edge — inte pga informationsasymmetri, utan pga att stora institutioner har kapacitetsbegränsningar (kan/vill inte handla positioner för små för sitt kapital). Det är en annan typ av marknadslucka än det som redan testats och dödförklarats i large-cap.
- **Kritisk lärdom från ejay-processen:** blind hypotesjakt (testa idé efter idé utan att räkna med multipel-testning) ger falska positiver. Detta system ska **strukturellt förhindra** att det upprepas, inte bara lita på god vilja.

---

## 2. Icke förhandlingsbara principer

1. **Pre-registrering före test.** Ingen backtest får köras förrän en hypotes är loggad med låst pass/fail-kriterium. Kriteriet får inte ändras efter att resultatet setts.
2. **Multipel-testning räknas explicit.** Varje ny testad hypotes ökar K (totalt antal testade varianter). Deflated Sharpe Ratio / False Strategy Theorem (Bailey & López de Prado) ska beräknas mot löpande K, inte bara mot den enskilda backtestens Sharpe.
3. **Friktion in från start.** För small-cap: kort-tillgänglighet, borrow-kostnad, bid-ask-spread ska vara en del av backtest-motorn från dag ett — inte läggas till efteråt "om resultatet ser bra ut."
4. **Risk är oberoende, inte underställd.** Risk-grenen rapporterar inte till samma linje som strategiutveckling. Den ska kunna blockera en hypotes från att gå vidare, inte bara kommentera i efterhand.
5. **Roller är strikt avgränsade.** Varje agent jobbar bara inom sin definierade roll. En agent som "råkar" göra en annan agents jobb är ett designfel, inte flexibilitet.

---

## 3. Vad "agenter" betyder här

Agenter är **inte** interaktiva Claude Code-chattroller du växlar mellan manuellt. De är:

- Fristående, **schemalagda eller manuellt triggade** körningar av Claude Code i headless-läge (`claude code -p "<rollprompt>"` eller motsvarande), var och en med:
  - En egen, versionerad rollprompt (fil i repot, t.ex. `/agents/data_engineer/ROLE.md`)
  - Begränsad filåtkomst till bara de mappar rollen behöver
  - Ett definierat output-kontrakt (vad den får skriva, vart, i vilket format)
- Delat tillstånd = **git-repot självt.** Alla agenter läser/skriver till samma repo. Git-historik = granskningsspår (audit trail) — ingen kan tyst ändra ett kriterium efter att ha sett resultatet, för det syns i commit-loggen.
- Scheduling: cron (Linux/macOS) eller motsvarande, körs enligt ett schema du sätter per agent, eller manuellt via `git commit`-triggad körning.

**OBS till nästa session:** definiera i din faktiska miljö (OS, om cron finns tillgängligt) hur schemaläggning konkret sätts upp — det är inte specificerat här och behöver bestämmas i implementationen, inte antas.

---

## 4. Overfitting- / pre-registreringssystemet (löser multipel-testnings-problemet)

**Lagring:** enkla, strukturerade filer i repot (YAML eller Markdown med frontmatter), git-trackade. Ingen databas i v1 — git ger versionering och en omöjlig-att-fuska-med tidsstämplad historik gratis, vilket räcker för en solo-operation. Om volymen av hypoteser blir för stor för filer senare, migrera då till SQLite — inte i förväg.

**Plats:** `/research/hypothesis_registry/`, en fil per hypotes: `HYP-{nummer}-{kort-namn}.yaml`

**Obligatoriska fält per hypotes:**
```yaml
id: HYP-008
date_registered: 2026-07-24
title: "v6-kärna replikerad på small-cap-universum"
universe: "small-cap, $100M - $2B börsvärde, EODHD All-World som datakälla"
data_range: "EODHD All-World, så lång historik som täckningen tillåter (mål 2010-2024)"
pass_fail_criterion: >
  Måste låsas HÄR, INNAN backtest körs. Exempel:
  "Sharpe > 0.5 OCH Calmar > 0.5 OCH ingen försämring i MaxDD
  jämfört med large-cap-basen, EFTER att borrow-kostnad och
  bid-ask-spread är inkluderade i simuleringen."
status: pre-registered   # pre-registered -> tested -> passed/failed
k_total_hypotheses_before_this: 7   # löpande räknare, inkl. alla döda ejay-varianter
tested_capital_levels: [100000, 1000000, 10000000]
  # OBLIGATORISKT för alla small-cap-hypoteser. Edgen antas vara
  # kapacitetsbegränsad (hela hypotesens premiss är att stora fonder
  # INTE kan handla small-cap-positioner). En backtest på en enda
  # kapitalnivå kan därför antingen dölja en edge som fungerar fint
  # på verklig handelsstorlek (~$100k), eller ge falskt förtroende
  # för en edge som bara existerar i den simulerade storleken. Kör
  # samma strategi på flera kapitalnivåer och notera VAR (om alls)
  # prestandan degraderar - det är samtidigt ett direkt test av
  # kapacitets-hypotesen i sig.
capital_level_results: {}
  # fylls i per nivå efter test, t.ex.
  # {100000: {sharpe: ..., calmar: ...}, 1000000: {...}, 10000000: {...}}
date_tested: null
result_summary: null
sharpe_raw: null
deflated_sharpe_ratio: null   # beräknad mot k_total ovan, inte bara denna hypotes
notes: ""
```

**Regel för Backtester-agenten:** vägra köra en backtest om motsvarande `.yaml`-fil inte existerar med status `pre-registered` och ett ifyllt `pass_fail_criterion`. Detta är en hård spärr, inte en rekommendation.

**Regel för Overfitting Detector-agenten:** efter varje testad hypotes, uppdatera `k_total`-räknaren globalt (en `/research/hypothesis_registry/_counter.yaml`) och räkna om Deflated Sharpe Ratio för samtliga hypoteser som fortfarande är under övervägande, inte bara den senaste.

**ENFORCEMENT ÄR KOD, INTE BARA ROLLPROMPT-INSTRUKTION.** Eftersom det inte finns någon annan människa än dig (CEO) som granskar agenternas arbete löpande, kan reglerna ovan INTE vila enbart på att en agent "kommer ihåg" sin instruktion. Bygg en faktisk valideringsspärr:

- Ett litet skript, t.ex. `/scripts/validate_hypothesis.py`, som Backtester-agenten MÅSTE köra (eller som triggas via en git pre-commit-hook) innan någon backtest-kod exekveras.
- Skriptet kontrollerar programmatiskt: (1) finns en `.yaml`-fil för hypotesen, (2) är `status: pre-registered`, (3) är `pass_fail_criterion` ifyllt (icke-tomt), (4) är `tested_capital_levels` ifyllt för small-cap-hypoteser.
- Om något av detta saknas: skriptet avbryter körningen med ett tydligt felmeddelande, och skriver INGET till registret.
- Detta gör disciplinen mekaniskt omöjlig att kringgå av misstag — den är inte beroende av att en agent "läser sin rollprompt noga" i varje enskild körning.

---

## 5. V1-omfattning — bygg BARA detta nu

**Aktiva grenar/agenter i v1:**

- **CTO**
  - *Data Engineer* — bygger dataabstraktion: yfinance nu (fallback/utveckling), **EODHD All-World som vald datakälla för small-cap** (CEO-beslut 2026-07-24, se avsnitt 6 punkt 1 — WRDS/CRSP är inte längre den aktiva planen för small-cap-data, men kan återkomma separat för fundamentaldata om det behövs senare). Måste inkludera fält för borrow-kostnad/tillgänglighet och bid-ask-spread från start (kan vara platshållarvärden tills riktig data finns, men schemat ska finnas).
  - *Strategy Builder* — **begränsad i v1 till att replikera v6-metodiken** (beta-neutral OLS-par, samma kärnlogik som redan validerad) på det nya universumet. Genererar INTE nya alfa-idéer i v1.
  - *Infrastructure Engineer* — repo-struktur, miljösetup, agent-scheduling.
- **Hypothesis Miner** (fristående gren, aktiverad genom explicit CEO-beslut 2026-07-24 — se ändringslogg nedan)
  - Läser papers/teorier om marknadsanomalier och skriver icke-bindande kandidatidéer till `/research/candidate_ideas.md`.
  - **HÅRDA REGLER:** rör ALDRIG `/research/hypothesis_registry/`; sätter ALDRIG `status`; skriver ALDRIG ett `pass_fail_criterion` (varken helt, delvis, eller som förslag formulerat som låst text) — det är och förblir CEO:s exklusiva område. Ökar ALDRIG `k_total`. En kandidatidé blir bara en riktig, K-räknad hypotes om CEO manuellt lyfter in den i registret med ett låst kriterium.
  - Fullständig rollprompt: `/agents/hypothesis_miner/ROLE.md`.
- **Risk**
  - *Backtester* — kör bara pre-registrerade hypoteser (se regel ovan).
  - *Overfitting Detector* — äger `/research/hypothesis_registry/`, blockerar otestade/olåsta hypoteser, beräknar Deflated Sharpe Ratio.
  - *Performance Analyst* — Sharpe/Calmar/MaxDD/win rate-rapportering per testad hypotes.
  - *Risk Manager* — friktionsmodellering (borrow, spread), portföljnivå-risk när fler än en strategi är aktiv.
- **Operations**
  - *Git Manager* — commit-disciplin, säkerställer att registret aldrig skrivs över utan historik.
  - *Documentation* — håller detta dokument och rollpromptar uppdaterade.
  - *Reporting* — sammanfattar status åt dig (CEO), t.ex. veckovis.
- **Orchestrator** — koordinerar ovanstående, genererar INTE själv nya hypoteser i v1.

**INTE i v1 (medvetet uteslutet, lägg inte till utan explicit beslut):**
- Hela CIO-grenen (Paper Agent, Market Structure Agent, News Agent, Small Cap Research Agent)
- ML Engineer

**Tidigare uteslutet, nu aktiverat:** "Hypothesis Miner" var ursprungligen medvetet uppskjuten av samma skäl som ovan (risk att återskapa det blinda-sökning-problemet som gav 7 dödförklarade Ejay-varianter). CEO hävde undantaget explicit 2026-07-24, under förutsättning att rollen hålls strikt icke-bindande (se de hårda reglerna under CTO/Hypothesis Miner ovan) — den genererar bara förslag, den kan aldrig själv registrera, låsa eller godkänna en hypotes.

---

## 5b. Varning: kombination av icke-signifikanta strategier är INTE en genväg runt multipel-testning

Om ett antal hypoteser (t.ex. 10 av 200 testade) inte klarar sin förutbestämda Deflated Sharpe Ratio-tröskel var för sig, är det FÖRVÄNTAT att ett visst antal ändå ser lovande ut av ren slump — vid K=200 test och p<0.05 väntas ~10 falska positiver även om INGET av det som testats är genuint. Att sedan kombinera de "bästa" av dessa i en portfölj, i hopp om att de tillsammans blir signifikanta, är strukturellt samma manöver som att fortsätta testa tills något ser bra ut — bara draperat som portföljteori. Detta är FÖRBJUDET som genväg.

**Regel:** en kombination av flera enskilda hypoteser räknas som en NY, egen pre-registrerad hypotes (eget K-bidrag till räknaren), inte ett sätt att rädda hypoteser som redan underkänts individuellt.

**Legitim process om kombination ändå ska undersökas:**
1. Beräkna korrelationsmatrisen mellan kandidaternas avkastningsserier (inte deras Sharpe var för sig). Låg/negativ korrelation är förutsättningen för att kombination ska kunna ge en diversifieringsvinst (grovt: kombinerad Sharpe växer ~√N för N okorrelerade, likvärdiga strategier).
2. Börja med NAIV, likaviktad kombination — inte in-sample-optimerade vikter (klassisk Markowitz-optimering överanpassar lätt kraftigt och lägger ytterligare ett lager brus ovanpå det som redan finns).
3. Testa den kombinerade portföljen OUT-OF-SAMPLE, på data ingen av de enskilda kandidaterna sågs mot vid urval.
4. Varje distinkt kombinationsmetod som testas (likaviktat, riskparitet, delmängder) räknas som ytterligare ett K-test i multipel-testnings-räkningen — kombinationssökandet är i sig ett sökutrymme som kan generera falska positiver.

**Innan kombination ens övervägs:** kontrollera om kandidaterna har en begriplig, oberoende motiverad mekanism var för sig (olika typer av edge, t.ex. kapacitetsbegränsning vs rapporteringsfördröjning) snarare än att bara vara de N bästa siffrorna av ett stort antal körningar. Om de senare — sannolikt bäst att lägga hela batchen åt sidan snarare än att leta efter ett sätt att rädda den genom kombination.

---

## 6. Öppna beroenden (måste lösas innan v1 kan köra på riktig data)

1. **WRDS/Compustat/CRSP-åtkomst** — ~~pending~~ **superseded 2026-07-24:** CEO har valt EODHD All-World som datakälla för small-cap-arbetet i HYP-008, istället för att vänta på WRDS-åtkomst. WRDS kvarstår som en möjlig framtida källa (t.ex. för fundamentaldata) men är inte längre en blockerande förutsättning för att köra small-cap-backtester.
2. **Lokal miljö för scheduling** — OS och tillgänglig schemaläggningsmekanism (cron etc.) är inte specificerat här, måste sättas upp konkret i nästa session.
3. **Definition av "small-cap"** — ~~inte låst än~~ **LÅST 2026-07-24:** $100M–$2B börsvärde, EODHD All-World som datakälla. Se `pass_fail_criterion` och `small_cap_definition` i `/research/hypothesis_registry/HYP-008-v6-smallcap-replication.yaml` för den ordagranna, låsta texten (registerfilen är källan till sanning — duplicera den inte här för att undvika att de glider isär).

---

## 7. Första konkreta uppgiften för nästa session

1. Bygg repo-struktur enligt ovan (`/agents/`, `/research/hypothesis_registry/`, `/data/`).
2. Skriv rollpromptar för v1-agenterna (Data Engineer, Strategy Builder, Backtester, Overfitting Detector, Performance Analyst, Risk Manager, Git Manager, Documentation, Reporting, Orchestrator).
3. Data Engineer: bygg dataabstraktionslagret (yfinance-adapter nu, WRDS-adapter som stub/interface redo att fyllas i).
4. Overfitting Detector: skapa `_counter.yaml` med `k_total = 7` (de dödförklarade ejay-varianterna) som startpunkt.
5. Skapa `HYP-008` som en pre-registrerad, olåst hypotes: "v6-kärna replikerad på small-cap" — med `pass_fail_criterion` ifylld INNAN någon kod som rör faktisk small-cap-data skrivs. Låt fältet för exakt small-cap-definition och friktionsantaganden vara explicit del av det låsta kriteriet, inte tillägg i efterhand.
6. Vänta med att köra HYP-008 tills WRDS-åtkomst (eller ett medvetet beslut att köra en interimsversion på en gratis small-cap-proxy) är klart.

---

*Detta dokument ska uppdateras av Documentation-agenten när strukturen ändras. Om en ny gren/agent läggs till, lägg till den här explicit — bygg inte tyst utanför detta kontrakt.*

---

## Ändringslogg

- **2026-07-24 (CEO-beslut):** Hypothesis Miner-undantaget hävt — rollen är nu aktiv i v1, strikt begränsad till icke-bindande förslag (se avsnitt 5). `pass_fail_criterion` och `small_cap_definition` för HYP-008 låsta (se avsnitt 4 och 6, punkt 3). EODHD All-World valt som datakälla för small-cap, vilket gör WRDS-beroendet (avsnitt 6, punkt 1) inte längre blockerande.
- Ej ännu tillagt i detta dokument, kvarstår som öppen post: uppdelningen av Strategy Builder-rollen i separat spec-skrivande (Strategy Builder) och kodimplementerande (ny roll: **Coder**, `/agents/coder/ROLE.md`), samt att `/reference_code/v6_core_large_cap.py` checkats in som återanvändbar referens. Dokumenterat i `CLAUDE.md` men inte ännu synkat hit — flagga för CEO vid nästa uppdatering av detta dokument.
