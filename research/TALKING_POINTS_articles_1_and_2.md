# Vad jag behöver kunna utantill — artikel 1 & 2

Enkel regel för båda: om du är osäker på en detaljfråga, svara "det är
proprietärt / kommer i en senare artikel" snarare än att gissa.

---

## Artikel 1 — Leverage decay (hävstångs-utspädning)

**En mening:** Dubbel hävstång ger inte dubbel avkastning, för
volatiliteten dubblas också — och volatilitet äter av den sammansatta
avkastningen över tid. Samma anledning till att hävstångs-ETF:er tappar
värde i en sidledes marknad även om index står still.

**Varför den enkla (naiva) metoden är fel:** Många nöjer sig med att
multiplicera CAGR och MaxDD med hävstångsfaktorn L. Det stämmer bara för
den *enkla* avkastningen. Den *sammansatta* (som är den som faktiskt
spelar roll) straffas av varians, och det straffet växer med **L i
kvadrat** — snabbare än själva vinsten, som bara växer med L. Det är
därför gapet mellan "naiv gissning" och "verklighet" blir större ju mer
hävstång du lägger på, inte konstant.

**Metoden vi använde:** Vi simulerade den faktiska dagliga avkastningen
dag för dag, med en verklig lånekostnad på den lånade delen, och lät
det sammansättas naturligt. Vi skalade INTE om redan färdigräknade
sammanfattningsmått i efterhand — det är exakt det felet artikeln
handlar om.

**Siffrorna (kan du utantill):**
- Baslinje (ingen hävstång): Sharpe 1,16 · CAGR 8,6% · MaxDD -7,3%
- 2,0x hävstång: naiv gissning säger CAGR +17,2% — verkligheten
  (försiktig lånekostnad) är +13,5%. **Gap: 3,7 procentenheter.**
- 2,0x hävstång med stressad (dyrare) finansiering: Sharpe faller till
  0,89 — under 1,0, alltså sämre riskjusterat än att inte hävstångsjustera alls.

**Om någon frågar "är detta nytt/originellt":** Nej, mekanismen
(volatility drag / Jensens olikhet) är väletablerad kvantteori. Poängen
med artikeln är att visa den konkret med verkliga siffror och rätt
metod, inte att göra anspråk på ny forskning.

**Vad du INTE avslöjar:** exakt vilken strategi siffrorna kommer från —
bara att det är "en systematisk multi-strategi aktieportfölj." Om någon
pressar: "sammansättningen är proprietär, poängen här är metodologisk."

---

## Artikel 2 — 57 tester, 8 överlevare (multipeltestnings-disciplin)

**En mening:** Om man testar tillräckligt många strategier kommer några
att se bra ut av ren slump — vi räknar varje test vi kör (K=57 hittills)
och kräver att kriteriet för godkänt/underkänt är nedskrivet och låst
INNAN vi ser resultatet, så att ingen (inklusive oss själva) kan flytta
målstolparna i efterhand.

**Varför det behövs:** Testar man 57 strategier mot en naiv gräns
(p<0,05) förväntas ~2-3 se "signifikanta" ut av ren slump — även om
INGEN av dem har verklig edge. Visar man bara vinnaren går det inte att
skilja på skicklighet och tur. Samma sjukdom som p-hacking inom
vetenskap, bara i en annan bransch.

**Verktyget som håller oss ärliga:** Deflated Sharpe Ratio (Bailey &
López de Prado) — höjer automatiskt ribban en strategis Sharpe måste
klara ju fler strategier man redan testat. Måste räknas om för ALLA
kandidater som fortfarande är under övervägande varje gång ett nytt
test läggs till, inte bara det senaste.

**Siffrorna (kan du utantill):**
- K (totalt räknade tester) = 57
- Formellt pre-registrerade med egen låst fil = 51
- Klarade sin låsta gräns = 8 (~16%)

**Reglerna vi faktiskt följer (inte bara påstår):**
1. Kriteriet låses INNAN backtest körs — kan aldrig ändras efteråt.
2. Varje testad variant räknas, även floppar — ingen "glömmer bort" en
   misslyckad idé.
3. Friktion (courtage, lånekostnad, likviditet) finns med från början,
   läggs aldrig på i efterhand efter ett bra resultat.
4. Att kombinera flera misslyckade idéer för att konstruera en "vinst"
   är förbjudet — en kombination räknas som en helt egen ny hypotes med
   eget K-bidrag, aldrig en genväg runt individuella floppar.
5. När flera kandidater tas fram i en batch (t.ex. AI-genererade):
   alla dras blint i en enda omgång, inga resultat ses mellan utkasten,
   och ALLA resultat (vinnare och förlorare) rapporteras tillsammans —
   att bara plocka ut vinnaren och tyst släppa resten räknas som samma
   överträdelse som att inte räkna K alls.

**Om någon frågar "varför är bara 16% godkända, är resten slöseri":**
Nej — en ~16%-siffra under en gräns som blir tuffare ju fler tester man
kör är ungefär vad man förväntar sig av en process som faktiskt filtrerar
på riktigt. 100% godkänt skulle betyda att gränsen inte är verklig; 0%
skulle betyda att det inte finns någon edge att hitta alls.

**Vad du INTE avslöjar:** vilka 8 hypoteser som klarade sig eller vad de
gör — bara det aggregerade antalet och andelen. Sammansättningen av den
faktiska strategin (artikel 3) är och förblir hemlig.

---

## Gemensamt för båda

- Du får använda AI för att skriva/strukturera texten, men du måste
  förstå och kunna försvara varje siffra själv.
- Om du är osäker på en fråga: hellre "det tar jag reda på" eller
  "proprietärt" än att gissa fel offentligt.
- Inget av detta avslöjar den faktiska handlade strategin — det är
  metodik och process, inte alfa.
