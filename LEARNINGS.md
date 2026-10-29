# LEARNINGS — persistent improvement harness (Harness² protocol)

Binding rules for every improvement cycle. The daily agent reads this file
BEFORE running a cycle and updates it AFTER (Reflect step). Rules are distilled
from kills; never delete a rule, only refine it with the reason recorded.

## Generation rules (Propose)

1. **Costs are part of reality.** Any candidate evaluated without spread +
   slippage is automatically killed, no exceptions.
2. **Selection data is poisoned data.** A variant may only be promoted on folds
   it was not selected on. The most recent 6 months are a holdout: report-only.
3. **The graveyard counts.** Every trial ever run raises the deflated-Sharpe
   bar for the next one (multiple-testing correction). Check state/trials.json
   length before believing any Sharpe.
4. **Minimum evidence:** ≥30 trades and ≥3 of 4 OOS folds positive vs the
   incumbent, or the candidate is killed regardless of headline return.
5. **Beat the benchmark or die.** The real opponent is buy&hold SPY after
   costs, not zero. A strategy that loses to it OOS is killed.
6. **Simple beats clever.** Prefer fewer parameters. A candidate with more
   parameters than the incumbent needs a *larger* OOS margin to be adopted.
7. **Regimes change.** A candidate whose OOS folds disagree violently with
   each other is fragile, not brilliant. Consistency is a gate, not a bonus.
8. **No leverage, no options, no intraday.** v1 universe is SPY/QQQ daily bars.
   Widening the search space needs Den's explicit approval.
9. **Paper until proven.** Nothing here ever graduates to real money without
   Den's explicit, separate decision.
10. **Report kills proudly.** A cycle that kills 24/24 candidates and changes
    nothing is a successful cycle. Changing something is not the goal.
11. **Every proposal carries its evidence.** Three channels feed a cycle: the
    baseline grid, near-miss mutations of the closest kills (Edit A), and
    agent proposals (Edit B) written to state/proposals.json. An agent
    proposal without a written rationale citing specific graveyard evidence
    is never evaluated. All channels face identical gates — a good story
    earns a trial, never an adoption.

## Graveyard

(Killed candidates with the reason, appended by the Reflect step. The script
keeps the full numeric record in state/trials.json; this is the human digest.)

- _Incumbent at inception (2026-10-29): sma_trend(fast=50, slow=200)
  — chosen as the simple, classic default, NOT because it tested best._
- **Cycle 1 (2026-10-29): 16 trials, 0 adopted.** Incumbent full-period after
  costs: CAGR 13.3% vs buy&hold 16.7%, Sharpe 0.81 vs 0.83 — it trails on
  return at similar risk; any case for it is drawdown control, unproven.
  Closest kill: rsi_meanrev(period=14, entry=30) — median fold Sharpe 2.26
  (above the incumbent's 1.85) but deflated-Sharpe prob 0.13: too few trades
  to believe. Lesson: fold Sharpe alone is not evidence; trade count is the
  credibility budget. Most other kills: failed to beat the benchmark in ≥3/4
  folds. Data note: Stooq bot-walls this VM — Yahoo chart API is the primary
  feed, Stooq only a fallback.
- **Cycle 2 (2026-10-30; trials stamped 2026-10-29 UTC): 24 trials
  (grid 16, mutation 4, agent 4), 40 total, 0 adopted.** Incumbent
  sma_trend(50,200) re-evaluated: median fold Sharpe 1.76, full CAGR 13.2%
  vs buy&hold 16.6%, deflated-Sharpe prob 0.22. Closest kill: mutation
  rsi_meanrev(period=21, entry=30, exit=70) — median fold Sharpe 2.53,
  beat the benchmark in 3/4 folds (passed those two gates), killed only
  on 11 trades (<30) and deflated-Sharpe prob 0.18. Agent attempts to fix
  the period=14/entry=30 trade shortage all failed informatively:
  entry=35 raised trades 14→21 (median Sharpe 1.84), exit=60 barely moved
  them (15, median 1.98), period=5 raised trades to 63 but median Sharpe
  collapsed to 0.55. Lesson: in the RSI family the high fold Sharpe IS
  the sparse trading — lengthening the period raises Sharpe and benchmark
  wins while trades fall further; no rung on this ladder buys credibility
  (≥30 trades) without destroying the Sharpe it was meant to certify.
