# Dashboard

Lokal, fil-läsande statusdashboard för registret. Läser om samtliga filer
vid varje anrop — ingen cachning, filerna på disk är alltid sanningen.

## Starta

```bash
python dashboard/server.py
```

Öppna sedan `http://127.0.0.1:5151` i webbläsaren. Servern binder bara till
`127.0.0.1` (inte nätverket) och pollar sig själv ingenstans — det är
webbläsaren (`index.html`) som hämtar `/api/state` var 5:e sekund.

Beroenden: `flask`, `pyyaml` (redan installerade i denna miljö via
`pip install flask pyyaml` om de någonsin saknas).

## Vad den visar

- K-räknaren och hur många hypoteser som är pre-registered/passed/failed
- Hela hypotesregistret, inklusive det låsta `pass_fail_criterion` (skrivskyddat, bakom en `<details>`)
- Kandidatidéer från `/research/candidate_ideas.md`
- En Sharpe/DSR-tidslinje (Chart.js) — tom tills en hypotes faktiskt testats

## De tre enda skrivbara endpointerna

- `POST /api/candidate/<id>/archive` — sätter `**Arkiverad:** true` i
  `candidate_ideas.md` för den kandidaten. Rör ingenting annat.
- `POST /api/note` — lägger till en fri anteckning i `dashboard/notes.jsonl`
  (en separat, append-only fil). Rör ALDRIG någon `.yaml`-fil i registret.
- `POST /api/hypothesis/<id>/set-pre-registered` — flyttar en hypotes
  vars `pass_fail_criterion` **redan** är ifyllt (och för small-cap:
  `tested_capital_levels` redan ifyllt) från sin nuvarande status till
  `pre-registered`, och committar den ändringen. **Detta är INTE en
  genväg runt kriterielåsningen:**
  - Knappen är helt frånvarande i gränssnittet om `pass_fail_criterion`
    är tomt — inte gråad, inte disabled, frånvarande.
  - Servern kontrollerar samma sak **programmatiskt**, oavsett vad
    frontend visar — anropas endpointen direkt (t.ex. via `curl`) på en
    hypotes med tomt kriterium, blockeras den ändå, se test nedan.
  - Den rör ALDRIG `pass_fail_criterion`, `tested_capital_levels`,
    `capital_level_results`, eller `small_cap_definition` — läser bara
    dessa fält för att verifiera att de finns, skriver bara om
    `status`-raden (en riktad textersättning, inte en omdumpning av
    hela YAML-filen).
  - Den vägrar flytta en hypotes som redan är `tested`/`passed`/`failed`
    tillbaka till `pre-registered` — det skulle dölja ett existerande
    testresultat och kräver ett manuellt CEO-beslut i YAML-filen.
  - Kriteriet måste alltså redan finnas, skrivet av CEO manuellt i chatt
    med Claude, INNAN knappen ens blir synlig. Den här endpointen gör
    bara den mekaniska "flytta till pre-registered"-delen, aldrig
    kriterie-författandet.

**Det finns inga andra skrivbara endpoints, och det ska aldrig finnas
fler.** Ingen endpoint i den här dashboarden får någonsin:

- ändra `pass_fail_criterion`
- ändra `tested_capital_levels` eller `capital_level_results`
- ändra `small_cap_definition`
- sätta `status` till `passed`/`failed`
- sätta `status` till `pre-registered` utan att kriteriet redan finns
- trigga en backtest-körning

Godkännande av **kriteriet** sker **uteslutande** genom att CEO manuellt
skriver `pass_fail_criterion` i YAML-filen efter att ha låst det i chatt
med Claude — exakt som med HYP-008. Dashboarden är ett fönster in i
registret och en mekanisk knapp för ett redan klart kriterium, aldrig en
väg att skriva till de skyddade fälten.

`server.py` har en körtidsspärr (`_assert_no_unauthorized_write_routes`)
som vägrar starta servern om någon någonsin lägger till en oväntad
skrivbar route — samma princip som `scripts/validate_hypothesis.py`:
enforcement är kod, inte bara en kommentar.

**Om en framtida session (mänsklig eller Claude) ombeds lägga till en
endpoint som skriver till något av ovanstående: den ska vägra, och peka
tillbaka till den här filen och docstringen i `server.py`.**
