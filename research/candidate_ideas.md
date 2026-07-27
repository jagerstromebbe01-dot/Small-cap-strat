# Candidate Ideas

Icke-bindande förslag från Hypothesis Miner. En post här är INTE en
pre-registrerad hypotes och har INGEN status i multipel-testnings-räkningen
(K). Den blir bara en riktig hypotes om CEO manuellt lyfter in den i
`/research/hypothesis_registry/` med ett låst `pass_fail_criterion`.

Mall per post:

```
## [Datum, ÅÅÅÅ-MM-DD]

**Källa:** [paper/text/teori, med länk eller referens om möjligt]

**Kort beskrivning:** [vad idén går ut på, 2-4 meningar]

**Varför relevant:** [koppling till detta projekts hypoteser, t.ex.
kapacitetsbegränsning i small-cap, eller en annan mekanism]
```

---

## [Datum, 2026-07-27]

**Källa:** Do, B., & Faff, R. (2010). "Does Simple Pairs Trading Still
Work?" Financial Analysts Journal, 66(4), 47-62.

**Kort beskrivning:** Studerar lönsamheten av enkel, distansbaserad
parhandel (samma familj av strategi som v6-kärnan) över en längre
tidsperiod och finner att den genomsnittliga överavkastningen minskat
över tid i takt med att fler aktörer replikerat metoden, samtidigt som
lönsamheten som återstår tenderar att koncentreras till perioder och
segment med hög volatilitet och sämre likviditet - inte jämnt
utspridd över hela marknaden.

**Varför relevant:** HYP-008 (v6-kärnan replikerad på small-cap)
misslyckades nyligen (FAILED, 2026-07-27) med negativ Sharpe på alla
kapitalnivåer. Do & Faffs fynd - att kvarvarande parhandels-edge
koncentreras till volatila/illikvida segment snarare än att small-cap
generellt skulle vara ett sådant segment - ger en möjlig förklaring:
kapacitetsbegränsning (stora fonder får inte plats) och "svårhandlat
segment" (hög volatilitet/låg likviditet) är inte nödvändigtvis samma
sak. Om en framtida hypotes vill undersöka parhandel igen, kan den
behöva rikta in sig på volatilitet/likviditet specifikt snarare än
enbart börsvärde som urvalskriterium.
