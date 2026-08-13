# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

This repository is **past pre-build** — `/research/hypothesis_registry/`, `/data/`, `/strategies/`, and `/scripts/` are all populated and under git history. As of 2026-08-13, `k_total = 85` (`research/hypothesis_registry/_counter.yaml`).

**Reference implementation:** HYP-081 (naive fifth-leg small-cap combination, unlevered). Historical: Sharpe 1.38, CAGR 7.9%, MaxDD -4.2%, DSR 0.99-1.00 at K=84.

**Leverage: not adopted.** HYP-087 (2.5x) and HYP-088 (3.0x margin-call overlay on HYP-081) both PASSED cleanly with zero real margin calls over 15 years, and 3.0x was briefly locked as the leverage standard on 2026-08-13. A same-day synthetic stress test (`scripts/diagnostic_hyp088_stress_test_all_levels.py`, see HYP-088's registry addenda) then showed the mechanism's delever floor is always 1.0x (never lower), so the chosen leverage level barely changes the outcome in a sufficiently deep/prolonged decline (1.5x: -38.9% vs 3.0x: -43.3% in the same constructed extreme scenario — only 4.4pp apart). The CEO reversed the leverage decision the same day: **HYP-081 unlevered is the sole reference implementation**; HYP-087/HYP-088 remain PASSED and documented but not adopted. Higher CAGR is pursued via new alpha, not this leverage mechanism, unless a future, separately pre-registered redesign (genuine delevering below 1.0x) is built.

For the full narrative and all intermediate decisions (Ejay closure, HYP-039/043/047/056 reference-chain history, the HYP-072 dilution-pipeline alpha family, the crypto pilot batch HYP-060-064, all FAILED), read the hypothesis registry directly rather than this file — it is the audit trail, this file is a pointer to it.

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
