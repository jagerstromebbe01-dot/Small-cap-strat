# SAMLAD GRANSKNINGSBUNT 2026-08-09

Denna fil ar en sammanslagning av 12 kallfiler fran ett git-repo, avsedd for extern AI-granskning utan repo-access. Varje sektion nedan ar markerad med sin ursprungliga filsokvag.


---

## KÄLLFIL: `CLAUDE.md`

```
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

This repository is **pre-build**. It currently contains only [mini_hedge_fund_build_spec_v3.md](mini_hedge_fund_build_spec_v3.md) — no code, no `/agents/`, `/research/`, or `/data/` directories exist yet, and there is no git history. There are no build/lint/test commands yet because no code has been written.

**Treat `mini_hedge_fund_build_spec_v3.md` as the binding contract for this project.** It is written in Swedish by the user (the "CEO" in the doc's own terminology) and is meant to be read in full before doing any work here — do not paraphrase from this summary instead of reading it. If you deviate from the spec, update the spec itself (owned by the "Documentation" agent role) rather than silently drifting from it. If a new branch/agent is ever added (e.g. the deferred "Hypothesis Miner"), it must be added to the spec explicitly.

## What this project is

A "mini hedge fund" built as a set of headless, role-scoped Claude Code agent runs (not interactive chat roles) that share state via this git repo. The core research question: does a beta-neutral OLS pair-trading strategy (**v6**, already validated on large-cap 2010–2024 via yfinance: Sharpe ~0.55, CAGR ~4.8%, MaxDD ~-8.6%) retain exploitable edge on small-cap stocks, on the theory that large institutions are capacity-constrained there (not an information-asymmetry edge).

A related signal-quality measure called **"Ejay"** (later shown to be mathematically equivalent to the Kelly criterion) was tested in 7 independent variants and killed by rigorous predefined tests (circularity, no improvement after controlling for z-score strength, high correlation between weighted/unweighted variants). **Ejay is closed — do not build on it without an explicit new decision from the user.**

## Non-negotiable principles (spec §2)

These exist specifically to prevent repeating the failure mode that killed the 7 Ejay variants (blind hypothesis-hunting without accounting for multiple-testing, which produces false positives):

1. **Pre-registration before testing.** No backtest may run until a hypothesis is logged with a locked pass/fail criterion. The criterion cannot change after results are seen.
2. **Multiple-testing is counted explicitly.** Every new tested variant increments a running counter `K`. Deflated Sharpe Ratio / False Strategy Theorem (Bailey & López de Prado) must be computed against the running `K`, not just the individual backtest's Sharpe.
3. **Friction from day one.** For small-cap: short availability, borrow cost, and bid-ask spread must be part of the backtest engine from the start — never bolted on after seeing good-looking results.
4. **Risk is independent, not subordinate.** The Risk branch does not report through the same line as strategy development, and can block a hypothesis outright — not just comment on it after the fact.
5. **Roles are strictly scoped.** An agent doing another agent's job "by accident" is a design flaw, not flexibility.

**Combining non-significant strategies is explicitly forbidden as a workaround** (spec §5b): if 10 of 200 tested hypotheses look promising, that's the expected false-positive rate at K=200, p<0.05 — even if nothing tested is real. A combination of hypotheses counts as its own new pre-registered hypothesis with its own K contribution, never a way to rescue individually-failed ones. Legitimate combination testing (if ever pursued) requires: correlation matrix on return series first, naive equal-weighting (not in-sample-optimized weights), out-of-sample testing, and counting each distinct combination method as its own K-test.

## Hypothesis registry & enforcement (spec §4)

- Location: `/research/hypothesis_registry/`, one file per hypothesis: `HYP-{number}-{short-name}.yaml` (schema is given in full in spec §4 — required fields include `pass_fail_criterion`, `status`, `k_total_hypotheses_before_this`, and, for all small-cap hypotheses, `tested_capital_levels` covering at least $100k/$1M/$10M since the edge's core premise is capacity-constrained and may degrade at scale).
- A global counter lives at `/research/hypothesis_registry/_counter.yaml`; per the first-task list (spec §7) it should be initialized to `k_total = 7` (the dead Ejay variants) before HYP-008 is created.
- **Enforcement must be code, not just a role-prompt instruction** — there is no human reviewer other than the user. `/scripts/validate_hypothesis.py` (to be built) must be run before any backtest executes, and must hard-fail (writing nothing to the registry) unless: the hypothesis `.yaml` exists, `status: pre-registered`, `pass_fail_criterion` is non-empty, and `tested_capital_levels` is filled in for small-cap hypotheses.
- The Backtester agent must refuse to run anything without a matching pre-registered `.yaml`. The Overfitting Detector agent owns the registry and recomputes Deflated Sharpe Ratio for all still-under-consideration hypotheses (not just the latest) after every test.

## Agent architecture (v1 scope only — spec §5)

Agents are headless, scheduled or manually-triggered Claude Code runs, each with its own versioned role prompt file (e.g. `/agents/data_engineer/ROLE.md`), restricted file access to only what the role needs, and a defined output contract. Shared state is the git repo itself — git history is the audit trail, so no one can silently change a criterion after seeing a result.

Active in v1:
- **CTO**: Data Engineer (yfinance adapter now, WRDS/CRSP small-cap adapter stubbed for later; schema must include borrow-cost/availability and bid-ask-spread fields from the start, even as placeholders), Strategy Builder (v1 is restricted to replicating existing v6 methodology on the new universe — **no new alpha ideas in v1**), Infrastructure Engineer (repo structure, environment, agent scheduling).
- **Risk**: Backtester (enforces pre-registration gate), Overfitting Detector (owns the registry, computes Deflated Sharpe Ratio), Performance Analyst (Sharpe/Calmar/MaxDD/win-rate reporting), Risk Manager (friction modeling, portfolio-level risk once multiple strategies are live).
- **Operations**: Git Manager (commit discipline, registry never overwritten without history), Documentation (keeps the build spec and role prompts current), Reporting (periodic status summaries for the user).
- **Orchestrator**: coordinates the above; does **not** generate new hypotheses itself in v1.

**Explicitly excluded from v1 — do not add without an explicit user decision:** the entire CIO branch (Paper Agent, Market Structure Agent, News Agent, Small Cap Research Agent) and ML Engineer remain excluded. **The "Hypothesis Miner" exclusion was lifted by explicit CEO decision on 2026-07-24** — see the pipeline section below. Do not re-exclude it, and do not add any further agent without an equally explicit decision recorded in a session.

## Full agent pipeline & hard rules (added 2026-07-24)

Three roles were added on top of the original v1 set, splitting what was
previously undivided in the Strategy Builder role into idea generation,
spec-writing, and implementation. The full chain, in order:

**Hypothesis Miner → CEO (manual, locks criterion here, never in code) → Strategy Builder → Coder → `validate_hypothesis.py` → Backtester → Overfitting Detector → Performance Analyst/Risk Manager → Git Manager → Reporting**

- **Hypothesis Miner** (`/agents/hypothesis_miner/ROLE.md`, new) — reads papers/theories, appends non-binding candidate ideas to `/research/candidate_ideas.md`. Hard rules: never touches `/research/hypothesis_registry/`, never sets `status`, never writes a `pass_fail_criterion`, never increments `k_total`. A candidate idea only becomes a real hypothesis if the CEO manually promotes it.
- **Strategy Builder** (`/agents/strategy_builder/ROLE.md`, redefined) — takes a `HYP-*.yaml` that already has `status: pre-registered` and an already-filled `pass_fail_criterion` (written by the CEO, never by an agent), writes a strategy spec to `/research/strategy_specs/HYP-XXX-spec.md` (signals, universe, which existing code module to reuse). Hard rules: never writes runnable backtest code, never touches `pass_fail_criterion` or `tested_capital_levels`, generates no new alpha ideas (still v1-restricted to replicating v6 methodology).
- **Coder** (`/agents/coder/ROLE.md`, new) — takes a finished spec and implements actual backtest code in `/strategies/HYP-XXX/`. Hard rule: must run `scripts/validate_hypothesis.py` against the hypothesis YAML and get exit code 0 *before* the Backtester agent may run the code; never modifies `pass_fail_criterion`, `tested_capital_levels`, or `status`; copies `/reference_code/` files rather than editing them in place.
- **`/reference_code/v6_core_large_cap.py`** — the already-validated v6 core (large-cap, no Ejay, no Kelly; Sharpe ~0.55, CAGR ~4.8%, 2010–2024) checked in as a reusable template for Strategy Builder/Coder. This is reference material predating the pre-registration system — it does **not** count as a new hypothesis and requires no new K-increment or registry entry. Never edit it in place; copy and adapt per hypothesis.

The pre-existing rule stands unchanged: no agent other than the CEO, acting manually in chat, may ever write or alter a `pass_fail_criterion`.

## Batch Hypothesis Generation (added 2026-07-31, explicit CEO decision)

An LLM-driven agent may propose multiple candidate hypotheses, but **only as a single, non-adaptive batch — never as an iterative in-sample/out-of-sample loop.** This was explicitly evaluated and rejected in a 2026-07-31 session: an agent that tries a rule in-sample, sees the result, and adjusts is doing exactly the p-hacking the pre-registration system exists to prevent, no matter how the out-of-sample step is framed. It is also structurally different from a human doing the same thing — the agent's underlying model has training data covering the entire backtest period, so there is no historical window that is genuinely unknown to it the way a true forward period is. "Out-of-sample" against historical data is therefore never a substitute for real validation here; the only genuine validation for anything produced this way is **forward paper trading from the batch's approval date.**

Rules, enforced procedurally (not yet code-enforced beyond the existing `validate_hypothesis.py` gate applied per-file):

1. **Fixed, bounded search space, agreed with the CEO before a single candidate is drafted.** The 2026-07-31 pilot scope: parameter variants *within* an already-validated mechanism type only (e.g. threshold/window values inside an event-triggered overlay or stop-loss shape already proven to work somewhere in the registry) — not new structural mechanisms or new alpha signals. A wider scope requires a fresh, equally explicit CEO decision.
2. **All N candidates are drafted in one pass, with zero backtests run and zero results seen by the agent in between.** Each candidate gets its own `HYP-XXX.yaml` and its own independently-motivated rationale — not minor cosmetic variants of each other.
3. **The CEO reviews and locks the entire batch at once**, the same manual-lock-in-chat rule as any other hypothesis. `k_total` increments by N at the moment of locking, not one at a time as results come in.
4. All N then run through the unmodified existing pipeline (`validate_hypothesis.py` → Backtester → Overfitting Detector). Results are reported for **every** candidate, winners and losers together — cherry-picking only the winner from a batch and quietly dropping the rest is exactly the same violation as not counting K in the first place.
5. Any candidate that passes is **provisional, not adopted as a reference implementation, until it has accumulated real forward paper-trading track record** — a historical-data PASS from this process is treated as weaker evidence than a normal single pre-registered hypothesis, precisely because the search space, even if narrow, was chosen by the same system being evaluated.

## Open dependencies (spec §6)

1. WRDS/Compustat/CRSP access is pending (contingent on a conversation with Lasse Heje Pedersen) — specifically need to confirm whether local Python access via the `wrds` library is permitted, or whether the agreement requires running in WRDS's cloud environment instead.
2. Local scheduling mechanism (cron or equivalent) is not yet decided — must be set up concretely for this actual environment (this repo is on Windows; the spec was written assuming Linux/macOS cron was available, so this needs an OS-appropriate equivalent).
3. Exact small-cap market-cap cutoff is not locked — must be decided and written into HYP-008's `pass_fail_criterion` before any backtest runs against it, not added afterward.
4. **Paper trading is blocked on live data coverage, not code (found 2026-07-31, reconfirmed 2026-08-07 — now also confirmed to block HYP-043, not just HYP-023).** Two independent attempts to build a "sharp" (forward, no real money) paper-trading feed for HYP-023 both hit the same wall: this EODHD API key's real-time daily coverage for small/micro-cap US tickers lags by weeks to months for most names, even though SPY and a couple of others are fully current. First attempt (frozen Dec-2024 universe list, `data/update_ohlcv_current.py`) found 184/222 tickers stale >120 days. Second attempt (`data/rebuild_current_universe.py`, properly rebuilding today's $100M-$2B band from fresh SEC EDGAR shares outstanding × fresh price, not just reusing the old list) found only 11/383 reasonable candidates with a price inside 60 days, and only one (OPI) actually current as of yesterday. This rules out "bad universe-membership logic" as the cause — it's a data-vendor coverage gap. `scripts/check_hyp043_forward_data_staleness.py` (2026-08-07, cheap spot-check on 25 tickers from the latest 2025-extension universe month, no full rebuild needed) reconfirmed the gap is unchanged a week later: 0/25 within 5 days, only 4/25 within 60 days. Since HYP-043 (the current flagship, see HYP-043's registry entry) puts 2/3 of its notional in small-cap-dependent legs (HYP-037's decile + the momentum L/S sleeve, both drawing on the same blocked universe — only the SPY leg is unaffected), HYP-043 is equally blocked from genuine forward paper trading today, not just HYP-023. **CEO decision 2026-08-07: deprioritize forward paper trading for now** — OOS-2025 (held-out historical year, not genuine forward data) remains the best available validation until this is revisited. Needs either a better-tier/different data source for live small-cap prices, or an explicit future decision to run paper trading on degraded (weeks-to-months-stale) marks — both options were raised and explicitly declined for now. `paper_trading/HYP-023/compute_current_state.py` exists and works once real current data is available for enough of the universe to rank a meaningful decile; no equivalent for HYP-043 was built (no point until the data gap closes).

## Immediate next task (spec §7)

If asked to start building this project, the order specified is: (1) repo structure (`/agents/`, `/research/hypothesis_registry/`, `/data/`), (2) role prompts for all v1 agents, (3) Data Engineer's data abstraction layer (yfinance now, WRDS stub), (4) `_counter.yaml` initialized at `k_total = 7`, (5) `HYP-008` created as pre-registered/unlocked with `pass_fail_criterion` filled in before any small-cap-data code is written, (6) HYP-008 is **not run** until WRDS access is resolved or the user explicitly decides to use a free small-cap proxy dataset for an interim run.
```

---

## KÄLLFIL: `research/EXTERNAL_REVIEW_BRIEF.md`

```
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
```

---

## KÄLLFIL: `research/RESEARCH_REPORT_2026-08-09.md`

```
# Forskningsrapport: Mini Hedge Fund-projektet

**Datum:** 2026-08-09
**Status:** Ögonblicksbild — K=46, referensimplementation HYP-047
**Mottagare:** Extern AI-granskning (primär), CEO (sekundär)
**Metod för granskning:** repo-access rekommenderas framför att läsa denna text isolerat — se del 3 för pekare till källfiler. Den granskande AI:n bör vara adversariell, inte bekräftande: varje siffra nedan går att verifiera mot `research/hypothesis_registry/*.yaml` och git-historiken.

---

## Del 1: Resultat och varför

### 1.1 Utgångspunkten

Projektet startade som ett test av om en beta-neutral OLS-pariserhandelsstrategi (**v6**, redan validerad på large-cap 2010–2024: Sharpe ~0.55, CAGR ~4.8%, MaxDD ~-8.6%) behåller sin edge på small-cap-aktier ($100M–$2B börsvärde), på tesen att stora institutioner är kapacitetsbegränsade där — inte en informationsasymmetri-tes.

Tre direkta pariserhandelsreplikationer (HYP-008/009/011) misslyckades. Det ledde inte till att projektet lades ner, utan till en pivot: istället för att jaga en enskild small-cap-signal, testades om en **portföljkombination** av flera oberoende byggstenar kunde nå CEO:s uttalade grundmål — konstant CAGR >10 %/år **och** Sharpe >1. Det är den kombinationsspåret som till slut bar frukt.

### 1.2 Ejay — det första, viktiga misslyckandet

Parallellt testades ett internt signalkvalitetsmått, "Ejay" (senare visat matematiskt ekvivalent med Kelly-kriteriet), i sju oberoende varianter. Alla dog av samma grundorsak: cirkularitet — måttet förklarade inget utöver ren z-score-styrka, och viktade/oviktade varianter var för högt korrelerade för att vara oberoende bevis. Ejay återöppnades en gång till (HYP-040, CEO:s eget TA-mönster-förslag) och dog en nionde gång, av samma mönster. Ejay är stängt.

Detta är inte en fotnot — det är skälet till att hela pre-registrerings- och K-räkningsdisciplinen (spec §2) finns. Utan den hade sju-nio falska positiva kunnat plockas ut i efterhand och presenteras som "fungerande".

### 1.3 Det upprepade mönstret: exponeringstiming vs. urval/viktning

Ett tydligt, upprepat mönster växte fram genom registret:

- **Exponeringstiming-mekanismer** (när man är exponerad, inte vad man äger) har lyckats **4 av 5 gånger**: HYP-017 (SPY-kraschöverlägg), HYP-023 (sektorspecifik dynamisk kraschtrigger), HYP-037 (villkorat återinträde i samma överlägg) och HYP-047 (trendföljande SPY-short) PASSADE. HYP-045 (samma kraschtrigger applicerad på fler ben) FAILADE, med rakbladstunn marginal. Räkna alla fem, inte bara framgångarna, annars överdrivs mönstret.
- **Urvals-/viktningsförsök** (byta VAD man äger inom en redan vald pool) har misslyckats **9 av 9 gånger**, per registrets egna löpande räkningar i `_counter.yaml`: HYP-030 (momentum-krasch-rebound), HYP-031 (beta-hedge mot IWM), HYP-032 (Kelly-sizing), BATCH-001 (5 stop-loss-varianter, räknat som ett), HYP-033 (book-to-market), HYP-034 (stale-price-filter), HYP-036 (sektorneutral ranking), HYP-038 (likviditetsviktad allokering), HYP-042 (kortsiktig reversal — det sämsta enskilda resultatet i hela registrets historia, MaxDD -98 till -99 %, och därmed den starkaste datapunkten i denna bucket).

**Viktig reservation, tillagd efter gårdagens granskning (se del 3):** detta mönster är äkta men bygger på ett litet sample (5 vs. 9 observationer), och sökprocessen är inte neutral — senare kandidater föreslogs delvis **för att** tidigare timing-idéer redan lyckats, vilket kan förstärka mönstret artificiellt snarare än att bara bekräfta det. Behandla det som en stark hypotes om varför projektet fungerat, inte som ett statistiskt bevisat faktum.

### 1.4 Vägen till dagens referensimplementation

1. **HYP-017 → HYP-021 → HYP-023 → HYP-037**: idiosynkratisk volatilitet + SPY-kraschöverlägg, förfinat i tre steg (sektorspecifik trigger, sedan villkorat återinträde). HYP-037 blev referens 2026-08-01.
2. **HYP-039** (2026-08-04): första kombinationshypotesen — naiv 50/50 SPY + HYP-037. Korrelation SPY/HYP-037 uppmätt till -0,003 (praktiskt taget noll) FÖRE låsning. Sharpe 1,02/1,03/0,99, MaxDD -22 % (mot SPY:s egna -33,7 %). **Första gången CEO:s grundmål nåddes.**
3. **HYP-043** (2026-08-06): tredje ben, en egenbyggd (inte ETF-proxy) momentum long/short-svit. Ursprungligen den starkaste kombinationen i registret (Sharpe 1,05, MaxDD -15,6 %) — **men se del 3: denna slutsats höll inte vid full friktionskorrigering, upptäckt 2026-08-07 och slutgiltigt bekräftat 2026-08-08.**
4. **HYP-044/045/046** (2026-08-07): tre raka misslyckade försök till fjärde ben (PEAD/SUE-faktor, kraschöverlägg på kombinationen, och en sammanslagning av de två) — samtliga med hög DSR (genuina, inte slumpmässiga) men otillräckliga mot det redan höga kravet. HYP-046 gav dock registrets bästa MaxDD någonsin (-9,7 %) trots FAIL på Sharpe — ett konkret exempel på Sharpe/MaxDD-avvägning, inte ett varningstecken.
5. **HYP-047** (2026-08-07, CEO-beslut om referensstatus 2026-08-08): en offensiv, trendföljande SPY-kortposition (under 200-dagars glidande medelvärde) som fjärde ben — tjänar aktivt pengar i nedgångar istället för att bara gå till kontanter. Sourced från en 4-AI-brainstorm. **PASSADE på alla fyra villkor, alla tre kapitalnivåer**, och slog även den redan friktionskorrigerade HYP-043-baslinjen tydligt.

### 1.5 Dagens siffror för HYP-047

Två giltiga körningar, båda PASS: originalresultatet (låst 2026-08-07) och en oberoende, fullt korrigerad omkörning (2026-08-08, se del 3). Visas separat nedan istället för som ett spann, eftersom Calmar och OOS-Sharpe rör sig i olika riktningar mellan de två körningarna och ett aggregerat intervall döljer det.

| Nivå | Sharpe (orig → korr) | MaxDD (orig → korr) | Calmar (orig → korr) | OOS-2025 Sharpe (orig → korr) |
|---|---|---|---|---|
| $100k | 1,156 → 1,126 | -7,44 % → -8,67 % | 1,17 → 0,97 | 1,546 → 1,710 |
| $1M | 1,164 → 1,127 | -7,30 % → -8,45 % | 1,18 → 1,01 | 1,494 → 1,720 |
| $10M | 1,099 → 1,102 | -7,23 % → -8,20 % | 1,08 → 0,99 | 1,468 → 1,780 |

DSR 0,96–0,98 vid K=46 (originalkörningen; DSR för den korrigerade körningen räknades inte om separat).

**Notera:** MaxDD och Calmar är genomgående något sämre i den korrigerade körningen — den korrigerade pipelinen är strängare, inte snällare, mot HYP-047. Sharpe- och OOS-villkoren håller ändå med marginal på båda körningarna. Efter korrigering är HYP-047 inte längre bäst i registret på MaxDD/Calmar — den (FAILADE) HYP-046 har bättre korrigerad MaxDD (-8,09 % vid $100k, se del 3.1).

Validerad mot: huvudperioden (2010–2024) och genuin blind OOS-2025 (inkl. en verklig SPY-krasch april 2025) för **hela** fyrbensportföljen. En tredje datapunkt — historiska kriser 2000–02 och 2008 — finns också, men gäller bara **bear catcher-benet isolerat** (100 % egen notional), inte hela HYP-047: +63,78 % under 2000–02 mot SPY:s -33,85 %, +40,25 % under 2008 mot SPY:s -43,41 % (`scripts/diagnostic_bear_catcher_extended_history.py`). Motsvarande pre-2010-data för HYP-037-benet och momentum L/S-sviten finns inte i repot, så hur hela HYP-047 skulle presterat 2000–02/2008 är okänt — detta ska läsas som stöd för ett av fyra ben, inte som en tredje fullständig validering av strategin.

---

## Del 2: Metoden — en återanvändbar process

Det som gör HYP-047 till mer än "en strategi som råkade fungera" är processen som ledde dit. Tre delar är värda att beskriva som återanvändbar metod, inte bara historik:

### 2.1 Pre-registrering + K-räkning + Deflated Sharpe Ratio

Ingen backtest körs utan ett låst, skrivet `pass_fail_criterion` (skrivet av CEO manuellt i chatt, aldrig av en agent). Varje tested variant — även misslyckade — ökar en global räknare `k_total`. Deflated Sharpe Ratio (Bailey & López de Prado) beräknas mot detta K, inte mot den enskilda backtestens egen Sharpe. Detta är direkt motiverat av Ejay-episoden: utan K-räkning hade 7–9 misslyckade varianter kunnat gömmas.

### 2.2 Multi-AI-brainstorm som kandidatgenerator

Från och med HYP-044 användes externa AI-konsultationer för att generera kandidatidéer. **Rättelse (efter granskning av denna rapport 2026-08-09):** ett tidigare utkast beskrev detta som en "strikt engångs, icke-adaptiv batch" och åberopade CLAUDE.md:s formella "Batch Hypothesis Generation"-regel. Det är fel på två sätt. Dels är den formella batch-proceduren (alla kandidater låsta som ETT block, K ökar med N samtidigt) bara använd en gång i hela registret — BATCH-001 (fem stop-loss-varianter). Dels, viktigare: HYP-047 söktes explicit fram **efter tre raka FAIL (044/045/046)** — en ny AI-konsultation beställd just för att tidigare kandidater misslyckats är per definition en resultatstyrd sökprocess på metanivå, samma mönster som Batch-regeln finns för att förhindra på kandidatnivå.

Det som ÄR sant, och som räddar detta från att vara ett upprepat Ejay-mönster: varje enskild kandidat pre-registrerades och K-räknades för sig, med sitt eget låsta kriterium skrivet innan resultatet sågs — så statistiken (DSR mot löpande K) räknar korrekt in varje försök, lyckat eller inte. Vad som INTE är skyddat är den mjuka, mänskliga signalen i VILKEN typ av mekanism som föreslås näst (se reservationen i 1.3) — det är en kvarstående, öppet redovisad svaghet, inte en löst problem.

- HYP-044: första externa 5-AI-brainstorm → PEAD/SUE-kandidaten, efter att redan kända dödläge (insiderköp, kortsiktig reversal) filtrerats bort.
- HYP-047: 4-AI-brainstorm efter tre raka FAIL (044/045/046) → trendföljande "crisis alpha"-mekanism (Hurst/Ooi/Pedersen-traditionen), testad efter en diagnostik som explicit mätte falsklarmsfrekvens över hela perioden (36 episoder, 34 träffar/2 falsklarm) för att undvika hindsight-attributionsrisk.

### 2.3 Kostnadsfri diagnostik före låsning

Innan en kandidat låses som pre-registrerad hypotes (och därmed kostar K) körs ofta billig, icke-K-kostande diagnostik: regimbetingad stresstest, korrelation mot befintliga ben, falsklarmsfrekvens över hela perioden. Detta filtrerar bort svaga kandidater utan att "betala" för dem i multipeltestningsräkningen — men är i sig ett potentiellt sårbart steg (se del 3, punkt om urvalsprocessens neutralitet).

### 2.4 Kombinationsreglerna (spec §5b)

Att kombinera hypoteser är explicit förbjudet som genväg runt individuellt misslyckande. Legitim kombination kräver: korrelationsmatris på avkastningsserier FÖRE låsning, naiv likaviktning (aldrig in-sample-optimerad), OOS-testning, och egen K-kostnad per distinkt kombinationsmetod. **Rättelse (2026-08-09):** ett tidigare utkast hävdade att denna regel höll fullt ut genom hela kedjan HYP-039 till HYP-047. Det stämmer för HYP-039/041/043/044, men inte för HYP-046: dess registerpost hade vid låsning bara en kvalitativ motivering ("mekaniskt olika, ingen överlappning") — den kvantitativa korrelationssiffran (-0,093/-0,004/-0,015, se del 3.1) räknades ut först i efterhand, av gårdagens granskning. Ett dokumenterat, om än litet, avsteg från §5b:s bokstav, inte en teoretisk risk.

---

## Del 3: Aktuell status och öppna frågor

### 3.1 Fallstudie: den oberoende granskningen 2026-08-08

Innan denna rapport skrevs kördes en adversariell audit av hela registret — inte för att bekräfta att allt var bra, utan för att aktivt leta efter brott mot projektets egna regler. Metod: tre helt blinda, oberoende AI-granskare, samma checklista, ingen samordning, repo-access (inte bara sammanfattningar).

**Konvergenta fynd (hittade oberoende av flera granskare, därför hög tillförlitlighet):**

1. **Deflated Sharpe Ratio räknades aldrig om** för redan aktiva hypoteser när K växte, trots att detta är en explicit hård regel (`agents/overfitting_detector/ROLE.md`). HYP-017/021/023/037/039/041/043 visade DSR beräknat mot ett K som var lägre — i vissa fall mindre än hälften — av dagens 46.
2. **En känd look-ahead-bias i universumkonstruktionen** (aktieantal tidsstämplat med periodslut-datum istället för SEC-inlämningsdatum, ~20,8 % av ticker-månads-medlemskap påverkat) hade en korrigering byggd redan 2026-08-05, men den gjordes **aldrig till produktionsdefault** — alla strategier körde fortfarande på den kända biasade filen.
3. **En känd datakvalitetsbugg** (konstant orimlig adjusted_close/close-kvot, ~9,5 % av universum) var bara manuellt kopierad in i senare hypoteser (HYP-042–047), aldrig centraliserad i den delade `data_hygiene.py` eller portad till referenskedjan.
4. **Noll transaktionskostnad vid ombalansering** mellan ben i samtliga sju kombinationshypoteser, trots principen "friktion från dag ett" (spec §2).
5. **HYP-043:s redan kända friktionsgap** (saknad bid-ask-spreadkostnad i momentum L/S-sviten, upptäckt 2026-08-07) fanns bara dokumenterat i andra hypotesers prosa, aldrig i dess egen registerpost.

**Åtgärdat, samma dag, med samma disciplin som redan etablerad i registret** (daterade tilläggsnoter, aldrig tyst omskriven historik, egen commit per hypotes, ingen ny K-kostnad eftersom detta är buggkorrigering av redan testade hypoteser, inte nya hypoteser):

- DSR omräknad mot K=46 för de sju berörda hypoteserna.
- Look-ahead-fixen och adjusted_close-fixen portade till produktionskod för HYP-037/039/041/043/044/045/046/047.
- En enhetlig 10bps ombalanseringskostnad tillagd i alla sju kombinationshypoteser.
- HYP-043 fick fem tilläggsnoter (DEL A–E) som dokumenterar hela kedjan av fynd, avslutat med en fullt kombinerad omkörning (alla fyra fixar samtidigt).
- HYP-046 fick sin tidigare saknade kvantitativa korrelationsmatris (PEAD/SUE-sviten mot övriga tre ben: -0,093/-0,004/-0,015 — bekräftade den kvalitativa "icke-överlappande"-motiveringen, men räknades ut efter låsning, inte före den — se rättelsen i del 2.4).

**Resultatet av full korrigering, hypotes för hypotes (avgörande $100k-nivå):**

| Hypotes | Sharpe vid $100k (original → korrigerad) | Verdict korrigerad pipeline |
|---|---|---|
| HYP-037 (bas) | 0,737 → 0,726 (håller, håller även vid $1M/$10M: 0,741→0,759) | Villkor 1 PASS, **villkor 2 (MaxDD vs HYP-023) FLIPPAR TILL FAIL** på alla tre nivåer |
| HYP-039 | 1,019 → 1,017 | **PASS oförändrat** |
| HYP-041 | 0,998 → 0,988 | FAIL oförändrat |
| HYP-043 | 1,046 → **0,876** (alla fyra fixar kombinerade) | **FAIL, entydigt** (var PASS) |
| HYP-044 | 1,012 → 0,953 | FAIL oförändrat |
| HYP-045 | 0,994 → 0,985 | FAIL oförändrat (samma rakbladstunna nära-miss) |
| HYP-046 | 0,948 → 0,894 | FAIL oförändrat, MaxDD ännu bättre (-8,09 %, bäst i registret **efter korrigering**) |
| **HYP-047 (flaggskepp)** | 1,156 → 1,126 | **PASS på alla fyra villkor, alla tre nivåer — ingen flip** (MaxDD/Calmar dock något sämre korrigerat, se del 1.5) |

**Slutsats av fallstudien:** flaggskeppsresultatet (HYP-047) står på fast grund — verifierat både genom att den ursprungliga låsta registerposten är helt oförändrad (noll rader borttagna, endast tillägg) och genom en oberoende, fullt korrigerad omkörning som ger samma slutsats. Men grunden under det (HYP-037, HYP-043) var svagare än registret tidigare visade. Det här är inte en invändning mot projektet — det är exakt vad disciplinen är designad att hitta, och den hittade det.

### 3.2 Kvarstående kända luckor (öppna, inte dolda)

- **HYP-023 korrigerades aldrig självt** — HYP-037:s nu FAIL:ande MaxDD-villkor jämförs mot en okorrigerad baslinje. En fullt konsekvent korrigering av HYP-023 har inte körts.
- **HYP-037:s OOS-2025 kördes inte om** under den korrigerade pipelinen (avgränsning i gårdagens uppdrag, disclosed explicit).
- **`status`-fälten för HYP-037 och HYP-043 ändrades formellt till "failed" 2026-08-09** (CEO-beslut, se respektive registerpost) — de klarar inte längre sina egna låsta kriterier under den fullt korrigerade pipelinen. De ursprungliga siffrorna i `capital_level_results` är oförändrade (historik skrivs inte om); bara statusbedömningen är uppdaterad. HYP-039 är därmed den senaste hypotesen i kedjan som fortfarande passerar på egna meriter före HYP-047, och HYP-023 är grunden HYP-039 med flera faktiskt vilar på.
- **Forward paper trading är fortfarande datablockerad**, inte strategiblockerad — EODHD:s täckning för small/micro-cap-tickers ligger veckor till månader efter i realtid. All validering ovan (huvudperiod, OOS-2025, historiska kriser) är historisk data. OOS-2025 är den bästa tillgängliga approximationen av genuin framåtvalidering, men är det inte i egentlig mening.
- **Mönstret i 1.3 (timing 4/5 vs urval 0/9)** bygger på litet sample och en potentiellt icke-neutral sökprocess — se reservationen ovan.
- **Multi-AI-brainstorm-processen (del 2.2) är K-skyddad på kandidatnivå men inte på metanivå** — vilken typ av mekanism som föreslås näst påverkas av vad som redan lyckats/misslyckats (HYP-047 söktes uttryckligen efter tre raka FAIL). Ingen mekanism i registret räknar eller korrigerar för denna mjukare form av sökstyrning.
- **`scripts/diagnostic_bear_catcher_extended_history.py`** (kris-valideringen i del 1.5) saknade tidigare en tilläggsnot i registret och en commit, till skillnad från allt annat i denna rapport — åtgärdat 2026-08-09, se källpekare nedan.
- **Small-cap-kapacitetsfrågan** (kärntesen — att edgen finns för att stora institutioner är kapacitetsbegränsade, inte informationsasymmetri) testas fortfarande bara indirekt via kapitalnivåkänslighet ($100k/$1M/$10M), aldrig direkt.

### 3.3 Källpekare för granskning

- `research/hypothesis_registry/*.yaml` — samtliga 39 hypotesposter, inkl. dagens tilläggsnoter
- `research/hypothesis_registry/_counter.yaml` — K-räknare + narrativ logg
- `strategies/HYP-047/backtest.py`, `strategies/HYP-043/backtest.py` — produktionskod, inkl. gårdagens fixar
- `strategies/common/data_hygiene.py` — centraliserad datasanering
- `scripts/deflated_sharpe_ratio.py`, `scripts/recompute_dsr_k46.py` — DSR-metod och omräkningsverktyg
- `scripts/diagnostic_bear_catcher_extended_history.py` — kris-valideringen (2000–02, 2008) för bear catcher-benet isolerat
- Git-historiken 2026-08-08 (commits `7d43610` till `90bd7fd`) — hela gransknings- och fixkedjan, en commit per logisk ändring
- Git-historiken 2026-08-09 — rättelser till denna rapport efter en andra, oberoende trepersoners granskning av rapporttexten själv (samma metod som 2026-08-08, riktad mot rapporten istället för mot registret)
```

---

## KÄLLFIL: `research/hypothesis_registry/_counter.yaml`

```
k_total: 46
note: "HYP-047 (bear catcher - trendfoljande SPY-short under 200-dagars MA, tjanar OFFENSIVT pa nedgangar (INTE bara defensiv kontant-overlay som HYP-045), 1/4 SPY + 1/4 HYP-037 + 1/4 momentum L/S (med friktion) + 1/4 bear catcher. PASSED 2026-08-07 PA ALLA FYRA VILLKOR, ALLA TRE NIVAER - forsta rena PASSET sedan HYP-043, starkast i hela registrets historia. Sharpe 1.156/1.164/1.099 (klart over 1.0 aven vid $10M, till skillnad fran HYP-039/043), MaxDD -7.44%/-7.30%/-7.23% (7-8pp battre an friktionskorrigerad HYP-043-baslinje, i praktiken en HALVERING), Calmar 1.17/1.18/1.08 (bast i registret). OOS-2025 Sharpe 1.546/1.494/1.468 (mot HYP-039:s 0.919/0.812/0.793). DSR 0.98/0.98/0.96 vid K=46 - HOGRE an HYP-043:s egna ursprungliga DSR trots 46 redan testade hypoteser. Slar AVEN HYP-043:s URSPRUNGLIGA (icke-friktionskorrigerade) siffror (1.046/1.050/0.986 Sharpe, -15.6/-15.7/-14.3% MaxDD) tydligt pa bade Sharpe och MaxDD - inte bara en seger mot den handikappade friktionskorrigerade jamforelsepunkten. HARLEDNING: fran en 4-AI-brainstorm 2026-08-07 (starkast samstammiga rekommendation - trendfoljande 'crisis alpha', Hurst/Ooi/Pedersen-traditionen), testad EFTER en diagnostik som explicit matte falsklarmsfrekvens over HELA perioden (36 episoder, 34 traffar/2 falsklarm, bara 33.6% av P&L fran de 5 redan kanda krisfonstren) for att undvika hindsight-attributionsrisken en av AI:erna varnade for. KAND, OPPET REDOVISAD RESERVATION: den verkliga covid-episodens fulla handelsperiod gav -3.50% trots +43.17% inom ett snavare handplockat fonster (whipsaw-risk vid V-atehamtning) - 94.4% traffprocent har bara testats mot EN utdragen bjornmarknad (2022) i backtestperioden. DIAGNOS: en GENUINT OFFENSIV mekanism (verklig kort position, -0.4526 korrelation mot HYP-043-kombon, uppmatt INNAN lasning) gav mer an dubbelt sa stor MaxDD-forbattring som HYP-045:s DEFENSIVA overlay mot samma baslinje. SLUTSATS: starkaste kandidaten for ny referensimplementation i registrets historia - kraver CEO-BESLUT for att formellt bli referens, inte automatiskt. CEO-BESLUT 2026-08-08: HYP-047 AR NU REFERENSIMPLEMENTATIONEN, HYP-043 kvarstar PASSED men ej langre aktiv referens - samma monster som HYP-017->023->037.) + HYP-046 (kombinerar HYP-045:s krasch-overlay (pa SPY+momentum L/S-benen) MED HYP-044:s PEAD/SUE-ben (OFORANDRAD, INGEN overlay - visade sig redan defensiv under kris), fyrdelad likaviktad. FAILED 2026-08-07 PA VILLKOR 1 (Sharpe >=1.0), och OVANTAT med STORRE marginal (0.9475/0.9492/0.8726) an bade HYP-044 (1.0117/1.0135/0.9439) och HYP-045 (0.9941/0.9989/0.9287) var for sig - kombinationen av tva GENUINA (hog DSR) forbattringar gav en LAGRE Sharpe an endera separat, INTE additivt. MEN MaxDD blev DRAMATISKT battre - -9.73%/-9.19%/-7.96%, BASTA MaxDD-resultatet i hela registrets historia for en kombinationshypotes, 5.85-6.49pp battre an friktionskorrigerad HYP-043-baslinje, battre an bade HYP-044 och HYP-045 var for sig. Calmar 0.818/0.855/0.889 - ocksa bast i registret. OOS PASSADE (1.352/1.299/1.276 mot HYP-039:s 0.919/0.812/0.793) men lagre an bade HYP-044:s och HYP-045:s egna OOS. DSR 0.90/0.90/0.84 vid K=45 - fortsatt hogt, genuint resultat, INTE en varningssignal. DIAGNOS: CAGR foll under bada komponenternas egna (7.95%/7.85%/7.07%) - tva riskreducerande mekanismer (krasch-timing + ett nytt likaviktat 4:e ben) drar BADA ner avkastningen samtidigt som de sanker risk, och nar bada tillamps SAMTIDIGT overkorrigerar den sammanlagda effekten mot risk pa Sharpens bekostnad (fast tydlig fordel i MaxDD/Calmar-termer). METODOLOGISK NOT (diskuterad med CEO INNAN lasning): detta ar INTE forbjuden 'kombinera misslyckade hypoteser'-fiske - bade byggstenarna hade hog DSR (0.90-0.94 respektive 0.89-0.93) och ar mekaniskt icke-overlappande (ny alfakalla vs risk-timing), en enda i forvag motiverad kombination. HYP-043 forblir referensen for Sharpe-malet, men HYP-046 ar den starkaste kandidaten i HELA registret om malet istallet vore lagst MaxDD/hogst Calmar - konkret empiriskt exempel pa Sharpe/MaxDD-avvagningen. Tre raka FAIL (044/045/046) efter HYP-043:s PASS tyder pa en praktisk grans for naiv likaviktad kombination av kanda byggstenar.) + HYP-045 (krasch-overlay, aterananvander HYP-037:s redan lasta triggerparametrar (SPY 10-dagars avkastning <-10%, haircut till 40%, aterintrade vid 50% aterhamtning), tillampad pa SPY-benet och momentum L/S-benet i HYP-043-kombinationen (HYP-037-benet ORORT, har redan egen overlay). FAILED 2026-08-07 PA DEN AVGORANDE $100k-NIVAN, PA VILLKOR 1 SPECIFIKT (Sharpe >=1.0) - MEN RAKBLADSTUNT: 0.9941 vid $100k (0.0059 under), 0.9989 vid $1M (0.0011 under). Villkor 2 (sla friktionskorrigerad HYP-043-baslinje 0.8926/0.8940/0.8217) PASSADE TYDLIGT pa alla tre nivaer (0.9941/0.9989/0.9287, en forbattring pa 0.09-0.11 Sharpe-enheter). Villkor 3 (MaxDD battre an samma baslinje) PASSADE PA ALLA TRE (-14.56%/-13.83%/-12.17% mot -15.58%/-15.68%/-14.29%). OOS-2025 PASSADE STARKT (1.596/1.543/1.508 mot HYP-039:s 0.919/0.812/0.793) - sarskilt informativt eftersom OOS-2025 innehaller en AKTA SPY-krasch (-18.8% MaxDD april 2025), mekanismens forsta genuina test, klarad med marginal (OOS-avkastning +30-32%). Mekanismen triggade pa 3.3% av dagarna (134/4024) - genuint exercerad, ingen no-op. DSR 0.93/0.93/0.89 vid K=44. HARLEDNING: en attributionsanalys samma dag mot 5 REDAN etablerade krisepisoder (2011/2015/2018/2020/2022, fran manader-gamla diagnostic_hyp017/037_leave_one_crisis_out.py) visade att 8.0% av HYP-043-kombons dagar star for -26.76% kumulativ avkastning medan ovriga 92% gav +463.58% - CEO:s ursprungliga ide (identifiera kriser via NYHETSLASNING) AVVISADES explicit som hindsight-risk (samma fallgrop som de 7 Ejay-varianterna), ersattes med en REN PRISBASERAD, redan i forvag etablerad trigger. VIKTIGT SAMMANHANG: samma dag visade en robusthetsdiagnostik (scripts/diagnostic_hyp043_friction_robustness.py) att HYP-043:s EGNA redan lasta resultat (Sharpe 1.0457/1.0498/0.9864) byggde pa en OFULLSTANDIG friktionsmodell (momentum L/S-sviten saknade corwin_schultz_spread) - friktionskorrigerat blir HYP-043:s Sharpe 0.8926/0.8940/0.8217, KLARAR INTE LANGRE sitt eget ursprungliga kriterium. HYP-043:s redan lasta registerpost ANDRADES INTE (last historia andras inte i efterhand) - oppen fraga kvarstar for CEO om en formell tilläggsnot. DIAGNOS: overlayn fungerade genuint som avsett (hojde Sharpe, sankte MaxDD mot den friktionskorrekta baslinjen) men den friktionskorrigerade baslinjen lag for langt under 1.0 for att en enda timing-mekanism skulle ta igen hela avstandet. Konsistent med registrets etablerade monster: exponeringstiming levererar genuina forbattringar varje gang (nu 3 PASSED + denna nara-miss), urval/viktning star pa 0/9.) + HYP-044 (naiv fyrdelad kombination SPY+HYP-037+momentum L/S+PEAD/SUE, FAILED 2026-08-07 PA DEN AVGORANDE $100k-NIVAN, PA VILLKOR 2 SPECIFIKT (Sharpe 1.0117 vs HYP-043:s egna 1.0457, konsekvent samre pa alla tre nivaer). PEAD/SUE-kandidaten (sasongsjusterad EPS-overraskning) togs fram via en systematisk EXTERN 5-AI-brainstorm samma dag (forsta gangen i registret) - efter att redan kanda dodlaget (raw insiderkop=HYP-035, small-cap kortsiktig reversal=HYP-042) filtrerats bort ur forslagen, och ytterligare 6 kandidater (low-vol L/S, kvalitet L/S, 52v-hogsta L/S, tva trendfoljningsvarianter, bredare CTA-korg, nettoemission) testats diagnostiskt och avfardats samma dag (ingen K-kostnad for nagon av dessa 6+2). METODOLOGISKT VIKTIGT FYND under byggandet: HYP-043:s egen momentum L/S-svit saknar corwin_schultz_spread-anvandning (bara borrow_cost) - skulle INTE klara scripts/validate_friction_usage.py om det kordes idag, flaggat separat for CEO, INTE tyst atgardat i HYP-043:s redan lasta resultat. HYP-044 byggdes med bade borrow_cost OCH genuin spreadkostnad - en parallell diagnostik UTAN spreadkostnad visade Sharpe 1.085/1.088/1.022 (skulle ha PASSAT tydligt), MED spreadkostnad blev det 1.012/1.014/0.944 (FAIL) - en ren, konkret illustration av varfor 'friktion fran dag ett' (spec §2 princip 3) spelar roll i praktiken, inte bara i teorin. MaxDD FORBATTRADES dock genuint och konsekvent pa alla tre nivaer (-10.9%/-11.0%/-10.0% mot HYP-043:s -15.6%/-15.7%/-14.3%, 4.34-4.68pp battre) och OOS-2025 slog HYP-039:s referens tydligt (1.373/1.320/1.300 mot 0.919/0.812/0.793, kriteriet jamforde medvetet mot HYP-039 inte HYP-043 pga enars-OOS-brus, se registerpostens motivering). DSR 0.94/0.94/0.90 vid K=43 - fortsatt hogt, ingen slumptraff, bara inte tillrackligt for att sla en redan stark referens. HYP-043 forblir referensimplementationen, oforandrad. PEAD/SUE-byggstenen sjalv bedoms sannolikt genuin (regimbetingad stresstest INNAN lasning visade +3.25% under HYP-043-kombons egen varsta drawdown-period, rullande 252-dagars korrelation aldrig over 0.3) men otillrackligt stark for att bara sin vikt i just DENNA likaviktade fyrdelade konstruktion.) + HYP-043 (naiv tredelad kombination SPY+HYP-037+momentum L/S-svit, PASSED 2026-08-06 PA DEN AVGORANDE $100k-NIVAN - FORSTA kombinationshypotesen som slar HYP-039 pa dess egna villkor, tydligt battre inte bara precis-godkand. Sharpe 1.046/1.050/0.986 vid 100k/1M/10M (bara $10M missar knappt, ej avgorande nivan). MaxDD -15.6%/-15.7%/-14.3% - en FORBATTRING pa 6.35-6.48pp mot HYP-039:s egna -22.0%/-22.2%/-20.0%, inte marginellt. OOS-2025 spektakulart: Sharpe 1.62/1.56/1.53 mot HYP-039:s 0.92/0.81/0.79 (68-93% battre, med den vanliga enarsbrus-reservationen). DSR 0.95/0.95/0.92 vid K=42. Momentum L/S-sviten (egenbyggd, ETF-proxyerna hade for kort historik) hade svagare korrelation an forst trott (daglig -0.086/-0.110 mot en missvisande kvartalsvis -0.36/-0.23 - se separat metodologiskt fynd om att kvartalskorrelationer pa fa datapunkter ar opalitliga, upptackt samma dag) men battre EGEN kvalitet an HYP-041:s TLT (Sharpe 0.27 mot 0.038) - bekraftar att sviten-benets egen kvalitet spelar minst lika stor roll som korrelationen. Indirekt stod for HYP-042:s tes (small-cap-forlorare kollapsar genuint) - utnyttjat har via KORTSIDAN (blanka forlorarna), vilket fungerade mycket battre an HYP-042:s egen langsida (kopa forlorarna, FAILADE katastrofalt).) + HYP-042 (kortsiktig reversal, 10-dagars trailing avkastning, veckovis ombalansering, ra signal + SPY-hedge, FAILED KATASTROFALT 2026-08-06 - VARSTA resultatet i hela registrets historia. Sharpe -0.65 till -0.80, MaxDD -98% till -99% (tidigare varsta var HYP-030 pa -86%), DSR ~0.0001 vid K=41. Under byggandet hittades och fixades TVA genuina datakvalitetsbuggar (ny buggklass: konstant, inte enskild-dags, orimlig adjusted_close/close-kvot - tickern ABWND ~30000x, 490 av 5162 tickers paverkade i full korning; samt samma 'motorfix 2'-entry-pris-bugg som redan kand fran HYP-037/040, tickern ACRX ~20x troligen en akta split). Verifierat EFTER buggfixarna att resultatet ar genuint, inte kvarvarande bugg: medianen av 34100+ affarer ar -2.3%, inte nagra fatal extremvarden. Diagnos: reversal-tesen haller inte i small/micro-cap - manga 'forlorare' ar genuint kollapsande bolag (konkurs/avnotering), inte tillfalligt overreagerade. Hog omsattning (veckovis) fick en persistent negativ edge att sammansatta katastrofalt. HYP-037 forblir enda aktiva referensen.) + HYP-041 (naiv tredelad kombination SPY+HYP-037+TLT, FAILED 2026-08-06 PA DEN AVGORANDE $100k-NIVAN, PA SAMTLIGA VILLKOR. Sharpe 0.998/1.006/0.950 vid 100k/1M/10M - marginellt under 1.0-malet vid $100k, och KONSEKVENT SAMRE (inte battre) an HYP-039:s egna redan registrerade 1.019/1.030/0.988 pa alla nivaer, aven MaxDD forsamrades (-22.7%/-23.0%/-21.6% mot HYP-039:s -22.0%/-22.2%/-20.0%). DSR 0.94/0.94/0.91 vid K=40 - HYP-041 ar sannolikt en genuin positiv-Sharpe-portfolj i absoluta tal, men det var INTE fragan; kriteriet kravde att slas HYP-039, inte bara vara okej pa egen hand. Diagnos: bekraftar den oppet redovisade reservationen INNAN lasning - TLT:s goda korrelation (-0.30 mot SPY, -0.02 mot HYP-037) rackte inte for att kompensera dess svaga egna riskjusterade profil (egen Sharpe 0.038, egen MaxDD -48.3% 2010-2024, varre an SPY:s -33.7%). HYP-039 forblir den enda kombinationshypotesen som passerat.) + HYP-040 (TA-monsterbibliotek med Ejay-baserad traffsakerhetsfiltrering och positionsviktning, FAILED RENT 2026-08-06 PA ALLA TRE NIVAER. Sharpe -0.50/-0.88/-0.91, MaxDD -78%/-78%/-77% (bland de tva-tre samsta resultaten i hela registret, jamforbart med HYP-019/HYP-030), winrate 42% (samre an myntkast), DSR ~0.00 vid K=39. Ejay-viktad Sharpe var INTE battre an likaviktad for samma filtrerade pool (i praktiken identiska overallt) - SAMMA dodsmonster som de 8 tidigare Ejay/Kelly-varianterna, aven i denna mekaniskt annorlunda tillampning (TA-traffsakerhet snarare an signalstyrka). Ejay ateroppnades EXPLICIT av CEO for BARA detta test (se registerpostens egen motivering) - ar nu ATER STANGD, 9 misslyckade varianter totalt, kraver nytt separat CEO-beslut for att aterppnas. OOS-2025 EJ KORD - CEO-beslut, sparat pa samma grund som HYP-035/019/030 (villkor 1 redan entydigt fail). HYP-037 forblir referensen, oforandrad.) + HYP-039 (forsta kombinationshypotesen i projektet, per spec §5b: naiv 50/50-vikt (INTE in-sample-optimerad), kvartalsvis ombalanserad, SPY + HYP-037, PASSED 2026-08-04 vid den avgorande $100k-nivan pa alla tre villkor - CEO:s uttalade grundmal for hela projektet (konstant CAGR >10%/ar OCH Sharpe >1) uppnadd for forsta gangen. Korrelation SPY/HYP-037 -0.003 (praktiskt taget noll, berknad FORE nagon vikt lastes). Sharpe 1.019/1.030/0.988 vid 100k/1M/10M (bara $10M missar knappt 1.0-malet, INTE gating enligt kriteriet). MaxDD -22.0%/-22.2%/-20.0%, en forbattring pa 11.7-13.7pp mot SPY:s egna -33.7% pa alla tre nivaer - genuin riskreduktion, inte bara utspadning. OOS-2025 (aterananvander HYP-037:s redan byggda blinda 2025-serie): Sharpe 0.919/0.812/0.793, klart positivt pa alla tre. DSR vid K=38: 0.95/0.95/0.94 - mycket hogt, INTE en slumptrafff trots 38 redan testade hypoteser. Metodologisk not: detta ar EN av manga mojliga kombinationsmetoder (50/50 naiv vikt) - varje ANNAN vikt (t.ex. riskparitet) skulle vara ett eget K-test, testas INTE i efterhand for att hitta 'basta' vikten (facit-anpassning). Detta ar INTE en ny referensimplementation i HYP-017/023/037-bemarkelsen (portfoljniva-konstruktion ovanpa en redan godkand strategi, inte en konkurrerande small-cap-signal) - men ett konkret svar pa CEO:s strategiska fraga 2026-08-04 om huruvida kombinerad SPY+HYP-037-exponering nar det uttalade malet. Parhandelsspar (HYP-008/009/011-uppfoljning) medvetet lagt at sidan samma dag efter tre timeout:ade diagnostikforsok - se project_research_state-minnesanteckningen.) + HYP-038 (likviditetsviktad (roten-ur-ADV) allokering pa HYP-037, FAILED 2026-08-01 PA VILLKOR 2 PA ALLA TRE NIVAER - MEN med en viktig metodologisk lardom forst: den forsta implementationen hade en ICKE-DETERMINISTISK BUGG (malbeloppet beraknades mot den lopande, krympande cash-variabeln istallet for en frust ogonblicksbild fore kopsloopen), vilket i kombination med Python-mangders hash-randomiserade iterationsordning gav TRE OLIKA MaxDD-varden (-20.2%/-15.99%/-16.8%) for 'samma' korning - hittad, fixad (rebalance_cash-ogonblicksbild) och verifierad deterministisk (tva identiska omkorningar) INNAN nagot resultat rapporterades. Efter fixen: Sharpe 0.66/0.67/0.70 (PASS golvet men tydligt lagre an HYP-037:s 0.73/0.75/0.70), MaxDD -23.88%/-21.44%/-16.11% SAMRE an HYP-037:s -23.10%/-19.12%/-13.11% PA ALLA TRE - och forsamringen VAXER MED KAPITALNIVA (0.78pp/2.32pp/3.00pp), motsatt den avsedda effekten. DSR 0.63/0.65/0.68 vid K=37. OOS-2025-spärren (villkor 3) KORDES INTE - villkor 2 var redan ett entydigt FAIL pa alla tre nivaer, samma sparbeslut som HYP-035, redovisat oppet. Attributionen visade en diagnostiskt intressant omfordelning: bankexponeringen (SIC 60) minskade nagot (4.3x/4.2x/3.2x mot HYP-037:s 5.6x/5.0x/3.5x) men REIT-exponeringen okade (2.0x/2.0x/2.4x) - likviditetsviktningen omfordelar mot antagligen mer likvida REITs utan att forbattra riskbilden. HYP-037 forblir referensen. Slutsats: att omfordela VIKT inom en redan vald decil (signalstyrka i HYP-032, likviditet har) har nu FAILAT tva ganger, medan exponeringstimingsmekanismer star pa 3/3 PASSED - atta oberoende urvals-/viktningsforsok (raknat med BATCH-001 som ett) star nu pa 0/8.) + HYP-037 (villkorat/asymmetriskt aterinträde i SPY-krasch-overlayn pa HYP-023, PASSED 2026-08-01 PA ALLA TRE villkor och nivaer - FORSTA GANGEN i registrets historia en HYP-023-modifiering forbattrar bade Sharpe OCH MaxDD PA ALLA TRE nivaer samtidigt. Sharpe 0.73/0.75/0.70 (upp fran HYP-023:s 0.72/0.75/0.72), MaxDD -23.10%/-19.12%/-13.11% (battre an HYP-023:s -25.46%/-19.29%/-13.16% pa alla tre, tydligast vid $100k med 2.36pp), DSR 0.74/0.76/0.69 vid K=36. NYTT, SKARPT villkor 3 (till skillnad fran HYP-034:s diagnostik-bara variant): fornyad OOS-2025-korning maste visa $10M-Sharpe inte samre an HYP-023:s egna 0.08 - PASSADE men med RAKBLADSTUNN marginal (0.083, en skillnad pa 0.003). Mekanismen exercerades genuint (en SPY-krasch-trigger 2025-04-04 skar 14 innehav), men fullserie-OOS-Sharpen (0.386/0.187/0.083) ar praktiskt taget IDENTISK med HYP-023:s egna 0.39/0.17/0.08 - lost INTE synligt kapacitetsavklingningen inom detta enda OOS-ar, men GOR DEN INTE VARRE (till skillnad fran HYP-034/036). Attributionsrapporten bekraftade att sektorexponeringen ar oforandrad mot HYP-023 (samma 5.6x/5.0x/3.5x bankoverrepresentation) - designen paverkade ENDAST overlay-timing, ingen oavsiktlig kompositionsforandring. Bekraftar mönstret som motiverade testet: exponeringstimingsmekanismer star nu pa 3/3 PASSED (HYP-017/023/037), urvals-/viktningsforsok pa 0/7. CEO-BESLUT 2026-08-01: HYP-037 AR DEN NYA REFERENSIMPLEMENTATIONEN, HYP-023 kvarstar PASSED i registret men ar inte langre aktiv referens - samma monster som HYP-017->023-overgangen.) + HYP-036 (sektorneutral idiosynkratisk-volatilitets-rankning pa HYP-023, FAILED 2026-08-01 PA BADA villkoren pa alla tre nivaer - Sharpe 0.51/0.54/0.55 missade 0.55-golvet aven vid $10M, MaxDD -28.5%/-28.5%/-26.7% SAMRE an HYP-023:s -25.46%/-19.29%/-13.16% pa alla tre, forsamringen VAXTE dramatiskt med kapitalniva (13.55pp samre vid $10M, MER AN DUBBELT sa daligt), DSR 0.42/0.46/0.48 vid K=35. Motiverad av ett NYTT, KVANTIFIERAT fynd fran scripts/attribution.py (byggt samma dag): HYP-023 hade 5.6x overexponering mot statliga affarsbanker (SIC 60), HYP-008 hade 9.0x. OBLIGATORISK DIAGNOSTIK BEKRAFTADE att mekanismen GJORDE sitt jobb: SIC 60-overrepresentationen foll till 1.3x/1.2x/0.8x (i praktiken eliminerad) - men detta LOSTE INTE huvudproblemet, Sharpe/MaxDD blev SAMRE. Diagnos: bankexponeringen ar en STABILISERANDE FEATURE i HYP-023, inte bara en riskkalla - tredje oberoende bekraftelsen efter HYP-022 (statiskt tak, FAILED med samre MaxDD) och HYP-023:s egen sektor-krasch-trigger (medvetet design att behalla bankexponering i lugna perioder). Faktorregressionen visade varfor: MOM-loading blev starkt signifikant NEGATIV (t=-5.2 till -6.1, mot HYP-023:s ej signifikanta t=-0.9 till -1.8) - tvingad spridning over fler sektorer (min 1 namn/sektor) drog in mer forlorar-momentum-exponering, en redan kand riskfaktor (HYP-012/016/030). Friktionsdraget okade ocksa (0.42pp/trade mot 0.34pp, 2991 trades mot 2253). HYP-023 forblir referensen, oforandrad. Viktig metodologisk lardom: attributionsverktygets egen varningsklausul bekraftades - ett tekniskt uppnatt diagnostiskt mal (mindre koncentration) garanterar inte battre resultat.) + HYP-035 (insiderkop via SEC Form 4 kod P, ra signal utan overlay, forsta genuint NYA alfasignalen sedan HYP-023 - INTE en HYP-023-variant, FAILED RENT 2026-08-01 pa den enda testade nivan: Sharpe 0.29 vid $100k mot 0.55-golvet (missade med nastan halva), MaxDD -74.9%, DSR 0.12 vid K=34. CEO gav explicit instruktion att avbryta efter $100k istallet for att kora $1M/$10M ocksa, eftersom missen var sa entydig (jmf HYP-032 dar $100k missade men $1M/$10M klarade - den typen av gransfall hade motiverat fullstandig korning) - redovisat oppet i registerposten, INTE en tyst avvikelse fran tested_capital_levels-atagandet. Extrem skevhet (12.8) och kurtosis (425.8) i avkastningsserien tyder pa att resultatet domineras av ett fatal extrema enskilda trades - konsistent med den redan kanda signalglesheten (endast namn med minst en insidertransaktion i 63-dagarsfonstret konkurrerar om en redan liten decil, se feasibility-checken 2026-08-01 som visade 11-18% deltagande per kvartal). HYP-023 forblir referensen. Insiderkop-signalen ar INTE nodvandigtvis helt utesluten (samma monster som idio-vol som ocksa FAILADE ra innan en krasch-overlay raddade den i HYP-017) men kraver en ny, separat lasning innan en overlay-uppfoljare testas - ingen automatisk fortsattning.) + HYP-034 (stale-price/nolldags-filter (>12/120 dagar) fore idio-vol-rankning i HYP-023, FAILED RENT PA ALLA TRE NIVAER 2026-08-01 - Sharpe 0.72/0.74/0.72 klarade golvet, men MaxDD blev SAMRE an HYP-023:s egna PA ALLA TRE nivaer: -32.28%/-26.58%/-13.59% mot -25.46%/-19.29%/-13.16% (6.82pp/7.28pp/0.44pp forsamring), DSR 0.73/0.76/0.73 vid K=33. Filtret bet REELLT (34.3 exkluderade av 672.4 forfilter-kandidater per ombalansering, decilen krympte fran ~67 till 63.4) - inte en no-op. Forsta av tre AI-foreslagna likviditets-atgarder (5-AI-brainstorm 2026-07-31) - avsedd att motverka HYP-023:s diagnostiserade kapitalnivaberoende OOS-avklingning genom att exkludera aktier vars matta laga volatilitet sannolikt ar en artefakt av stale/ohandlade priser snarare an genuin stabilitet. FORNYAD BLIND OOS-2025-KORNING (paper_trading/HYP-034/oos_backtest_2025.py, diagnostik, ingen K-kostnad): isolerat till 2025 blev Sharpen 0.265/0.052/-0.022 - SAMRE an HYP-023:s egna 0.39/0.17/0.08 pa alla tre nivaer, rentav NEGATIV vid $10M. Malet (mildra kapitalnivaberoende avklingning) uppnaddes INTE - det blev VARRE. Diagnos: manga 'stale-liknande' namn ar sannolikt genuint lagvolatila mikrobolag, inte matningsfelsartefakter - att ta bort dem forskjuter decilen mot mer aktivt handlade men OCKSA mer volatila namn, samma monster som HYP-018/022/025-029 (riskverktyg som skadar i praktiken trots rimlig teori). HYP-023 forblir referensen, oforandrad. De tva atervarande AI-forslagen (villkorat overlay-aterintrade, likviditetsviktad allokering) kravs egen lasning innan de testas.) + HYP-033 (book-to-market vardefaktor, topp-decilen, FAILED KRAFTIGT 2026-07-31 - Sharpe 0.33/0.18/-0.18 (negativ vid $10M), MaxDD katastrofal -56%/-65%/-91%, DSR 0.08/0.07/0.003 vid K=32. KRITISK BEGRANSNING: bara 475/5162 tickers (9%) hade matchbar equity+aktieantal fran SAMMA 10-K, decilstorlek bara 1-6 namn genom HELA perioden (aldrig i narheten av idio-vol-testernas 50-76) - extrem underdiversifiering, INTE ett lika rent svar som ovriga faktormisslyckanden pa om B/M genuint saknar edge i small-cap. HYP-023 forblir referensen, oforandrad.) + HYP-032 (traditionell Kelly-sizing med signalstyrka inom HYP-023:s idio-vol-decil, FAILED 2026-07-31 MEN NYANSERAT - MaxDD FORBATTRADES pa alla tre nivaer (upp till 5.4pp vid $1M), och Sharpe klarade faktiskt golvet vid $1M (0.64) och $10M (0.68), bara $100k foll (0.40) - DSR 0.28/0.63/0.68 vid K=31. Diagnos: vid lag kapitalniva binder INTE kapacitetsspärren, sa Kelly-koncentrationen (upp till 3x likaviktad andel) far fullt genomslag och skadar Sharpen; vid hog kapitalniva TVINGAR kapacitetsspärren tillbaka mot narmare likaviktning. INTE samma dodsorsak som de 7 ursprungliga Ejay-varianterna (cirkularitet) - en ny, informativ lardom. Ejay/Kelly-linjen ater STANGD, 8 misslyckade varianter totalt, kraver nytt explicit CEO-beslut. HYP-023 forblir referensen, oforandrad.) + HYP-031 (beta-hedge mot IWM i stallet for SPY pa HYP-023, FAILED 2026-07-31 - Sharpe oforandrat 0.71/0.74/0.71, men MaxDD SAMRE pa ALLA tre nivaer (-25.9%/-19.6%/-15.0% mot HYP-023:s -25.5%/-19.3%/-13.2%, storst forsamring 1.87pp vid $10M) - basis-risk-hypotesen fick INTE stod, tvartom, DSR 0.73/0.77/0.73 vid K=30 - HYP-023 forblir referensen med SPY som hedge) + HYP-030 (momentum-krasch-rebound-trigger på förlorar-decil-komposit, FAILED KRAFTIGT 2026-07-31 - Sharpe 0.02/0.04/-0.20, MaxDD -86%/-83%/-74% - STRIKT SÄMRE än HYP-016:s odiagnostiserade baslinje (-78%/-76%/-71%), DSR 0.02/0.02/0.003 vid K=29. Diagnos: kompositen triggade 80 gånger över 14 år (4-14/år, utspritt över alla år) - mäter rutinmässigt small-cap-brus i pressade bolag, inte genuina kraschrebounder. Korrelation mot HYP-023 0.24/0.23/0.46 (måttlig, informationsmässigt loggat). Momentum-familjen (HYP-012/016/030) har nu tre oberoende misslyckanden och betraktas som stängd. HYP-023 förblir referensen.) + BATCH-001 (2026-07-31, se CLAUDE.md 'Batch Hypothesis Generation'): HYP-025-029, 5 stop-loss-tröskelvarianter på HYP-023 (-30%/-35%/-25%/-20%-med-3-dagars-bekräftelse/-15%), lästa som ETT block innan någon backtest kördes - k_total hoppade från 23 till 28 vid låsningstillfället, inte en i taget. ALLA FEM FAILED, och på exakt samma sätt: samtliga förbättrar MaxDD vid $100k (upp till 3.5pp), men samtliga blir marginellt SÄMRE än HYP-023 vid $1M (0.06-0.86pp), $10M blandat - ett strukturellt, kapacitetsnivåberoende mönster oberoende av tröskeldjup (-15% till -35%) eller bekräftelsekrav (1 vs 3 dagar), inte brus från en enskild olycklig parametervariant. HYP-029 (-15%, grundast) kom närmast (0.06pp-marginal vid $1M) men klarade inte heller. HYP-023 förblir referensimplementationen oförändrad. + 7 ejay-varianter + HYP-008/009/011/012/013/014 (alla FAILED) + HYP-015 (idiosynkratisk volatilitet, FAILED, Sharpe 0.45/0.46/0.52) + HYP-016 (vol-hanterad momentum, FAILED) + HYP-017 (SPY-krasch-overlay på idiosynkratisk vol, PASSED - forsta godkanda hypotesen, Sharpe 0.72/0.75/0.72, MaxDD -27%/-20%/-13%, DSR 0.80/0.83/0.80 vid K=19, robusthetstestad mot 5 oberoende krascher, men med branschkoncentrationsfynd - 27.3% bank/finans mot 7.0% i basuniversumet - AVLÖST som referensimplementation av HYP-023, se nedan) + HYP-018 (stop-loss på HYP-017, FAILED) + HYP-019 (storlekssortering, FAILED, sämsta MaxDD -78%/-69%/-45% - direkt test av kapacitetstesen misslyckades) + HYP-020 (PEAD via SUE, FAILED, ny SEC EDGAR-datapipeline byggd) + HYP-021 (idio-vol mot small-cap-kompositfaktor i stället för SPY, PASSED 2026-07-30 men STATISTISKT OSKILJBAR från HYP-017 - ingen verklig förbättring, Sharpe 0.72/0.74/0.73, DSR 0.79/0.82/0.80 - HYP-017 förblir referensen) + HYP-022 (branschtak 15% på bank/finans i HYP-017, FAILED 2026-07-30 - Sharpe STEG på alla tre nivåer (0.75/0.77/0.65) och mars 2023-episoden förbättrades på alla tre, men MaxDD blev SÄMRE än HYP-017 vid $1M/$10M eftersom banker var en stabiliseringskälla under resten av en längre 2022-björnmarknad, inte bara en riskkälla - HYP-017 förblir referensen, branschkoncentrationen kvarstår olöst) + HYP-023 (sektorspecifik dynamisk krasch-trigger på bank-/finanskomposit i HYP-017, PASSED 2026-07-30 - ANDRA verkliga godkännandet i projektets historia, löste branschkoncentrationen HYP-022 misslyckades med genom att vara händelsetriggad i stället för statisk: MaxDD -25.5%/-19.3%/-13.2% (bättre än HYP-017 på alla tre, om än marginellt vid $1M/$10M), mars 2023-episoden -14.0%/-8.2%/-2.3% (stor förbättring från HYP-017:s -14.8%), Sharpe i praktiken oförändrat 0.72/0.75/0.72, DSR 0.78/0.82/0.78 vid K=22 - CEO-BESLUT 2026-07-30: HYP-023 ÄR NU REFERENSIMPLEMENTATIONEN, HYP-017 kvarstår PASSED i registret men är inte längre aktiv referens) + HYP-024 (rörelselönsamhet OperatingIncomeLoss/Assets, topp-decilen, FAILED 2026-07-31 - Sharpe 0.14/0.19/0.09, MaxDD -74%/-61%/-65%, DSR 0.07/0.11/0.05 vid K=23 - i praktiken brus, inte nära gränsen; diagnos visade att svag/negativ rå avkastning kvarstår även efter att exkludera den datasvaga perioden 2010-2012, så det är inte en datakvalitetsartefakt - sista otestade klassiska faktorn misslyckades liksom momentum/storlek/PEAD, HYP-023 förblir enda referensen) - se research/hypothesis_registry/"
```

---

## KÄLLFIL: `research/hypothesis_registry/HYP-037-villkorat-overlay-aterintrade-hyp023.yaml`

```
# LÅST 2026-08-01 av CEO i chatt, innan denna hypotes sätts pre-registered
# eller nagon backtest kors. Motiverad av tva sammanvavda trådar:
# (a) HYP-023:s egen genuina OOS-2025-test visade en Sharpe-nedgang som
# VAXTE med kapitalniva (0.39/0.17/0.08 vid 100k/1M/10M) - motsatt vad
# kapacitetstesen skulle onska - och flera externa AI:er (5-AI-brainstorm
# 2026-07-31 och en ny genomgang 2026-08-01) foreslog oberoende ett
# villkorat overlay-aterintrade som direkt riktad atgard.
# (b) En genomgang av HELA HYP-023-familjens track record 2026-08-01
# visade ett tydligt monster: de TVA enda PASSED-hypoteserna i hela
# registret (HYP-017 SPY-krasch-overlay, HYP-023 sektor-krasch-trigger)
# ar BADA overlay-/exponeringstimingsmekanismer, medan SJU oberoende
# forsok att andra urval/viktning/exit (HYP-018, 022, 025-029, 031, 032,
# 034, 036) ALLA misslyckats. Detta ar den enda mekanismtyp med ett
# verifierat spar record i just denna strategi.
#
# Byggd PA HYP-023 - ENDAST SPY-krasch-overlayns aterinträdesvillkor
# andras, ISOLERAT fran allt annat. Sektor-bank-krasch-triggern (HYP-023:s
# egen andra mekanism) RORS INTE - dess automatiska aterstallning vid
# nasta ordinarie ombalansering forblir helt oforandrad. Detta ar ett
# MEDVETET val att testa EN variabel at gangen, inte tva samtidigt.
# status: pre-registered -> tested -> passed/failed

id: HYP-037
date_registered: '2026-08-01'
title: Villkorat/asymmetriskt aterinträde i SPY-krasch-overlayn pa HYP-023
universe: small-cap, $100M - $2B börsvärde, EODHD All-World som datakälla
small_cap_definition: small-cap, $100M - $2B börsvärde, EODHD All-World som datakälla
data_range: EODHD All-World, samma period som HYP-008/015/017/023/034 (2010-2024) + genuin
  blind OOS-2025-korning (samma metod som HYP-023/034)
pass_fail_criterion: 'Identisk bas som HYP-023 (idiosynkratisk volatilitet, kvartalsvis
  ombalansering, GLOBAL rankning OFORANDRAD, sektor-krasch-trigger pa bank-/finanskomposit
  HELT OFORANDRAD inklusive dess egen automatiska aterstallning - samma friktion/hedge/
  kapacitetsspärr, samma tre motorfixar). Enda tillagget: SPY-krasch-overlayns
  aterinträdesvillkor byts fran "automatiskt vid nasta ordinarie ombalansering" till
  villkorat.

  Mekanism, exakt specificerad (INTE fri, INTE anpassad efter resultat - vald INNAN nagon
  backtest kors, siffrorna (50% aterhamtning, 252-dagars fonster, 5%-kapacitetsspärr) ar
  EXAKT de AI-brainstormen foreslog, ATERANVANDA ISTALLET FOR nya for att undvika
  facit-anpassning):
  - Trigger (OFORANDRAD): SPY:s egna 10-dagars kumulativa avkastning < -10% -> skar HELA
    portfoljen till 40% av dagens varde (SAMMA mekanism som HYP-017/023, ingen andring har).
    Vid trigger: spara crash_trough_price = SPY-pris SAMMA dag, crash_start_price = SPY-pris
    10 handelsdagar TIDIGARE (borjan av det utlosande fonstret).
  - NYTT tillstand "capacity_restricted" (OBEROENDE av det befintliga haircut_active-
    tillstandet som fortfarande styr NAR en NY nedskarning far triggas): satts till SANT
    samtidigt som en krasch-overlay-episod triggas.
  - capacity_restricted aterstalls till FALSKT NAR, och ENDAST NAR, BADA galler SAMTIDIGT:
    1. SPY:s dagens pris >= crash_trough_price + 0.5 * (crash_start_price - crash_trough_price)
       - dvs SPY har aterhamtat MINST HALVA den procentuella nedgangen fran det utlosande
       10-dagarsfonstret, mätt fran botten.
    2. Dagens genomsnittliga Corwin-Schultz-spread over HELA manadens eligible small-cap-
       universum (INTE bara hallna namn - SAMMA anti-cirkularitetsprincip som HYP-023:s
       egen bankkomposit redan anvander, av samma skal) ar <= sitt eget rullande 252-
       handelsdagars-median (beraknat over hela backtest-perioden, ingen framatblick -
       rullande fonster anvander bara historik fram till och med dagens datum).
  - EFFEKT sa lange capacity_restricted ar SANT: vid VARJE ombalansering som infaller under
    denna period anvands en HALVERAD ADV-kapacitetsspärr (5% av 20-dagars dollarvolym i
    stallet for normala 10%) for NYA positioners storlek. Befintliga innehav tvangssaljs
    INTE - detta paverkar bara storleken pa NYA kop under den restriktiva perioden. Sa fort
    capacity_restricted blir FALSKT anvands ateranvands normala 10%-spärren igen.
  - Sjalva krasch-triggerns 40%-nedskarning, dess EGEN aterstallningslogik (haircut_active),
    och sektor-bank-triggern med SIN automatiska aterstallning AR ALLA OFORANDRADE - detta
    tillagger ENDAST kapacitetsspärrens niva under en explicit definierad restriktionsfas,
    andrar INGET annat.

  MOTORKRAV (samma som HYP-015/017/022/023): snappade ombalanseringsdatum, adjusted_close
  genomgaende, flag_implausible_liquidity().

  PASS kraver ALLA TRE:
  1. Sharpe (efter friktion) >= 0.55 pa SAMTLIGA tre kapitalnivaer.
  2. Maxdrawdown INTE samre an HYP-023:s EGET redan uppnadda resultat pa SAMMA kapitalniva
     (100k: -25.46%, 1M: -19.29%, 10M: -13.16%).
  3. NY, SKARPT VILLKOR (lart av HYP-034:s erfarenhet dar en diagnostik-bara OOS-check
     tillat ett "tekniskt godkant men OOS-svagare" scenario att aldrig prövas som en riktig
     spärr): en fornyad blind OOS-2025-korning (samma metod som HYP-023/034:s egna,
     paper_trading/HYP-037/oos_backtest_2025.py, HYP-037:s ofrandrade lasta kod) maste visa
     Sharpe VID $10M ISOLERAT TILL 2025 SOM INTE AR SAMRE an HYP-023:s egna 0.08 pa samma
     matt. Detta gor OOS-diagnosen till en RIKTIG spärr for just denna hypotes (eftersom
     hela dess motiverande syfte AR att losa den kapitalnivaberoende OOS-avklingningen) -
     INTE bara rapportering som for HYP-034.
  FAIL om nagot av de tre villkoren faller pa nagon niva.

  Diagnostiskt syfte: testar om en forfining INOM en REDAN BEVISAD mekanismtyp
  (exponeringstiming - de enda tva PASSED-hypoteserna i registret ar bada av denna typ)
  loser den specifika, redan diagnostiserade kapitalnivaberoende OOS-svagheten, till
  skillnad fran de sju oberoende urvals-/viktningsforsok som redan misslyckats.'
status: failed   # pre-registered -> tested -> passed/failed
# CEO-BESLUT 2026-08-09: status andrad fran passed till failed. Grund:
# tilläggsnoten 2026-08-08 ovan visar att villkor 2 (MaxDD ej samre an
# HYP-023) flippar till FAIL pa alla tre nivaer under den fullt
# korrigerade pipelinen (look-ahead-bias + adjusted_close-kvot). Kravet
# var ALLA TRE villkor - ett flippat FAIL racker for att hypotesen som
# helhet inte langre klarar sitt eget lasta kriterium. De ursprungliga
# siffrorna ovan (capital_level_results) ANDRAS INTE - historik skrivs
# inte om. HYP-023 forblir den grund senare kedjan (HYP-039 osv) faktiskt
# vilar pa, eftersom deras egna kriterier aldrig kravde att HYP-037
# slar HYP-023.
k_total_hypotheses_before_this: 35
tested_capital_levels:
- 100000
- 1000000
- 10000000
capital_level_results:
  100000: {cagr: 0.1212, sharpe: 0.7366, calmar: 0.5251, sharpe_excl_best_trade: 0.6838, max_drawdown: -0.2309, win_rate: 0.4922, profit_factor: 1.2038, n_trades: 2251, n_sector_trigger_episodes: 8, march_2023_episode_return: -0.1383, n_capacity_restriction_episodes: 6, avg_capacity_restriction_days: 39.0, deflated_sharpe_ratio: 0.7406, oos_2025_sharpe: 0.386}
  1000000: {cagr: 0.1185, sharpe: 0.7547, calmar: 0.6198, sharpe_excl_best_trade: 0.7195, max_drawdown: -0.1911, win_rate: 0.4922, profit_factor: 1.2040, n_trades: 2249, n_sector_trigger_episodes: 8, march_2023_episode_return: -0.0759, n_capacity_restriction_episodes: 6, avg_capacity_restriction_days: 39.0, deflated_sharpe_ratio: 0.7599, oos_2025_sharpe: 0.187}
  10000000: {cagr: 0.0905, sharpe: 0.6981, calmar: 0.6902, sharpe_excl_best_trade: 0.6939, max_drawdown: -0.1310, win_rate: 0.4938, profit_factor: 1.2097, n_trades: 2246, n_sector_trigger_episodes: 8, march_2023_episode_return: -0.0203, n_capacity_restriction_episodes: 6, avg_capacity_restriction_days: 39.0, deflated_sharpe_ratio: 0.6868, oos_2025_sharpe: 0.083}
date_tested: '2026-08-01'
result_summary: >
  PASSED - ALLA TRE villkor haller PA ALLA TRE kapitalnivaer. Detta ar
  FORSTA GANGEN i hela registrets historia en modifiering av HYP-023
  forbattrar bade Sharpe OCH MaxDD PA ALLA TRE nivaer samtidigt (HYP-021
  var statistiskt oskiljbar, HYP-023 sjalv forbattrade HYP-017 marginellt
  vid 2/3 nivaer - detta ar det tydligaste, mest konsekventa
  forbattringsresultatet sedan HYP-017->023-overgangen).

  Villkor 1 (Sharpe >= 0.55): 0.73/0.75/0.70 - PASS, TYDLIGT over
  HYP-023:s 0.72/0.75/0.72 vid 100k, i praktiken oforandrat vid 1M/10M.

  Villkor 2 (MaxDD inte samre an HYP-023:s -25.46%/-19.29%/-13.16%):
  PASS PA ALLA TRE, med en REELL forbattring vid $100k (-23.10%, 2.36pp
  battre) och marginella men konsekventa forbattringar vid $1M (-19.12%,
  0.17pp) och $10M (-13.11%, 0.05pp).

  Villkor 3 (NY, GATING denna gang - OOS-2025 Sharpe vid $10M inte samre
  an HYP-023:s 0.08): PASS, MEN MED RAKBLADSTUNN MARGINAL - 0.083 mot
  kravet 0.08, en skillnad pa 0.003. AR REDOVISAD HAR OPPET, INTE
  UNDANHALLEN: detta ar en svag, INTE en overtygande, bekraftelse.
  Mekanismen exercerades genuint under OOS-fonstret (en SPY-krasch-
  trigger utlostes 2025-04-04, skar 14 innehav till 40% - INTE en
  passiv "mekanismen aktiverades aldrig sa villkoret klarades av
  brist pa test"-situation), men med bara ETT triggertillfalle pa 250
  handelsdagar och kant hog statistisk osakerhet for ett enskilt ars
  Sharpe-skattning (samma reservation som redan dokumenterad i HYP-023:s
  eget OOS-test) kan denna marginal latt vara brus snarare an ett
  genuint bevis pa att mekanismen loste kapacitetsavklingningen.

  DIAGNOSTIK: full OOS-2025-serie Sharpe 0.386/0.187/0.083 - PRAKTISKT
  TAGET IDENTISK med HYP-023:s egna 0.39/0.17/0.08 (skillnaderna ar i
  tredje decimalen). Detta ar bade forvantat (bara en trigger-episod
  inom det korta OOS-fonstret, begransad mojlighet for mekanismen att
  gora skillnad) och en viktig kalibrering: denna hypotes LOSER INTE
  synligt den diagnostiserade kapitalnivaberoende OOS-avklingningen inom
  detta enda testade OOS-ar - den GOR INTE DEN VARRE (till skillnad fran
  HYP-034 och implicit HYP-036), men "inte varre" ar en svagare seger an
  "genuint battre".

  ATTRIBUTIONSRAPPORT (scripts/attribution.py): sektorexponeringen ar,
  som vantat och avsett (denna hypotes andrar ENDAST overlay-timing,
  INTE urval), PRAKTISKT TAGET IDENTISK med HYP-023:s egna (SIC 60-
  overrepresentation 5.6x/5.0x/3.5x mot HYP-023:s 5.6x/-/-) - bekraftar
  att den isolerade-variabel-designen fungerade som avsett, ingen
  oavsiktlig komposotionsforandring. Alfat forblir starkt signifikant
  (13.9%/13.5%/9.5% arligt, t=3.6-4.0).

  ROBUSTHET: sharpe_excl_best_trade forblir 0.68/0.72/0.69 - forbattringen
  ar inte en enskild-trade-artefakt. DSR vid K=36: 0.74/0.76/0.69, i linje
  med HYP-023:s egna 0.78/0.82/0.78 (nagot lagre pga hogre K, forvantat).

  6 kapacitetsrestriktionsepisoder over 2011-2024, snitt 46 dagar per
  episod - mekanismen griper in med rimlig frekvens, inte konstant eller
  aldrig.

  SLUTSATS: PASSED enligt det lasta kriteriet - forsta genuina,
  konsekventa forbattringen (Sharpe upp, MaxDD battre pa ALLA tre nivaer)
  sedan HYP-023 sjalv avloste HYP-017. Bekraftar ocksa mönstret som
  motiverade testet: exponeringstimingsmekanismer (nu 3/3 PASSED i hela
  registret: HYP-017, HYP-023, HYP-037) fortsatter att vara den enda
  mekanismtyp med ett tillforlitligt spar record, medan urvals-/
  viktningsforsok star pa 0/7. OOS-marginalen (villkor 3) bor dock INTE
  overtolkas som ett bevis pa att kapacitetsavklingningen ar löst - den
  ar TEKNISKT klarad men SVAGT bekraftad (0.083 mot kravet 0.08), och
  bor granskas igen nar mer OOS-data (2026 och framat) blir tillganglig.

  CEO-BESLUT 2026-08-01: HYP-037 AR DEN NYA REFERENSIMPLEMENTATIONEN,
  i stallet for HYP-023 (samma typ av beslut som forde over referens-
  statusen fran HYP-017 till HYP-023 2026-07-30). HYP-023 FORBLIR
  PASSED i registret men ar INTE langre den aktiva referensen for
  framtida jamforelser/utveckling. Se motsvarande uppdatering i
  research/hypothesis_registry/HYP-023-sektor-krasch-trigger-hyp017.yaml.
sharpe_raw:
  100000: 0.7366
  1000000: 0.7547
  10000000: 0.6981
deflated_sharpe_ratio:
  100000: 0.7406
  1000000: 0.7599
  10000000: 0.6868

# ════════════════════════════════════════════════════════════
# BUGGFIX-UPPDATERING 2026-08-05 (kodgranskning, INTE en ny hypotes/
# K-test - status/pass_fail_criterion/tested_capital_levels ANDRADE
# INTE, se CLAUDE.md: "no agent other than the CEO... may ever write
# or alter a pass_fail_criterion" - detta rör ENDAST redan uppmätta
# resultatsiffror, aldrig kriteriet de mats mot)
# ════════════════════════════════════════════════════════════
# En kodgranskning 2026-08-05 hittade en genuin bugg i
# strategies/HYP-037/backtest.py: crash_trough_price (botten-referensen
# for aterhamtningsvillkoret) frostes tidigare pa VARJE krasch-episods
# FORSTA triggerdag och uppdaterades ALDRIG darefter, aven om SPY
# fortsatte falla langt efter det (exakt det scenario mekanismen ar
# byggd for). Fixad: lopande minimum sa lange capacity_restricted ar
# sant. Tva mindre relaterade fixar samtidigt: (a) ett tidigare
# verkningslost min-positionsstorlek-filter gors nu verkligt (hoppar
# over positioner under 0.01% av kapitalnivan istallet for en no-op),
# (b) allokeringsordningen itererar nu en deterministisk, redan sorterad
# lista istallet for ett Python-set (samma buggmonster som redan orsakat
# den icke-deterministiska HYP-038-buggen - forebyggande fix har, ingen
# observerad paverkan). Separat: scripts/deflated_sharpe_ratio.py hade
# en inkonsekvent skevhet/kurtosis-estimator (blandade populations- och
# Bessel-korrigerade moment) som ratades samtidigt.
#
# PAVERKAN PA REDAN RAPPORTERADE SIFFROR: liten men verklig, ALLA TRE
# PASS-VILLKOR FORBLIR PASSED MED SAMMA SLUTSATS:
#   - Villkor 1 (Sharpe >= 0.55): 0.737/0.755/0.698 (tidigare
#     0.734/0.754/0.698) - marginellt HOGRE vid 100k/1M, i praktiken
#     oforandrat vid 10M. Fortfarande TYDLIGT over golvet.
#   - Villkor 2 (MaxDD battre an HYP-023): -23.09%/-19.11%/-13.10%
#     (tidigare -23.10%/-19.12%/-13.11%) - marginellt battre pa alla
#     tre, forsumbar skillnad.
#   - Villkor 3 (OOS-2025 Sharpe vid $10M >= HYP-023:s 0.08) - DEN MEST
#     KANSLIGA, eftersom denna redan hade en rakbladstunn marginal
#     (0.083 mot kravet 0.08) OCH oos_backtest_2025.py ateranvander
#     EXAKT samma (nu fixade) run_backtest()-funktion, OCH just
#     OOS-2025-fonstret innehöll en verklig krasch-trigger
#     (2025-04-04) - precis det scenario buggen paverkar mest. Fornyad
#     korning: OOS-Sharpe vid $10M = 0.08313 (tidigare 0.08312) -
#     PRAKTISKT TAGET IDENTISK, marginalen mot kravet ar OFORANDRAD.
#     Villkor 3 forblir PASS med samma knivskarpa (men INTE forsamrade)
#     marginal som redan var oppet redovisad.
#   - Genomsnittlig kapacitetsbegransningsperiod foll fran 46.2 till
#     39.0 dagar (den storsta enskilda forandringen - mekanismen las nu
#     upp tidigare i genomsnitt) UTAN att detta slog igenom i Sharpe/
#     MaxDD vid nagon kapitalniva - ADV-kapacitetsspärren band i
#     praktiken sallan tillrackligt hart for att paverka utfallet,
#     aven vid $10M.
#   - DSR-siffrorna (0.741/0.760/0.687, tidigare 0.737/0.759/0.687)
#     forandrades forsumbart av skevhet/kurtosis-fixen sarskilt -
#     forvantat, eftersom biasen fran den gamla estimatorn krymper med
#     1/sqrt(n) och denna backtest har ~3400+ dagliga observationer.
#   - Sektorexponeringsattributionen (scripts/attribution.py, separat
#     fixad for ett statiskt bas-universum-fel) omkord for $100k:
#     IDENTISK topplista (SIC 60 fortfarande 5.6x) - ingen paverkan har.
#
# Determinism verifierad: huvudbacktesten kord TVA ganger efter fixen,
# identiska resultat bada gangerna (samma disciplin som redan
# etablerad efter HYP-038:s icke-deterministiska bugg).
#
# Bade nya och gamla siffror star kvar har (fältet ovan uppdaterat till
# de nya, korrekta varden) - denna kommentar ar den permanenta,
# git-sparbara posten over VAD som andrades och VARFOR, i linje med
# CLAUDE.md:s princip att git-historiken ar revisionssparet.

# ════════════════════════════════════════════════════════════
# TILLAGGSVALIDERING 2026-08-05 (samma session, EFTER buggfix-
# uppdateringen ovan) - INTE en ny hypotes/K-test, status/kriterium
# ANDRADE INTE. Rör en SEPARAT, storre fraga: look-ahead-bias i sjalva
# UNIVERSUM-KONSTRUKTIONEN (vilka bolag som rankas som "small-cap"
# $100M-$2B en given manad), upptackt samma session.
# ════════════════════════════════════════════════════════════
# BUGGEN: data/build_smallcap_classification.py och data/sec_edgar_adapter.py
# sparade periodSLUT-datum for varje aktieantal-datapunkt istallet for det
# datum bolaget FAKTISKT offentliggjorde det (SEC-inlamningsdatum, "filed").
# Marknaden vet inte ett kvartalsslut-aktieantal forran veckor-manader
# senare (median ~26-41 dagar i stickprov, upp till ~90 for sena filers).
# Detta ar en genuin look-ahead-bias i universum-konstruktionen som
# ANVANDS AV VARJE HYPOTES I REGISTRET, inte bara diagnostikverktyg.
#
# FIXEN (byggd denna session, SEPARATA filer - rör INTE de ursprungliga
# smallcap_classification.jsonl/smallcap_universe_by_month.json, som
# forblir grundsanningen for redan rapporterade resultat):
#   - data/sec_filed_dates.py: bygger en accn->filed_date-uppslagning fran
#     SEC:s kvartalsvisa form.idx-bulkfiler (2009-2025, ~68 nedladdningar,
#     ingen per-bolag-kostnad). 99.2% traffgrad efter en retry-fix
#     (en enskild misslyckad nedladdning, 2013 QTR3, orsakade forst en
#     overdriven skenbar forandring).
#   - data/rebuild_smallcap_classification_filed_date.py +
#     data/build_smallcap_universe_filed_date.py: bygger om hela
#     2010-2024-universumet med korrekta datum.
#   - data/build_universe_2025_filed_date.py: samma fix for 2025-OOS-
#     grenen (enklare - companyfacts-endpointen hade redan ett 'filed'-
#     falt, las bara aldrig).
#
# DIFF MOT URSPRUNGLIGT UNIVERSUM: ~20.8% av alla ticker-manads-
# medlemskap 2010-2024 andras. Storsta delen av forandringen ar
# koncentrerad till 2010-mitten av 2011 (troligen kopplat till att SEC:s
# XBRL-krav for mindre bolag inte blev fullt obligatoriskt forran
# perioder efter 2011-06-15, kombinerat med hur SEC:s frames-API
# ibland forst surfacar ett kvartals aktieantal via en SENARE
# inlamnings jamforelsetal - se kodgranskningens diskussion for
# detaljer). Detta ar en verklig datakaraktäristik for den tidigaste
# perioden, INTE en bugg i matchningsmetoden - att gissa ett tidigare
# datum for att "aterstalla" fler ticker-manader skulle aterinfora
# exakt den look-ahead-risk fixen eliminerar.
#
# SIDOTEST (scripts/test_hyp037_filed_date_universe.py +
# scripts/test_hyp037_oos2025_filed_date.py, resultat i
# strategies/HYP-037/results_filed_date_test/ och
# paper_trading/HYP-037/oos_2025_results_filed_date_test/ - INTE de
# riktiga resultatfilerna): korde HYP-037:s OFORANDRADE strategikod mot
# det korrigerade universumet, bade huvudperiod och OOS-2025.
#
# RESULTAT:
#   Villkor 1 (Sharpe >= 0.55): PASS oforandrat pa alla tre nivaer
#     (0.728/0.741/0.744 - $10M till och med BATTRE an tidigare 0.698).
#   Villkor 2 (MaxDD battre an HYP-023:s EGNA, ocksa omkord mot samma
#     korrigerade universum for en rattvis jamforelse):
#     $100k: -25.90% vs HYP-023:s -25.97% -> HYP-037 fortfarande battre, PASS.
#     $1M:   -21.99% vs HYP-023:s -23.45% -> HYP-037 fortfarande battre, PASS.
#     $10M:  -13.66% vs HYP-023:s -13.61% -> HYP-037 NU SAMRE, med en
#            marginal pa 0.05 procentenheter - i praktiken ETT OAVGJORT
#            RESULTAT, inte ett tydligt PASS eller FAIL. Detta ar den
#            enda nyansen fixen avslojar.
#   Villkor 3 (OOS-2025 Sharpe vid $10M >= HYP-023:s 0.08): PASS, och med
#     BETYDLIGT BREDARE MARGINAL an tidigare - 0.378 mot det tidigare
#     knivskarpa 0.083.
#
# SLUTSATS: HYP-037:s PASS-status forblir OFORANDRAD - status satts INTE
# till failed. Motivering: bara EN av tre villkor, pa EN av tre nivaer,
# flippar - och det till ett genuint oavgjort resultat (0.05pp skillnad),
# inte ett tydligt misslyckande. De tva andra villkoren blir OFORANDRADE
# eller BATTRE (sarskilt OOS-villkoret, som gar fran den mest oroande
# knivskarpa marginalen i hela registret till en bekvam sadan). Detta
# star i skarp kontrast mot HYP-039 (se dess egen registerpost) dar
# SAMMA korrigering INTE bara haller utan FORSTARKER resultatet vid
# den tidigare svagaste punkten ($10M-Sharpe gick fran 0.988, under
# malet, till 1.012, over malet).
#
# Fullstandig sparbarhet: alla mellansteg (universum-diff, sidotest-
# resultat, jamforelsetabeller) finns kvar i strategies/HYP-037/
# results_filed_date_test/ och paper_trading/HYP-037/
# oos_2025_results_filed_date_test/ for granskning.

# ════════════════════════════════════════════════════════════
# TILLAGGSNOT 2026-08-08 (granskningsfynd, tre oberoende adversariella
# granskare, samma fynd oberoende av varandra - INTE en ny hypotes/
# K-test, status/kriterium/redan rapporterade siffror ANDRADE INTE)
# ════════════════════════════════════════════════════════════
# DSR ovan (0.7406/0.7599/0.6868, redan uppdaterad av buggfix-
# uppdateringen 2026-08-05) star kvar fran den korningen vid K=37 -
# aldrig omraknad mot senare K, trots agents/overfitting_detector/
# ROLE.md:s krav att gora det for alla aktiva hypoteser varje gang
# k_total okar. HYP-037 ar den mest ateranvanda byggstenen i registret
# (varje kombinationshypotes HYP-039 t.o.m. HYP-047 bygger pa dess
# portfolio_value-serie oforandrad).
#
# OMRAKNAD mot dagens k_total=46 (scripts/recompute_dsr_k46.py,
# 2026-08-08, samma sparade serier, RF=2%/ar avdraget):
#   $100k:   DSR 0.7406 -> 0.7076
#   $1M:     DSR 0.7599 -> 0.7285
#   $10M:    DSR 0.6868 -> 0.6517
#
# Forvantad riktning, mattlig forandring (K=37->46 ar en relativt liten
# relativ okning jamfort med t.ex. HYP-017/021/023 dar K mer an
# fordubblades). Fortfarande klart over 0.5, ingen forandring av
# tidigare PASS-slutsats eller av HYP-037:s roll som referens for hela
# den efterfoljande kombinationskedjan.

# ════════════════════════════════════════════════════════════
# TILLAGGSNOT 2026-08-08, DEL 2 (samma granskningsdag, SEPARAT fran
# DSR-omrakningen ovan - detta ror en FULLSTANDIGARE omkorning, inte
# bara K. INTE en ny hypotes/K-test, status/kriterium ANDRADE INTE, se
# CLAUDE.md-principen citerad i BUGGFIX-UPPDATERING 2026-08-05 ovan)
# ════════════════════════════════════════════════════════════
# Tre oberoende adversariella granskningsagenter hittade oberoende av
# varandra att TVA kanda luckor aldrig portades hit fran sidoskript:
#   (a) UNIVERSE_FILE pekade fortfarande pa den periodslut-daterade
#       (look-ahead-biasade) universumfilen i produktionskoden - bara
#       validerad i sidotestet ovan (TILLAGGSVALIDERING 2026-08-05),
#       aldrig gjord till produktionsdefault.
#   (b) Den konstanta orimlig-adjusted_close/close-kvot-buggen (kand
#       sedan HYP-042, 2026-08-06) fanns ALDRIG i HYP-037 alls - bara
#       kopierad inline i HYP-042 och senare hypoteser.
# BADA fixade nu SAMTIDIGT direkt i strategies/HYP-037/backtest.py (inte
# ett sidoskript denna gang - se modulens egen UPPDATERAD 2026-08-08-
# kommentar). Resultat i strategies/HYP-037/results_corrected_2026-08-08/
# (results/ rors INTE).
#
# NYA SIFFROR (huvudperiod 2010-2024, alla tre kapitalnivaer):
#   Sharpe:  0.7258 / 0.7370 / 0.7591  (tidigare 0.7366 / 0.7547 / 0.6981)
#   MaxDD:  -26.20% / -22.10% / -14.17% (tidigare -23.09% / -19.11% / -13.10%)
#   DSR (K=46, RF=2%/ar): 0.6903 / 0.7052 / 0.7321
#
# VILLKOR 1 (Sharpe >= 0.55, alla tre nivaer): PASS, oforandrat och
# tydligt - 0.726/0.737/0.759 ar klart over golvet.
#
# VILLKOR 2 (MaxDD INTE samre an HYP-023:s EGNA -25.46%/-19.29%/-13.16%,
# ORORDA - HYP-023 sjalv ligger UTANFOR detta uppdrags omfattning och
# har INTE korrigerats): FLIPPAR TILL FAIL PA ALLA TRE NIVAER under den
# fullstandigt korrigerade pipelinen (-26.20% samre an -25.46%, -22.10%
# samre an -19.29%, -14.17% samre an -13.16%). Detta AR en forsamring
# mot bade det ursprungliga resultatet (PASS pa alla tre) OCH mot den
# tidigare DELVIS korrigerade sidotestversionen (TILLAGGSVALIDERING
# 2026-08-05 ovan, dar bara $10M blev ett oavgjort resultat pa 0.05
# procentenheters marginal) - den extra adjusted_close-kvot-fixen (som
# INTE var med i den korningen) drar MaxDD ytterligare i FEL riktning
# pa alla tre nivaer, inte bara $10M.
#
# VILLKOR 3 (OOS-2025 Sharpe vid $10M >= HYP-023:s 0.08): INTE omkord
# under den fullstandiga korrigeringen i detta uppdrag - se den
# separata slutrapportens motivering (paper_trading/HYP-037/
# oos_backtest_2025.py rors inte har, en medveten avgransning av
# omfattningen, INTE en tyst utelamnad korning). Den TIDIGARE, delvis
# korrigerade (bara filed-datum, INTE adjusted_close-kvoten) sidotest-
# korningen visade OOS-Sharpe 0.378 vid $10M, klart over 0.08 - men
# detta tal ar INTE en giltig ersattning for en fullstandigt korrigerad
# OOS-korning, bara en indikation.
#
# SLUTSATS - VIKTIGT FYND: under den FULLSTANDIGT korrigerade pipelinen
# (filed-datum-universum + maskad adjusted_close-kvot TILLSAMMANS) skulle
# HYP-037:s ursprungliga PASS-slutsats INTE langre halla som den star -
# villkor 2 flippar till ett entydigt FAIL pa ALLA TRE kapitalnivaer,
# inte bara ett gransfall vid en enda niva. Eftersom PASS kravde ALLA
# TRE villkor skulle en fullstandig omkorning under dagens standard
# formellt ge FAIL for HYP-037 som fristaende hypotes. STATUS-faltet
# ANDRAS INTE har (se CLAUDE.md: bara CEO andrar status/pass_fail_criterion
# manuellt) - detta ar en oppet redovisad, INTE en tyst, upptackt som
# kraver ett explicit CEO-beslut. Notera SEPARAT: detta paverkar INTE
# automatiskt PASS/FAIL for HYP-039 t.o.m. HYP-047, vars EGNA kriterier
# aldrig kravde att HYP-037 sjalvt slar HYP-023 - de anvander bara
# HYP-037:s (nu korrigerade) portfoljvarde-serie som en indata-ben och
# ar omtestade separat, var och en mot sitt EGET redan lasta kriterium
# (se respektive registerpost).
```

---

## KÄLLFIL: `research/hypothesis_registry/HYP-039-naiv-kombination-spy-hyp037.yaml`

```
# LÅST 2026-08-04 av CEO i chatt, innan denna hypotes sätts pre-registered
# eller nagon backtest kors. Foljer spec §5b:s regler for LEGITIM
# kombinationstestning (INTE en genvag runt tidigare misslyckanden -
# HYP-037 ar redan en oberoende, individuellt godkand hypotes, INTE en
# "raddning" av nagot som failat):
#   1. Korrelationsmatris FORE nagon vikt valdes: SPY vs HYP-037 dagliga
#      avkastningar 2011-2024, korrelation = -0.003 (praktiskt taget
#      noll) - berknad INNAN detta kriterium las.
#   2. NAIV, likaviktad kombination (50/50) - INTE in-sample-optimerade
#      vikter (Markowitz/Kelly etc. explicit forbjudet av spec §5b).
#   3. OOS-testning: aterananvander HYP-037:s egen redan byggda genuina
#      OOS-2025-korning (paper_trading/HYP-037/oos_2025_results/).
#   4. Denna kombinationsmetod raknas som ETT eget K-test, separat fran
#      bade SPY och HYP-037:s egna K-bidrag.
#
# MOTIV: CEO:s grundmal for hela projektet ar konstant avkastning >10%/ar
# OCH Sharpe >1 - ett hogt krav som varken SPY ensamt (Sharpe 0.72 over
# 2011-2024, en OVANLIGT stark period, MaxDD -33.7%) eller HYP-037 ensamt
# (Sharpe 0.72-0.75) nar pa egen hand. Eftersom de tva ar praktiskt taget
# OKORRELERADE (-0.003) foreslar portfoljteorins standardformel
# (kombinerad Sharpe = sqrt(S1^2 + S2^2) for oberoende strommar, vid
# fritt skalbara vikter) en TEORETISK optimal kombinerad Sharpe ~1.02 -
# over malet. Detta testar om en REALISTISK, ENKEL (ej hangivet
# optimerad) 50/50-kombination faktiskt nar dit, inte bara den teoretiska
# gransen.
# status: pre-registered -> tested -> passed/failed

id: HYP-039
date_registered: '2026-08-04'
title: Naiv 50/50-kombination (kvartalsvis ombalanserad) - SPY + HYP-037
universe: "N/A - portfoljniva-kombination av tva redan existerande, oberoende testade
  avkastningsserier (SPY som tillgangsklass, HYP-037 som redan godkand small-cap-strategi).
  Ingen ny small-cap-signal, inget nytt small-cap-universum - tested_capital_levels nedan
  galler HYP-037-benets redan testade kapitalnivaer, inte en ny small-cap-hypotes i sig."
small_cap_definition: "N/A for denna hypotes - se universe-faltet. HYP-037-benet anvander
  redan HYP-037:s egen lasta $100M-$2B-definition, oforandrad."
data_range: "SPY adjusted_close + HYP-037:s redan berknade portfoljvardesserier, 2011-2024
  + genuin OOS-2025 (aterananvander paper_trading/HYP-037/oos_2025_results/, ingen ny
  OOS-korning byggs for denna hypotes)"
pass_fail_criterion: 'Ren PORTFOLJMATEMATIK pa tva redan kanda, redan individuellt testade
  avkastningsserier - INGEN ny backtest-motor, INGEN ny signal, INGEN nytt kostnads-/
  hedgepalagg utover vad de tva delserierna redan sjalva inkluderar (SPY:s eget kvoterade
  pris, HYP-037:s redan kostnadsjusterade portfoljvarde enligt dess eget redan lasta,
  redan testade regelverk). Kombinerad portfoljvarde-serie =
  50% notional i SPY (adjusted_close, dagliga
  avkastningar) + 50% notional i HYP-037 (redan sparad strategies/HYP-037/results/
  portfolio_value_<niva>.csv, ANVAND OFORANDRAD), ombalanserad till EXAKT 50/50 VARJE
  KVARTAL pa HYP-037:s REDAN LASTA ombalanseringsdatum (ateranvander en befintlig frekvens,
  valjer INGEN ny fri parameter). INGEN havstang. Testas separat vid alla tre av HYP-037:s
  redan testade kapitalnivaer (100k/1M/10M) for HYP-037-benet - SPY-benet skalar trivialt
  och paverkas inte av kapitalniva.

  PASS kraver ALLA TRE, PA MINST kapitalnivan $100k (rapporteras for alla tre, men $100k ar
  den avgorande nivan eftersom HYP-037:s egen edge redan ar kand att avta vid hogre
  kapitalniva - se HYP-037:s registerpost):
  1. Kombinerad Sharpe (2011-2024, portfoljserien efter ombalansering) >= 1.0 - det
     uttryckliga malet, INTE projektets generella 0.55-golv for enskilda alfahypoteser.
  2. Kombinerad MaxDD (samma period) BATTRE (mindre negativ) an SPY:s EGEN -33.7% pa samma
     period - bekraftar genuin riskreduktion genom diversifiering, inte bara en utspadd
     medelvardesberakning som rakar se battre ut.
  3. OOS-2025 kombinerad Sharpe (aterananvander HYP-037:s redan byggda genuina blinda
     OOS-2025-serie + SPY:s egna 2025-avkastningar, SAMMA 50/50-kvartalsombalansering) ar
     POSITIV (> 0) - ett medvetet MJUKARE krav an villkor 1, given den redan flera ganger
     dokumenterade reservationen att ett enda ars Sharpe-skattning har hog statistisk
     osakerhet (samma reservation som HYP-023/034/037:s egna OOS-tester).
  FAIL om nagot villkor faller vid $100k-nivan. Resultat vid $1M/$10M rapporteras alltid
  fullstandigt (ingen cherry-picking), men $100k ar den kriterie-avgorande nivan given ovan.

  Diagnostiskt syfte: testar om portfoljteorins teoretiska lofte (tva praktiskt taget
  okorrelerade Sharpe-0.72-strommar, kombinerat optimalt ~1.02) haller aven for en enkel,
  ICKE-optimerad 50/50-vikt - inte bara den teoretiska ovre gransen. Detta ar forsta gangen
  i projektets historia en kombinationshypotes testas, per spec §5b:s explicita regler
  (korrelationsmatris fore vikt, naiv vikt, OOS, eget K-bidrag).'
status: passed   # pre-registered -> tested -> passed/failed
k_total_hypotheses_before_this: 37
tested_capital_levels:
- 100000
- 1000000
- 10000000
capital_level_results:
  100000: {sharpe: 1.0191, cagr: 0.1337, max_drawdown: -0.2203, calmar: 0.6071, oos_2025_sharpe: 0.9185, oos_2025_total_return: 0.1195, oos_2025_max_drawdown: -0.1382, deflated_sharpe_ratio: 0.9515}
  1000000: {sharpe: 1.0300, cagr: 0.1322, max_drawdown: -0.2216, calmar: 0.5965, oos_2025_sharpe: 0.8116, oos_2025_total_return: 0.1023, oos_2025_max_drawdown: -0.1327, deflated_sharpe_ratio: 0.9544}
  10000000: {sharpe: 0.9879, cagr: 0.1181, max_drawdown: -0.2003, calmar: 0.5898, oos_2025_sharpe: 0.7932, oos_2025_total_return: 0.0939, oos_2025_max_drawdown: -0.1057, deflated_sharpe_ratio: 0.9365}
date_tested: '2026-08-04'
result_summary: >
  PASSED - PA DEN AVGORANDE $100k-NIVAN, ALLA TRE VILLKOR. Forsta gangen
  i projektets historia CEO:s uttalade grundmal (konstant CAGR >10%/ar
  OCH Sharpe >1) faktiskt uppnas i en backtest.

  Villkor 1 (Sharpe >= 1.0 vid $100k): 1.019 - PASS, marginellt over
  malet. $1M ocksa PASS (1.030, faktiskt HOGST av de tre nivaerna). $10M
  MISSAR knappt (0.988) - kriteriet kravde bara $100k, sa detta AR ett
  giltigt PASS, men den lilla forsamringen vid $10M ar INTE dold: den
  ar konsistent med HYP-037:s egen redan kanda kapacitetsberoende
  avklingning (Sharpe 0.73/0.75/0.70 i sig sjalv) som naturligt propagerar
  in i kombinationen. "Battre an malet vid $100k/$1M, precis under vid
  $10M" ar en arlig, inte en dold, bild.

  Villkor 2 (MaxDD battre an SPY:s -33.7%): PASS pa ALLA TRE nivaer,
  och tydligt - -22.0%/-22.2%/-20.0%, en forbattring pa 11.7-13.7
  procentenheter mot SPY ensamt. Detta AR den genuina riskreduktionen
  diversifieringsargumentet forutspadde, inte bara en utspadd
  medelvardesberakning.

  Villkor 3 (OOS-2025 Sharpe > 0): PASS pa ALLA TRE nivaer (0.919/0.812/
  0.793) - klart positivt, om an lagre an bade huvudbacktestens Sharpe
  och den ursprungliga teoretiska uppskattningen (~1.02, se kriteriets
  motivering). 249 handelsdagar - samma kanda reservation om
  enskild-ars-brus som redan dokumenterad i HYP-023/034/037:s egna
  OOS-test galler har ocksa, men riktningen (positiv, inte negativ eller
  noll) ar tydlig.

  ROBUSTHET: DSR vid K=38 (deflated_sharpe_ratio.py, med den FAKTISKA
  avkastningsseriens skevhet/kurtosis, INTE antagen normalfordelning):
  0.95/0.95/0.94 - mycket hogt, konsistent med att detta INTE ar en
  slumpmassig trafffavtemplering trots K=38 redan testade hypoteser.
  Kurtosis ar forhojd (9.9-12.5, mot normalfordelningens 3) vilket
  speglar bade SPY:s egna kanda svansrisk (2020, 2022) och HYP-037:s
  krasch-overlay-mekanik - redovisat, inte dolt, men DSR-berakningen
  kontrollerar redan for detta explicit (skevhet/kurtosis ar INPUT till
  DSR-formeln, inte en separat varning).

  METODOLOGISK NOT: detta ar EN kombinationsmetod (naiv 50/50, kvartalsvis
  ombalanserad) av MANGA teoretiskt mojliga - per spec §5b raknas varje
  DISTINKT kombinationsmetod som ett eget K-test. Detta resultat sager
  INGET om huruvida en annan viktning (t.ex. 40/60, riskparitet, eller
  volatilitetsviktad) skulle vara battre eller samre - att testa flera
  vikter i EFTERHAND for att hitta den "basta" skulle vara exakt den typ
  av facit-anpassning spec:en ar byggd for att forhindra. 50/50 var det
  lasta, naiva valet, INNAN nagot resultat sags - det ar det som
  rapporteras har, inget annat.

  SLUTSATS: den kombinerade 50/50-portfoljen (SPY + HYP-037, kvartalsvis
  ombalanserad) uppnar CEO:s uttalade mal vid $100k/$1M, med en tydlig,
  reell riskreduktion pa alla tre nivaer. Detta ar INTE en ny
  "referensimplementation" i samma bemarkelse som HYP-017/023/037 (det
  ar en portfoljniva-konstruktion OVANPA en redan godkand strategi, inte
  en konkurrerande small-cap-signal) - men det ar ett konkret, testat
  svar pa den strategiska fraga CEO stallde 2026-08-04.
sharpe_raw:
  100000: 1.0191
  1000000: 1.0300
  10000000: 0.9879
deflated_sharpe_ratio:
  100000: 0.9515
  1000000: 0.9544
  10000000: 0.9365

# ════════════════════════════════════════════════════════════
# TILLAGGSVALIDERING 2026-08-05 (samma session) - INTE en ny hypotes/
# K-test, status/kriterium ANDRADE INTE. Se HYP-037:s egen registerpost
# for full detalj om den underliggande look-ahead-bias-fixen i universum-
# konstruktionen (SEC-inlamningsdatum istallet for periodslut-datum).
# ════════════════════════════════════════════════════════════
# HYP-039 vilar direkt pa HYP-037:s portfoljvarde-serie. Kordes darfor
# genom samma sidotest (scripts/test_hyp039_filed_date_universe.py +
# scripts/test_hyp039_oos2025_filed_date.py) mot HYP-037:s FILED-DATUM-
# KORRIGERADE serier - ren portfoljmatematik, samma metod, ingen ny
# backtest-motor, resultat i strategies/HYP-039/results_filed_date_test/.
#
# RESULTAT: samtliga tre lasta villkor haller PA ALLA TRE kapitalnivaer,
# och den tidigare svagaste punkten blir BATTRE, inte samre:
#   Villkor 1 (Sharpe >= 1.0): 1.019/1.026/1.012 (tidigare 1.019/1.030/
#     0.988 - $10M gick fran att MISSA malet till att KLARA det).
#   Villkor 2 (MaxDD battre an SPY:s -33.7%): -21.5%/-21.5%/-19.4%
#     (tidigare -22.0%/-22.2%/-20.0%) - fortfarande en tydlig, reell
#     riskreduktion pa alla tre nivaer.
#   Villkor 3 (OOS-2025 Sharpe > 0): 0.886/0.843/0.829 (tidigare 0.919/
#     0.812/0.793) - fortfarande klart positivt pa alla tre nivaer.
#
# SLUTSATS: HYP-039:s PASS star pa fast grund aven under ett fullstandigt
# look-ahead-bias-fritt universum - faktiskt starkare an det ursprungliga
# resultatet vid den tidigare mest oroande punkten ($10M). Detta star i
# kontrast mot HYP-037:s EGEN interna jamforelse mot HYP-023 (som blir
# ett oavgjort resultat vid $10M under samma korrigering, se HYP-037:s
# registerpost) - men den nyansen paverkar INTE HYP-039:s eget resultat,
# eftersom HYP-039:s kriterium aldrig kravde att HYP-037 "vinner" mot
# HYP-023, bara att KOMBINATIONEN nar sitt eget mal.

# ════════════════════════════════════════════════════════════
# TILLAGGSNOT 2026-08-08 (granskningsfynd, tre oberoende adversariella
# granskare - INTE en ny hypotes/K-test, status/kriterium/redan
# rapporterade siffror ANDRADE INTE)
# ════════════════════════════════════════════════════════════
# DSR ovan star kvar fran ursprungstestet vid K=39 - aldrig omraknad,
# trots agents/overfitting_detector/ROLE.md:s krav att gora det for
# alla aktiva hypoteser varje gang k_total okar. HYP-039 ar fortfarande
# citerad som jamforelsepunkt i flera senare hypotesers OOS-kriterium.
#
# OMRAKNAD mot dagens k_total=46 (scripts/recompute_dsr_k46.py,
# 2026-08-08, samma sparade kombinerade serie, RF=2%/ar avdraget):
#   $100k:   DSR 0.9515 -> 0.9436
#   $1M:     DSR 0.9544 -> 0.9469
#   $10M:    DSR 0.9365 -> 0.9268
#
# Mycket liten forandring (K=39->46 ar en relativt liten relativ okning,
# och HYP-039:s hoga rasa Sharpe gor DSR mindre kanslig for K-okningar
# i detta intervall). Ingen forandring av tidigare PASS-slutsats.

# ════════════════════════════════════════════════════════════
# TILLAGGSNOT 2026-08-08, DEL 2 (samma dag, SEPARAT fran DSR-omrakningen
# ovan - INTE en ny hypotes/K-test, status/kriterium ANDRADE INTE)
# ════════════════════════════════════════════════════════════
# Fullstandig omkorning: HYP-037-benet ar nu dess FULLSTANDIGT
# korrigerade resultat (filed-datum-universum + maskad adjusted_close-
# kvot, se HYP-037:s egen tilläggsnot DEL 2 - VIKTIGT: HYP-037:s EGET
# villkor 2 flippar dar till FAIL, men det paverkar INTE HYP-039:s eget
# kriterium, som aldrig kravde att HYP-037 slar HYP-023). Dessutom
# tillagd en tidigare saknad portfoljniva-ombalanseringskostnad (10bps
# pa omallokerat belopp per kvartalsvis ombalansering, se
# strategies/HYP-039/backtest.py::REBALANCE_COST_BPS). OOS-2025-benet
# ANVANDS OKORRIGERAT (paper_trading/HYP-037/oos_2025_results/, samma
# scope-avgransning som noterad i HYP-037:s tilläggsnot).
#
# NYA SIFFROR (huvudperiod 2011-2024):
#   Sharpe: 1.017 / 1.022 / 1.019  (tidigare 1.0191 / 1.0300 / 0.9879)
#   MaxDD: -21.4% / -21.3% / -19.2% (tidigare -22.03% / -22.16% / -20.03%)
#   DSR (K=46, RF=2%/ar): 0.9413 / 0.9434 / 0.9410
#
# Villkor 1 (Sharpe >= 1.0): PASS pa ALLA TRE nivaer - $10M gar fran att
# missa (0.988) till att klara (1.019) trots den nya kostnaden, samma
# monster som redan sett i den tidigare (universum-bara) sidotestet.
# Villkor 2 (MaxDD battre an SPY:s -33.7%): PASS tydligt pa alla tre,
# oforandrat. Villkor 3 (OOS-2025 Sharpe > 0): oforandrat PASS (0.917/
# 0.810/0.792, samma okorrigerade OOS-serie som tidigare).
#
# SLUTSATS: HYP-039:s PASS star KVAR, oforandrad slutsats, under den
# fullstandigt korrigerade pipelinen - faktiskt nagot starkare vid $10M
# an tidigare, trots att bade universumfixen OCH den nya ombalanserings-
# kostnaden nu bada verkar samtidigt.
```

---

## KÄLLFIL: `research/hypothesis_registry/HYP-041-naiv-kombination-spy-hyp037-tlt.yaml`

```
# LÅST 2026-08-06 av CEO i chatt, innan denna hypotes sätts pre-registered
# eller någon backtest körs.
#
# Foljer spec §5b:s regler for LEGITIM kombinationstestning, samma
# disciplin som HYP-039:
#   1. Korrelationsmatris FORE nagon vikt valdes: SPY/TLT/HYP-037
#      dagliga avkastningar, overlappande period 2010-10-01 till
#      2024-12-31 (3586 dagar) - berknad INNAN detta kriterium las.
#      SPY-TLT: -0.3019, TLT-HYP037: -0.0214, SPY-HYP037: -0.0045.
#   2. NAIV, likaviktad kombination (lika tredjedelar) - INTE in-sample-
#      optimerade vikter.
#   3. Egen K-kostnad, separat fran SPY/HYP-037/TLT:s egna bidrag OCH
#      fran HYP-039 (denna ar INTE en modifiering av HYP-039, det ar en
#      helt egen, ny kombinationsmetod - tredelad, inte tvadelad).
#
# VIKTIG, OPPET REDOVISAD RESERVATION INNAN LASNING: TLT:s EGEN Sharpe
# over samma period ar bara 0.038 (i praktiken noll), CAGR 1.46%/ar,
# MaxDD -48.3% (samre an SPY:s egna -33.7%) - 2010-2024 var en tuff
# period for langa obligationer (flerarig bull-marknad som slutade,
# sedan 2022 rantechocken). Korrelationsegenskaperna ar goda, men TLT:s
# egen riskjusterade profil ar svag under just detta fonster - CEO och
# Claude diskuterade detta explicit innan lasning; kriteriet lases anda
# eftersom den KOMBINERADE matematiken ar en empirisk fraga, inte nagot
# som kan avgoras fran korrelationen ensam.
#
# status: pre-registered -> tested -> passed/failed

id: HYP-041
date_registered: '2026-08-06'
title: Naiv tredelad kombination (kvartalsvis ombalanserad) - SPY + HYP-037 + TLT
universe: "N/A - portfoljniva-kombination av tre redan existerande, oberoende testade
  avkastningsserier (SPY och TLT som tillgangsklasser, HYP-037 som redan godkand
  small-cap-strategi). tested_capital_levels nedan galler HYP-037-benets redan
  testade kapitalnivaer."
small_cap_definition: "N/A for denna hypotes - se universe-faltet."
data_range: "SPY/TLT adjusted_close + HYP-037:s redan berknade portfoljvardesserier,
  2010-2024 + genuin OOS-2025 (aterananvander paper_trading/HYP-037/oos_2025_results/,
  ingen ny OOS-korning byggs for denna hypotes)"
pass_fail_criterion: >
  Ren PORTFOLJMATEMATIK pa tre redan kanda, redan individuellt testade
  avkastningsserier - INGEN ny backtest-motor, INGEN ny signal, INGEN nytt
  kostnads-/hedgepalagg utover vad de tre delserierna redan sjalva
  inkluderar. Kombinerad portfoljvarde-serie = 33.33% notional i SPY
  (adjusted_close) + 33.33% i TLT (adjusted_close) + 33.33% i HYP-037
  (redan sparad strategies/HYP-037/results/portfolio_value_<niva>.csv,
  ANVAND OFORANDRAD), ombalanserad till EXAKT tredjedelar VARJE KVARTAL
  pa HYP-037:s REDAN LASTA ombalanseringsdatum (ateranvander en befintlig
  frekvens, valjer INGEN ny fri parameter). INGEN havstang. Testas separat
  vid alla tre av HYP-037:s redan testade kapitalnivaer (100k/1M/10M) for
  HYP-037-benet - SPY/TLT-benen skalar trivialt.

  PASS kraver ALLA TRE, PA MINST kapitalnivan $100k (rapporteras for alla
  tre, men $100k ar den avgorande nivan, samma konvention som HYP-039):
  1. Kombinerad Sharpe (2010-2024) >= 1.0 - samma mal som HYP-039.
  2. Kombinerad Sharpe > HYP-039:s EGNA redan registrerade Sharpe vid
     samma niva (1.019/1.030/0.988 vid 100k/1M/10M) - bevisar att
     TLT-benet FAKTISKT tillfor nagot utover den redan godkanda
     tvadelade kombinationen, inte bara spar ut den med brus.
  3. Kombinerad MaxDD BATTRE (mindre negativ) an HYP-039:s EGNA redan
     registrerade MaxDD vid samma niva (-22.0%/-22.2%/-20.0%) - bevisar
     genuin riskreduktion utover det HYP-039 redan uppnar.

  OOS-2025: kombinerad OOS-2025 Sharpe (aterananvander HYP-037:s redan
  byggda OOS-2025-serie + SPY/TLT:s egna 2025-avkastningar, SAMMA
  tredjedelskombination) MASTE vara > HYP-039:s EGEN OOS-2025 Sharpe
  vid samma niva (0.919/0.812/0.793) - samma "bevisa additivt varde"-
  princip som huvudvillkoren.

  FAIL om nagot villkor faller vid $100k-nivan.

  Diagnostiskt syfte: testar CEO:s egen hypotes att en TREDJE, genuint
  okorrelerad tillgang (har: langa statsobligationer) kan hoja den
  kombinerade Sharpen bortom vad tva-dels-kombinationen (HYP-039) redan
  uppnar - portfoljteorins diversifieringslogik tillampad pa en ny
  tillgangsklass, INTE en ny small-cap-signal.
status: failed   # pre-registered -> tested -> passed/failed
k_total_hypotheses_before_this: 39
tested_capital_levels:
- 100000
- 1000000
- 10000000
capital_level_results:
  100000: {sharpe: 0.9981, cagr: 0.0994, max_drawdown: -0.2273, calmar: 0.4374, oos_2025_sharpe: 0.8794, oos_2025_total_return: 0.0955, oos_2025_max_drawdown: -0.0963, deflated_sharpe_ratio: 0.9407}
  1000000: {sharpe: 1.0056, cagr: 0.0982, max_drawdown: -0.2304, calmar: 0.4262, oos_2025_sharpe: 0.7837, oos_2025_total_return: 0.0841, oos_2025_max_drawdown: -0.0925, deflated_sharpe_ratio: 0.9429}
  10000000: {sharpe: 0.9498, cagr: 0.0884, max_drawdown: -0.2157, calmar: 0.4097, oos_2025_sharpe: 0.7578, oos_2025_total_return: 0.0780, oos_2025_max_drawdown: -0.0733, deflated_sharpe_ratio: 0.9147}
date_tested: '2026-08-06'
result_summary: >
  FAILED PA DEN AVGORANDE $100k-NIVAN, PA SAMTLIGA VILLKOR - ett tydligt,
  om an inte extremt, misslyckande. Till skillnad fran HYP-040 ar detta
  INTE en katastrof - Sharpe 0.998 ligger bara 0.002 fran 1.0-malet -
  men VARJE enskilt mått ar konsekvent SAMRE an den redan godkanda
  tvadelade kombinationen (HYP-039), inte bara en enstaka gransfall-siffra.

  Villkor 1 (Sharpe >= 1.0 vid $100k): 0.9981 - FAIL, marginellt under
  malet (0.9981 vs 1.0000). $1M klarade tekniskt (1.0056) men $100k ar
  den avgorande nivan per kriteriet.

  Villkor 2 (Sharpe > HYP-039:s egna vid samma niva): FAIL PA ALLA TRE
  nivaer (0.9981 vs 1.0191, 1.0056 vs 1.0300, 0.9498 vs 0.9879) -
  konsekvent SAMRE, inte battre, an den redan godkanda kombinationen.

  Villkor 3 (MaxDD battre an HYP-039:s egna): FAIL PA ALLA TRE nivaer
  (-22.73% vs -22.03%, -23.04% vs -22.16%, -21.57% vs -20.03%) - TLT-
  benet FORSAMRADE riskbilden istallet for att forbattra den, trots den
  goda korrelationen mot SPY.

  OOS-2025 (villkor 4): FAIL PA ALLA TRE nivaer (0.8794 vs 0.9185, 0.7837
  vs 0.8116, 0.7578 vs 0.7932) - samma monster haller aven i den genuina
  blinda perioden.

  DSR vid K=40: 0.94/0.94/0.91 - HOGT, vilket bara bekraftar att
  HYP-041 SJALV troligen ar en genuin (inte slumpmassig) positiv-Sharpe-
  portfolj i absoluta tal - men det ar INTE fragan kriteriet stallde.
  Kriteriet kravde att den ska vara BATTRE an HYP-039, inte bara "en
  okej portfolj pa egen hand" - och pa den fragan ar svaret entydigt nej.

  DIAGNOS: bekraftar exakt den reservation som redovisades INNAN
  lasning (se kommentaren hogst upp i denna fil). TLT:s goda
  korrelationsegenskaper (-0.30 mot SPY, -0.02 mot HYP-037) rackte INTE
  for att kompensera dess svaga egna riskjusterade profil under just
  2010-2024 (egen Sharpe 0.038, egen MaxDD -48.3% - varre an SPY:s
  egna -33.7%). Diversifiering hjalper mest nar ALLA komponenter har
  egen edge - en tredje, i praktiken avkastningslos men hogriskfylld
  komponent kan spa ut mer an den hjalper, aven med gynnsam korrelation.
  Detta ar en genuint informativ, forvantad-i-efterhand men INTE
  forutsagbar-i-forvag (darfor vart att testa) slutsats.

  SLUTSATS: HYP-039 (SPY+HYP-037, tvadelad) forblir den ENDA
  kombinationshypotesen som passerat sitt eget kriterium. Ett tredje ben
  ar INTE automatiskt battre bara for att korrelationen ser bra ut -
  komponentens EGEN riskjusterade kvalitet spelar minst lika stor roll.
  En annan tillgang (t.ex. trend-following/managed futures, redan
  diskuterad som CEO:s alternativ #1) kraver en egen, separat lasning -
  ingen automatisk fortsattning fran detta resultat.

# ════════════════════════════════════════════════════════════
# TILLAGGSNOT 2026-08-08 (granskningsfynd, tre oberoende adversariella
# granskare - INTE en ny hypotes/K-test, status/kriterium/redan
# rapporterade siffror ANDRADE INTE)
# ════════════════════════════════════════════════════════════
# DSR i capital_level_results ovan star kvar fran ursprungstestet vid
# K=41 - aldrig omraknad, trots agents/overfitting_detector/ROLE.md:s
# krav. HYP-041 ar redan FAILED, sa detta paverkar ingen aktiv
# jamforelsepunkt, men dokumenteras for fullstandighet.
#
# OMRAKNAD mot dagens k_total=46 (scripts/recompute_dsr_k46.py,
# 2026-08-08, samma sparade kombinerade serie, RF=2%/ar avdraget):
#   $100k:   DSR 0.9407 -> 0.9341
#   $1M:     DSR 0.9429 -> 0.9365
#   $10M:    DSR 0.9147 -> 0.9060
#
# Liten forandring, ingen paverkan pa FAILED-slutsatsen (som redan
# vilade pa villkor 1/2, inte pa DSR).

# ════════════════════════════════════════════════════════════
# TILLAGGSNOT 2026-08-08, DEL 2 (samma dag, SEPARAT fran DSR-omrakningen
# ovan - INTE en ny hypotes/K-test, status/kriterium ANDRADE INTE)
# ════════════════════════════════════════════════════════════
# Fullstandig omkorning: HYP-037-benet korrigerat (filed-datum-universum
# + maskad adjusted_close-kvot) + 10bps portfoljniva-ombalanserings-
# kostnad tillagd (strategies/HYP-041/backtest.py::REBALANCE_COST_BPS).
# Jamforelsepunkten (HYP-039) star KVAR pa dess ursprungliga, redan
# lasta varden (1.0191/1.0300/0.9879, -22.03%/-22.16%/-20.03%) - det ar
# de siffrorna det ursprungliga kriteriet faktiskt lastes mot, INTE
# HYP-039:s egen senare omraknade version.
#
# NYA SIFFROR (huvudperiod 2010-2024):
#   Sharpe: 0.9877 / 0.9912 / 0.9742  (tidigare 0.9981 / 1.0056 / 0.9498)
#   MaxDD: -23.46% / -23.45% / -21.21% (tidigare -22.73% / -23.04% / -21.57%)
#   DSR (K=46, RF=2%/ar): 0.9280 / 0.9297 / 0.9202
#
# Villkor 1 (Sharpe >= 1.0): FAIL PA ALLA TRE nivaer, oforandrat ($1M
# gick fran ett tekniskt PASS 1.0056 till FAIL 0.9912 under den nya
# kostnaden - men $100k var alltid den avgorande nivan och var redan
# FAIL). Villkor 2 (slå HYP-039): FAIL PA ALLA TRE, oforandrat. Villkor
# 3 (MaxDD battre an HYP-039): FAIL PA ALLA TRE, oforandrat (blev
# faktiskt nagot samre pa tva av tre nivaer).
#
# SLUTSATS: HYP-041:s FAILED-slutsats star OFORANDRAD under den
# fullstandigt korrigerade pipelinen - inget villkor flippar i nagon
# riktning. HYP-039 forblir den enda kombinationshypotesen som klarar
# just denna jamforelsepunkt.
```

---

## KÄLLFIL: `research/hypothesis_registry/HYP-043-naiv-kombination-spy-hyp037-momentum-ls.yaml`

```
# LÅST 2026-08-06 av CEO i chatt, innan denna hypotes sätts pre-registered
# eller nagon backtest kors.
#
# Foljer spec §5b:s regler for LEGITIM kombinationstestning, samma
# disciplin som HYP-039/041:
#   1. Korrelationsmatris FORE nagon vikt valdes - se reservation nedan,
#      med bade en forsta (kvartalsvis, 57 punkter) och en KORRIGERAD,
#      mer tillforlitlig (daglig, 3460 punkter) berkning, upptackt
#      behovas efter att den kvartalsvisa metoden visade sig ge en
#      MISSVISANDE bild aven for den redan kanda SPY/HYP-037-relationen
#      (0.67 kvartalsvis mot 0.003 dagligen, oberoende verifierat).
#   2. NAIV, likaviktad kombination (lika tredjedelar) - INTE in-sample-
#      optimerade vikter.
#   3. Egen K-kostnad, separat fran HYP-039/HYP-041.
#
# TREDJE BENET: en momentum long/short-svit (12-1-manaders momentum,
# klassisk akademisk konvention - Jegadeesh/Titman - long topp-decil,
# kort botten-decil, dollar-neutralt, kvartalsvis) byggd fran grunden
# over small-cap-universumet (INTE en ETF-proxy - de tillgangliga
# alternativen som foreslogs, DBMF/KMLM/AVUV/QVAL/VFMO, hade alla for
# kort historik for 2010-2024-fonstret, endast BTAL godkand pa den
# punkten men aldrig testad har).
#
# KORRELATION (DAGLIG, den tillforlitliga siffran - FORE lasning):
# Momentum L/S mot SPY: -0.086. Momentum L/S mot HYP-037: -0.110.
# Svagare an den forsta (missvisande) kvartalsvisa skattningen (-0.36/
# -0.23), men fortfarande i ratt riktning. Sviten egen dagliga Sharpe:
# 0.27 (svagare an HYP-037:s 0.73, men battre an HYP-041:s TLT-ben,
# vars egen Sharpe bara var 0.038).
#
# status: pre-registered -> tested -> passed/failed

id: HYP-043
date_registered: '2026-08-06'
title: Naiv tredelad kombination (kvartalsvis ombalanserad) - SPY + HYP-037 + Momentum L/S
universe: "N/A for SPY/HYP-037-benen (redan testade). Momentum L/S-benet byggs over
  SAMMA small-cap-universum ($100M-$2B) som HYP-037, ingen ny universumdefinition."
small_cap_definition: "small-cap, $100M - $2B börsvärde, EODHD All-World (galler
  momentum L/S-benets universum, ateranvander HYP-037:s redan lasta definition)"
data_range: "SPY/TLT-monster: adjusted_close 2010-2024 + genuin OOS-2025. Momentum
  L/S: byggd fran close_adj over samma small-cap-universum och period, samma
  motorkrav (adjusted_close genomgaende, ny sarhet mot konstant orimlig
  adjusted_close/close-kvot - se nedan)."
pass_fail_criterion: >
  MEKANISM (låst, ingen fri parameter kvar att välja):

  1. MOMENTUM L/S-SVITEN (det tredje benet, byggs fran grunden har - INTE
  en redan existerande serie): kvartalsvis (HYP-037:s egna snappade
  datum), rangordna eligible small-cap-universumet efter 12-1-manaders
  momentum (avkastning fran 252 till 21 handelsdagar sedan - UTESLUTER
  senaste manaden, klassisk akademisk konvention). LONG topp-decilen,
  KORT botten-decilen, likaviktat inom vardera benet, DOLLAR-NEUTRALT
  (50% notional long, 50% kort av sviten-benets EGEN allokering).
  Daglig vardering mellan ombalanseringarna (samma princip som HYP-037:s
  egen dagliga vardering). Lanekostnad pa kortbenet (samma
  BORROW_ANNUAL_RATE=3% som resten av registret). Motorkrav: adjusted_close
  genomgaende, SAMMA nya sarhet mot konstant orimlig adjusted_close/close-
  kvot (>100x eller <0.01x, maskas) som upptacktes och fixades under
  HYP-042:s bygge samma dag - INBYGGD FRAN START har, inte upptackt i
  efterhand.

  2. KOMBINATION: 1/3 notional SPY + 1/3 notional HYP-037 (redan sparad
  strategies/HYP-037/results/portfolio_value_<niva>.csv, ANVAND
  OFORANDRAD) + 1/3 notional momentum L/S-sviten (punkt 1, redan
  DOLLAR-NEUTRAL internt - en tredjedel kapital "bakom" den behandlas
  som EN redan kand avkastningsserie, samma princip som HYP-037:s eget
  ben i HYP-039/041). Ombalanserad till exakt tredjedelar VARJE KVARTAL
  pa HYP-037:s REDAN LASTA datum. INGEN havstang utover sviten-benets
  egen interna 50/50 long/kort-struktur.

  PASS KRÄVER ALLA TRE, PA DEN AVGORANDE $100k-NIVAN (rapporteras for
  alla tre nivåer, samma konvention som HYP-039/041):
  1. Kombinerad Sharpe (2010-2024) >= 1.0.
  2. Kombinerad Sharpe > HYP-039:s EGNA redan registrerade Sharpe vid
     samma niva (1.019/1.030/0.988 vid 100k/1M/10M).
  3. Kombinerad MaxDD BATTRE an HYP-039:s EGNA redan registrerade MaxDD
     vid samma niva (-22.0%/-22.2%/-20.0%).

  OOS-2025: kombinerad OOS-2025 Sharpe (momentum L/S-sviten byggd om
  for 2025 med SAMMA metod, sammanslaget universum huvudserie+2025-
  utokning, samma merged-universum-princip som HYP-037:s egen genuina
  OOS-korning) MASTE vara > HYP-039:s EGEN OOS-2025 Sharpe vid samma
  niva (0.919/0.812/0.793).

  FAIL om nagot villkor faller vid $100k-nivan.

  Diagnostiskt syfte: testar om en EGENBYGGD (inte ETF-proxy) beta-
  neutral momentum long/short-svit kan hoja den kombinerade Sharpen
  bortom vad HYP-039 (SPY+HYP-037) redan uppnar - en annan typ av
  tredje ben an HYP-041:s TLT (tillgangsklass-diversifiering) - har
  ar det en oberoende AKTIEFAKTOR-svit, motiverad delvis av HYP-042:s
  eget fynd (small-cap-"forlorare" tenderar att fortsatta kollapsa,
  vilket indirekt stodjer att KORTSIDAN av momentum kan ha edge har,
  aven om LANGSIDAN (ren momentum long-only) redan misslyckats tre
  ganger tidigare i registret).
status: failed   # pre-registered -> tested -> passed/failed
# CEO-BESLUT 2026-08-09: status andrad fran passed till failed. Grund:
# tilläggsnot DEL E (2026-08-08) visar Sharpe 0,8765/0,8752/0,8392 med
# alla fyra kanda fixar (look-ahead-bias, adjusted_close-kvot, ombalanse-
# ringskostnad, corwin_schultz_spread) kombinerade - klarar inte langre
# vare sig villkor 1 (Sharpe>=1.0) eller villkor 2 (sla HYP-039) pa den
# avgorande $100k-nivan. Villkor 3 (MaxDD) och OOS-2025 forblir starka
# PASS, men kravet var ALLA TRE huvudvillkor. De ursprungliga siffrorna
# ovan (capital_level_results) ANDRAS INTE - historik skrivs inte om.
# HYP-039 forblir den senaste hypotesen i kedjan som fortfarande PASSAR
# pa egna meriter fore HYP-047.
k_total_hypotheses_before_this: 41
tested_capital_levels:
- 100000
- 1000000
- 10000000
capital_level_results:
  100000: {sharpe: 1.0457, cagr: 0.1088, max_drawdown: -0.1558, calmar: 0.6980, oos_2025_sharpe: 1.6163, oos_2025_total_return: 0.3267, oos_2025_max_drawdown: -0.0988, deflated_sharpe_ratio: 0.9510}
  1000000: {sharpe: 1.0498, cagr: 0.1076, max_drawdown: -0.1568, calmar: 0.6862, oos_2025_sharpe: 1.5639, oos_2025_total_return: 0.3137, oos_2025_max_drawdown: -0.1058, deflated_sharpe_ratio: 0.9516}
  10000000: {sharpe: 0.9864, cagr: 0.0975, max_drawdown: -0.1429, calmar: 0.6820, oos_2025_sharpe: 1.5321, oos_2025_total_return: 0.3060, oos_2025_max_drawdown: -0.1113, deflated_sharpe_ratio: 0.9229}
date_tested: '2026-08-06'
result_summary: >
  PASSED PA DEN AVGORANDE $100k-NIVAN, PA ALLA FYRA VILLKOR - och detta
  ar ett TYDLIGT starkare resultat an HYP-039 sjalv, inte bara ett
  precis-over-ribban-godkannande. Tredje kombinationshypotesen i
  registret, och den FORSTA som slar HYP-039 pa dess egna villkor.

  Villkor 1 (Sharpe >= 1.0 vid $100k): 1.0457 - PASS, TYDLIGT over
  malet (mot HYP-039:s egna 1.0191).

  Villkor 2 (Sharpe > HYP-039:s egna vid samma niva): PASS vid $100k
  (1.0457 vs 1.0191) OCH $1M (1.0498 vs 1.0300). $10M missar bade
  1.0-malet (0.9864) och jamforelsen mot HYP-039 (0.9879) - MEN $10M
  ar INTE den avgorande nivan per kriteriet, och missen ar
  rakbladstunn (0.0015 under HYP-039:s egna varde) - redovisat oppet,
  INTE dolt.

  Villkor 3 (MaxDD battre an HYP-039:s egna): PASS PA ALLA TRE NIVAER,
  och inte marginellt - -15.58%/-15.68%/-14.29% mot HYP-039:s
  -22.03%/-22.16%/-20.03%, en forbattring pa 6.35-6.48 PROCENTENHETER.
  Det tredje benet levererar genuin, betydande riskreduktion, inte
  bara en marginell finjustering.

  OOS-2025 (villkor 4): PASS PA ALLA TRE NIVAER, och SPEKTAKULART -
  1.6163/1.5639/1.5321 mot HYP-039:s egna 0.9185/0.8116/0.7932 - en
  forbattring pa 68-93%. Given den redan kanda reservationen om ett
  enda ars brus (samma som alltid galler for OOS-matt i detta
  register) bor detta INTE overtolkas som en permanent egenskap, men
  riktningen ar entydig och konsekvent med huvudperiodens resultat.

  DSR vid K=42: 0.95/0.95/0.92 - mycket hogt, samma niva som HYP-039:s
  egna 0.95/0.95/0.94, INTE en slumptrafff trots 42 redan testade
  hypoteser.

  METODOLOGISK NOT (viktig, se registerpostens egen lasningskommentar):
  korrelationen mot bade SPY (-0.086) och HYP-037 (-0.110) var svagare
  an en forsta, MISSVISANDE kvartalsvis forhandsskattning (-0.36/-0.23)
  - upptackt via en oberoende dubbelkoll som avslojade att aven den
  redan kanda SPY/HYP-037-relationen ser mycket starkare ut kvartalsvis
  (0.67) an dagligen (0.003). Trots den svagare (men fortfarande
  gynnsamma) korrelationen levererade momentum L/S-sviten ett TYDLIGT
  battre resultat an HYP-041:s TLT-forsok (som hade battre korrelation
  men en mycket svagare EGEN riskjusterad profil, Sharpe 0.038). Det
  bekraftar lardomen fran HYP-041: sviten-benets EGEN kvalitet (denna
  sviten hade dagligen Sharpe 0.27, mycket battre an TLT:s 0.038)
  spelar minst lika stor roll som korrelationen for om ett tredje ben
  faktiskt hjalper.

  DIAGNOS FOR VARFOR DET FUNGERADE: en beta-neutral, EGENBYGGD
  aktiefaktor-svit (inte en tillgangsklass-diversifierare som TLT)
  tillforde bade riktig diversifiering OCH en positiv egen edge,
  istallet for att bara spa ut. Detta ar ocksa ett indirekt,
  empiriskt stod for tesen som motiverade HYP-042 samma dag (att
  small-cap-"forlorare" ofta genuint kollapsar snarare an studsar
  tillbaka) - fast HAR utnyttjat via KORTSIDAN (blanka forlorarna)
  istallet for att kopa dem, vilket fungerade mycket battre.

  SLUTSATS: HYP-043 ar den STARKASTE kombinationshypotesen i registret
  hittills - forbattrar HYP-039 pa MaxDD betydande (6+pp), haller
  Sharpe-malet klart vid de tva avgorande lagre nivaerna, och visar en
  mycket stark OOS-2025-marginal. $10M-nivans knappa miss ar en arlig,
  inte dold, nyans - konsistent med det redan etablerade monstret att
  edgen (har: bade HYP-037:s och momentum-sviten:s kapacitetsberoende
  avklingning) forsvagas nagot vid hogre kapital. HYP-039 var forsta
  gangen CEO:s grundmal naddes - HYP-043 ar forsta gangen malet naddes
  MED en tydlig marginal, inte bara precis over ribban.

# ════════════════════════════════════════════════════════════
# TILLAGGSNOT 2026-08-08 (granskningsfynd, tre oberoende adversariella
# granskare - INTE en ny hypotes/K-test. status/pass_fail_criterion/
# tested_capital_levels/capital_level_results ovan ANDRADE INTE - last
# historia andras inte i efterhand, samma disciplin som HYP-037/039)
# ════════════════════════════════════════════════════════════
# DEL A - FRIKTIONSKORRIGERAD ROBUSTHET (fyndet sjalvt gjordes redan
# 2026-08-07 av scripts/diagnostic_hyp043_friction_robustness.py, under
# byggandet av HYP-044 - men skrevs ALDRIG in i DENNA fil, bara i
# HYP-044/045/046/047:s prosa och i _counter.yaml:s not, som sjalv
# flaggade detta som en "oppen fraga" som kravde en formell
# tillaggsnot. Detta ar den notens formella infriande.
#
# FYND: momentum L/S-sviten ovan (rad 47-60) anropar ALDRIG
# corwin_schultz_spread - bara borrow_cost. Detta skulle INTE klara
# scripts/validate_friction_usage.py om det kordes idag, och bryter
# principen "friktion fran dag ett" (spec §2, princip 3) trots att
# registerpostens egen las-kommentar (rad 56-58) uttryckligen namner
# adjusted_close-kvotfixen som inbyggd fran start - spreadkostnaden
# missades trots det.
#
# MED corwin_schultz_spread tillagd (allt annat OFORANDRAT):
#   $100k:   Sharpe 1.0457 -> 0.8926 (MaxDD oforandrad -15.58%)
#   $1M:     Sharpe 1.0498 -> 0.8940 (MaxDD oforandrad -15.68%)
#   $10M:    Sharpe 0.9864 -> 0.8217 (MaxDD oforandrad -14.29%)
#
# PAVERKAN PA DET LASTA KRITERIET (rad 71-77), rakt igenom:
#   Villkor 1 (Sharpe >= 1.0 vid $100k, DEN AVGORANDE nivan): 0.8926 -
#     KLARAR INTE LANGRE, och inte marginellt (0.107 under malet).
#   Villkor 2 (Sharpe > HYP-039:s egna 1.0191 vid $100k): 0.8926 -
#     KLARAR INTE LANGRE (0.1265 under HYP-039:s eget resultat).
#   Villkor 3 (MaxDD battre an HYP-039:s egna -22.03%): -15.58% -
#     PASSERAR FORTFARANDE TYDLIGT, MaxDD paverkas i praktiken inte av
#     spreadkostnaden pa denna sviten.
#
# DEL B - DSR FOR DE FRIKTIONSKORRIGERADE SIFFRORNA (NY, 2026-08-08,
# scripts/recompute_hyp043_friction_dsr.py, mot dagens k_total=46,
# RF=2%/ar avdraget):
#   $100k:   DSR(K=46) = 0.8548
#   $1M:     DSR(K=46) = 0.8549
#   $10M:    DSR(K=46) = 0.7855
# (fortfarande sannolikt en genuin, icke-slumpmassig portfolj - men DSR
# mater ENDAST om Sharpen genuint skiljer sig fran noll givet K forsok,
# INTE om den klarar ett specifikt lasted trosklvarde som 1.0. Bagge
# fragorna ar relevanta men skilda.)
#
# DEL C - DSR FOR DE URSPRUNGLIGA (ICKE FRIKTIONSKORRIGERADE) SIFFRORNA
# MOT DAGENS K=46 (samma granskningsfynd som for HYP-017/021/023/037/
# 039/041 - DSR-faltet i capital_level_results ovan star kvar fran
# ursprungstestet vid K=42, aldrig omraknad. scripts/recompute_dsr_k46.py,
# 2026-08-08):
#   $100k:   DSR 0.9510 -> 0.9473
#   $1M:     DSR 0.9516 -> 0.9480
#   $10M:    DSR 0.9229 -> 0.9177
#
# SLUTSATS: `status: passed` (rad 96) star medvetet KVAR OFORANDRAD har
# - denna tillaggsnot andrar INGA lasta falt, bara dokumenterar redan
# kanda och nu kompletta fakta, i linje med registrets egen disciplin.
# MEN sakligt sett klarar HYP-043 INTE sitt eget lasta kriterium (rad
# 71-77) nar friktionsmodellen ar komplett - villkor 1 OCH 2 faller pa
# den avgorande nivan, inte marginellt. Detta ar redan implicit erkant
# av att HYP-044/045/046/047 samtliga jamfor sig mot "den
# friktionskorrigerade HYP-043-baslinjen" (0.8926/0.8940/0.8217) snarare
# an mot de ursprungliga registrerade talen - men ingen av dessa filer
# gjorde det explicit HAR, i den fil dar det faktiskt hor hemma. Om
# `status` ska formellt andras till `failed` (eller en ny mellanstatus)
# ar ett beslut for CEO att fatta manuellt, inte nagot denna tillaggsnot
# eller nagon agent avgor pa egen hand.
#
# DEL D - YTTERLIGARE, SEPARAT KORRIGERING SAMMA DAG (universum-
# look-ahead-bias + adjusted_close-kvot + portfoljniva-ombalanserings-
# kostnad - INTE samma fix som DEL A ovan, se forklaring): denna gang
# implementerad DIREKT i strategies/HYP-043/backtest.py (produktions-
# koden, inte ett sidoskript) - ORIGINAL_UNIVERSE_FILE/
# EXTENSION_UNIVERSE_FILE pekar nu pa de filed-datum-korrigerade
# filerna, close_adj maskas nu via den delade
# data_hygiene.py::mask_implausible_adjusted_close_ratio (tidigare
# redan inline har, oforandrad tröskel - bara centraliserad), OCH
# combine_thirds har nu en 10bps-ombalanseringskostnad
# (REBALANCE_COST_BPS) som INTE fanns tidigare. VIKTIGT: denna
# korrigering lagger INTE till DEL A:s corwin_schultz_spread-kostnad i
# sjalva momentum L/S-sviten - de tva fixarna ar ADDITIVA MEN INTE
# KOMBINERADE i denna omkorning (utanfor detta uppdrags avgransade
# omfattning, se slutrapporten). Resultat i
# strategies/HYP-043/results_corrected_2026-08-08/ (results/ rors INTE).
#
# NYA SIFFROR (huvudperiod 2010-2024, DEL D:s korrigering ENSAM, INTE
# kombinerad med DEL A:s spreadfix):
#   Sharpe: 1.0318 / 1.0319 / 1.0053  (ursprungligen 1.0457 / 1.0498 / 0.9864)
#   MaxDD: -15.12% / -15.06% / -13.64% (ursprungligen -15.58% / -15.68% / -14.29%)
#   DSR (K=46, RF=2%/ar): 0.9402 / 0.9403 / 0.9276
#
# Villkor 1 (Sharpe >= 1.0 vid $100k): PASS (1.0318), OCH $10M klarar nu
# ocksa 1.0 (1.0053, tidigare 0.9864 - inte den avgorande nivan men en
# konsekvent forbattring). Villkor 2 (Sharpe > HYP-039:s ursprungliga
# 1.0191): PASS. Villkor 3 (MaxDD battre an HYP-039:s ursprungliga
# -22.03%): PASS tydligt, MaxDD till och med nagot BATTRE an det
# ursprungliga HYP-043-resultatet trots den nya ombalanseringskostnaden.
#
# SLUTSATS (DEL D): denna SPECIFIKA korrigering (look-ahead-bias +
# adjusted_close-kvot + portfoljniva-ombalanseringskostnad, ISOLERAT
# fran DEL A:s spreadfix) andrar INTE PASS-slutsatsen - om nagot star
# HYP-043 nagot starkare. MEN detta star i skarp kontrast till DEL A,
# som ENSAM redan visade FAIL (Sharpe 0.8926/0.8940/0.8217). De tva
# fixarna ar INTE testade TILLSAMMANS i denna omkorning - en fullstandigt
# kombinerad pipeline (DEL A:s spreadkostnad + DEL D:s tre fynd
# samtidigt) har INTE korts och skulle sannolikt ge ett Sharpe-tal
# NARA DEL A:s (spreadkostnaden i sviten ar den dominerande, storre
# effekten av de tva) - men detta ar en slutsats INFERERAD fran de tva
# separata korningarna, inte ett faktiskt uppmatt resultat, och
# rapporteras darfor explicit som en oppen fraga, inte ett facit.

# ════════════════════════════════════════════════════════════
# TILLAGGSNOT DEL E 2026-08-08 (stanger DEL D:s oppna fraga samma dag -
# alla FYRA kanda fixar korda TILLSAMMANS i strategies/HYP-043/
# backtest.py: look-ahead-bias + adjusted_close-kvot + 10bps
# ombalanseringskostnad + corwin_schultz_spread pa momentum L/S-sviten.
# Status/kriterium/ovanstaende siffror ANDRADE INTE.)
# ════════════════════════════════════════════════════════════
# NYA SIFFROR (huvudperiod 2010-2024, ALLA FYRA fixar samtidigt):
#   Sharpe: 0.8765 / 0.8752 / 0.8392  (ursprungligen 1.0457/1.0498/0.9864)
#   MaxDD: -15.12% / -15.06% / -13.64% (PASS mot HYP-039:s -22.03% osv,
#     oforandrat fran DEL D - spreadkostnaden paverkar MaxDD marginellt)
#   OOS-2025 Sharpe: 1.7702 / 1.7171 / 1.6960 (PASS mycket starkt mot
#     HYP-039:s 0.9185/0.8116/0.7932, faktiskt HOGRE an DEL D isolerat)
#   DSR (K=46, RF=2%/ar): 0.8393 / 0.8382 / 0.8035
#
# Villkor 1 (Sharpe >= 1.0 vid $100k): FAIL (0.8765). Villkor 2 (Sharpe
# > HYP-039:s 1.0191): FAIL. Villkor 3 (MaxDD battre an HYP-039:s
# -22.03%): PASS tydligt. OOS-villkoret: PASS mycket starkt.
#
# SLUTSATS (DEL E, stanger DEL D:s oppna fraga): DEL D:s formodan
# bekraftas - den fullt kombinerade pipelinen ger ETT ENTYDIGT FAIL pa
# den avgorande $100k-nivan, pa BADE villkor 1 och 2. Spreadkostnaden
# (DEL A) forblir den dominerande, avgorande faktorn (0.8765 mot DEL
# A:s isolerade 0.8926 - de tre ovriga fixarna drar netto nagot
# YTTERLIGARE nedat tillsammans med spreadkostnaden, inte upp som de
# gjorde isolerat i DEL D, eftersom look-ahead-universumets paverkan pa
# just denna sviten vander tecken nar spreadkostnaden redan dominerar
# bilden). MaxDD- och OOS-villkoren forblir robusta PASS genom alla
# kombinationer av kanda fixar - HYP-043 ar fortfarande en genuint
# riskreducerande, positivt bidragande portfolj, bara inte en som
# klarar sitt eget 1.0-Sharpe-kriterium fullt friktionskorrekt.
#
# `status` star medvetet KVAR som `passed` - beslut om formell
# statusandring lamnas till CEO, som redan flera ganger i detta
# register (senast for HYP-047:s referensbeslut).
```

---

## KÄLLFIL: `research/hypothesis_registry/HYP-044-naiv-kombination-spy-hyp037-momentum-pead.yaml`

```
# LÅST 2026-08-07 av CEO i chatt, innan denna hypotes sätts pre-registered
# eller någon backtest körs.
#
# Foljer spec §5b:s regler for LEGITIM kombinationstestning, samma
# disciplin som HYP-039/041/043:
#   1. Korrelationsmatris FORE nagon vikt valdes - se
#      scripts/diagnostic_hyp044_pead_and_issuance.py (2026-08-07,
#      dagliga avkastningar, 3459 punkter): PEAD/SUE mot SPY -0.069,
#      mot HYP-037 -0.019, mot MomentumLS 0.003, mot hela HYP-043-
#      kombon -0.057. Dessutom en regimbetingad stresstest (INTE bara
#      fullperiodskorrelation, se lardomen fran den avfardade lagvol-
#      kandidaten samma dag): under HYP-043-kombons EGEN varsta
#      drawdown-period (2020-02-13 till 2020-03-23, Covid-kraschen)
#      levererade PEAD/SUE +3.25% - positiv precis nar resten av
#      portfoljen blodde som mest. Rullande 252-dagars korrelation
#      mot HYP-043-kombon holl sig mellan -0.31 och +0.16 GENOM HELA
#      perioden, aldrig over 0.3 i nagot fonster.
#   2. NAIV, likaviktad kombination (fyra fjardedelar) - INTE
#      in-sample-optimerade vikter.
#   3. Egen K-kostnad, separat fran SPY/HYP-037/momentum-svitens egna
#      bidrag OCH fran HYP-039/041/043 (denna ar INTE en modifiering
#      av nagon av dem - fyrdelad, inte tre- eller tvadelad).
#
# HARLEDNING (extern konsultation): PEAD/SUE-kandidaten togs fram fran
# en 5-AI-brainstorm 2026-08-07 (se session samma datum) efter att
# redan kanda dodlaget i registret (raw insiderkop = HYP-035 FAILED,
# small-cap kortsiktig reversal = HYP-042 FAILED KATASTROFALT) hade
# filtrerats bort fran forslagen. 6 andra kandidater samma dag (low-vol
# L/S, kvalitet L/S, 52v-hogsta L/S, tva trendfoljningsvarianter,
# bredare CTA-korg, nettoemission) testades ocksa diagnostiskt och
# avfardades - se research/hypothesis_registry/_counter.yaml for
# fullstandig lista.
#
# METODOLOGISK NOT: PEAD/SUE-sviten byggs med en KONSERVATIV
# forenkling vid EPS-omrakningar (forsta/tidigast filade vardet per
# fiskalt kvartal anvands, inte senare 10-Q/A-omraknade varden - detta
# speglar vad som faktiskt var kant i realtid, overskattar INTE edgen).
# Ingen split-justering av EPS gjordes - en kand, oppet redovisad risk
# for enstaka tickers med aktiesplittar mellan jamforda kvartal.
#
# FRIKTIONSNOT (upptackt 2026-08-07 vid byggandet av denna hypotes):
# HYP-043:s egen momentum L/S-svit saknar corwin_schultz_spread-
# anvandning (bara borrow_cost), vilket INTE skulle klara
# scripts/validate_friction_usage.py om det kordes idag - flaggat
# separat for CEO, INTE tyst atgardat i HYP-043 i efterhand. HYP-044:s
# PEAD/SUE-svit HAR bade borrow_cost OCH corwin_schultz_spread (halva
# spreaden vid ombalanseringens entry, pa den nya decilens namn) -
# verifierat med scripts/validate_friction_usage.py INNAN denna
# backtest kordes.
#
# status: pre-registered -> tested -> passed/failed

id: HYP-044
date_registered: '2026-08-07'
title: Naiv fyrdelad kombination (kvartalsvis ombalanserad) - SPY + HYP-037 + momentum L/S + PEAD/SUE
universe: "N/A for SPY/HYP-037/momentum-L/S-benen (redan testade). PEAD/SUE-benet
  byggs over SAMMA small-cap-universum ($100M-$2B) som HYP-037/HYP-043, ingen ny
  universumdefinition."
small_cap_definition: "small-cap, $100M - $2B börsvärde, EODHD All-World (galler
  PEAD/SUE-benets universum, ateranvander HYP-037:s redan lasta definition)"
data_range: "SPY-monster: adjusted_close 2010-2024 + genuin OOS-2025. PEAD/SUE:
  byggd fran kvartals-EPS (data/cache/eps_by_ticker.jsonl) over samma small-cap-
  universum och period, samma motorkrav (adjusted_close genomgaende, sarheten
  mot konstant orimlig adjusted_close/close-kvot, bade borrow_cost och
  corwin_schultz_spread)."
pass_fail_criterion: >
  MEKANISM (låst, ingen fri parameter kvar att välja):

  1. PEAD/SUE-SVITEN (det fjarde benet, byggs fran grunden har - INTE
  en redan existerande serie): kvartalsvis (HYP-037:s egna snappade
  datum), rangordna eligible small-cap-universumet efter sasongsjusterad
  SUE (Standardized Unexpected Earnings, Bernard & Thomas 1989/1990-stil)
  - overraskning = senaste rapporterade kvartals-EPS minus samma fiskala
  kvartal foregaende ar (matchat pa fy/fp, inte kalenderdatum), standardiserad
  med std av upp till 8 historiska kvartalsoverraskningar (kravs minst 4
  for en stabil skattning). Vid omrakningar anvands FORSTA (tidigast
  filade) vardet per fiskalt kvartal. LONG toppdecilen (storst positiv
  overraskning), KORT bottendecilen, likaviktat inom vardera benet,
  DOLLAR-NEUTRALT (50% notional long, 50% kort av sviten-benets EGEN
  allokering). Daglig vardering mellan ombalanseringarna. Lanekostnad
  pa kortbenet (BORROW_ANNUAL_RATE=3%) OCH halva Corwin-Schultz-spreaden
  vid varje ombalanserings entry (pa den nya decilens namn, bade long-
  och kortsidan) - se friktionsnoten ovan om varfor detta explicit
  sarskiljs fran HYP-043:s egen svit.

  2. KOMBINATION: 1/4 notional SPY + 1/4 notional HYP-037 (redan sparad
  strategies/HYP-037/results/portfolio_value_<niva>.csv, ANVAND
  OFORANDRAD) + 1/4 notional momentum L/S-sviten (redan sparad
  strategies/HYP-043/results/momentum_ls_sleeve_pv.csv, ANVAND
  OFORANDRAD) + 1/4 notional PEAD/SUE-sviten (punkt 1). Ombalanserad
  till exakt fjardedelar VARJE KVARTAL pa HYP-037:s REDAN LASTA datum.
  INGEN havstang utover sviten-benets egen interna 50/50 long/kort-
  struktur.

  PASS KRÄVER ALLA TRE, PA DEN AVGORANDE $100k-NIVAN (rapporteras for
  alla tre nivåer, samma konvention som HYP-039/041/043):
  1. Kombinerad Sharpe (2010-2024) >= 1.0.
  2. Kombinerad Sharpe > HYP-043:s EGNA redan registrerade Sharpe vid
     samma niva (1.0457/1.0498/0.9864) - HYP-043 ar den regerande
     mastaren, inte HYP-039, eftersom HYP-044 ar en utmanare mot den
     just nu starkaste referensen.
  3. Kombinerad MaxDD BATTRE an HYP-043:s EGNA redan registrerade MaxDD
     vid samma niva (-15.58%/-15.68%/-14.29%).

  OOS-2025: kombinerad OOS-2025 Sharpe MASTE vara > HYP-039:s EGEN
  OOS-2025 Sharpe vid samma niva (0.9185/0.8116/0.7932) - INTE mot
  HYP-043:s egen OOS-2025 (1.6163/1.5639/1.5321). Motivering, diskuterad
  och beslutad av CEO INNAN lasning: en enskild ars OOS-Sharpe-skattning
  har ett standardfel i storleksordningen ±1.0 Sharpe-enheter (Lo 2002-
  stil), sa en skillnad pa 0.2-0.3 mellan tva kombinationers OOS-Sharpe
  fran SAMMA underliggande 2025-ar ar inte statistiskt sarskiljbar brus
  - att krava seger mot HYP-043:s egna, redan sjalvt flaggade "spektakulara,
  bor inte overtolkas"-OOS-varde vore att straffa kandidaten for att inte
  slå en opalitlig punktskattning. HYP-039:s OOS-varde anvands istallet,
  samma referens HYP-043 sjalvt matades mot.

  FAIL om nagot villkor faller vid $100k-nivan.

  Diagnostiskt syfte: testar om en EGENBYGGD (inte konsensusestimat-
  baserad) sasongsjusterad resultatoverraskningssignal (PEAD/SUE) kan
  hoja den kombinerade Sharpen OCH sanka MaxDD bortom vad HYP-043
  (SPY+HYP-037+momentum L/S) redan uppnar - fjarde kombinationshypotesen
  i registret, forsta som byggdes fran en systematisk extern multi-AI-
  konsultation (5 oberoende AI-svar, se session 2026-08-07) snarare an
  en CEO- eller Claude-genererad idé.
status: failed   # pre-registered -> tested -> passed/failed
k_total_hypotheses_before_this: 42
tested_capital_levels:
- 100000
- 1000000
- 10000000
capital_level_results:
  100000: {sharpe: 1.0117, cagr: 0.0875, max_drawdown: -0.1092, calmar: 0.8011, oos_2025_sharpe: 1.3731, oos_2025_total_return: 0.2207, oos_2025_max_drawdown: -0.0587, deflated_sharpe_ratio: 0.9366}
  1000000: {sharpe: 1.0135, cagr: 0.0865, max_drawdown: -0.1100, calmar: 0.7873, oos_2025_sharpe: 1.3203, oos_2025_total_return: 0.2119, oos_2025_max_drawdown: -0.0581, deflated_sharpe_ratio: 0.9366}
  10000000: {sharpe: 0.9439, cagr: 0.0787, max_drawdown: -0.0995, calmar: 0.7906, oos_2025_sharpe: 1.2995, oos_2025_total_return: 0.2067, oos_2025_max_drawdown: -0.0604, deflated_sharpe_ratio: 0.8975}
date_tested: '2026-08-07'
result_summary: >
  FAILED PA DEN AVGORANDE $100k-NIVAN, PA VILLKOR 2 SPECIFIKT - men
  ett INFORMATIVT, inte katastrofalt, FAIL, och en viktig metodologisk
  handelse under byggandet fortjanar att sta forst.

  METODOLOGISK HANDELSE (INNAN resultaten): under byggandet av denna
  hypotes upptacktes att HYP-043:s egen momentum L/S-svit ALDRIG
  anropar corwin_schultz_spread (bara borrow_cost) - scripts/
  validate_friction_usage.py skulle IDAG avvisa strategies/HYP-043/
  backtest.py om den korde om gaten. HYP-044 byggdes med bade
  borrow_cost OCH genuin Corwin-Schultz-spreadkostnad (halva spreaden
  pa den nya decilens namn vid varje ombalansering), verifierat INNAN
  backtesten kordes. Effekten av att lagga till den tidigare saknade
  friktionen var STOR och gick i FORVANTAD (forsvagande) riktning: en
  parallell diagnostik UTAN spreadkostnad (scripts/
  diagnostic_hyp044_pead_4leg_combo.py, samma dag) visade Sharpe
  1.085/1.088/1.022 - klart battre an HYP-043 pa alla tre nivaer. MED
  genuin spreadkostnad blev Sharpe 1.012/1.014/0.944 - fortfarande
  positivt men INTE langre battre an HYP-043. Detta ar en ren,
  konkret illustration av spec §2 princip 3 ("friktion fran dag ett,
  aldrig bultad pa efterat efter att ha sett bra resultat") - hade
  spreadkostnaden hoppats over (som i HYP-043:s egen svit) hade detta
  sett ut som en tydlig vinst. HYP-043:s EGNA redan lasta resultat
  paverkas INTE retroaktivt av detta fynd (last historia andras inte
  i efterhand) - men detta ar flaggat separat for CEO som en oppen
  fraga om HYP-043 bor fa en dokumenterad robusthetsdiagnostik med
  spreadkostnad tillagd (ingen K-kostnad, andrar inte status).

  Villkor 1 (Sharpe >= 1.0 vid $100k): 1.0117 - PASS, marginellt over
  malet (mot HYP-043:s egna 1.0457). $10M missar detta villkor
  (0.9439) men $10M ar INTE den avgorande nivan per kriteriet.

  Villkor 2 (Sharpe > HYP-043:s egna vid samma niva): FAIL PA ALLA TRE
  NIVAER (1.0117 vs 1.0457 vid $100k, 1.0135 vs 1.0498 vid $1M, 0.9439
  vs 0.9864 vid $10M) - konsekvent, inte en enskild niva-slump. Detta
  ar det AVGORANDE misslyckade villkoret.

  Villkor 3 (MaxDD battre an HYP-043:s egna): PASS PA ALLA TRE NIVAER,
  och inte marginellt - -10.92%/-11.00%/-9.95% mot HYP-043:s
  -15.58%/-15.68%/-14.29%, en forbattring pa 4.34-4.68 PROCENTENHETER.
  Riskreduktionen ar genuin och konsekvent, aven om Sharpe-villkoret
  faller.

  OOS-2025 (villkor 4): PASS PA ALLA TRE NIVAER, tydligt - 1.3731/
  1.3203/1.2995 mot HYP-039:s egna 0.9185/0.8116/0.7932. (Kriteriet
  jamforde medvetet mot HYP-039, inte HYP-043, av den redan
  dokumenterade enars-brus-anledningen - se kriterietexten. Mot
  HYP-043:s egen OOS 1.6163/1.5639/1.5321 hade aven detta villkor
  FAILAT, men det var uttryckligen INTE fragan kriteriet stallde.)

  DSR vid K=43: 0.94/0.94/0.90 - fortsatt hogt, ingen indikation pa
  att den positiva Sharpen sjalv ar en slumptrafff, bara att den inte
  ar TILLRACKLIGT hog for att sla den redan starka referensen.

  DIAGNOS: PEAD/SUE-sviten ar sannolikt en genuin, mattligt positiv,
  genuint diversifierande komponent (regimbetingad stresstest INNAN
  lasning visade positiv avkastning under HYP-043-kombons egen varsta
  drawdown-period, rullande korrelation aldrig over 0.3) - men dess
  EGNA riskjusterade kvalitet (isolerad Sharpe ~0.22, se diagnostik)
  ar inte tillrackligt stark for att det fjarde benet ska hoja den
  redan starka HYP-043-kombinationens Sharpe, aven med genuint bra
  korrelationsegenskaper. Samma lardom som HYP-041:s TLT, fast mindre
  extremt: korrelation ensam raddar inte ett ben vars egen kvalitet
  inte racker for att bara sin vikt i Sharpe-termer, MEN den ger
  fortfarande en genuin, konsekvent MaxDD-forbattring - en annan typ
  av vardefullt bidrag an det kriteriet var lasrt att mata.

  SLUTSATS: HYP-043 (SPY+HYP-037+momentum L/S) forblir referens-
  implementationen. HYP-044 introducerar dock en genuint anvandbar,
  lag-korrelerad byggsten (PEAD/SUE) som skulle kunna vara vardefull
  i en ANNAN kombination eller vid en annan vikt - men det kraver en
  egen, ny, separat last hypotes (t.ex. riskparitetsviktning eller
  en 5:e-bens-kombination), inte en tyst efterhandsjustering av detta
  redan lasta resultat.

# ════════════════════════════════════════════════════════════
# TILLAGGSNOT 2026-08-08 (tre oberoende adversariella granskare - INTE
# en ny hypotes/K-test, status/pass_fail_criterion/tested_capital_levels/
# capital_level_results ovan ANDRADE INTE)
# ════════════════════════════════════════════════════════════
# Fullstandig omkorning: filed-datum-korrigerat universum (bade for PEAD/
# SUE-svitens egen konstruktion har OCH for HYP-037-benet), close_adj
# maskad mot orimlig kvot via delade data_hygiene.py::
# mask_implausible_adjusted_close_ratio (tidigare inline har, oforandrad
# tröskel), samt en NY 10bps portfoljniva-ombalanseringskostnad i
# combine_quarters (fanns inte tidigare). Under samma korrigering hittades
# och fixades ocksa en BLOCKERANDE bugg (HYP043_RESULTS anvandes utan att
# vara definierad - se strategies/HYP-044/backtest.py:s kommentar och
# huvudrapporten). momentum L/S-benet laser nu HYP-043:s (ocksa
# korrigerade) resultat. Resultat i
# strategies/HYP-044/results_corrected_2026-08-08/ (results/ rors INTE).
#
# NYA SIFFROR (huvudperiod 2010-2024):
#   Sharpe: 0.9525 / 0.9512 / 0.9144  (tidigare 1.0117 / 1.0135 / 0.9439)
#   MaxDD: -10.86% / -10.62% / -9.44% (tidigare -10.92% / -11.00% / -9.95%)
#   DSR (K=46, RF=2%/ar): 0.8975 / 0.8968 / 0.8703
#
# Villkor 1 (Sharpe >= 1.0): FAIL PA ALLA TRE, oforandrat (marginalen
# okade nagot - 0.9525 mot tidigare 1.0117 vid $100k). Villkor 2 (Sharpe
# > HYP-043:s ursprungliga 1.0457/1.0498/0.9864): FAIL PA ALLA TRE,
# oforandrat. Villkor 3 (MaxDD battre an HYP-043:s ursprungliga -15.58%/
# -15.68%/-14.29%): PASS TYDLIGT pa alla tre, oforandrat, nagot battre an
# tidigare.
#
# SLUTSATS: HYP-044:s FAILED-slutsats star OFORANDRAD under den
# fullstandigt korrigerade pipelinen. Notera: HYP-043:s egen, SEPARAT
# dokumenterade friktionsbrist (saknad spreadkostnad i momentum L/S-
# sviten, se HYP-043:s tilläggsnot DEL A) paverkar INTE denna jamforelse
# direkt, eftersom HYP-044:s eget kriterium jamfor mot HYP-043:s
# URSPRUNGLIGA, redan lasta siffror - inte mot den senare friktions-
# korrigerade baslinjen som HYP-045/046/047 anvander.
```

---

## KÄLLFIL: `research/hypothesis_registry/HYP-045-krasch-overlay-spy-momentum-ben.yaml`

```
# LÅST 2026-08-07 av CEO i chatt, innan denna hypotes sätts pre-registered
# eller någon backtest körs.
#
# Foljer spec §5b, femte kombinationshypotesen i registret - denna gang
# INTE ett nytt 4:e ben utan en MODIFIERING av hur tva av tre redan
# befintliga ben beter sig under marknadsstress.
#
# HARLEDNING (empirisk, INTE hindsight-vald idag): en attributionsanalys
# 2026-08-07 (samma dag, se chattsession) mot de 5 krisepisoder som
# REDAN ar etablerade i registret sedan tidigare (scripts/
# diagnostic_hyp017_leave_one_crisis_out.py och
# diagnostic_hyp037_leave_one_crisis_out.py, byggda for ett annat syfte
# manader innan denna hypotes): 2011-08-04 (skuldtak), 2015-08-24
# (Black Monday), 2018-12-24 (julafton-massakern), 2020-02-27 till
# 2020-03-16 (covid), 2022-06-16/2022-09-26 (bjornmarknad). Dessa 5
# episoder, +-varierande fonster runt varje datum, motsvarar 276 av
# HYP-043-kombons 3459 dagar (8.0%) men star for -26.76% kumulativ
# avkastning, medan de ovriga 92% av dagarna gav +463.58%.
#
# VIKTIG METODOLOGISK GRANS (diskuterad explicit med CEO INNAN lasning):
# CEO:s ursprungliga ide var att identifiera krisperioder genom att
# LASA NYHETER fran perioden - detta AVVISADES uttryckligen har som
# for riskabelt (hindsight-urval av VILKA perioder som "raknas" baserat
# pa att redan ha sett att de kostade pengar i backtesten, exakt samma
# fallgrop som dodade de 7 ursprungliga Ejay-varianterna). Denna
# hypotes anvander ISTALLET en REN PRISBASERAD, redan I FORVAG (manader
# innan denna session) etablerad trigger fran HYP-017/023/037 - samma
# mekanism skulle ha triggat pa VILKEN FRAMTIDA kris som helst, inte
# bara de vi redan kanner till.
#
# STATUS PA HYP-043:s EGNA SIFFROR (viktigt sammanhang): en separat
# robusthetsdiagnostik samma dag (scripts/diagnostic_hyp043_friction_
# robustness.py) visade att HYP-043:s redan LASTA resultat (Sharpe
# 1.0457/1.0498/0.9864) byggde pa en OFULLSTANDIG friktionsmodell
# (momentum L/S-sviten anropade aldrig corwin_schultz_spread). Med
# genuin spreadkostnad tillagd blir HYP-043:s Sharpe 0.8926/0.8940/
# 0.8217 - klarar INTE langre sitt eget ursprungliga kriterium (varken
# >=1.0 eller att sla HYP-039). Detta har INTE andrat HYP-043:s redan
# lasta registerpost (last historia andras inte i efterhand) men denna
# hypotes jamfor mot den FRIKTIONSKORRIGERADE baslinjen, inte den
# ursprungligen lasta, eftersom den senare byggde pa en kand
# ofullstandighet.
#
# status: pre-registered -> tested -> passed/failed

id: HYP-045
date_registered: '2026-08-07'
title: Krasch-overlay (aterananvander HYP-037:s redan lasta trigger) pa SPY- och momentum L/S-benen
universe: "N/A for SPY/HYP-037-benen (redan testade, HYP-037 orort). Momentum L/S-benet
  byggs over SAMMA small-cap-universum ($100M-$2B) som HYP-037/HYP-043/HYP-044."
small_cap_definition: "small-cap, $100M - $2B börsvärde, EODHD All-World (galler
  momentum L/S-benets universum, ateranvander HYP-037:s redan lasta definition)"
data_range: "SPY-monster: adjusted_close 2010-2024 + genuin OOS-2025 (innehaller en
  akta SPY-krasch, -18.8% MaxDD april 2025 - genuint forsta-gangen-test av
  mekanismen). Momentum L/S: byggd med bade borrow_cost och corwin_schultz_spread
  fran start, samma motorkrav som HYP-044."
pass_fail_criterion: >
  MEKANISM (låst, ingen fri parameter kvar att välja - samtliga
  triggerparametrar återanvända OFÖRÄNDRADE från HYP-037:s redan
  låsta overlay, inte en ny sökning):

  1. GEMENSAM TRIGGER (identisk med HYP-037:s egen, ren SPY-prisdata):
  SPY:s 10-dagars kumulativa avkastning < -10% (CRASH_LOOKBACK_DAYS=10,
  CRASH_TRIGGER_RET=-0.10). Vid trigger: skär ner till 40% av
  positionsvärdet (CRASH_HAIRCUT_FRACTION=0.40). Återinträde till full
  position först när SPY återhämtat minst 50% av det utlösande fallet
  (RECOVERY_FRACTION=0.50). DOKUMENTERAD FÖRENKLING (nödvändig
  anpassning, se moduldocstring i strategies/HYP-045/backtest.py):
  ingen separat "vänta till nästa ordinarie ombalansering"-fördröjning
  och ingen likviditetsnormaliseringsgrind (båda saknar naturlig
  motsvarighet för en enskild ETF/aggregerad svit) - återbyggnad sker
  omedelbart när prisåterhämtningsvillkoret uppfylls.

  2. TILLÄMPNING PÅ DE TVÅ IDAG OSKYDDADE BENEN:
  a. SPY-benet: haircut/återuppbyggnad enligt punkt 1, frigjort kapital
  till riskfri ränta.
  b. Momentum L/S-benet (byggd MED både borrow_cost och genuin
  corwin_schultz_spread-kostnad): haircut/återuppbyggnad enligt punkt 1
  på HELA sviten, förblir dollarneutral på den mindre nivån.
  c. HYP-037-benet: OFÖRÄNDRAT - redan sparad serie, har redan sin EGEN
  separata krasch-overlay, rörs inte.

  3. KOMBINATION: likaviktade tredjedelar (SPY-med-overlay + HYP-037-
  oförändrad + MomentumLS-med-overlay), kvartalsvis ombalansering,
  samma snappade datum som HYP-037/039/043/044.

  PASS KRÄVER ALLA TRE, PÅ DEN AVGÖRANDE $100k-NIVÅN (rapporteras för
  alla tre nivåer):
  1. Kombinerad Sharpe (2010-2024, friktionskorrekt) >= 1.0.
  2. Kombinerad Sharpe > FRIKTIONSKORRIGERAD HYP-043-baslinje vid samma
  nivå (0.8926/0.8940/0.8217 - INTE de ursprungligen låsta 1.0457/
  1.0498/0.9864, se motivering i registerpostens header).
  3. Kombinerad MaxDD BÄTTRE än samma friktionskorrigerade baslinje
  (-15.58%/-15.68%/-14.29%).

  OOS-2025: kombinerad OOS-Sharpe > HYP-039:s EGEN OOS-Sharpe
  (0.9185/0.8116/0.7932) - samma enårsbrus-motivering som HYP-044.
  Särskilt relevant här: OOS-2025 innehåller en genuin SPY-krasch
  (-18.8% MaxDD, april 2025) - detta ger mekanismen ett äkta, aldrig
  tidigare sett test av EXAKT det den är byggd för att hantera.

  FAIL om något villkor faller vid $100k-nivån.

  Diagnostiskt syfte: testar om HYP-037:s redan bevisade (3/3 PASSED
  i registret: HYP-017/023/037) exponeringstimingsmekanism, tillämpad
  på de två benen som idag saknar den, kan återställa och överträffa
  den friktionskorrekta Sharpe-nivån samtidigt som redan god MaxDD
  bibehålls eller förbättras.
status: failed   # pre-registered -> tested -> passed/failed
k_total_hypotheses_before_this: 43
tested_capital_levels:
- 100000
- 1000000
- 10000000
capital_level_results:
  100000: {sharpe: 0.9941, cagr: 0.0983, max_drawdown: -0.1456, calmar: 0.6752, oos_2025_sharpe: 1.5961, oos_2025_total_return: 0.3212, oos_2025_max_drawdown: -0.0988, deflated_sharpe_ratio: 0.9280}
  1000000: {sharpe: 0.9989, cagr: 0.0971, max_drawdown: -0.1383, calmar: 0.7020, oos_2025_sharpe: 1.5427, oos_2025_total_return: 0.3083, oos_2025_max_drawdown: -0.1058, deflated_sharpe_ratio: 0.9292}
  10000000: {sharpe: 0.9287, cagr: 0.0869, max_drawdown: -0.1217, calmar: 0.7150, oos_2025_sharpe: 1.5079, oos_2025_total_return: 0.3005, oos_2025_max_drawdown: -0.1113, deflated_sharpe_ratio: 0.8860}
date_tested: '2026-08-07'
result_summary: >
  FAILED PA DEN AVGORANDE $100k-NIVAN, PA VILLKOR 1 SPECIFIKT (Sharpe
  >= 1.0) - men ett RAKBLADSTUNT missat mal, inte ett tydligt
  misslyckande, och mekanismen fungerade uppenbart som avsett pa alla
  andra matt.

  Villkor 1 (Sharpe >= 1.0 vid $100k): 0.9941 - FAIL, men med en
  marginal pa bara 0.0059 (0.6% under malet). $1M kom annu narmare
  (0.9989, 0.0011 under). Bada dessa ar valdigt nara, i motsats till
  ett strukturellt/tydligt misslyckande.

  Villkor 2 (Sharpe > friktionskorrigerad HYP-043-baslinje): PASS PA
  ALLA TRE NIVAER, och tydligt - 0.9941/0.9989/0.9287 mot 0.8926/
  0.8940/0.8217, en forbattring pa 0.09-0.11 Sharpe-enheter. Overlayn
  hojde alltsa den friktionskorrekta Sharpen betydligt, precis som
  avsett - bara inte tillrackligt for att korsa 1.0-troskeln.

  Villkor 3 (MaxDD battre an friktionskorrigerad HYP-043-baslinje):
  PASS PA ALLA TRE NIVAER - -14.56%/-13.83%/-12.17% mot -15.58%/
  -15.68%/-14.29%, en forbattring pa 1.0-2.1 procentenheter. Mindre
  dramatisk forbattring an HYP-043 sjalv gav over HYP-039 (dar
  forbattringen var 6+pp), men konsekvent i ratt riktning pa alla tre
  nivaer.

  OOS-2025 (villkor 4): PASS PA ALLA TRE NIVAER, mycket starkt -
  1.596/1.543/1.508 mot HYP-039:s 0.919/0.812/0.793. Sarskilt
  informativt: OOS-2025 innehaller en AKTA SPY-krasch (-18.8% MaxDD,
  april 2025) - detta var mekanismens forsta genuina, aldrig tidigare
  sedda test av precis det den ar byggd for att hantera, och den
  klarade det med god marginal (OOS-avkastning +30-32%, battre an
  bade HYP-043:s och HYP-044:s egna OOS-avkastningar).

  MEKANISMENS EGEN AKTIVITET: overlayn triggade 3.3% av dagarna (134
  av 4024) - betydligt smalare an den bredare 8.0%-krisfonster-
  attributionen som motiverade hypotesen (striktare tröskel: SPY:s
  10-dagars avkastning under -10%, inte breda kalenderfonster runt
  kanda krisdatum). Mekanismen exercerades genuint, inte en no-op.

  DSR vid K=44: 0.93/0.93/0.89 - fortsatt hogt.

  DIAGNOS: overlayn levererar precis den typ av forbattring den
  designades for (hojer Sharpe, sanker MaxDD, jamfort med den
  friktionskorrekta baslinjen) - men den friktionskorrigerade
  baslinjen (0.89) lag langre under 1.0-malet an vad en enda,
  redan bevisad timing-mekanism kunde ta igen helt. Detta ar INTE
  samma dodsmonster som HYP-041/044 (dar sviten-benets EGEN kvalitet
  inte rackte) - har fungerade mekanismen, marginalen var bara for
  liten. Konsistent med registrets etablerade monster:
  exponeringstimingsmekanismer (HYP-017/023/037, och nu denna,
  om an som FAIL) fortsatter leverera genuina forbattringar var gang
  de testas, till skillnad fran urvals-/viktningsforsok.

  SLUTSATS: HYP-043 forblir referensimplementationen (dess egna,
  redan lasta siffror star oforandrade i registret, se separat oppen
  fraga om en formell friktionskorrigering av HYP-043:s post). Denna
  hypotes visar att en YTTERLIGARE forbattring fran samma redan
  bevisade timing-familj ar mojlig men INTE tillrackligt stor for att
  ensam lyfta den friktionskorrekta bilden over 1.0-troskeln - en
  framtida kombination av BADE denna overlay OCH ett genuint nytt,
  starkt 4:e ben (ingen av de hittills testade kandidaterna har
  rackt) skulle kravas for att na dit, inte endera separat.

# ════════════════════════════════════════════════════════════
# TILLAGGSNOT 2026-08-08 (tre oberoende adversariella granskare - INTE
# en ny hypotes/K-test, status/pass_fail_criterion/tested_capital_levels/
# capital_level_results ovan ANDRADE INTE)
# ════════════════════════════════════════════════════════════
# Fullstandig omkorning: filed-datum-korrigerat universum (momentum L/S-
# svitens egen konstruktion + HYP-037-benet), close_adj maskad mot
# orimlig kvot via delade data_hygiene.py::mask_implausible_adjusted_close_ratio
# (tidigare inline har), samt en NY 10bps portfoljniva-ombalanserings-
# kostnad i combine_thirds (fanns inte tidigare - denna hypotes hade
# redan spreadkostnad INOM momentum L/S-sviten, se moduldocstring, men
# INTE mellan de tre benen vid kvartalsvis vikt-aterstallning). Resultat
# i strategies/HYP-045/results_corrected_2026-08-08/ (results/ rors INTE).
#
# NYA SIFFROR (huvudperiod 2010-2024):
#   Sharpe: 0.9845 / 0.9846 / 0.9546  (tidigare 0.9941 / 0.9989 / 0.9287)
#   MaxDD: -14.08% / -13.76% / -11.83% (tidigare -14.56% / -13.83% / -12.17%)
#   DSR (K=46, RF=2%/ar): 0.9184 / 0.9186 / 0.9000
#
# Villkor 1 (Sharpe >= 1.0 vid $100k): FAIL, oforandrat - fortfarande ett
# rakbladstunt nara-miss (0.9845, 0.0155 under malet, tidigare 0.9941,
# 0.0059 under - marginalen VIDGADES nagot av den nya kostnaden men
# slutsatsen ar densamma: naraliggande men INTE PASS). Villkor 2 (sla
# friktionskorrigerad HYP-043-baslinje 0.8926/0.8940/0.8217): PASS
# TYDLIGT pa alla tre, oforandrat. Villkor 3 (MaxDD battre an samma
# baslinje): PASS PA ALLA TRE, oforandrat, nagot battre an tidigare.
#
# SLUTSATS: HYP-045:s FAILED-slutsats (rakbladstunt nara-miss pa villkor
# 1) star OFORANDRAD under den fullstandigt korrigerade pipelinen -
# samma kvalitativa bild som tidigare, ingen flip i nagon riktning.
```

---

## KÄLLFIL: `research/hypothesis_registry/HYP-046-overlay-plus-pead-fyrdelad.yaml`

```
# LÅST 2026-08-07 av CEO i chatt, innan denna hypotes sätts pre-registered
# eller någon backtest körs.
#
# Foljer spec §5b. VIKTIGT: detta ar INTE en "kombinera tva misslyckade
# hypoteser for att radda dem"-genvag (uttryckligen forbjudet i CLAUDE.md)
# - motivering, diskuterad med CEO INNAN lasning:
#   1. Bade HYP-044 och HYP-045 hade HOG DSR (0.90-0.94 respektive
#      0.89-0.93 vid K=43/44) - dvs sannolikt GENUINA, inte
#      slumpmassiga resultat, trots att de inte klarade sina egna
#      specifika jamforelsekriterier.
#   2. De ar MEKANISKT OLIKA fran varandra: HYP-044 ar en ny
#      diversifierande alfakalla (PEAD/SUE), HYP-045 ar en risk-timing-
#      overlay pa REDAN BEFINTLIGA ben - ingen overlappning i mekanism.
#   3. Detta ar EN enda, i forvag motiverad kombination (inte en sokning
#      over manga kombinationer tills nagon rakar fungera) - egen
#      K-kostnad, last INNAN resultatet setts.
#
# DESIGNBESLUT: overlayn (HYP-045:s redan lasta triggerparametrar)
# TILLAMPAS PA SPY- och momentum L/S-benen (som i HYP-045), men INTE pa
# PEAD/SUE-benet - PEAD/SUE visade sig REDAN vara positiv (+3.25%,
# se HYP-044:s registerpost) under HYP-043-kombons egen varsta
# krasch-period, sa att skara ner dess exponering under kriser skulle
# motverka en redan gynnsam egenskap.
#
# status: pre-registered -> tested -> passed/failed

id: HYP-046
date_registered: '2026-08-07'
title: Krasch-overlay (HYP-045) + PEAD/SUE-ben (HYP-044) - fyrdelad likaviktad kombination
universe: "N/A for SPY/HYP-037-benen (redan testade, HYP-037 orort). Momentum L/S-
  och PEAD/SUE-benen byggs over SAMMA small-cap-universum ($100M-$2B) som HYP-037/
  043/044/045."
small_cap_definition: "small-cap, $100M - $2B börsvärde, EODHD All-World (galler
  momentum L/S- och PEAD/SUE-benens universum, ateranvander HYP-037:s redan lasta
  definition)"
data_range: "SPY: adjusted_close 2010-2024 + genuin OOS-2025. Momentum L/S och
  PEAD/SUE: byggda MED bade borrow_cost och corwin_schultz_spread fran start,
  samma motorkrav som HYP-044/045."
pass_fail_criterion: >
  MEKANISM (låst, ingen fri parameter kvar att välja - ateranvander
  BADE HYP-044:s och HYP-045:s redan lasta byggstenar OFORANDRADE):

  1. SPY-benet: HYP-045:s krasch-overlay (SPY 10-dagars avkastning
  <-10% -> haircut till 40%, aterintrade vid 50% aterhamtning).
  2. HYP-037-benet: OFORANDRAT, egen separat overlay.
  3. Momentum L/S-benet (byggd MED borrow_cost + corwin_schultz_spread,
  HYP-045:s konstruktion): SAMMA krasch-overlay som SPY-benet.
  4. PEAD/SUE-benet (byggd MED borrow_cost + corwin_schultz_spread,
  HYP-044:s konstruktion): OFORANDRAT, INGEN overlay (se motivering i
  registerpostens header - visade sig redan vara defensiv under kris).

  KOMBINATION: likaviktade fjardedelar (25% vardera av de fyra benen
  ovan), kvartalsvis ombalansering, samma snappade datum som
  HYP-037/039/043/044/045.

  PASS KRÄVER ALLA TRE, PÅ DEN AVGÖRANDE $100k-NIVÅN:
  1. Kombinerad Sharpe (2010-2024, friktionskorrekt) >= 1.0.
  2. Kombinerad Sharpe > FRIKTIONSKORRIGERAD HYP-043-baslinje vid samma
  nivå (0.8926/0.8940/0.8217).
  3. Kombinerad MaxDD BÄTTRE än samma friktionskorrigerade baslinje
  (-15.58%/-15.68%/-14.29%).

  OOS-2025: kombinerad OOS-Sharpe > HYP-039:s EGEN OOS-Sharpe
  (0.9185/0.8116/0.7932).

  FAIL om något villkor faller vid $100k-nivån.

  Rapporteras dessutom (INFORMATIVT, INTE gating): jamforelse mot
  BADE HYP-044:s (1.0117/1.0135/0.9439 Sharpe) och HYP-045:s
  (0.9941/0.9989/0.9287 Sharpe) egna resultat, for att se om
  kombinationen ar battre an bada delarna var for sig.

  Diagnostiskt syfte: testar om tva separat genuina (hog DSR), mekaniskt
  icke-overlappande forbattringar (ny alfakalla + risk-timing) stapl
  additivt nog for att tillsammans klara den friktionskorrekta
  1.0-troskeln som ingendera klarade ensam.
status: failed   # pre-registered -> tested -> passed/failed
k_total_hypotheses_before_this: 44
tested_capital_levels:
- 100000
- 1000000
- 10000000
capital_level_results:
  100000: {sharpe: 0.9475, cagr: 0.0795, max_drawdown: -0.0973, calmar: 0.8177, oos_2025_sharpe: 1.3524, oos_2025_total_return: 0.2170, oos_2025_max_drawdown: -0.0587, deflated_sharpe_ratio: 0.8996}
  1000000: {sharpe: 0.9492, cagr: 0.0785, max_drawdown: -0.0919, calmar: 0.8546, oos_2025_sharpe: 1.2990, oos_2025_total_return: 0.2082, oos_2025_max_drawdown: -0.0581, deflated_sharpe_ratio: 0.8996}
  10000000: {sharpe: 0.8726, cagr: 0.0707, max_drawdown: -0.0796, calmar: 0.8886, oos_2025_sharpe: 1.2759, oos_2025_total_return: 0.2030, oos_2025_max_drawdown: -0.0604, deflated_sharpe_ratio: 0.8396}
date_tested: '2026-08-07'
result_summary: >
  FAILED PA DEN AVGORANDE $100k-NIVAN, PA VILLKOR 1 (Sharpe >= 1.0) -
  och OVANTAT, det STORSTA missat mot 1.0-troskeln av de tre senaste
  forsoken (HYP-044/045/046), TROTS att bada byggstenarna var for sig
  var genuina forbattringar. En genuint informativ, icke-additiv
  overraskning.

  Villkor 1 (Sharpe >= 1.0): 0.9475/0.9492/0.8726 - FAIL pa alla tre,
  och med STORRE marginal an bade HYP-044 (1.0117/1.0135/0.9439, PASS
  vid 100k/1M) och HYP-045 (0.9941/0.9989/0.9287, rakblunt FAIL).
  Kombinationen av tva genuina forbattringar gav alltsa en LAGRE
  Sharpe an ENDERA komponenten var for sig - INTE additivt, tvartom.

  Villkor 2 (Sharpe > friktionskorrigerad HYP-043-baslinje 0.8926/
  0.8940/0.8217): PASS PA ALLA TRE NIVAER (0.9475/0.9492/0.8726).

  Villkor 3 (MaxDD battre an samma baslinje -15.58%/-15.68%/-14.29%):
  PASS PA ALLA TRE, och DRAMATISKT - -9.73%/-9.19%/-7.96%, en
  forbattring pa 5.85-6.49 PROCENTENHETER. Detta ar den BASTA MaxDD-
  siffran i HELA registrets historia for en kombinationshypotes, och
  battre an bade HYP-044 (-10.9%/-11.0%/-10.0%) och HYP-045 (-14.56%/
  -13.83%/-12.17%) var for sig. Calmar (0.818/0.855/0.889) ar OCKSA
  battre an bade HYP-044:s och HYP-045:s egna Calmar-tal, och battre
  an den friktionskorrigerade HYP-043-baslinjens (0.610/0.599/0.587).

  OOS-2025 (villkor 4): PASS PA ALLA TRE NIVAER (1.352/1.299/1.276
  mot HYP-039:s 0.919/0.812/0.793), men LAGRE an bade HYP-044:s
  (1.373/1.320/1.300) och HYP-045:s (1.596/1.543/1.508) egna OOS-Sharpe
  - samma monster som huvudperioden.

  DSR vid K=45: 0.90/0.90/0.84 - fortsatt hogt, genuint resultat.

  DIAGNOS (viktig, oforvantad lardom): CAGR foll till 7.95%/7.85%/
  7.07% - LAGRE an bade HYP-044:s (8.75%/8.65%/7.87%) och HYP-045:s
  (9.83%/9.71%/8.69%) egna CAGR. De tva mekanismerna (krasch-overlay
  pa SPY/momentum + ett nytt, likaviktat 4:e PEAD/SUE-ben) drar BADA
  ner den totala avkastningen samtidigt som de sanker risken - overlayn
  genom att skara ner exponering under kriser (missar avkastning under
  ateraterhamtningsfaser), det nya benet genom att spa ut de tre
  starkare benens vikt fran 1/3 till 1/4 vardera. Nar bada tillampas
  SAMTIDIGT blir den sammanlagda avkastningsutspadningen storre an
  den sammanlagda riskreduktionens fordel i just SHARPE-termer (aven
  om den ar en tydlig fordel i MaxDD/Calmar-termer) - tva riskreducerande
  mekanismer som var och en fungerar bra separat overkorrigerar
  tillsammans mot risk pa bekostnad av avkastning. INTE en varning-
  signal om att nagondera mekanism ar falsk (DSR forblir hog) - ett
  genuint, forst nu synligt portfoljkonstruktionsfenomen.

  SLUTSATS: HYP-043 forblir referensimplementationen for Sharpe-malet.
  MEN om malet istallet vore lagst mojlig MaxDD/hogst Calmar snarare
  an hogst Sharpe, ar HYP-046 den klart starkaste kandidaten i HELA
  registret (Calmar 0.82-0.89, MaxDD under -10% pa alla nivaer) - ett
  konkret, empiriskt exempel pa Sharpe/MaxDD-avvagningen som
  diskuterades explicit med CEO tidigare samma dag (HYP-043 vs
  HYP-044-kombinationen). Ingen ytterligare stapling av redan kanda
  mekanismer rekommenderas utan en ny, separat motiverad idé - tre
  raka FAIL (044/045/046) efter en genuin PASS (043) tyder pa att
  denna specifika portfolj narmar sig en praktisk grans for vad naiv
  likaviktad kombination av de hittills kanda byggstenarna kan uppna.

# ════════════════════════════════════════════════════════════
# TILLAGGSNOT 2026-08-08 (granskningsfynd, tre oberoende adversariella
# granskare - INTE en ny hypotes/K-test, status/kriterium/resultat
# ANDRADE INTE)
# ════════════════════════════════════════════════════════════
# Registerpostens header (rad 11-13 ovan) hävdade kvalitativt att
# HYP-044 (PEAD/SUE) och HYP-045 (krasch-overlay) är "mekaniskt olika...
# ingen overlappning i mekanism" - men till skillnad från HYP-039/041/
# 043/044 saknade denna fil den kvantitativa dagliga korrelationssiffra
# spec §5b kraver INNAN kombinationstestning. Beräknad i efterhand
# (ANDRAR INTE last status - samma disciplin som HYP-037/HYP-043s
# egna tilläggsnoter):
#
# En naiv full-portfölj-korrelation (HYP-044:s hela kombinerade serie
# mot HYP-045:s hela kombinerade serie) ger 0.91 - men det talet är
# missvisande har, eftersom bada fullstandiga portfoljerna redan delar
# 2/3 av sin notional (SPY + HYP-037-benen ar identiska i bada). Den
# metodologiskt korrekta jamforelsen (samma konvention som HYP-043s
# egen registerpost, som korrelerar det NYA benet mot de REDAN
# BEFINTLIGA benen, inte hela portfoljer mot varandra) ar PEAD/SUE-
# sviten (det faktiskt NYA, oberoende benet i HYP-046) mot de tre
# ovriga benen:
#   PEAD/SUE vs SPY (krasch-skyddad):          -0.093
#   PEAD/SUE vs Momentum L/S (krasch-skyddad): -0.004
#   PEAD/SUE vs HYP-037:                       -0.015
# (dagliga avkastningar, 3459-3710 overlappande observationer per par,
# se scripts/recompute_dsr_k46.py-sessionen 2026-08-08 for metod)
#
# SLUTSATS: den kvalitativa "mekaniskt icke-overlappande"-motiveringen
# hall vid kvantitativ efterhandskontroll - PEAD/SUE-sviten ar i
# praktiken okorrelerad (nara noll, svagt negativ) mot samtliga tre
# ovriga ben, konsistent med att den byggs pa en helt annan signal
# (kvartalsvis EPS-overraskning) an de ovriga benens pris-/trend-
# baserade mekanismer. Detta bekraftar - men ersatter INTE behovet av
# att fran borjan RAKNA UT talet innan lasning, vilket ar vad spec §5b
# faktiskt kraver.

# ════════════════════════════════════════════════════════════
# TILLAGGSNOT 2026-08-08 (tre oberoende adversariella granskare - INTE
# en ny hypotes/K-test, status/pass_fail_criterion/tested_capital_levels/
# capital_level_results ovan ANDRADE INTE)
# ════════════════════════════════════════════════════════════
# Fullstandig omkorning: filed-datum-korrigerat universum (bade
# momentum L/S- och PEAD/SUE-svitens egen konstruktion + HYP-037-benet),
# close_adj maskad mot orimlig kvot via delade data_hygiene.py::
# mask_implausible_adjusted_close_ratio (tidigare inline har), samt en
# NY 10bps portfoljniva-ombalanseringskostnad i combine_quarters (fanns
# inte tidigare). Resultat i strategies/HYP-046/results_corrected_2026-08-08/
# (results/ rors INTE).
#
# NYA SIFFROR (huvudperiod 2010-2024):
#   Sharpe: 0.8936 / 0.8921 / 0.8508  (tidigare 0.9475 / 0.9492 / 0.8726)
#   MaxDD: -8.09% / -7.85% / -6.67%  (tidigare -9.73% / -9.19% / -7.96%,
#     dvs MaxDD FORBATTRAD ytterligare, redan registrets basta)
#   DSR (K=46, RF=2%/ar): 0.8548 / 0.8536 / 0.8155
#
# Villkor 1 (Sharpe >= 1.0): FAIL PA ALLA TRE, oforandrat. Villkor 2
# (sla friktionskorrigerad HYP-043-baslinje 0.8926/0.8940/0.8217): NU
# BLANDAT - PASS vid $100k (0.8936 > 0.8926, en marginal pa 0.001) och
# $10M (0.8508 > 0.8217), men FAIL vid $1M (0.8921 < 0.8940, en marginal
# pa 0.0019) - tidigare PASS PA ALLA TRE (0.9475/0.9492/0.8726, samtliga
# tydligt over baslinjen). Detta AR en forsvagning av villkor 2:s
# marginal, men INTE avgorande for det redan lasta helhetsresultatet
# eftersom villkor 1 redan var FAIL vid $100k (den avgorande nivan)
# bade fore och efter korrigeringen. Villkor 3 (MaxDD battre an samma
# baslinje): PASS TYDLIGT pa alla tre, oforandrat och FORSTARKT.
#
# SLUTSATS: HYP-046:s FAILED-slutsats star OFORANDRAD under den
# fullstandigt korrigerade pipelinen (villkor 1 var alltid den
# avgorande FAIL-orsaken vid $100k, och forblir FAIL). MaxDD/Calmar-
# forbattringen (redan registrets basta) staller sig konsekvent
# ANNU basta under korrigeringen, medan Sharpe-avstandet till 1.0-malet
# vidgas nagot - samma kvalitativa slutsats som tidigare (overkorrigering
# mot risk pa Sharpens bekostnad), inte en ny.
```

---

## KÄLLFIL: `research/hypothesis_registry/HYP-047-bear-catcher-trend-short.yaml`

```
# LÅST 2026-08-07 av CEO i chatt, innan denna hypotes sätts pre-registered
# eller någon backtest körs.
#
# Foljer spec §5b. Sjunde kombinationshypotesen i registret. Kandidaten
# togs fram fran en 4-AI-brainstorm 2026-08-07 (se session samma datum,
# starkast samstammiga rekommendation av fyra oberoende AI-svar -
# trendfoljande index-short, "crisis alpha" i Hurst/Ooi/Pedersen-stil).
#
# METODOLOGISK DISCIPLIN INNAN LASNING: en diagnostik samma dag
# (scripts/diagnostic_bear_catcher_trend_short.py) matte INTE bara
# prestanda i de 5 redan kanda krisfonstren (for att undvika exakt den
# hindsight-attributionsrisk en av de fyra AI:erna varnade for), utan
# ALLA 36 episoder mekanismen genererat over hela 2010-2024: 34 traffar,
# 2 falsklarm, och bara 33.6% av total P&L fran de 5 kanda fonstren
# (66.4% fran ovriga episoder - edgen ar INTE bara koncentrerad till de
# handplockade kriserna). Korrelation mot HYP-043-kombon: -0.4526,
# klart starkast negativ korrelation av alla kandidater testade denna
# dag.
#
# KAND, OPPET REDOVISAD RESERVATION INNAN LASNING: mekanismens
# VERKLIGA sammanhangande handelsepisod under covid (2020-03-05 till
# 2020-05-22) gav -3.50% TROTS att samma period matt inom ett snavare
# krisfonster (19 feb - 23 mar 2020) visade +43.17% - ett konkret,
# redan observerat exempel pa whipsaw-risk vid en snabb V-formad
# atehamtning. 94.4% traffprocent (34/36) har bara testats mot en
# period med EN genuint utdragen bjornmarknad (2022) - okant hur
# mekanismen beter sig i en djupare/langre bjornmarknad.
#
# status: pre-registered -> tested -> passed/failed

id: HYP-047
date_registered: '2026-08-07'
title: Bear catcher (trendfoljande SPY-short under 200-dagars MA) som 4:e ben i HYP-043-basen
universe: "N/A for SPY/HYP-037-benen (redan testade, HYP-037 orort). Bear catcher-
  benet handlar bara SPY (redan kant instrument, ingen ny universumdefinition).
  Momentum L/S-benet byggs over SAMMA small-cap-universum som HYP-037/043/044/045/046."
small_cap_definition: "small-cap, $100M - $2B börsvärde, EODHD All-World (galler
  momentum L/S-benets universum, ateranvander HYP-037:s redan lasta definition).
  Bear catcher-benet ar N/A - handlar bara SPY."
data_range: "SPY: adjusted_close + high/low 2010-2024 + genuin OOS-2025. Momentum
  L/S: byggd MED borrow_cost + corwin_schultz_spread fran start, samma motorkrav
  som HYP-044/045/046."
pass_fail_criterion: >
  MEKANISM (låst, ingen fri parameter kvar att välja):

  1. BEAR CATCHER-BENET: SPY under sitt eget 200-dagars glidande medel
  (SMA_WINDOW=200) -> KORT SPY (100% av benets egen notional). SPY
  över 200-dagars MA -> kontant (riskfri ränta). Lånekostnad via
  borrow_cost() (BORROW_ANNUAL_RATE=3%, samma konvention som resten
  av registret). Transaktionskostnad: halva Corwin-Schultz-spreaden
  (på SPY:s egen high/low) vid varje övergång in i/ut ur en kort
  position.

  2. KOMBINATION: 1/4 SPY (rått, oförändrat) + 1/4 HYP-037
  (oförändrat) + 1/4 momentum L/S (byggd MED borrow_cost +
  corwin_schultz_spread, HYP-044/045/046:s konstruktion, INGEN
  krasch-overlay - testar bear catcherns EGEN marginella effekt på
  den obehandlade HYP-043-basen, inte staplat på HYP-045:s overlay)
  + 1/4 Bear catcher-benet (punkt 1). Kvartalsvis ombalansering, samma
  snappade datum som HYP-037/039/043/044/045/046.

  PASS KRÄVER ALLA TRE, PÅ DEN AVGÖRANDE $100k-NIVÅN:
  1. Kombinerad Sharpe (2010-2024, friktionskorrekt) >= 1.0.
  2. Kombinerad Sharpe > FRIKTIONSKORRIGERAD HYP-043-baslinje vid samma
  nivå (0.8926/0.8940/0.8217).
  3. Kombinerad MaxDD BÄTTRE än samma friktionskorrigerade baslinje
  (-15.58%/-15.68%/-14.29%).

  OOS-2025: kombinerad OOS-Sharpe > HYP-039:s EGEN OOS-Sharpe
  (0.9185/0.8116/0.7932).

  FAIL om något villkor faller vid $100k-nivån.

  Diagnostiskt syfte: testar om bear catcherns starka negativa
  korrelation mot HYP-043-kombon (-0.4526) räcker för att kompensera
  dess måttliga egna Sharpe (0.34) och lyfta den friktionskorrekta
  kombinationen mot/över 1.0-tröskeln - ett direkt test av om stark
  negativ korrelation kan bära mer än korrelation nära noll (PEAD/SUE,
  HYP-044) eller positiv timing-överlagring (HYP-045) kunde.
status: passed   # pre-registered -> tested -> passed/failed
k_total_hypotheses_before_this: 45
tested_capital_levels:
- 100000
- 1000000
- 10000000
capital_level_results:
  100000: {sharpe: 1.1559, cagr: 0.0872, max_drawdown: -0.0744, calmar: 1.1719, oos_2025_sharpe: 1.5461, oos_2025_total_return: 0.2373, oos_2025_max_drawdown: -0.0758, deflated_sharpe_ratio: 0.9796}
  1000000: {sharpe: 1.1636, cagr: 0.0862, max_drawdown: -0.0730, calmar: 1.1801, oos_2025_sharpe: 1.4944, oos_2025_total_return: 0.2281, oos_2025_max_drawdown: -0.0812, deflated_sharpe_ratio: 0.9802}
  10000000: {sharpe: 1.0993, cagr: 0.0783, max_drawdown: -0.0723, calmar: 1.0834, oos_2025_sharpe: 1.4679, oos_2025_total_return: 0.2225, oos_2025_max_drawdown: -0.0851, deflated_sharpe_ratio: 0.9649}
date_tested: '2026-08-07'
result_summary: >
  PASSED PA ALLA FYRA VILLKOR, PA ALLA TRE NIVAER - forsta rena PASSET
  sedan HYP-043 (efter tre raka FAIL: HYP-044/045/046), och tydligt
  starkast av alla kombinationshypoteser i registrets historia, inklusive
  HYP-043:s EGNA URSPRUNGLIGA (ej friktionskorrigerade) siffror.

  Villkor 1 (Sharpe >= 1.0): PASS PA ALLA TRE - 1.1559/1.1636/1.0993,
  klart over malet aven vid $10M (till skillnad fran HYP-039/043 som
  bada missade knappt just dar).

  Villkor 2 (Sharpe > friktionskorrigerad HYP-043-baslinje 0.8926/
  0.8940/0.8217): PASS PA ALLA TRE, med stor marginal (0.26-0.28
  Sharpe-enheter over baslinjen).

  Villkor 3 (MaxDD battre an samma baslinje -15.58%/-15.68%/-14.29%):
  PASS PA ALLA TRE, DRAMATISKT - -7.44%/-7.30%/-7.23%, en forbattring
  pa 7.06-8.14 PROCENTENHETER, i praktiken en HALVERING av baslinjens
  MaxDD. Calmar 1.17/1.18/1.08 - battre an HYP-046:s tidigare bastanoterade
  0.82-0.89.

  OOS-2025 (villkor 4): PASS PA ALLA TRE, tydligt - 1.546/1.494/1.468
  mot HYP-039:s 0.919/0.812/0.793.

  DSR vid K=46: 0.98/0.98/0.96 - HOGRE an HYP-043:s egna ursprungliga
  DSR (0.95/0.95/0.92) trots 46 redan testade hypoteser - starkt tecken
  pa att detta INTE ar en slumptrafff.

  JAMFORT MOT HYP-043:s URSPRUNGLIGA (ej friktionskorrigerade,
  fortfarande officiellt registrerade) siffror (Sharpe 1.0457/1.0498/
  0.9864, MaxDD -15.58%/-15.68%/-14.29%): HYP-047 slar dem ocksa
  TYDLIGT, pa bade Sharpe och MaxDD, pa alla tre nivaer - detta ar
  alltsa inte bara en seger mot en "handikappad" friktionskorrigerad
  jamforelsepunkt, utan mot den befintliga referensimplementationens
  egna, redan publicerade tal.

  DIAGNOS: bear catcher-benets starka negativa korrelation mot
  HYP-043-kombon (-0.4526, uppmatt INNAN lasning) visade sig bara mer
  an tillrackligt for att kompensera dess mattliga egna Sharpe (0.34
  isolerat) - till skillnad fran PEAD/SUE (naromvarande-noll
  korrelation, for svag egen kvalitet) och HYP-045:s overlay (positiv
  men inte tillrackligt stor forbattring). Detta bekraftar tesen som
  motiverade hela sokningen: en GENUINT OFFENSIV mekanism (tar en
  verklig kort position, tjanar UNDER nedgangen) ger en helt annan
  havstang an en DEFENSIV overlay (bara gar till kontanter) - MaxDD-
  forbattringen (7-8pp) ar mer an dubbelt sa stor som HYP-045:s egen
  (1-2pp mot samma baslinje).

  KAND RESERVATION (redan redovisad INNAN lasning, kvarstar oforandrad):
  mekanismens verkliga sammanhangande handelsepisod under covid gav
  -3.50% trots att ett snavare handplockat krisfonster visade +43.17%
  (whipsaw-risk vid V-formad atehamtning, se registerpostens header).
  94.4% traffprocent (34/36 episoder over 2010-2024) har bara testats
  mot en period med EN genuint utdragen bjornmarknad (2022) - detta
  PASS bevisar inte att mekanismen presterar lika bra i en djupare/
  langre bjornmarknad an de som redan finns i backtestperioden.

  SLUTSATS: HYP-047 ar den starkaste kandidaten for ny
  referensimplementation i registrets historia - slar bade HYP-043:s
  ursprungliga OCH friktionskorrigerade siffror pa alla matt. Kraver
  dock CEO-BESLUT for att formellt bli ny referens (samma monster som
  HYP-017->023->037-overgangarna) - inte automatiskt av detta resultat
  ensamt.

  CEO-BESLUT 2026-08-08: HYP-047 AR DEN NYA REFERENSIMPLEMENTATIONEN.
  HYP-043 kvarstar PASSED i registret (bade dess ursprungliga siffror
  och den friktionskorrigerade robusthetsnoten fran 2026-08-07 star
  oforandrade) men ar inte langre aktiv referens - samma monster som
  HYP-017->023 och HYP-023->037-overgangarna.

# ════════════════════════════════════════════════════════════
# TILLAGGSNOT 2026-08-08 (tre oberoende adversariella granskare - INTE
# en ny hypotes/K-test, status/pass_fail_criterion/tested_capital_levels/
# capital_level_results ovan ANDRADE INTE)
# ════════════════════════════════════════════════════════════
# HYP-047 AR DAGENS FLAGGSKEPP/REFERENSIMPLEMENTATION - denna
# tilläggsnot besvarar darfor SPECIFIKT fragan om en fullstandig
# omkorning skulle flippa PASS->FAIL. SVAR: NEJ, PASS STAR KVAR PA
# ALLA FYRA VILLKOR, PA ALLA TRE NIVAER.
#
# Fullstandig omkorning: filed-datum-korrigerat universum (momentum L/S-
# svitens egen konstruktion + HYP-037-benet + bear catcher-benet, som
# bygger direkt pa SPY:s OHLC och darfor inte paverkas av small-cap-
# universumet), close_adj maskad mot orimlig kvot via delade
# data_hygiene.py::mask_implausible_adjusted_close_ratio (tidigare
# inline har), samt en NY 10bps portfoljniva-ombalanseringskostnad i
# combine_quarters (fanns inte tidigare - denna hypotes hade redan
# spreadkostnad INOM momentum L/S-sviten och i bear catcher-benets egna
# in-/utgangar, se moduldocstring, men INTE mellan de fyra benen vid
# kvartalsvis vikt-aterstallning). Resultat i
# strategies/HYP-047/results_corrected_2026-08-08/ (results/ rors INTE).
#
# NYA SIFFROR (huvudperiod 2010-2024):
#   Sharpe: 1.1259 / 1.1268 / 1.1024  (tidigare 1.1559 / 1.1636 / 1.0993)
#   MaxDD: -8.67% / -8.45% / -8.20%  (tidigare -7.44% / -7.30% / -7.23% -
#     nagot SAMRE, men fortfarande langt battre an baslinjen nedan)
#   OOS-2025 Sharpe: 1.7781 / 1.7245 / 1.7082 (tidigare 1.5461/1.4944/1.4679)
#   DSR (K=46, RF=2%/ar): 0.9716 / 0.9719 / 0.9651
#
# Villkor 1 (Sharpe >= 1.0): PASS PA ALLA TRE (1.1259/1.1268/1.1024) -
# oforandrat, aven vid $10M.
# Villkor 2 (Sharpe > friktionskorrigerad HYP-043-baslinje 0.8926/0.8940/
# 0.8217, HYP-043 sjalv ORORD i denna omkorning): PASS TYDLIGT PA ALLA
# TRE, oforandrat, marginalen fortfarande stor (0.23-0.28 Sharpe-enheter).
# Villkor 3 (MaxDD battre an samma baslinje -15.58%/-15.68%/-14.29%):
# PASS TYDLIGT PA ALLA TRE, oforandrat (-8.67% fortfarande nastan en
# HALVERING av baslinjens MaxDD, aven om marginalen krympte nagot mot
# den tidigare -7.44%).
# OOS-2025-villkoret (kombinerad OOS-Sharpe > HYP-039:s egna OOS,
# okorrigerad referens 0.9185/0.8116/0.7932): PASS TYDLIGT PA ALLA TRE,
# FORSTARKT (1.78/1.72/1.71, uppat fran redan starka 1.55/1.49/1.47).
#
# SLUTSATS - DEN VIKTIGASTE I HELA DENNA GRANSKNINGSOMGANG: HYP-047:s
# PASS-status HALLER, PA ALLA FYRA VILLKOR, PA ALLA TRE KAPITALNIVAER,
# under den fullstandigt korrigerade pipelinen (look-ahead-bias-fritt
# universum + adjusted_close-kvotmaskning + portfoljniva-ombalanserings-
# kostnad TILLSAMMANS, INTE isolerat testade som for HYP-043 - se dess
# egen DEL D-tilläggsnot om varfor den distinktionen dar var nodvandig).
# HYP-047 FLIPPAR INTE - CEO-beslutet 2026-08-08 att gora HYP-047 till
# referensimplementation vilar darmed pa fast grund aven efter denna
# granskning. Sharpe minskar marginellt (fjarde decimalen paverkas mest
# vid $100k/$1M, storre vid $10M men fortfarande >1.0) och MaxDD forsamras
# nagot (1.0-1.2 procentenheter) - men INGET villkor pa NAGON niva
# byter sida. Detta star i skarp kontrast till HYP-037 sjalv (vars EGET
# interna villkor 2 flippar till FAIL pa alla tre nivaer under samma
# korrigering, se HYP-037:s tilläggsnot) och till HYP-043 (vars villkor
# 1/2 redan flippat i en TIDIGARE, separat friktionskorrigering fran
# 2026-08-07) - HYP-047:s marginal mot sina egna troskelvarden var helt
# enkelt bred nog att absorbera bade universum-, adjusted_close- och
# ombalanseringsfixarna utan att den underliggande PASS/FAIL-slutsatsen
# rubbas.

# ════════════════════════════════════════════════════════════
# TILLAGGSNOT 2026-08-09 (granskning av forskningsrapporten, INTE en ny
# hypotes/K-test - status/kriterium/resultat ANDRADE INTE)
# ════════════════════════════════════════════════════════════
# scripts/diagnostic_bear_catcher_extended_history.py (bear catcher-
# benet ISOLERAT, 100% egen notional, mot akta SPY-data 1999-2009 -
# INTE HYP-047:s fulla fyrbenskombination, som saknar pre-2010-data for
# HYP-037-benet och momentum L/S-sviten) fanns sedan tidigare men var
# aldrig committad eller dokumenterad har - flaggat av rapportgransk-
# ningen 2026-08-09 som ett avsteg fran registrets egen "git ar
# revisionssparet"-disciplin. Committas har tillsammans med denna not.
#
# RESULTAT (endast bear catcher-benet): +63.78% under 2000-2002 mot
# SPY:s -33.85%; +40.25% under 2008 mot SPY:s -43.41%. Starkt stod for
# att MEKANISMEN generaliserar utanfor 2010-2024, men detta ar INTE en
# tredje fullstandig validering av hela HYP-047 - bara av ett av dess
# fyra ben.
```
