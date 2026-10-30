# Trading Harness²

A self-improving **paper-trading** system on live market data, run under the
Harness² protocol (Propose → Probe → Compose → Reflect) with
falsification-first rules.

**Paper only.** There is no broker integration, no API key, and no credential
anywhere in this repo. Fills are simulated against end-of-day market data
(Yahoo Finance chart API, free; Stooq fallback). This project exists to answer one question honestly:

> Does any simple systematic strategy beat buy&hold after real costs,
> out-of-sample — or not?

## Why the gates are so strict

A self-improving loop pointed at market data will happily "discover" edges
that are pure curve-fitting. So improvement here means *falsification speed*,
not return maximization:

- **Costs always on** — spread + slippage in every backtest and paper fill.
- **No lookahead** — signals use data up to close *t* and earn *t → t+1*;
  an integrity test mutates the future and proves past signals don't change.
- **Out-of-sample promotion only** — candidates are judged on folds they were
  not selected on; the most recent 6 months are a report-only holdout.
- **Deflated Sharpe** — every trial ever run is remembered in
  `state/trials.json` (the graveyard) and raises the statistical bar for the
  next candidate. A cycle that kills 24/24 candidates is a *successful* cycle.
- **Risk guardrails in plain code**, outside the strategies: per-symbol cap,
  gross cap, daily-loss halt, drawdown kill switch.

## Layout

```
config.json            universe, costs, risk caps, evaluation gates, incumbent
PLAN.md                design + hard constraints
LEARNINGS.md           binding rules for the improvement loop (read before a cycle)
src/harness/data.py    Yahoo daily bars, cached (stdlib only — zero dependencies)
src/harness/strategies.py  sma_trend / donchian_breakout / rsi_meanrev / buy_hold
src/harness/backtest.py    costs, folds, deflated Sharpe
src/harness/risk.py        guardrails + halts
src/harness/paper.py       paper account ($100 start, fractional shares)
scripts/run_paper.py   one paper cycle (fetch → signal → risk → simulated fills)
scripts/improve.py     batch evaluation (grid + mutations + supervisor proposals)
scripts/probe.py       probe ONE candidate through the same gates; adopts in code
scripts/report.py      daily digest vs buy&hold benchmark
harness/               the standalone self-improving loop (pi + OpenRouter):
                       TASK.md (objective + rails), run_continuous.sh (runner)
tests/run_tests.py     integrity tests (python3 tests/run_tests.py)
state/                 paper account, trials graveyard, cycle reports (committed)
logs/trades.csv        every simulated fill (committed)
```

Universe v1: SPY + QQQ, daily bars, end-of-day decisions. Incumbent at
inception: `sma_trend(fast=50, slow=200)` — the simple classic default,
explicitly *not* cherry-picked by backtest.

## Run it

```bash
python3 tests/run_tests.py     # integrity tests
python3 scripts/run_paper.py   # one paper cycle
python3 scripts/improve.py     # one improvement cycle
python3 scripts/report.py      # digest
```

## The self-improving harness (standalone, OpenRouter)

`harness/run_continuous.sh` is an autonomous loop in the Harness² pattern —
the same architecture as Den's RFS idea-search loop. A pi coding agent
(OpenRouter free-tier models, key in `~/.config/rfs/openrouter.key`) runs
back-to-back cycles: read LEARNINGS + the graveyard → propose ONE code edit
(a new strategy family, or a variant answering a specific kill) → probe it
through `scripts/probe.py` (identical gates; adoption happens in code, never
by the agent's say-so) → restore backups for killed edits → reflect into
LEARNINGS. The runner commits each cycle locally, mechanically reverts any
edit to protected files (gates, risk, tests), re-runs the test suite after
every cycle, backs off on quota limits, and parks after 3 consecutive failed
cycles. Stop it any time with `touch harness/state/STOP`.

A separate weekday supervisor job (Muse) runs the paper cycle after the US
close, launches the harness if it isn't running, pushes this repo to GitHub,
and sends a short digest.

## Honest expectations

Most simple strategies do not beat buy&hold after costs, out-of-sample. The
likely output of this system is a well-documented *no* — with the numbers to
prove it — and that is a useful result. Nothing here is financial advice, and
nothing here ever trades real money without a separate, explicit human
decision.
