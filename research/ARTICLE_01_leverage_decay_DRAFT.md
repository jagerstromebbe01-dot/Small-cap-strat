# Naive Leverage Scaling Overstates Backtested Returns: A Worked Example

*Draft v0.1 — methodology note, not investment advice. Strategy composition
deliberately not disclosed; the point is general and applies to any
backtested return stream.*

## Abstract (draft)

A common shortcut in retail and semi-professional backtesting is to
approximate the effect of leverage by algebraically scaling summary
statistics — multiplying CAGR and max drawdown by the leverage factor L.
We show, using an actual systematic multi-strategy equity portfolio
(Sharpe ≈1.16, CAGR ≈8.6%, MaxDD ≈-7.3% unlevered), that this shortcut
materially overstates realistic returns. Simulating leverage correctly —
applying L to each day's actual return and compounding day by day, with
an explicit borrowing cost on the levered portion — shows a gap that
grows with L: at 2.0x leverage, naive scaling implies CAGR of +17.2%
while honest daily-compounded simulation with a conservative borrowing
spread yields +13.5%, a 3.7 percentage-point overstatement. Sharpe falls
from 1.16 to 1.02 (conservative financing) or 0.89 (stressed financing)
at the same leverage level. We argue any backtest report that leverages
a strategy without daily-compounded simulation and an explicit borrow
cost assumption should be treated as unreliable.

## 1. The shortcut, and why it's wrong

Naive scaling assumes:

    CAGR_levered ≈ L × CAGR_base
    MaxDD_levered ≈ L × MaxDD_base

This treats leverage as a free multiplier on the *arithmetic* return.
But compounding is geometric, and geometric returns are penalized by
variance:

    CAGR_geometric ≈ L·μ − (L²·σ²)/2 − (L−1)·borrow_cost

The mean return scales linearly with L; the variance-drag term scales
with **L²**. Borrowing cost, charged only on the levered portion (L−1),
is a third term naive scaling ignores entirely. This is the same
mathematical mechanism (Jensen's inequality applied to compounding) that
causes leveraged ETFs to decay in choppy, range-bound markets even when
the underlying index is flat.

## 2. Method

We do not scale summary statistics. We replay the strategy's actual
daily return series, apply

    levered_return_t = L × r_t − (L−1) × (rf + spread)/252

and compound value day by day. Two borrowing-spread assumptions are
tested for sensitivity: a conservative +1.5%/year over the risk-free
rate, and a stressed +3.0%/year (proxy for tighter financing
conditions).

## 3. Results

| Leverage | Sharpe (cons.) | CAGR (cons.) | MaxDD (cons.) | Sharpe (stressed) | CAGR (stressed) |
|---|---|---|---|---|---|
| 1.00x (baseline) | 1.16 | 8.6% | -7.3% | 1.16 | 8.6% |
| 1.25x | 1.11 | 9.8% | -9.2% | 1.05 | 9.4% |
| 1.50x | 1.07 | 11.1% | -11.2% | 0.98 | 10.3% |
| 1.75x | 1.04 | 12.3% | -13.1% | 0.93 | 11.1% |
| 2.00x | 1.02 | 13.5% | -15.0% | 0.89 | 11.8% |

Naive-vs-real comparison at conservative spread:

| Leverage | Naive CAGR | Real CAGR | Gap | Naive MaxDD | Real MaxDD | Gap |
|---|---|---|---|---|---|---|
| 1.5x | 12.9% | 11.1% | -1.9pp | -11.0% | -11.2% | -0.2pp |
| 2.0x | 17.2% | 13.5% | -3.7pp | -14.6% | -15.0% | -0.4pp |

The CAGR gap grows with leverage (as the L² variance term predicts);
the MaxDD gap is smaller in this case but not zero and not guaranteed
to stay small in general.

## 4. Implication

Under conservative financing, moderate leverage (1.25–1.5x) partially
preserves Sharpe while lifting CAGR meaningfully. Beyond ~1.5–2x, the
variance-drag and financing-cost terms consume most of the incremental
return, and under stressed financing Sharpe drops below the levered
strategy's own unlevered baseline threshold. Any report that quotes
"leverage this strategy Nx for Nx the return" without showing a daily
-compounded, cost-inclusive simulation should be treated with suspicion
— including our own future reports, which is why this note documents
the method explicitly.

## TODO before publishing
- [ ] Decide venue (SSRN vs blog) and finalize language (drafted in English for reach)
- [ ] Add a small toy-example section (e.g. synthetic 2-asset case) so the
      L² mechanism is provable from first principles, not just shown empirically
- [ ] Confirm no detail in this draft indirectly reveals the underlying
      strategy's signal composition (currently: only Sharpe/CAGR/MaxDD/leverage
      table are strategy-specific; composition, universe, and legs are absent — keep it that way)
- [ ] CEO sign-off on exact numbers before any public posting
