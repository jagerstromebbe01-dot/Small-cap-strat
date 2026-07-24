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

**Explicitly excluded from v1 — do not add without an explicit user decision:** the entire CIO branch (Paper Agent, Market Structure Agent, News Agent, Small Cap Research Agent), ML Engineer, and the "Hypothesis Miner" concept (mining others' published hypotheses) — deliberately deferred until the v1 pre-registration/friction discipline is proven robust, since adding more hypothesis-generating agents before the guardrails exist would recreate the same blind-search problem that killed the 7 Ejay variants.

## Open dependencies (spec §6)

1. WRDS/Compustat/CRSP access is pending (contingent on a conversation with Lasse Heje Pedersen) — specifically need to confirm whether local Python access via the `wrds` library is permitted, or whether the agreement requires running in WRDS's cloud environment instead.
2. Local scheduling mechanism (cron or equivalent) is not yet decided — must be set up concretely for this actual environment (this repo is on Windows; the spec was written assuming Linux/macOS cron was available, so this needs an OS-appropriate equivalent).
3. Exact small-cap market-cap cutoff is not locked — must be decided and written into HYP-008's `pass_fail_criterion` before any backtest runs against it, not added afterward.

## Immediate next task (spec §7)

If asked to start building this project, the order specified is: (1) repo structure (`/agents/`, `/research/hypothesis_registry/`, `/data/`), (2) role prompts for all v1 agents, (3) Data Engineer's data abstraction layer (yfinance now, WRDS stub), (4) `_counter.yaml` initialized at `k_total = 7`, (5) `HYP-008` created as pre-registered/unlocked with `pass_fail_criterion` filled in before any small-cap-data code is written, (6) HYP-008 is **not run** until WRDS access is resolved or the user explicitly decides to use a free small-cap proxy dataset for an interim run.
