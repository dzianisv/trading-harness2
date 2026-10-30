CYCLE 3 — PROPOSE EDIT
=======================

## Proposal: New strategy family "momentum_close"

**Strategy**: `momentum_close(dates, closes, params)`
- Goes long a symbol when its close price is above its level N days ago (pure momentum).
- Causal: weight at day i uses only closes[0..i] (checks `closes[s][i] > closes[s][i-lookback]`).
- Equal-weight across universe (SPY/QQQ) when long.

**PARAM_GRIDS entry**:
```json
"momentum_close": [
    {"lookback": 50},
    {"lookback": 100},
    {"lookback": 150}
]
```

**Rationale (evidence from graveyard)**:
- Cycle 2's closest kill was `rsi_meanrev(period=21, entry=30, exit=70)`: median fold Sharpe 2.53, beat benchmark in 3/4 folds, but only 11 trades (<30) and deflated-Sharpe prob 0.18.
- SMA trend family (incumbent `sma_trend(50,200)`) has median fold Sharpe 1.76 with more trades but only beats benchmark in 2/4 folds and loses to buy&hold CAGR 16.6% vs its 13.2%.
- The gap: RSI gives high fold Sharpe but too few trades; SMA gives more trades but fails to consistently beat the benchmark. A pure momentum family sits between these — it uses price level crossings (no lookahead) and should generate enough trades while capturing trend momentum that outperforms buy&hold OOS.

**Hypothesis**: 
- A momentum_close strategy with lookback=100 will produce ≥30 trades in folds, beat the benchmark in ≥3/4 folds, achieve median fold Sharpe > 1.76, and achieve deflated-Sharpe prob > 0.9.
- The lookback of 100 is chosen as a middle ground: shorter lookbacks (50) may produce more trades but lower Sharpe; longer (150) may produce higher Sharpe but fewer trades.

**What actually happened (probe results)**:
All three lookback values were evaluated via probe.py and killed. Key numbers:

- **lookback=50**: 45 trades in folds (passes trade-count gate), but only 1/4 folds beating benchmark, median fold Sharpe 1.25 <= incumbent 1.76, deflated Sharpe prob 0.28 < 0.9 — killed.
- **lookback=100**: 23 trades in folds (<30), 1/4 folds beating benchmark, median fold Sharpe 1.61 <= incumbent 1.76, deflated Sharpe prob 0.27 < 0.9 — killed.
- **lookback=150**: 26 trades in folds (<30), 0/4 folds beating benchmark, median fold Sharpe 1.76 <= incumbent 1.76 (tie, not strictly greater), deflated Sharpe prob 0.12 < 0.9 — killed.

**Lesson**: Pure momentum suffers the same RSI-family trade-off: shorter lookbacks increase trade count but collapse median fold Sharpe and benchmark consistency; longer lookbacks raise Sharpe potential but trades fall below 30 and benchmark folds vanish. No single rung on this ladder satisfies all four gates simultaneously. The fundamental constraint is that SPY/QQQ daily momentum, without additional dimensions (volatility targeting, sector rotation, etc.), cannot simultaneously achieve ≥30 OOS trades, ≥3/4 folds beating buy&hold, median fold Sharpe > 1.76, AND deflated-Sharpe prob > 0.9. Future cycles may explore combining momentum with a secondary filter (e.g., volume or volatility conditions) as a new strategy family, or abandon the momentum direction entirely.

**File edits executed**:
- `src/harness/strategies.py`: NEW `momentum_close` function + registered in `STRATEGIES` + `momentum_close` entry to `PARAM_GRIDS` (then reverted from backup)
- `harness/runs/cycle3.md`: this rationale + outcomes

## Cycle 3 Summary

1 proposed: momentum_close strategy family in strategies.py
1 killed: probe.py gate failures across all three lookback values (50, 100, 150)
0 ADOPTED

Restored strategies.py from backup; no code changes persist.