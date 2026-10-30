# TASK — standalone self-improving trading harness

## Objective

Continuously improve a PAPER-trading system (SPY/QQQ, daily bars) so that its
incumbent strategy earns the right to be believed: beat buy&hold after costs,
out-of-sample, under the gates in `src/harness/backtest.py: gate_failures`.
Fitness is evidence, not returns on a screenshot. A cycle that kills its own
proposal is a successful cycle.

## Who runs what

- **You (the harness agent, pi + OpenRouter)** own Propose and Reflect:
  read the graveyard, design ONE edit per cycle, back it with evidence,
  probe it, write the lesson.
- **Code owns Probe and Compose**: `scripts/probe.py` evaluates and applies
  the gates; adoption happens inside probe.py or not at all. You cannot
  adopt, promote, or declare an edge yourself.
- **The runner** (`harness/run_continuous.sh`) owns git commits, protected-
  file enforcement, and test verification after every cycle.

## Editable (your surface)

- `src/harness/strategies.py` — new strategy families, new params, grids.
- `LEARNINGS.md` — graveyard entries, lessons, new rules (append/refine,
  never delete a rule).
- `state/proposals.json` — not used by this harness (that's the supervisor's
  channel); you work through probe.py.
- `harness/runs/cycle<N>.md` — your per-cycle working doc.
- `state/trials.json`, `state/cycle_report.json` — only via the scripts.

## Protected (never edit; the runner reverts violations)

`src/harness/backtest.py`, `src/harness/risk.py`, `src/harness/paper.py`,
`src/harness/data.py`, `scripts/probe.py`, `scripts/improve.py`,
`scripts/run_paper.py`, `scripts/report.py`, `tests/`, `tools/`,
`harness/TASK.md`, `harness/run_continuous.sh`, and the risk/evaluation
sections of `config.json` (the incumbent field changes only via probe.py).

## Hard rails

1. Paper only. No broker code, no real accounts, no credentials, ever.
2. Universe is SPY/QQQ. No leverage, options, intraday, new tickers.
3. Risk caps in config.json never go up. Costs in config.json never go down.
4. Every strategy must be causal (weights at day i use only closes[0..i]);
   tests/run_tests.py checks every registered strategy — a failing test is
   an automatic kill of your edit.
5. One edit per cycle. Back up every file before editing it
   (harness/state/backup/cycle<N>-<filename>); restore backups for killed
   edits, delete them for adopted ones.
6. No git commands. The runner commits.
7. Every claim in your cycle doc carries a number from probe/test output.
