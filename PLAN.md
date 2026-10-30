# Trading Harness² — Implementation Plan

Owner: Muse (product owner mode, per Den's instruction 2026-10-29)
Status: v1 built 2026-10-29

## What this is

A self-improving **paper-trading** system on live market data, run under the
Harness² protocol (Propose → Probe → Compose → Reflect) with falsification-first
rules. It exists to find out, honestly and cheaply, whether any simple systematic
strategy has an edge after costs. It is NOT a money printer and it never touches
real money or a real brokerage account.

## Hard constraints (not negotiable, enforced in code)

1. **Paper only.** There is no broker integration and no credential anywhere in
   this repo. Fills are simulated against live/EOD market data.
2. **Costs always on.** Every backtest and paper fill pays spread + slippage.
   A result without costs does not exist in this system.
3. **No lookahead.** A signal for day *t* uses only data up to close of *t*;
   it earns the return from *t* to *t+1*. An integrity test enforces this.
4. **Out-of-sample promotion only.** A candidate replaces the incumbent only if
   it beats the incumbent on out-of-sample folds it was not selected on, clears
   a deflated-Sharpe gate that gets stricter with every trial ever run, and has
   enough trades to mean anything. The most recent 6 months are a holdout used
   for reporting, never for selection.
5. **Risk guardrails live outside the strategy.** Max weight per symbol, max
   gross exposure, daily-loss halt, max-drawdown kill switch. No strategy or
   improvement cycle can override them.
6. **The loop must self-report.** Every daily cycle ends in a digest to Den —
   including "nothing adopted, N candidates killed" and failures. Silent
   parking is a bug.

## Architecture

```
data.py        Yahoo Finance daily bars (free, no key; Stooq fallback — it
               bot-walls datacenter IPs), cached CSVs. Stdlib only.
strategies.py  sma_trend, donchian_breakout, rsi_meanrev, buy_hold (benchmark)
backtest.py    Equity simulation with costs; Sharpe / CAGR / maxDD / trades
               Walk-forward style OOS folds + deflated Sharpe (trial-count aware)
risk.py        Guardrails: position caps, daily-loss halt, drawdown kill switch
paper.py       Paper account ($100 start, fractional shares), simulated fills
improve.py     Harness² Probe/Compose: bounded candidate grid, kill criteria,
               graveyard in state/trials.json, adopts only on OOS evidence
report.py      Daily digest: equity vs buy&hold, position, cycle verdicts
```

Universe v1: SPY, QQQ (liquid index ETFs; no survivorship bias, no stock-picking
fantasy). Daily bars, end-of-day decisions — the only frequency where a small
account's cost structure is not instantly fatal.

## How the harness runs (executor + tokens) — v2, Den's design

v1 ran the agent layer as a Muse cron (Muse Spark). Den corrected that
(2026-10-30): the harness must be a **standalone self-improving system
powered by the OpenRouter API**, the same pattern as his RFS loop. v2:

- **Deterministic core — zero LLM tokens.** Data, signals, backtests, risk
  checks, paper fills and gate evaluation are pure Python (stdlib only).
  This is the Probe layer: it judges, it cannot be argued with.
- **Standalone harness — pi CLI + OpenRouter.** `harness/run_continuous.sh`
  runs back-to-back cycles (Propose → Probe → Compose → Reflect): the agent
  reads LEARNINGS + the graveyard, makes ONE code edit per cycle (a new
  strategy family or a graveyard-motivated variant), probes it via
  `scripts/probe.py` (same gates; adoption happens in code or not at all),
  restores backups for killed edits, and reflects into LEARNINGS. The runner
  commits locally, reverts protected-file violations, re-runs the test suite
  after every cycle, backs off 30 min on OpenRouter 429s, switches model
  after 2 primary failures, and parks after 3 consecutive failed cycles
  (3-strike rule). Key: `~/.config/rfs/openrouter.key` (shared with the RFS
  loop). Primary model: `deepseek/deepseek-v4.1-flash` (Den's choice;
  $0.045/M input, $0.50/M output — a heavy cycle costs roughly $0.15–0.40).
  It is NOT free on OpenRouter (the free variant Den knows is OpenCode Zen's,
  a different provider), and the shared key's usage limit is $0, so the model
  returns 403 until Den raises the key limit (his account action; the runner
  detects the 403 and parks immediately with the remedy written to
  harness/state/PARKED.md). Fallback: `google/gemma-4-31b-it:free`.
  Per-attempt timeout defaults to 1800s (HARNESS_ATTEMPT_TIMEOUT) — bounded
  on purpose, see the 2026-10-30 smoke test note in LEARNINGS: pi agent
  turns on free models currently stall, while the raw OpenRouter API
  answers in ~1s on the same key.
- **Muse's role is now supervisor only**: a weekday cron runs the tests and
  the paper cycle, launches the harness if it is not running, pushes the
  repo to GitHub, and sends Den the digest. Muse no longer proposes or
  judges strategies.

## Daily cycle (cron, weekdays after US market close)

1. `run_paper.py` — fetch data, apply incumbent strategy, risk-check, simulate
   fills, update account state.
2. `improve.py` — one bounded improvement cycle (≤24 candidate trials).
3. `report.py` — digest.
4. Agent reflects: updates LEARNINGS.md with kills/adoptions, commits all
   changes to GitHub, sends Den the digest.

## Success criteria (honest)

- 3 months of uninterrupted paper operation with full logs.
- A verdict, with numbers: does the incumbent beat buy&hold SPY after costs,
  out-of-sample, or not?
- If nothing survives the gates, that IS the result — reported as such.

## Explicitly out of scope

- Real-money execution, Robinhood login/API (no official API exists; unofficial
  endpoints would risk Den's account), options, leverage, intraday/HFT.
- LLM in the order path. The agent runs the loop and reflects; signals and risk
  are deterministic code.
