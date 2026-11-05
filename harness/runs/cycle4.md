CYCLE 4 — PROPOSE EDIT
=======================

## Proposal: Add period=3 to rsi_meanrev PARAM_GRIDS

**What changed**: Added `period` = 3 to the rsi_meanrev parameter grid, changing
the RSI period ladder from `(2, 14)` to `(2, 3, 14)`. The strategy function
`rsi_meanrev` and its causality contract are unchanged; only the candidate grid
gains one new rung.

**Rationale (evidence from graveyard)**:
- `rsi_meanrev(period=2, entry=30, exit=70)`: 160 trades in folds, median fold
  Sharpe 1.00, deflated Sharpe prob 0.05 — passes the trade-count gate but
  fails on Sharpe and deflated probability.
- `rsi_meanrev(period=14, entry=30, exit=70)`: 14 trades in folds, median fold
  Sharpe 2.26, deflated Sharpe prob 0.13 — passes on Sharpe but fails on
  trade count and deflated probability.
- `rsi_meanrev(period=21, entry=30, exit=70)`: 11 trades in folds, median fold
  Sharpe 2.53, deflated Sharpe prob 0.18 — best Sharpe but trade count too
  low and deflated probability still insufficient.

The period ladder skips from 2 directly to 14, leaving the middle ground
(untested) unexplored. Period=3 is the adjacent rung that uses the same RSI
mean-reversion logic but with a shorter lookback, which should fire the
entry=30 threshold more often than period=14 while retaining more selectivity
than period=2.

**Hypothesis**: 
- period=3 with entry=30 will produce ≥30 trades in folds (more than period=14's
  14, but fewer than period=2's 160), while achieving a median fold Sharpe
  higher than period=2's 1.00.
- If the median fold Sharpe lands between ~1.5 and ~2.0, and deflated Sharpe
  prob exceeds 0.9, the candidate could clear all four gates simultaneously.
- The deflated Sharpe prob gate (0.9) is the hardest — it requires the observed
  Sharpe to be in the top ~10% of chance given the number of trials. This may
  require a sufficiently distinct Sharpe signal that period=3 might or might not
  provide.

**What result would falsify it**: If probe.py reports the candidate killed with
any of the four gate failures (trades < 30, folds beating benchmark < 3,
median fold Sharpe ≤ incumbent 1.762, deflated Sharpe prob < 0.9), especially
if the trade count or deflated probability falls outside the period=2 → period=14
interpolation range.

**File edits executed**:
- `src/harness/strategies.py`: Added period=3 to rsi_meanrev PARAM_GRIDS
  (from `for p in (2, 14)` to `for p in (2, 3, 14)`)
- `harness/runs/cycle4.md`: this proposal doc