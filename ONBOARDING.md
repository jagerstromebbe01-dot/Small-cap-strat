# Onboarding — hur du använder labbet

Den här filen är skriven för dig som CEO, inte som teknisk dokumentation.
Ingen bakgrundskunskap antas — läs den när du kommer tillbaka till
projektet efter ett uppehåll och behöver komma ihåg hur allt hänger ihop.

---

## 1. Hur en vanlig session ser ut

När du sätter dig för att jobba med labbet, i den här ordningen:

1. **Starta dashboarden** (se avsnitt 4) och öppna den i webbläsaren.
   Det är din snabbaste överblick — inga filer att leta i.
2. **Kolla K-räknaren och statusfördelningen** överst på sidan — hur
   många hypoteser är pre-registered/passed/failed just nu.
3. **Kolla kandidatidéer**-sektionen — om Hypothesis Miner har lagt till
   något sedan sist.
4. **Kolla hypotesregistret**-sektionen — om något är klart för dig att
   agera på (se avsnitt 3 för vad som är ditt jobb kontra systemets).
5. Om du har en ny idé du vill testa: följ checklistan i avsnitt 5.

Du behöver aldrig öppna en YAML-fil för att bara kolla status — dashboarden
räcker för det. Du öppnar filerna direkt bara när du ska **skriva** något
(låsa ett kriterium), inte för att läsa.

---

## 2. Var du hittar saker

| Vad | Var | Hur du tittar |
|---|---|---|
| Kandidatidéer (icke-bindande förslag) | `research/candidate_ideas.md` | Dashboarden, sektionen "Kandidatidéer" |
| Hypotesregistret (alla hypoteser, status, kriterier) | `research/hypothesis_registry/HYP-*.yaml`, en fil per hypotes | Dashboarden, sektionen "Hypotesregister" |
| K-räknaren (totalt antal testade varianter) | `research/hypothesis_registry/_counter.yaml` | Dashboarden, siffran längst upp till vänster |
| Resultat från en körd backtest | `strategies/HYP-XXX/results/` (t.ex. `report.md` för en läsbar sammanfattning) | Öppna filen direkt, eller be mig sammanfatta den |
| Dashboarden själv (när den körs) | `http://127.0.0.1:5151` i webbläsaren | — |

---

## 3. Vad DU gör manuellt kontra vad systemet gör själv

**Du (och bara du) gör alltid manuellt, i chatt med Claude:**
- Skriver och låser `pass_fail_criterion` för en ny hypotes — INGEN
  agent får någonsin göra detta åt dig, det är medvetet.
- Bestämmer om en kandidatidé från Hypothesis Miner ska bli en riktig,
  registrerad hypotes.
- Klickar **"Sätt pre-registered"**-knappen i dashboarden — men bara
  EFTER att kriteriet redan är skrivet i YAML-filen. Knappen är
  bara en mekanisk sista-steget-flytt, inte ett sätt att skriva
  kriteriet. Om knappen inte syns för en hypotes betyder det att
  kriteriet inte är ifyllt än (den döljs medvetet, inte bara gråad).
- Bedömer resultat och avgör pass/fail-tolkning tillsammans med Claude
  — systemet räknar ut talen (Sharpe, DSR osv.), men den slutgiltiga
  bedömningen och nästa steg är alltid ett samtal med dig.

**Systemet (agenterna) gör själva, en gång du satt igång dem:**
- Hämtar prisdata, bygger universum, kör backtester.
- Räknar ut Sharpe/Calmar/Deflated Sharpe Ratio.
- Skriver resultat till registret och till resultatfiler.
- Kontrollerar mekaniskt (kod, inte löfte) att en backtest inte kan köras
  utan ett låst kriterium, och att friktion faktiskt används i koden om
  kriteriet kräver det.

---

## 4. Så startar du dashboarden

Kör i terminalen, från projektmappen:

```bash
python dashboard/server.py
```

Öppna sedan `http://127.0.0.1:5151` i webbläsaren. Den uppdaterar sig
själv var 5:e sekund så länge sidan är öppen — du behöver inte ladda om
manuellt.

---

## 5. Checklista: ge en ny hypotes till systemet, från grunden

1. **Idé finns** — antingen från dig direkt, eller en post i
   "Kandidatidéer" du vill gå vidare med.
2. **Diskutera med Claude i chatt** vad exakt hypotesen ska testas mot:
   vilket universum, vilken tidsperiod, vilka trösklar (Sharpe/Calmar)
   som räknas som godkänt.
3. **Lås `pass_fail_criterion` tillsammans med Claude** — detta skrivs in
   i en ny fil `research/hypothesis_registry/HYP-XXX-kort-namn.yaml`,
   med `status: pre-registered` men kriteriet TOMT till en början om du
   vill separera "registrera" från "lås kriteriet" i två steg (som med
   HYP-008).
4. Om det är en small-cap-hypotes: se till att
   `tested_capital_levels` (minst $100k/$1M/$10M) är ifyllt — det är
   obligatoriskt, inte valfritt.
5. Om kriteriet nämner friktion (borrow-kostnad, spread): notera det
   tydligt i kriterietexten — systemet kontrollerar sedan mekaniskt att
   backtest-koden faktiskt använder friktionsfunktionerna, inte bara att
   texten nämner dem.
6. **Klicka "Sätt pre-registered" i dashboarden** när kriteriet är
   skrivet (om det inte redan sattes direkt i steg 3).
7. Be Claude implementera och köra backtesten. Systemet vägrar mekaniskt
   köra något förrän steg 3–6 är klara — du behöver inte komma ihåg att
   kontrollera det själv.
8. **Granska rådata tillsammans med Claude** innan ni går vidare till
   Deflated Sharpe Ratio-tolkning och slutlig pass/fail-bedömning.

---

## 6. Ordlista

- **K-räknare** — hur många olika varianter/hypoteser som testats totalt,
  någonsin (inklusive de 7 döda "ejay"-varianterna från innan detta
  system byggdes). Varje NY testad hypotes höjer talet med 1. Ju högre K,
  desto starkare resultat krävs för att lita på att något är på riktigt
  och inte bara tur.
- **DSR (Deflated Sharpe Ratio)** — ett sannolikhetstal (0–1) för "är det
  här resultatet troligen genuint bra, GIVET hur många andra varianter vi
  redan testat (K)?" Ett högt rått Sharpe-tal betyder mindre om K är
  stort — DSR är den ärliga, K-justerade versionen.
- **Pre-registrering** — regeln att ett kriterium för vad som räknas som
  "lyckat" måste skrivas ner INNAN ett test körs, och aldrig får ändras
  efteråt. Finns för att man annars lätt lurar sig själv i efterhand.
- **Capital levels (kapitalnivåer)** — samma strategi testas vid flera
  olika kapitalstorlekar ($100k/$1M/$10M) eftersom hela idén med
  small-cap-hypotesen är att stora pengasummor kanske inte får plats i
  små bolags aktier utan att själva flytta priset. Om resultatet är
  sämre vid $10M än vid $100k är det ett tecken på just detta.
- **Friktion** — kostnader för att faktiskt handla (courtage-liknande
  spread mellan köp-/säljkurs, och kostnad för att låna aktier vid en
  kort position) som måste räknas in i en backtest, annars ser
  strategin bättre ut än den skulle vara i verkligheten.
- **Status (i hypotesregistret)** — var i livscykeln en hypotes befinner
  sig: `pre-registered` (registrerad, väntar på eller under test) →
  `passed`/`failed` (testad, klart resultat).
