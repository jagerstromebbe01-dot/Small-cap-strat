# Granskningsbrief för extern AI-granskning

**Underlag:** `research/RESEARCH_REPORT_2026-08-09.md` (läs den först). Repo-access till hela projektet rekommenderas starkt framför att bara läsa rapporttexten isolerat.

## Din roll

Du granskar inte en pitch — du granskar en disciplin. Utgå från att varje positivt resultat kan vara ett falskt positiv tills du själv verifierat det mot faktisk kod/data i repot, inte mot rapportens egen sammanfattning av sig själv. Var adversariell: leta aktivt efter ställen där disciplinen (pre-registrering, K-räkning, Deflated Sharpe Ratio, friktionsmodellering) har brutits, urvattnats eller kringgåtts — även om slutresultatet "råkar" hålla ändå. Ett resultat som håller trots ett brutet protokoll är fortfarande ett problem, inte en ursäkt.

## Tillgång

Läs `CLAUDE.md` i repo-roten först (bindande kontraktdokumentation). Sedan: `research/hypothesis_registry/*.yaml` (alla, inte bara de i rapportens tabeller), `research/hypothesis_registry/_counter.yaml`, `strategies/*/backtest.py`, `strategies/common/data_hygiene.py`, `scripts/deflated_sharpe_ratio.py`, och git-historiken (särskilt 2026-08-08 och 2026-08-09).

## Vad som redan är känt och fixat (verifiera att det faktiskt stämmer, ta inte för givet)

Rapporten beskriver två redan genomförda granskningsrundor (2026-08-08 mot registret, 2026-08-09 mot rapporttexten själv), båda med tre blinda oberoende granskare. Bekräfta att de fynd och fixar som beskrivs i rapportens del 3 verkligen finns i git-historiken och i registret som beskrivet — inte bara att rapporten säger det.

## Särskilt att jaga (utöver egna fynd)

- Håller K-räkningen (46) och DSR-beräkningarna ihop, rad för rad, mot registret?
- Är `status: failed` för HYP-037/HYP-043 (satt 2026-08-09) korrekt konsekvent tillämpad — påverkar den några senare hypotesers egna resonemang som borde uppdateras men inte gjorts?
- Håller mönstret "exponeringstiming 4/5 vs urval/viktning 0/9" (del 1.3) vid närmare granskning, eller är kategoriseringen fortfarande diskutabel?
- Finns fler outnyttjade/ofixade luckor av samma typ som de två granskningsrundorna redan hittat (dvs. samma sorts sökning, inte bara samma resultat)?
- Är HYP-047:s status som referensimplementation fortfarande korrekt given ALLT ovanstående, eller finns ett skäl att ifrågasätta den som de två tidigare rundorna missade?

## Leverans

En rangordnad lista av fynd, allvarligast först. För varje fynd: vad som är fel/svagt, hur du verifierade det (fil/rad om möjligt), och hur allvarligt det är för trovärdigheten i HYP-047 som referensimplementation. Inga "sammanfattningsvis ser detta bra ut"-slutsatser utan att varje punkt ovan explicit är avprickad eller flaggad.
