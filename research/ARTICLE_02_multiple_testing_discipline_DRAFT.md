# 57 Tests, 8 Survivors: What Actually Doing Multiple-Testing Discipline Looks Like

*Draft v0.1 — methodology note, not investment advice. Which specific
hypotheses became the live reference implementation is not disclosed;
the point is the process, not the payload.*

## Abstract (draft)

Systematic trading research has a well-known disease: test enough
strategies and some will look like genuine edge by pure chance. Most
public backtests only show you the winner, which makes it impossible to
tell skill from survivorship. We document a research process that
tracks every hypothesis tested, win or lose, against a running counter,
and requires each hypothesis's pass/fail bar to be written down *before*
the backtest runs and never altered afterward. Over 57 counted tests
(51 formally logged with individual pre-registration files), 8 passed
their locked bar — a ~16% survival rate. We describe the mechanics that
make this auditable rather than just claimed.

## 1. The problem

If you test 57 independent strategies against a naive p<0.05 bar, you'd
expect roughly 2-3 to look "significant" from pure noise alone — even if
none of them have any real edge. Report only the winner and it looks
like skill. This is the same statistical disease as p-hacking in
science, wearing a different lab coat.

## 2. The fix: Deflated Sharpe Ratio / False Strategy Theorem

Bailey & López de Prado's Deflated Sharpe Ratio adjusts the bar a
strategy's Sharpe ratio must clear based on how many trials produced it
— not just its own backtest. The more strategies you've tried, the
higher the bar climbs for the next one to count as real. Critically,
this has to be recomputed for *every* hypothesis still under
consideration each time a new test is added, not just the newest one —
otherwise old "passes" quietly become stale statistics.

## 3. What we actually enforce (not just claim)

- **Pre-registration before testing.** A hypothesis's pass/fail
  criterion is written and locked *before* any backtest runs. It cannot
  be changed after seeing results. No exceptions, enforced by a script
  that refuses to run a backtest without a matching locked file.
- **A running counter (K), not per-test amnesia.** Every tested variant
  — including dead ends — increments K. K currently stands at 57.
- **Friction from day one.** Bid-ask spread, borrow cost, and (for
  small-cap names) short availability are modeled in the backtest
  engine from the start, never bolted on after a good-looking result.
- **Combining failed hypotheses to manufacture a pass is explicitly
  banned.** If 10 of 200 tested ideas look promising, that is the
  expected false-positive count at that K — even if nothing tested is
  real. A combination of ideas is itself a new hypothesis, with its own
  K-cost and its own locked criterion; it is never a workaround for
  ideas that failed individually.
- **Batch-generated candidates follow the same rule, with one addition.**
  When many candidate variants are drafted in a single pass (e.g. by an
  LLM), all N are drafted blind — zero backtests run and zero results
  seen in between drafts — and every single result, winners and losers,
  must be reported together. Cherry-picking the one winner from a batch
  and quietly dropping the rest is the same violation as not counting K
  at all.

## 4. The numbers

| Metric | Value |
|---|---|
| Total counted tests (K) | 57 |
| Formally pre-registered (individual locked files) | 51 |
| Passed their locked bar | 8 |
| Survival rate | ~16% |

A ~16% survival rate under a rising, cumulative significance bar is
roughly what you'd expect from a process doing genuine filtering rather
than either (a) everything working, which would suggest the bar isn't
real, or (b) nothing surviving, which would suggest there's no edge to
find at all.

## 5. Why publish the graveyard

A report that shows only the winner is unverifiable — there is no way
to distinguish it from the lucky 2-3 out of 57 you'd expect from noise
alone. A report that shows the full record — every hypothesis, its
locked criterion, and its outcome — is falsifiable. That is the entire
point of publishing this one.

## TODO before publishing
- [ ] Decide venue (pair with Article 1, or stand alone)
- [ ] Do NOT name which 8 hypotheses passed or what they do — aggregate
      counts only, composition stays private
- [ ] Consider a simple chart: cumulative K vs. cumulative passes over time
- [ ] CEO sign-off on exact numbers before any public posting
